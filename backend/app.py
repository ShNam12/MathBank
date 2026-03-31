# --- PHẦN 1: KHAI BÁO THƯ VIỆN ---
from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import io
import contextlib
import time
import random
import re
from datetime import datetime

# Import các class quản lý Database từ file database.py của bạn
from database import Database, SubjectRepository, CategoryRepository, TemplateRepository, SolverRepository, QuestionRepository
from models import Subject, Category, Template, Solver, Question, QuestionStatus, DistractorConfig, ParamDefinition

# Import Question Generation Service
from services import QuestionGenerationService, QuestionService

app = Flask(__name__)
CORS(app) # Cho phép Frontend gọi API

# --- PHẦN 2: KẾT NỐI DATABASE ---
# Khởi tạo kết nối đến file SQLite
db = Database("question_bank.db")
subject_repo = SubjectRepository(db)
category_repo = CategoryRepository(db)
template_repo = TemplateRepository(db)
solver_repo = SolverRepository(db)
question_repo = QuestionRepository(db)

# Initialize Question Generation Service
question_generator = QuestionGenerationService(db)
question_service = QuestionService(db)


# --- PHẦN 3: CÁC API (CHỨC NĂNG) ---

# API 1: LẤY CODE ĐỂ HIỂN THỊ (Dùng cho trang Template)
@app.route('/api/get-template', methods=['GET'])
def get_template():
    template_id = request.args.get('template_id')
    if template_id:
        try:
            template_id = int(template_id)
            # Lấy template đầy đủ từ database
            template = template_repo.get_by_id(template_id)
            if not template:
                return jsonify({"error": "Template không tồn tại"}), 404
            
            # Lấy solver active
            solver = solver_repo.get_active_for_template(template_id)
            
            # Map difficulty từ số sang chữ
            diff_map = {1: "Easy", 2: "Medium", 3: "Hard", 4: "Expert"}
            
            # Chuyển param_schema sang dict
            param_schema_dict = {}
            if template.param_schema:
                for name, param_def in template.param_schema.items():
                    param_schema_dict[name] = param_def.to_dict()
            
            return jsonify({
                "id": template.id,
                "name": template.name,
                "code": template.code,
                "content": template.question_template or template.math_formula,
                "difficulty": diff_map.get(template.difficulty_base, "Medium"),
                "tags": template.tags or [],
                "param_schema": param_schema_dict,
                "solver_code": solver.code if solver else "",
                "category_id": template.category_id,
                "subject_id": template.subject_id
            })
        except ValueError:
            return jsonify({"error": "Template ID không hợp lệ"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # Fallback: Demo: Lấy template mới nhất (nếu không có template_id)
    templates = template_repo.get_all(limit=1)
    if templates:
        tmpl = templates[0]
        # Lấy code solver tương ứng
        solver = solver_repo.get_active_for_template(tmpl.id)
        code = solver.code if solver else ""
        return jsonify({"code": code, "content": tmpl.question_template})
    return jsonify({"code": "", "content": ""})

# ============================================================================
# HELPER FUNCTIONS FOR TEMPLATE IMPORT (V2 - New Structure)
# ============================================================================

def convert_placeholder(text: str) -> str:
    """
    Convert placeholder format từ {{param}} sang {{{{param}}}}
    
    Args:
        text: String chứa placeholder dạng {{param}}
    
    Returns:
        String với placeholder đã convert thành {{{{param}}}}
    
    Ví dụ:
        Input:  "Cho ma trận {{a}}x + {{b}} = 0"
        Output: "Cho ma trận {{{{a}}}}x + {{{{b}}}} = 0"
    """
    if not text or not isinstance(text, str):
        return text
    
    # Pattern để tìm {{param}} (2 dấu ngoặc nhọn)
    # Tránh match với {{{{param}}}} đã có sẵn (4 dấu ngoặc)
    pattern = r'\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}(?!\{)'
    
    def replace_placeholder(match):
        param_name = match.group(1)
        return f'{{{{{param_name}}}}}'
    
    # Replace tất cả {{param}} thành {{{{param}}}}
    result = re.sub(pattern, replace_placeholder, text)
    
    return result

def parse_param_schema(param_schema_json: dict) -> dict:
    """
    Parse param_schema từ JSON format sang Dict[str, ParamDefinition]
    
    Args:
        param_schema_json: Dictionary chứa param_schema từ JSON
                          Format: {"a": {"type": "integer", "min": -5, "max": 5}, ...}
    
    Returns:
        Dict[str, ParamDefinition]: Dictionary với key là tên param, value là ParamDefinition object
    
    Ví dụ:
        Input:  {"a": {"type": "integer", "min": -5, "max": 5}}
        Output: {"a": ParamDefinition(name="a", param_type="integer", min_value=-5, max_value=5)}
    """
    if not param_schema_json:
        return {}
    
    if not isinstance(param_schema_json, dict):
        print(f"[WARNING] param_schema không phải dictionary, bỏ qua. Type: {type(param_schema_json)}")
        return {}
    
    parsed_schema = {}
    errors = []
    
    for param_name, param_def in param_schema_json.items():
        try:
            # Validate param_name
            if not isinstance(param_name, str) or not param_name.strip():
                errors.append(f"Tên tham số không hợp lệ: {param_name}")
                continue
            
            # Validate param_def là dict
            if not isinstance(param_def, dict):
                errors.append(f"Định nghĩa tham số '{param_name}' không phải dictionary")
                continue
            
            # Dùng ParamDefinition.from_dict() để parse
            param_definition = ParamDefinition.from_dict(param_name, param_def)
            parsed_schema[param_name] = param_definition
            
        except Exception as e:
            # Log warning nhưng không dừng toàn bộ process
            error_msg = f"Lỗi parse tham số '{param_name}': {str(e)}"
            errors.append(error_msg)
            print(f"[WARNING] {error_msg}")
            continue
    
    # Log tổng hợp nếu có lỗi
    if errors:
        print(f"[WARNING] Có {len(errors)} lỗi khi parse param_schema:")
        for error in errors:
            print(f"  - {error}")
    
    return parsed_schema

def parse_solver_object(solver_obj: dict) -> dict:
    """
    Parse solver object từ JSON và validate solver code
    
    Args:
        solver_obj: Dictionary chứa solver từ JSON
                   Format: {"code": "...", "entry_function": "solve", "dependencies": ["sympy"]}
    
    Returns:
        dict: Dictionary chứa {"code": str, "entry_function": str, "dependencies": list}
    
    Raises:
        ValueError: Nếu thiếu 'code' hoặc code không có hàm entry_function
    
    Ví dụ:
        Input:  {"code": "def solve(a, b): return a+b", "entry_function": "solve"}
        Output: {"code": "def solve(a, b): return a+b", "entry_function": "solve", "dependencies": ["sympy"]}
    """
    if not solver_obj:
        raise ValueError("Solver object không được để trống")
    
    if not isinstance(solver_obj, dict):
        raise ValueError(f"Solver object phải là dictionary, nhận được: {type(solver_obj)}")
    
    # Extract code (bắt buộc)
    code = solver_obj.get('code', '')
    if not code or not isinstance(code, str) or not code.strip():
        raise ValueError("Solver phải có 'code' (không được để trống)")
    
    # Extract entry_function (optional, default "solve")
    entry_function = solver_obj.get('entry_function', 'solve')
    if not entry_function or not isinstance(entry_function, str):
        entry_function = 'solve'
    
    # Extract dependencies (optional, default ["sympy"])
    dependencies = solver_obj.get('dependencies', ['sympy'])
    if not isinstance(dependencies, list):
        dependencies = ['sympy']
    # Đảm bảo có "sympy" trong dependencies (vì hầu hết solver dùng sympy)
    if 'sympy' not in dependencies:
        dependencies.append('sympy')
    
    # Validate solver code có hàm entry_function
    try:
        # Tạo namespace với các module cần thiết (giống SolverService.execute)
        namespace = {
            # SymPy
            'sp': None,  # Sẽ import sau
            'sympy': None,
            'symbols': None,
            'Symbol': None,
            'integrate': None,
            'diff': None,
            'limit': None,
            'exp': None,
            'sin': None,
            'cos': None,
            'tan': None,
            'log': None,
            'ln': None,
            'sqrt': None,
            'simplify': None,
            'expand': None,
            'factor': None,
            'latex': None,
            'fraction': None,
            'Rational': None,
            'oo': None,
            'E': None,
            'pi': None,
            'Matrix': None,
            
            # Python built-ins
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'round': round,
            'range': range,
            'len': len,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
        }
        
        # Import sympy vào namespace (nếu có)
        try:
            import sympy as sp
            from sympy import (
                symbols, Symbol, integrate, diff, limit,
                exp, sin, cos, tan, log, ln, sqrt,
                simplify, expand, factor, latex, fraction, Rational,
                oo, E, pi, Matrix
            )
            namespace.update({
                'sp': sp,
                'sympy': sp,
                'symbols': symbols,
                'Symbol': Symbol,
                'integrate': integrate,
                'diff': diff,
                'limit': limit,
                'exp': exp,
                'sin': sin,
                'cos': cos,
                'tan': tan,
                'log': log,
                'ln': ln,
                'sqrt': sqrt,
                'simplify': simplify,
                'expand': expand,
                'factor': factor,
                'latex': latex,
                'fraction': fraction,
                'Rational': Rational,
                'oo': oo,
                'E': E,
                'pi': pi,
                'Matrix': Matrix,
            })
        except ImportError:
            # Nếu không có sympy, vẫn tiếp tục (có thể code không dùng sympy)
            pass
        
        # Thực thi code để kiểm tra
        exec(code, namespace)
        
        # Kiểm tra có hàm entry_function không
        entry_func = namespace.get(entry_function)
        if not entry_func or not callable(entry_func):
            raise ValueError(
                f"Không tìm thấy hàm '{entry_function}' trong solver code. "
                f"Code phải định nghĩa hàm: def {entry_function}(...): ..."
            )
        
    except SyntaxError as e:
        raise ValueError(f"Solver code có lỗi syntax: {str(e)}")
    except Exception as e:
        # Các lỗi khác (runtime errors) có thể chấp nhận được khi validate
        # Vì code có thể cần params để chạy
        # Chỉ cần kiểm tra có hàm entry_function là đủ
        if 'entry_function' in str(e).lower() or 'not found' in str(e).lower():
            raise ValueError(f"Không tìm thấy hàm '{entry_function}' trong solver code")
        # Nếu là lỗi khác, vẫn pass (có thể là lỗi runtime khi chạy không có params)
        pass
    
    return {
        'code': code.strip(),
        'entry_function': entry_function,
        'dependencies': dependencies
    }

# API 1.1: IMPORT TEMPLATE TỪ FILE JSON
@app.route('/api/import-template', methods=['POST'])
def import_template():
    """
    Import template từ file JSON (V2 - New Structure)
    Format file: [{Topic: "...", Questions: [...]}]
    
    Logic:
    - Mỗi Question trong file → tạo 1 Template
    - solver.code → lưu vào Solver (bắt buộc)
    - param_schema → parse và lưu vào Template
    - content_latex, difficulty, explanation_latex → lưu vào Template
    - Convert placeholder: {{param}} → {{{{param}}}}
    - Đảm bảo template có ID để có thể click vào sửa
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Không có file"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Chưa chọn file"}), 400
        
        category_id = request.form.get('category_id')
        if category_id:
            try:
                category_id = int(category_id)
                # Lấy subject_id từ category
                category = category_repo.get_by_id(category_id)
                subject_id = category.subject_id if category else None
            except ValueError:
                return jsonify({"error": "Category ID không hợp lệ"}), 400
        else:
            category_id = None
            subject_id = None
        
        # Đọc và parse JSON
        file_content = file.read().decode('utf-8')
        data = json.loads(file_content)
        
        if not isinstance(data, list):
            return jsonify({"error": "File JSON phải là mảng"}), 400
        
        templates_created = []
        errors = []
        
        # Map difficulty từ chữ sang số
        diff_map = {"Easy": 1, "Medium": 2, "Hard": 3, "Expert": 4}
        
        for topic_data in data:
            topic_raw = topic_data.get('Topic', 'Unknown Topic')
            questions = topic_data.get('Questions', [])
            
            # Xử lý Topic: có thể là string hoặc mảng
            if isinstance(topic_raw, list):
                # Nếu là mảng, tách thành các tags riêng biệt
                tags = [str(tag).strip() for tag in topic_raw if tag and str(tag).strip()]
                # Lấy phần tử cuối cùng làm tên topic (hoặc join nếu muốn)
                topic_name = tags[-1] if tags else 'Unknown Topic'
            else:
                # Nếu là string, chuyển thành mảng 1 phần tử
                topic_name = str(topic_raw).strip() if topic_raw else 'Unknown Topic'
                tags = [topic_name] if topic_name else ['Unknown Topic']
            
            for idx, question in enumerate(questions):
                try:
                    # ============================================================
                    # BƯỚC 1: VALIDATE VÀ PARSE QUESTION DATA
                    # ============================================================
                    
                    # Validate solver object bắt buộc có
                    solver_obj = question.get('solver')
                    if not solver_obj:
                        raise ValueError("Question phải có 'solver' object với field 'code'")
                    
                    # Parse solver object (validate code và entry_function)
                    solver_info = parse_solver_object(solver_obj)
                    
                    # Parse param_schema (có thể rỗng {})
                    param_schema_json = question.get('param_schema', {})
                    param_schema = parse_param_schema(param_schema_json)
                    
                    # Extract và convert placeholder trong content_latex
                    content_latex = question.get('content_latex', '')
                    content_latex = convert_placeholder(content_latex)
                    
                    # Extract difficulty
                    difficulty_str = question.get('difficulty', 'Medium')
                    difficulty = diff_map.get(difficulty_str, 2)
                    
                    # ============================================================
                    # BƯỚC 2: TẠO TEMPLATE
                    # ============================================================
                    
                    template_name = f"{topic_name} - Câu {idx + 1}"
                    
                    # Tags đã được xử lý ở trên
                    
                    # Tạo code cho template (đảm bảo unique)
                    timestamp = int(time.time() * 1000)  # milliseconds để tránh trùng
                    code = f"TMP-{timestamp}-{idx}"
                    
                    # Tạo Template object với:
                    # - param_schema: Đã parse từ JSON (Bước 1)
                    # - question_template: content_latex đã convert placeholder (Bước 1)
                    # - math_formula: content_latex đã convert placeholder (dùng chung với question_template)
                    new_template = Template(
                        id=None,
                        subject_id=subject_id,
                        category_id=category_id,
                        code=code,
                        name=template_name,
                        description=f"Imported from {file.filename}",
                        math_formula=content_latex,  # Đã convert placeholder: {{param}} → {{{{param}}}}
                        question_template=content_latex,  # Đã convert placeholder: {{param}} → {{{{param}}}}
                        param_schema=param_schema,  # Đã parse từ JSON: Dict[str, ParamDefinition]
                        difficulty_base=difficulty,
                        estimated_time=5,
                        tags=tags,
                        hints=[],
                        is_active=True,
                        is_verified=False,
                        created_by=1
                    )
                    saved_template = template_repo.create(new_template)
                    
                    # ============================================================
                    # BƯỚC 3: TẠO SOLVER (V2 - Từ solver object)
                    # ============================================================
                    
                    # Convert explanation_latex placeholder nếu có
                    # (explanation_latex có thể chứa placeholder như {{param}})
                    explanation_latex = question.get('explanation_latex', '')
                    if explanation_latex:
                        explanation_latex = convert_placeholder(explanation_latex)
                    
                    # Tạo Solver object với:
                    # - code: Đã validate có hàm entry_function (Bước 1)
                    # - entry_function: Từ solver object hoặc default "solve"
                    # - dependencies: Từ solver object hoặc default ["sympy"]
                    # - solution_template: explanation_latex đã convert placeholder
                    new_solver = Solver(
                        id=None,
                        template_id=saved_template.id,
                        version="1.0",
                        language="python",
                        code=solver_info['code'],  # Đã validate: có hàm entry_function
                        entry_function=solver_info['entry_function'],  # Từ JSON hoặc default "solve"
                        dependencies=solver_info['dependencies'],  # Từ JSON hoặc default ["sympy"]
                        distractor_config=DistractorConfig([], 3, True),
                        solution_template=explanation_latex,  # Đã convert placeholder: {{param}} → {{{{param}}}}
                        test_cases=[],  # Có thể mở rộng để parse từ JSON sau
                        is_active=True,
                        is_validated=False,  # Sẽ validate sau khi import
                        validation_log=""
                    )
                    solver_repo.create(new_solver)
                    
                    templates_created.append({
                        "template_id": saved_template.id,
                        "name": template_name,
                        "code": code
                    })
                    
                except Exception as e:
                    errors.append({
                        "topic": topic_name,
                        "question_index": idx,
                        "error": str(e)
                    })
        
        return jsonify({
            "success": True,
            "templates_created": len(templates_created),
            "templates": templates_created,
            "errors": errors
        })
        
    except json.JSONDecodeError as e:
        return jsonify({"error": f"File JSON không hợp lệ: {str(e)}"}), 400
    except Exception as e:
        print(f"Lỗi khi import template: {e}")
        return jsonify({"error": str(e)}), 500

# API 2: LƯU TEMPLATE & SINH CÂU HỎI (QUAN TRỌNG NHẤT)
# Logic: Lưu Template -> Lưu Code -> Chạy Code sinh câu hỏi -> Lưu vào bảng Question
@app.route('/api/save-template', methods=['POST'])
def save_template():
    try:
        data = request.json
        
        # 1. Tạo & Lưu Template vào DB
        # Map độ khó từ chữ sang số
        diff_map = {"Easy": 1, "Medium": 2, "Hard": 3, "Expert": 4}
        difficulty = diff_map.get(data.get('difficulty'), 2)
        
        # 1.1. Parse param_schema từ JSON → Dict[ParamDefinition]
        param_schema_dict = {}
        if 'param_schema' in data and data.get('param_schema'):
            try:
                for param_name, param_def in data['param_schema'].items():
                    param_schema_dict[param_name] = ParamDefinition.from_dict(param_name, param_def)
            except Exception as e:
                print(f"Lỗi parse param_schema: {e}")
                param_schema_dict = {}
        
        # 1.2. Lấy subject_id và category_id từ request
        category_id = data.get('category_id')
        subject_id = data.get('subject_id')
        
        # Nếu có category_id nhưng chưa có subject_id, lấy từ category
        if category_id and not subject_id:
            category = category_repo.get_by_id(category_id)
            if category:
                subject_id = category.subject_id
        
        # 1.3. Kiểm tra nếu đang edit (có template_id)
        template_id = data.get('template_id')
        if template_id:
            # Update template hiện có
            existing_template = template_repo.get_by_id(template_id)
            if existing_template:
                existing_template.name = data.get('name', existing_template.name)
                existing_template.description = "Updated via Editor"
                existing_template.math_formula = data.get('content', existing_template.math_formula)
                existing_template.question_template = data.get('content', existing_template.question_template)
                existing_template.param_schema = param_schema_dict
                existing_template.difficulty_base = difficulty
                existing_template.tags = data.get('tags', existing_template.tags)
                if category_id:
                    existing_template.category_id = category_id
                if subject_id:
                    existing_template.subject_id = subject_id
                saved_template = template_repo.update(existing_template)
            else:
                return jsonify({"error": "Template không tồn tại"}), 404
        else:
            # Tạo template mới
            new_template = Template(
                id=None,
                subject_id=subject_id,
                category_id=category_id,
                code=f"TMP-{int(datetime.now().timestamp())}", # Tạo mã giả lập
                name=data.get('name', 'Untitled Template'),
                description="Created via Editor",
                math_formula=data.get('content', ''),
                question_template=data.get('content', ''),
                param_schema=param_schema_dict,  # ← LƯU param_schema ĐÚNG
                difficulty_base=difficulty,
                estimated_time=5,
                tags=data.get('tags', []),
                hints=[],
                is_active=True,
                is_verified=False,  # ← Đặt False để validate sau
                created_by=1
            )
            saved_template = template_repo.create(new_template)
        
        # 2. Tạo hoặc Cập nhật Solver (Code Python)
        # Kiểm tra xem đã có solver active chưa (mỗi template chỉ có 1 solver active)
        existing_solver = solver_repo.get_active_for_template(saved_template.id)
        
        if existing_solver:
            # Update solver hiện có
            existing_solver.code = data.get('code', existing_solver.code)
            existing_solver.entry_function = "solve"
            existing_solver.dependencies = []
            existing_solver.distractor_config = DistractorConfig([], 3, True)
            existing_solver.solution_template = ""
            existing_solver.test_cases = []
            existing_solver.is_active = True
            existing_solver.is_validated = True
            existing_solver.validation_log = ""
            saved_solver = solver_repo.update(existing_solver)
        else:
            # Tạo solver mới
            new_solver = Solver(
                id=None,
                template_id=saved_template.id,
                version="1.0",
                language="python",
                code=data.get('code', ''),
                entry_function="solve",
                dependencies=[],
                distractor_config=DistractorConfig([], 3, True),
                solution_template="",
                test_cases=[],
                is_active=True,
                is_validated=True,
                validation_log=""
            )
            saved_solver = solver_repo.create(new_solver)
        
        # 3. CHẠY CODE ĐỂ SINH CÂU HỎI THẬT (Instance)
        # Đây là bước giúp câu hỏi xuất hiện bên trang Assignment
        local_scope = {}
        try:
            # Chạy code Python người dùng gửi
            exec(saved_solver.code, {}, local_scope)
            
            # Kiểm tra có hàm solve không
            if 'solve' not in local_scope:
                raise ValueError("Không tìm thấy hàm 'solve' trong code")
            
            solve_func = local_scope['solve']
            
            # a. Sinh biến số - Ưu tiên dùng param_schema nếu có
            params = {}
            if saved_template.param_schema:
                # Dùng param_schema để sinh tham số
                import random
                for param_name, param_def in saved_template.param_schema.items():
                    valid_values = param_def.get_valid_values()
                    if valid_values:
                        params[param_name] = random.choice(valid_values)
                    elif param_def.default_value is not None:
                        params[param_name] = param_def.default_value
                    else:
                        # Fallback: sinh giá trị ngẫu nhiên theo type
                        if param_def.param_type == "integer":
                            min_val = int(param_def.min_value) if param_def.min_value is not None else -5
                            max_val = int(param_def.max_value) if param_def.max_value is not None else 5
                            params[param_name] = random.randint(min_val, max_val)
                        elif param_def.param_type == "float":
                            min_val = float(param_def.min_value) if param_def.min_value is not None else -5.0
                            max_val = float(param_def.max_value) if param_def.max_value is not None else 5.0
                            params[param_name] = random.uniform(min_val, max_val)
                        else:
                            params[param_name] = 0
            elif 'generate_variables' in local_scope:
                # Fallback: dùng hàm generate_variables nếu không có param_schema
                params = local_scope['generate_variables']()
            else:
                raise ValueError("Không có param_schema và không tìm thấy hàm 'generate_variables'")
            
            # Validate params với param_schema nếu có
            if saved_template.param_schema:
                is_valid, error_msg = saved_template.validate_params(params)
                if not is_valid:
                    raise ValueError(f"Tham số không hợp lệ: {error_msg}")
            
            # b. Giải toán để lấy đáp án đúng
            result = solve_func(**params)
            
            # c. Thay số vào nội dung câu hỏi (VD: "Tính {{a}} + {{b}}" -> "Tính 5 + 10")
            q_text = saved_template.question_template
            for key, val in params.items():
                # Thay thế {{key}} bằng giá trị
                q_text = q_text.replace(f"{{{{{key}}}}}", str(val))
                
                # d. Lưu vào bảng Questions
                new_question = Question(
                    id=None,
                    template_id=saved_template.id,
                    solver_id=saved_solver.id,
                    param_values=params,
                    param_hash=str(hash(json.dumps(params))),
                    question_text=q_text,
                    question_latex=q_text,
                    question_html="",
                    answers={ # Giả lập 4 đáp án
                        "A": {"text": str(result), "is_correct": True},
                        "B": {"text": "Kết quả khác", "is_correct": False},
                        "C": {"text": "Sai số", "is_correct": False},
                        "D": {"text": "Không xác định", "is_correct": False}
                    },
                    correct_answer="A",
                    correct_value=str(result),
                    correct_symbolic="",
                    solution="Đang cập nhật...",
                    solution_latex="",
                    solution_steps=[],
                    difficulty=difficulty,
                    quality_score=1.0,
                    estimated_time=5,
                    status=QuestionStatus.APPROVED, # Trạng thái APPROVED để hiện ngay
                    is_active=True,
                    usage_count=0,
                    last_used_at=None
                )
                question_repo.create(new_question)
                print(f"--> Đã sinh và lưu câu hỏi ID: {new_question.id}")

        except Exception as e:
            print(f"Lỗi khi sinh câu hỏi mẫu: {e}")
            # Không return lỗi để Frontend vẫn báo Save thành công (chỉ lỗi sinh câu hỏi)

        return jsonify({
            "message": "Đã lưu Template và sinh câu hỏi mẫu!",
            "template_id": saved_template.id
        })
        
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500
    
# API 3: LẤY DANH SÁCH TEMPLATE (Dùng cho trang Template Management)
@app.route('/api/get-all-templates', methods=['GET'])
def get_all_templates():
    try:
        # Lấy tham số từ query string
        keyword = request.args.get('keyword', '').strip()
        tag = request.args.get('tag', '').strip()
        difficulty = request.args.get('difficulty', '').strip()
        status = request.args.get('status', '').strip()
        grade = request.args.get('grade', '').strip()  # Khối lớp (tạm thời chưa dùng)
        category_id = request.args.get('category_id', '').strip()  # Filter theo mục
        subject_id = request.args.get('subject_id', '').strip()  # Filter theo môn học
        limit = int(request.args.get('limit', 10))
        offset = int(request.args.get('offset', 0))
        
        # Lấy templates theo category_id hoặc subject_id nếu có
        if category_id:
            try:
                cat_id = int(category_id)
                templates = template_repo.get_all(category_id=cat_id, active_only=False)
            except ValueError:
                templates = []
        elif subject_id:
            try:
                sub_id = int(subject_id)
                # Lấy tất cả templates rồi filter theo subject_id
                all_templates = template_repo.get_all(active_only=False)
                templates = [t for t in all_templates if t.subject_id == sub_id]
            except ValueError:
                templates = []
        else:
            # Lấy tất cả template (chỉ active vì đã chuyển sang hard delete)
            # Nếu status là "Hoạt động" hoặc "Tất cả", lấy tất cả active templates
            templates = template_repo.get_all(active_only=True)
        
        # Filter theo status (nếu đã filter theo category/subject)
        # Vì đã hard delete, chỉ còn active templates nên không cần filter theo status nữa
        
        # Filter theo keyword (tìm trong name, code)
        if keyword:
            keyword_lower = keyword.lower()
            templates = [t for t in templates if 
                        keyword_lower in t.name.lower() or 
                        keyword_lower in t.code.lower()]
        
        # Filter theo tag (chuyên đề)
        if tag and tag != "Tất cả":
            templates = [t for t in templates if tag in t.tags]
        
        # Filter theo difficulty
        if difficulty and difficulty != "all" and difficulty != "Tất cả":
            try:
                diff_level = int(difficulty)
                templates = [t for t in templates if t.difficulty_base == diff_level]
            except ValueError:
                pass
        
        # Filter theo status đã được xử lý ở trên khi lấy dữ liệu
        # Không cần filter lại ở đây
        
        # Tính tổng số trước khi pagination
        total = len(templates)
        
        # Pagination
        templates = templates[offset:offset + limit]
        
        result = []
        for t in templates:
            # Xử lý updated_at an toàn
            try:
                updated_at_str = t.updated_at.strftime("%d/%m/%Y") if t.updated_at and hasattr(t.updated_at, 'strftime') else "N/A"
            except (AttributeError, ValueError):
                updated_at_str = "N/A"
            
            result.append({
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "difficulty": t.difficulty_base, # Backend trả về số (1,2,3,4) -> Frontend map thành chữ
                "tags": t.tags, # Trả về mảng tags
                "updated_at": updated_at_str,
                "status": "Hoạt động" if t.is_active else "Đã xóa"
            })
        
        return jsonify({
            "templates": result,
            "total": total,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

# API 3.1: LẤY DANH SÁCH TAGS DUY NHẤT (Dùng cho dropdown chuyên đề)
@app.route('/api/get-all-tags', methods=['GET'])
def get_all_tags():
    try:
        # Lấy tất cả template để extract tags
        templates = template_repo.get_all(active_only=False)
        
        # Collect tất cả tags và loại bỏ duplicate
        all_tags = set()
        for t in templates:
            if t.tags:
                all_tags.update(t.tags)
        
        # Sắp xếp và trả về
        tags_list = sorted(list(all_tags))
        return jsonify(tags_list)
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

# API 4: LẤY DANH SÁCH CÂU HỎI (Dùng cho trang Assignment)
@app.route('/api/get-questions', methods=['GET'])
def get_questions_api():
    try:
        # Lấy tham số filter từ query string
        category_id = request.args.get('category_id', type=int)
        difficulty = request.args.get('difficulty', type=int)
        
        # Lấy câu hỏi với filter
        questions = question_repo.search(
            category_id=category_id,
            difficulty=difficulty,
            active_only=True,
            limit=100,
            order_by="created_at DESC"
        )
        
        print(f"[API] get-questions: Found {len(questions)} questions (category_id={category_id}, difficulty={difficulty})")
        
        result = []
        # Mapping dữ liệu từ DB sang format JSON mà Frontend cần
        diff_labels = {1: "Easy", 2: "Medium", 3: "Hard", 4: "Expert"}
        
        for q in questions:
            # Lấy tên môn học từ Template -> Category -> Subject
            subject_name = "Toán học"  # Mặc định
            if q.template_id:
                template = template_repo.get_by_id(q.template_id)
                if template and template.subject_id:
                    subject = subject_repo.get_by_id(template.subject_id)
                    if subject:
                        subject_name = subject.name
            
            # Format answers
            answers_dict = {}
            if q.answers:
                for key, answer in q.answers.items():
                    answers_dict[key] = {
                        "text": answer.text,
                        "latex": answer.latex if hasattr(answer, 'latex') and answer.latex else answer.text,
                        "is_correct": answer.is_correct
                    }
            
            result.append({
                "id": f"ID-{q.id}",
                "question_id": q.id,  # ID thực trong DB
                "content": q.question_text if q.question_text else "",
                "difficulty": diff_labels.get(q.difficulty, "Medium"),
                "difficulty_level": q.difficulty,
                "subject": subject_name,
                "type": "Trắc nghiệm",
                "answers": answers_dict,
                "correct_answer": q.correct_answer
            })
        
        print(f"[API] get-questions: Returning {len(result)} questions")
        return jsonify(result)
    except Exception as e:
        print(f"[API] get-questions ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# API 5: CHẠY TEST CODE (Nút Run Test)
@app.route('/api/run-code', methods=['POST'])
def run_code():
    data = request.json
    user_code = data.get('code', '')
    output_log = io.StringIO()
    variables = {}
    final_result = None
    error_message = None

    try:
        with contextlib.redirect_stdout(output_log):
            # Kiểm tra numpy có sẵn trong môi trường không (chỉ để debug, không import vào namespace)
            try:
                import numpy
                numpy_available = True
            except ImportError:
                numpy_available = False
            
            local_scope = {}
            # Truyền local_scope vào cả 2 vị trí để gộp chung phạm vi
            exec(user_code, local_scope, local_scope)
            
            # Kiểm tra code có 2 hàm chuẩn không
            has_generate_variables = 'generate_variables' in local_scope
            has_solve = 'solve' in local_scope
            
            if has_generate_variables and has_solve:
                # Dạng 1: Code có 2 hàm chuẩn (logic cũ - giữ nguyên)
                print(f"Running solver logic...")
                variables = local_scope['generate_variables']()
                final_result = local_scope['solve'](**variables)
            else:
                # Dạng 2: Code không có 2 hàm (code tự do, chỉ có print hoặc code thường)
                # Code đã được exec ở trên, output từ print() đã được capture vào output_log
                # Lấy output từ print() làm result
                output_content = output_log.getvalue()
                # Tìm dòng cuối cùng có output thực tế (bỏ qua dòng system message)
                lines = output_content.strip().split('\n')
                result_lines = [line for line in lines if line.strip() and 
                               not line.strip().startswith('Running') and
                               not line.strip().startswith('Lỗi:') and
                               not line.strip().startswith('Variable inputs:')]
                if result_lines:
                    # Lấy dòng cuối cùng có output thực tế
                    final_result = result_lines[-1].strip()
                else:
                    final_result = None

    except Exception as e:
        error_message = str(e)
        error_str = str(e)
        
        # Cải thiện thông báo lỗi cho trường hợp thiếu import
        if "No module named" in error_str:
            module_name = error_str.split("'")[1] if "'" in error_str else "thư viện"
            output_log.write(f"Runtime Error: {error_str}\n")
            output_log.write(f"\n=== PHÂN TÍCH LỖI ===\n")
            output_log.write(f"Thư viện '{module_name}' không tìm thấy trong môi trường Python của backend.\n")
            output_log.write(f"\n=== CÁCH KHẮC PHỤC ===\n")
            output_log.write(f"1. Kiểm tra numpy đã được cài đặt chưa:\n")
            output_log.write(f"   - Mở terminal trong thư mục backend\n")
            output_log.write(f"   - Chạy: pip install numpy\n")
            output_log.write(f"   - Hoặc: pip install -r requirements.txt\n")
            output_log.write(f"2. Khởi động lại backend server sau khi cài đặt\n")
            output_log.write(f"3. Kiểm tra lại bằng cách chạy: python -c \"import numpy; print(numpy.__version__)\"\n")
            output_log.write(f"\nLưu ý: Code của bạn đã có 'import numpy as np' đúng rồi.\n")
            output_log.write(f"Vấn đề là môi trường Python chưa có numpy được cài đặt.\n")
        elif "name 'np' is not defined" in error_str or "name 'sp' is not defined" in error_str:
            module_name = "numpy" if "np" in error_str else "sympy"
            output_log.write(f"Runtime Error: {error_str}\n")
            output_log.write(f"Gợi ý: Bạn có thể đã quên import. Thử thêm 'import {module_name} as {'np' if module_name == 'numpy' else 'sp'}' vào đầu code.\n")
        else:
            output_log.write(f"Runtime Error: {error_str}")

    # Lấy logs (loại bỏ dòng "Running code..." nếu là code tự do)
    logs_content = output_log.getvalue()
    
    return jsonify({
        "logs": logs_content,
        "variables": variables,
        "result": str(final_result) if final_result is not None else None,
        "error": error_message
    })

# API 6: THỐNG KÊ DASHBOARD
@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    try:
        # Đếm tổng số template
        templates = template_repo.get_all(active_only=True)
        total_templates = len(templates)
        
        # Đếm tổng số câu hỏi
        questions = question_repo.search(active_only=True, limit=10000)
        total_questions = len(questions)
        
        # Đếm đề thi (tạm thời hardcode vì chưa có ExamRepository)
        total_exams = 0
        
        # Người dùng hoạt động (tạm thời hardcode)
        active_users = 24
        
        return jsonify({
            "total_templates": total_templates,
            "total_questions": total_questions,
            "total_exams": total_exams,
            "active_users": active_users
        })
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

# API 7: SINH CÂU HỎI TỪ TEMPLATE (V2 - Hybrid AI + Rule-based)
@app.route('/api/generate-questions', methods=['POST'])
def generate_questions():
    """
    Sinh câu hỏi từ template với AI + Rule-based hybrid approach
    
    Request body:
    {
        "template_ids": [1, 2, 3],
        "quantity": 20,
        "difficulty": "Trung bình",  # "Dễ", "Trung bình", "Khó", "Rất khó", "Ngẫu nhiên"
        "min_value": -10,
        "max_value": 10,
        "template_configs": {
            "1": {
                "params": {
                    "a": [2, 3, 5, 10],
                    "require_integer_solution": true
                }
            }
        }
    }
    """
    try:
        data = request.json
        template_ids = data.get('template_ids', [])
        quantity = data.get('quantity', 20)
        difficulty_str = data.get('difficulty', 'Trung bình')
        min_value = data.get('min_value', -10)
        max_value = data.get('max_value', 10)
        template_configs = data.get('template_configs', {})
        
        # Validate input
        if not template_ids:
            return jsonify({"error": "Vui lòng chọn ít nhất một template"}), 400
        
        if quantity <= 0:
            return jsonify({"error": "Số lượng câu hỏi phải lớn hơn 0"}), 400
        
        if min_value >= max_value:
            return jsonify({"error": "min_value phải nhỏ hơn max_value"}), 400
        
        # Map difficulty string to number
        difficulty_map = {
            "Dễ (Nhận biết)": 1,
            "Dễ": 1,
            "Trung bình (Thông hiểu)": 2,
            "Trung bình": 2,
            "Khó (Vận dụng)": 3,
            "Khó": 3,
            "Rất khó (Vận dụng cao)": 4,
            "Rất khó": 4,
            "Ngẫu nhiên": random.randint(1, 4)
        }
        user_difficulty = difficulty_map.get(difficulty_str, 2)
        
        # Convert template_configs keys to int
        template_configs_int = {}
        for key, value in template_configs.items():
            try:
                template_id_int = int(key)
                template_configs_int[template_id_int] = value
            except ValueError:
                continue
        
        # Gọi QuestionGenerationService với logging
        print(f"[INFO] Bắt đầu sinh câu hỏi: {len(template_ids)} template(s), {quantity} câu hỏi/template")
        start_time = time.time()
        
        try:
            result = question_generator.generate_batch(
                template_ids=template_ids,
                quantity=quantity,
                user_difficulty=user_difficulty,
                global_range={"min": min_value, "max": max_value},
                template_configs=template_configs_int
            )
            
            elapsed_time = time.time() - start_time
            print(f"[INFO] Hoàn thành sinh câu hỏi trong {elapsed_time:.2f} giây. Đã sinh: {result.get('total_generated', 0)} câu hỏi")
        except Exception as e:
            elapsed_time = time.time() - start_time
            print(f"[ERROR] Lỗi khi sinh câu hỏi sau {elapsed_time:.2f} giây: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "error": f"Lỗi khi sinh câu hỏi: {str(e)}",
                "success": False
            }), 500
        
        # Format questions cho frontend
        formatted_questions = []
        for q in result.get("questions", []):
            # q là Question object
            answers_dict = {}
            if hasattr(q, 'answers') and q.answers:
                for letter, answer in q.answers.items():
                    # Xử lý Answer object
                    if hasattr(answer, 'text'):
                        answer_text = answer.text
                    elif hasattr(answer, 'latex'):
                        answer_text = answer.latex
                    elif hasattr(answer, 'value'):
                        answer_text = str(answer.value)
                    else:
                        answer_text = str(answer)
                    
                    answers_dict[letter] = {
                        "text": answer_text,
                        "latex": answer.latex if hasattr(answer, 'latex') else answer_text,
                        "is_correct": answer.is_correct if hasattr(answer, 'is_correct') else False
                    }
            
            # Lấy question_text
            question_text = q.question_text if hasattr(q, 'question_text') and q.question_text else ''
            if not question_text and hasattr(q, 'question_latex'):
                question_text = q.question_latex
            
            formatted_questions.append({
                "id": f"Q-{q.id if hasattr(q, 'id') and q.id else 'unknown'}",
                "question_text": question_text,  # Thêm field này để frontend dễ dùng
                "content": question_text,  # Giữ lại để tương thích
                "answers": answers_dict,
                "correct_answer": q.correct_answer if hasattr(q, 'correct_answer') else 'A',
                "difficulty": q.difficulty if hasattr(q, 'difficulty') else 2,
                "template_id": q.template_id if hasattr(q, 'template_id') else None,
                "quality_score": q.quality_score if hasattr(q, 'quality_score') else 0.0,
                # V2 fields
                "explanation": getattr(q, 'explanation', '') or '',
                "ai_enriched": getattr(q, 'ai_enriched', False),
                "review_status": getattr(q, 'review_status', 'DRAFT') or 'DRAFT',
                "param_values": getattr(q, 'param_values', {})
            })
        
        # V2: Cập nhật stats với review info (nếu chưa có trong result)
        stats = result.get("stats", {})
        if "ai_enriched" not in stats:
            stats["ai_enriched"] = sum(1 for q in formatted_questions if q.get("ai_enriched", False))
        if "pending_review" not in stats:
            stats["pending_review"] = sum(1 for q in formatted_questions if q.get("review_status") == "AI_GENERATED")
        
        return jsonify({
            "success": result.get("success", True),
            "questions": formatted_questions,
            "total": result.get("total_generated", len(formatted_questions)),
            "stats": stats,
            "warnings": result.get("warnings", [])
        })
        
    except Exception as e:
        print(f"[ERROR] generate_questions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# API 8: LẤY DANH SÁCH CÂU HỎI VỚI FILTER (Dùng cho Question bank.html)
@app.route('/api/questions/search', methods=['GET'])
def search_questions():
    try:
        # Lấy tham số từ query string
        keyword = request.args.get('keyword', '')
        subject = request.args.get('subject', '')
        difficulty = request.args.get('difficulty', '')
        status = request.args.get('status', '')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        # Lấy tất cả câu hỏi
        questions = question_repo.search(active_only=True, limit=limit + offset)
        
        # Filter theo keyword
        if keyword:
            questions = [q for q in questions if keyword.lower() in q.question_text.lower() or keyword in str(q.id)]
        
        # Filter theo difficulty (hỗ trợ cả số và chữ)
        if difficulty and difficulty != "Tất cả" and difficulty != "":
            try:
                target_diff = int(difficulty)
                questions = [q for q in questions if q.difficulty == target_diff]
            except ValueError:
                diff_map = {"Easy": 1, "Medium": 2, "Hard": 3, "Expert": 4, "Dễ": 1, "Trung bình": 2, "Khó": 3, "Cực khó": 4}
                target_diff = diff_map.get(difficulty, None)
                if target_diff:
                    questions = [q for q in questions if q.difficulty == target_diff]
        
        # Filter theo status
        if status and status != "Tất cả" and status != "":
            status_map = {"Đã duyệt": QuestionStatus.APPROVED, "Chờ duyệt": QuestionStatus.DRAFT, "Có lỗi": QuestionStatus.REJECTED}
            target_status = status_map.get(status, None)
            if target_status:
                questions = [q for q in questions if q.status == target_status]
        
        # Filter theo subject
        if subject and subject != "":
            filtered_questions = []
            for q in questions:
                template = template_repo.get_by_id(q.template_id) if q.template_id else None
                subject_name = template.tags[0] if template and template.tags else "Toán học"
                if subject.lower() in subject_name.lower():
                    filtered_questions.append(q)
            questions = filtered_questions
        
        # Pagination
        total = len(questions)
        questions = questions[offset:offset + limit]
        
        # Format kết quả
        diff_labels = {1: "Dễ (Nhận biết)", 2: "Trung bình (Thông hiểu)", 3: "Khó (Vận dụng)", 4: "Cực khó (Vận dụng cao)"}
        result = []
        for q in questions:
            # Lấy template để lấy subject, category
            template = template_repo.get_by_id(q.template_id) if q.template_id else None
            subject_name = "Toán học"
            subject_code = ""
            chapter_name = ""
            section_name = ""
            
            if template:
                # Lấy subject từ template
                if template.subject_id:
                    subject = subject_repo.get_by_id(template.subject_id)
                    if subject:
                        subject_name = subject.name
                        subject_code = subject.code or ""
                
                # Lấy chapter và section từ category
                if template.category_id:
                    category = category_repo.get_by_id(template.category_id)
                    if category:
                        if category.level == 1:  # Chapter
                            chapter_name = category.name
                        elif category.level >= 2:  # Section
                            section_name = category.name
                            # Lấy chapter (parent)
                            if category.parent_id:
                                chapter = category_repo.get_by_id(category.parent_id)
                                if chapter:
                                    chapter_name = chapter.name
                # Fallback: nếu không có category, thử lấy từ tags
                if not chapter_name and template.tags:
                    subject_name = template.tags[0] if template.tags else "Toán học"
            
            # Format answers
            answers_dict = {}
            if q.answers:
                for key, answer in q.answers.items():
                    answers_dict[key] = {
                        "text": answer.text,
                        "is_correct": answer.is_correct
                    }
            
            result.append({
                "id": f"#Q-2023-{q.id:03d}",
                "question_id": q.id,  # ID thực trong DB để xóa
                "content": q.question_text,
                "subject": subject_name,
                "subject_code": subject_code,
                "chapter": chapter_name,
                "section": section_name,
                "difficulty": diff_labels.get(q.difficulty, "Trung bình"),
                "difficulty_level": q.difficulty,
                "status": "Đã duyệt" if q.status == QuestionStatus.APPROVED else "Chờ duyệt" if q.status == QuestionStatus.DRAFT else "Có lỗi" if q.status == QuestionStatus.REJECTED else "Đã lưu trữ",
                "rating": 4,  # Tạm thời hardcode
                "answers": answers_dict,
                "type": "Trắc nghiệm"
            })
        
        return jsonify({
            "questions": result,
            "total": total,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

# API 8.1: XÓA CÂU HỎI (Hard delete)
@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    try:
        # Kiểm tra câu hỏi có tồn tại không
        question = question_repo.get_by_id(question_id)
        if not question:
            return jsonify({"error": "Câu hỏi không tồn tại"}), 404
        
        # Xóa trực tiếp khỏi database (hard delete)
        success = question_repo.hard_delete(question_id)
        if success:
            return jsonify({"success": True, "message": "Đã xóa câuỏi thành công"})
        else:
            return jsonify({"error": "Không thể xóa câu hỏi"}), 500
    except Exception as e:
        print(f"Lỗi xóa câu hỏi: {e}")
        return jsonify({"error": str(e)}), 500

# API 9: LẤY DANH SÁCH TEMPLATE CHO CREATE QUESTION PAGE
@app.route('/api/templates/list', methods=['GET'])
def list_templates():
    try:
        templates = template_repo.get_all(active_only=True)
        result = []
        for t in templates:
            result.append({
                "id": t.id,
                "name": t.name,
                "code": t.code,
                "description": t.description or "",
                "tags": t.tags,
                "difficulty": t.difficulty_base,
                "math_formula": t.math_formula or "",
                "question_template": t.question_template or ""
            })
        return jsonify(result)
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

# API 9.1: XÓA TEMPLATE (Hard Delete)
@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Xóa template khỏi database (hard delete - xóa vĩnh viễn)"""
    try:
        # Kiểm tra template có tồn tại không
        template = template_repo.get_by_id(template_id)
        if not template:
            return jsonify({"success": False, "error": "Template không tồn tại"}), 404
        
        # Thực hiện hard delete (xóa vĩnh viễn khỏi database)
        # Các bản ghi liên quan (questions, solvers) sẽ tự động bị xóa nhờ ON DELETE CASCADE
        success = template_repo.delete(template_id)
        
        if success:
            return jsonify({"success": True, "message": "Đã xóa template thành công"})
        else:
            return jsonify({"success": False, "error": "Không thể xóa template"}), 500
            
    except Exception as e:
        print(f"Lỗi khi xóa template: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# API 10: LẤY DANH SÁCH MÔN HỌC DUY NHẤT (Dùng cho dropdown filter)
@app.route('/api/subjects', methods=['GET'])
def get_subjects():
    """Lấy danh sách tất cả môn học duy nhất từ database"""
    try:
        # Lấy tất cả templates active để extract tags (môn học)
        templates = template_repo.get_all(active_only=True)
        
        # Collect tất cả subjects từ tags của templates
        subjects_set = set()
        for template in templates:
            if template.tags:
                # Môn học thường là tag đầu tiên
                for tag in template.tags:
                    # Chỉ lấy tag đầu tiên làm môn học (hoặc có thể filter theo pattern)
                    if tag and tag.strip():
                        subjects_set.add(tag.strip())
        
        # Nếu không có môn học nào, thêm môn học mặc định
        if not subjects_set:
            subjects_set.add("Toán học")
        
        # Sắp xếp và trả về
        subjects_list = sorted(list(subjects_set))
        return jsonify(subjects_list)
    except Exception as e:
        print(f"Lỗi khi lấy danh sách môn học: {e}")
        return jsonify(["Toán học"]), 500

# ============================================================================
# SUBJECT APIs
# ============================================================================

# API: LẤY DANH SÁCH MÔN HỌC
@app.route('/api/get-all-subjects', methods=['GET'])
def get_all_subjects():
    """Lấy danh sách tất cả môn học"""
    try:
        subjects = subject_repo.get_all(active_only=True)
        result = [s.to_dict() for s in subjects]
        return jsonify({"subjects": result})
    except Exception as e:
        print(f"Lỗi khi lấy danh sách môn học: {e}")
        return jsonify({"error": str(e)}), 500

# API: TẠO MÔN HỌC MỚI
@app.route('/api/subjects', methods=['POST'])
def create_subject():
    """Tạo môn học mới"""
    try:
        data = request.json
        subject = Subject(
            name=data.get('name', ''),
            code=data.get('code', ''),
            description=data.get('description', ''),
            is_active=True
        )
        subject = subject_repo.create(subject)
        return jsonify({"success": True, "subject": subject.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: CẬP NHẬT MÔN HỌC
@app.route('/api/subjects/<int:subject_id>', methods=['PUT'])
def update_subject(subject_id):
    """Cập nhật môn học"""
    try:
        subject = subject_repo.get_by_id(subject_id)
        if not subject:
            return jsonify({"error": "Môn học không tồn tại"}), 404
        
        data = request.json
        subject.name = data.get('name', subject.name)
        subject.code = data.get('code', subject.code)
        subject.description = data.get('description', subject.description)
        subject.is_active = data.get('is_active', subject.is_active)
        
        subject = subject_repo.update(subject)
        return jsonify({"success": True, "subject": subject.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: XÓA MÔN HỌC
@app.route('/api/subjects/<int:subject_id>', methods=['DELETE'])
def delete_subject(subject_id):
    """Xóa môn học (soft delete)"""
    try:
        success = subject_repo.delete(subject_id)
        if success:
            return jsonify({"success": True})
        return jsonify({"error": "Môn học không tồn tại"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# CHAPTER APIs (Categories level=1)
# ============================================================================

# API: LẤY DANH SÁCH CHƯƠNG CỦA MÔN HỌC
@app.route('/api/subjects/<int:subject_id>/chapters', methods=['GET'])
def get_chapters_by_subject(subject_id):
    """Lấy danh sách chương của một môn học"""
    try:
        chapters = category_repo.get_chapters_by_subject(subject_id)
        result = [c.to_dict() for c in chapters]
        return jsonify({"chapters": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: TẠO CHƯƠNG MỚI
@app.route('/api/subjects/<int:subject_id>/chapters', methods=['POST'])
def create_chapter(subject_id):
    """Tạo chương mới cho môn học"""
    try:
        # Kiểm tra subject tồn tại
        subject = subject_repo.get_by_id(subject_id)
        if not subject:
            return jsonify({"error": "Môn học không tồn tại"}), 404
        
        data = request.json
        category = Category(
            subject_id=subject_id,
            name=data.get('name', ''),
            description=data.get('description', ''),
            parent_id=None,  # Chương không có parent
            level=1,  # Level 1 = Chương
            sort_order=data.get('sort_order', 0),
            is_active=True
        )
        category = category_repo.create(category)
        return jsonify({"success": True, "chapter": category.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# SECTION APIs (Categories level=2+)
# ============================================================================

# API: LẤY DANH SÁCH MỤC CỦA CHƯƠNG
@app.route('/api/chapters/<int:chapter_id>/sections', methods=['GET'])
def get_sections_by_chapter(chapter_id):
    """Lấy danh sách mục của một chương"""
    try:
        sections = category_repo.get_sections_by_chapter(chapter_id)
        result = [s.to_dict() for s in sections]
        return jsonify({"sections": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: TẠO MỤC MỚI
@app.route('/api/chapters/<int:chapter_id>/sections', methods=['POST'])
def create_section(chapter_id):
    """Tạo mục mới cho chương"""
    try:
        # Kiểm tra chapter tồn tại
        chapter = category_repo.get_by_id(chapter_id)
        if not chapter:
            return jsonify({"error": "Chương không tồn tại"}), 404
        
        data = request.json
        section = Category(
            subject_id=chapter.subject_id,  # Kế thừa subject_id từ chapter
            name=data.get('name', ''),
            description=data.get('description', ''),
            parent_id=chapter_id,  # Parent là chapter
            level=chapter.level + 1,  # Level = level của chapter + 1
            sort_order=data.get('sort_order', 0),
            is_active=True
        )
        section = category_repo.create(section)
        return jsonify({"success": True, "section": section.to_dict()}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: CẬP NHẬT CATEGORY (Chương hoặc Mục)
@app.route('/api/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    """Cập nhật category (chương hoặc mục)"""
    try:
        category = category_repo.get_by_id(category_id)
        if not category:
            return jsonify({"error": "Category không tồn tại"}), 404
        
        data = request.json
        category.name = data.get('name', category.name)
        category.description = data.get('description', category.description)
        category.sort_order = data.get('sort_order', category.sort_order)
        category.is_active = data.get('is_active', category.is_active)
        
        category = category_repo.update(category)
        return jsonify({"success": True, "category": category.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: XÓA CATEGORY
@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    """Xóa category (soft delete)"""
    try:
        success = category_repo.delete(category_id)
        if success:
            return jsonify({"success": True})
        return jsonify({"error": "Category không tồn tại"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: LẤY THÔNG TIN CATEGORY VÀ BREADCRUMB
@app.route('/api/categories/<int:category_id>/breadcrumb', methods=['GET'])
def get_category_breadcrumb(category_id):
    """Lấy breadcrumb path của category"""
    try:
        category = category_repo.get_by_id(category_id)
        if not category:
            return jsonify({"error": "Category không tồn tại"}), 404
        
        breadcrumb = []
        
        # Lấy subject
        if category.subject_id:
            subject = subject_repo.get_by_id(category.subject_id)
            if subject:
                breadcrumb.append({"type": "subject", "id": subject.id, "name": subject.name})
        
        # Lấy parent chain (nếu có)
        current = category
        path = []
        while current:
            path.insert(0, {"type": "category", "id": current.id, "name": current.name, "level": current.level})
            if current.parent_id:
                current = category_repo.get_by_id(current.parent_id)
            else:
                break
        
        breadcrumb.extend(path)
        
        return jsonify({"breadcrumb": breadcrumb})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API 11: LẤY DANH SÁCH LỚP HỌC (Dùng cho dropdown filter)
@app.route('/api/grades', methods=['GET'])
def get_grades():
    """Lấy danh sách lớp học (có thể mở rộng từ database sau)"""
    try:
        # Hiện tại trả về danh sách lớp học cố định
        # Có thể mở rộng để lấy từ database nếu có bảng grades
        grades = ["10", "11", "12"]
        return jsonify(grades)
    except Exception as e:
        print(f"Lỗi khi lấy danh sách lớp học: {e}")
        return jsonify(["10", "11", "12"]), 500

# API 12: LẤY TỔNG SỐ CÂU HỎI (Dùng cho hiển thị số lượng)
@app.route('/api/questions/count', methods=['GET'])
def get_questions_count():
    """Lấy tổng số câu hỏi trong database"""
    try:
        # Lấy tham số filter từ query string
        subject = request.args.get('subject', '')
        difficulty = request.args.get('difficulty', '')
        status = request.args.get('status', '')
        
        # Lấy tất cả câu hỏi để filter
        questions = question_repo.search(active_only=True, limit=10000)
        
        # Filter theo difficulty
        if difficulty and difficulty != "Tất cả" and difficulty != "":
            try:
                target_diff = int(difficulty)
                questions = [q for q in questions if q.difficulty == target_diff]
            except ValueError:
                diff_map = {"Easy": 1, "Medium": 2, "Hard": 3, "Expert": 4, "Dễ": 1, "Trung bình": 2, "Khó": 3, "Cực khó": 4}
                target_diff = diff_map.get(difficulty, None)
                if target_diff:
                    questions = [q for q in questions if q.difficulty == target_diff]
        
        # Filter theo status
        if status and status != "Tất cả" and status != "":
            status_map = {"Đã duyệt": QuestionStatus.APPROVED, "Chờ duyệt": QuestionStatus.DRAFT, "Có lỗi": QuestionStatus.REJECTED}
            target_status = status_map.get(status, None)
            if target_status:
                questions = [q for q in questions if q.status == target_status]
        
        # Filter theo subject
        if subject and subject != "":
            filtered_questions = []
            for q in questions:
                template = template_repo.get_by_id(q.template_id) if q.template_id else None
                subject_name = template.tags[0] if template and template.tags else "Toán học"
                if subject.lower() in subject_name.lower():
                    filtered_questions.append(q)
            questions = filtered_questions
        
        return jsonify({
            "count": len(questions),
            "total": len(questions)
        })
    except Exception as e:
        print(f"Lỗi khi đếm số câu hỏi: {e}")
        return jsonify({"count": 0, "total": 0}), 500

# API 13: REVIEW QUESTION (V2 - Review Workflow)
@app.route('/api/questions/<int:question_id>/review', methods=['POST'])
def review_question(question_id):
    """
    Review câu hỏi (V2)
    
    Request body:
    {
        "action": "approve" | "reject" | "edit",
        "notes": "...",
        "reviewer_id": 1
    }
    """
    try:
        data = request.json or {}
        action = data.get('action', '').lower()
        notes = data.get('notes', '')
        reviewer_id = data.get('reviewer_id')
        
        if action not in ['approve', 'reject', 'edit']:
            return jsonify({
                "error": "Invalid action. Must be 'approve', 'reject', or 'edit'"
            }), 400
        
        success = question_service.review_question(
            question_id=question_id,
            action=action,
            reviewer_id=reviewer_id,
            notes=notes
        )
        
        if not success:
            return jsonify({"error": "Question not found"}), 404
        
        # Lấy question đã được update
        question = question_service.get(question_id)
        
        return jsonify({
            "success": True,
            "message": f"Question {action}d successfully",
            "question": {
                "id": question.id,
                "review_status": question.review_status,
                "status": question.status.value if isinstance(question.status, QuestionStatus) else question.status,
                "reviewed_by": question.reviewed_by,
                "reviewed_at": question.reviewed_at.isoformat() if question.reviewed_at else None,
                "review_notes": question.review_notes
            }
        })
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[ERROR] review_question: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# API 14: GET PENDING REVIEW QUESTIONS (V2)
@app.route('/api/questions/pending-review', methods=['GET'])
def get_pending_review():
    """
    Lấy danh sách câu hỏi cần review (V2)
    
    Query params:
    - limit: Số lượng tối đa (default: 50)
    - offset: Offset cho pagination (default: 0)
    """
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        questions = question_service.get_pending_review(limit=limit, offset=offset)
        total = question_service.count_pending_review()
        
        # Format questions
        formatted_questions = []
        for q in questions:
            # Format answers
            answers_dict = {}
            if hasattr(q, 'answers') and q.answers:
                for letter, answer in q.answers.items():
                    if hasattr(answer, 'text'):
                        answer_text = answer.text
                    elif hasattr(answer, 'latex'):
                        answer_text = answer.latex
                    elif hasattr(answer, 'value'):
                        answer_text = str(answer.value)
                    else:
                        answer_text = str(answer)
                    
                    answers_dict[letter] = {
                        "text": answer_text,
                        "latex": answer.latex if hasattr(answer, 'latex') else answer_text,
                        "is_correct": answer.is_correct if hasattr(answer, 'is_correct') else False
                    }
            
            formatted_questions.append({
                "id": q.id,
                "question_text": q.question_text if hasattr(q, 'question_text') and q.question_text else '',
                "answers": answers_dict,
                "correct_answer": q.correct_answer if hasattr(q, 'correct_answer') else 'A',
                "difficulty": q.difficulty if hasattr(q, 'difficulty') else 2,
                "template_id": q.template_id if hasattr(q, 'template_id') else None,
                "quality_score": q.quality_score if hasattr(q, 'quality_score') else 0.0,
                "review_status": getattr(q, 'review_status', 'DRAFT'),
                "ai_enriched": getattr(q, 'ai_enriched', False),
                "explanation": getattr(q, 'explanation', ''),
                "created_at": q.created_at.isoformat() if hasattr(q, 'created_at') and q.created_at else None
            })
        
        return jsonify({
            "success": True,
            "questions": formatted_questions,
            "total": total,
            "limit": limit,
            "offset": offset
        })
        
    except Exception as e:
        print(f"[ERROR] get_pending_review: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- PHẦN 4: KHỞI CHẠY ---
if __name__ == '__main__':
    # Tạo bảng DB nếu chưa có
    db._init_database()
    print("Database Initialized & Server Running at http://127.0.0.1:5000")
    app.run(debug=True, port=5000)