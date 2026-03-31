
"""
services.py - Logic nghiệp vụ của hệ thống
"""

import random
import time
import uuid
import json
import re
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# SymPy để giải toán
import sympy as sp
from sympy import (
    symbols, integrate, diff, limit, exp, sin, cos, tan, log, ln,
    sqrt, simplify, latex, fraction, expand, factor, Rational,
    oo, E, pi, Symbol, Matrix
)

from models import (
    Category, Template, ParamDefinition, Solver,
    Question, Answer, Exam, ExamQuestion, ExamConfig,
    QuestionStatus, ExamStatus, DistractorConfig, TestCase, GenerationLog, ReviewStatus
)
from database import (
    Database, CategoryRepository, TemplateRepository,
    SolverRepository, QuestionRepository, ExamRepository, GenerationLogRepository
)
from config import Config

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TEMPLATE SERVICE
# ============================================================================

class TemplateService:
    """Service quản lý Template"""
    
    def __init__(self, db: Database):
        self.db = db
        self.repo = TemplateRepository(db)
        self.category_repo = CategoryRepository(db)
    
    def create(self,
               code: str,
               name: str,
               math_formula: str,
               param_schema: Dict[str, Dict],
               category_id: Optional[int] = None,
               description: str = "",
               question_template: str = "",
               difficulty_base: int = 3,
               estimated_time: int = 3,
               tags: List[str] = None,
               hints: List[str] = None,
               created_by: Optional[int] = None) -> Template:
        """Tạo template mới"""
        
        # Chuyển đổi param_schema
        parsed_schema = {}
        for param_name, param_def in param_schema.items():
            parsed_schema[param_name] = ParamDefinition.from_dict(param_name, param_def)
        
        template = Template(
            category_id=category_id,
            code=code,
            name=name,
            description=description,
            math_formula=math_formula,
            question_template=question_template,
            param_schema=parsed_schema,
            difficulty_base=difficulty_base,
            estimated_time=estimated_time,
            tags=tags or [],
            hints=hints or [],
            created_by=created_by
        )
        
        return self.repo.create(template)
    
    def get(self, template_id: int) -> Optional[Template]:
        """Lấy template theo ID"""
        return self.repo.get_by_id(template_id)
    
    def get_by_code(self, code: str) -> Optional[Template]:
        """Lấy template theo code"""
        return self.repo.get_by_code(code)
    
    def list(self, category_id: Optional[int] = None) -> List[Template]:
        """Liệt kê templates"""
        return self.repo.get_all(category_id)
    
    def search(self, query: str) -> List[Template]:
        """Tìm kiếm templates"""
        return self.repo.search(query)
    
    def update(self, template: Template) -> Template:
        """Cập nhật template"""
        return self.repo.update(template)
    
    def delete(self, template_id: int) -> bool:
        """Xóa template khỏi database (hard delete)"""
        return self.repo.delete(template_id)
    
    def get_stats(self, template_id: int) -> Dict:
        """Lấy thống kê của template"""
        question_repo = QuestionRepository(self.db)
        
        total = question_repo.count(template_id=template_id)
        approved = question_repo.count(template_id=template_id, status=QuestionStatus.APPROVED)
        draft = question_repo.count(template_id=template_id, status=QuestionStatus.DRAFT)
        
        template = self.repo.get_by_id(template_id)
        total_combinations = template.get_total_combinations() if template else 0
        
        return {
            "total_questions": total,
            "approved": approved,
            "draft": draft,
            "total_combinations": total_combinations,
            "coverage": round(total / total_combinations * 100, 2) if total_combinations > 0 else 0
        }


# ============================================================================
# SOLVER SERVICE
# ============================================================================

class SolverService:
    """Service quản lý và thực thi Solver"""
    
    def __init__(self, db: Database):
        self.db = db
        self.repo = SolverRepository(db)
        self.template_repo = TemplateRepository(db)
    
    def register(self,
                 template_id: int,
                 code: str,
                 version: str = "1.0.0",
                 language: str = "python",
                 entry_function: str = "solve",
                 dependencies: List[str] = None,
                 distractor_strategies: List[str] = None,
                 distractor_count: int = 3,
                 solution_template: str = "",
                 test_cases: List[Dict] = None) -> Solver:
        """Đăng ký solver mới"""
        
        solver = Solver(
            template_id=template_id,
            version=version,
            language=language,
            code=code,
            entry_function=entry_function,
            dependencies=dependencies or ["sympy"],
            distractor_config=DistractorConfig(
                strategies=distractor_strategies or [
                    "sign_error", "missing_bound", "coefficient_error", "adjacent_param"
                ],
                count=distractor_count
            ),
            solution_template=solution_template,
            test_cases=[
                TestCase(
                    input_params=tc.get('input', {}),
                    expected_output=str(tc.get('expected', '')),
                    description=tc.get('description', '')
                )
                for tc in (test_cases or [])
            ]
        )
        
        return self.repo.create(solver)
    
    def get(self, solver_id: int) -> Optional[Solver]:
        """Lấy solver theo ID"""
        return self.repo.get_by_id(solver_id)
    
    def get_active(self, template_id: int) -> Optional[Solver]:
        """Lấy solver active của template"""
        return self.repo.get_active_for_template(template_id)
    
    def execute(self, solver: Solver, params: Dict[str, Any]) -> Any:
        """Thực thi solver và trả về kết quả"""
        
        # Tạo namespace với các module cần thiết
        namespace = {
            # SymPy
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
        
        # Thực thi code solver
        try:
            exec(solver.code, namespace)
        except Exception as e:
            raise RuntimeError(f"Lỗi compile solver: {e}")
        
        # Lấy hàm entry
        entry_func = namespace.get(solver.entry_function)
        if not entry_func or not callable(entry_func):
            raise ValueError(f"Không tìm thấy hàm '{solver.entry_function}' trong solver")
        
        # Thực thi hàm với params
        try:
            result = entry_func(**params)
            return result
        except Exception as e:
            raise RuntimeError(f"Lỗi thực thi solver: {e}")
    
    def validate(self, solver_id: int) -> Tuple[bool, str]:
        """Validate solver với test cases"""
        solver = self.repo.get_by_id(solver_id)
        if not solver:
            return False, "Solver không tồn tại"
        
        if not solver.test_cases:
            return True, "Không có test case"
        
        results = []
        all_passed = True
        
        for i, tc in enumerate(solver.test_cases):
            try:
                actual = self.execute(solver, tc.input_params)
                actual_str = str(simplify(actual))
                expected_str = str(simplify(sp.sympify(tc.expected_output)))
                
                # So sánh kết quả
                passed = actual_str == expected_str
                if not passed:
                    # Thử so sánh số học
                    try:
                        diff = simplify(sp.sympify(actual_str) - sp.sympify(expected_str))
                        passed = diff == 0
                    except:
                        pass
                
                results.append({
                    "test": i + 1,
                    "input": tc.input_params,
                    "expected": expected_str,
                    "actual": actual_str,
                    "passed": passed
                })
                
                if not passed:
                    all_passed = False
                    
            except Exception as e:
                results.append({
                    "test": i + 1,
                    "input": tc.input_params,
                    "error": str(e),
                    "passed": False
                })
                all_passed = False
        
        # Cập nhật trạng thái
        import json
        log = json.dumps(results, indent=2, ensure_ascii=False)
        self.repo.set_validated(solver_id, all_passed, log)
        
        return all_passed, log


# ============================================================================
# DISTRACTOR SERVICE
# ============================================================================

class DistractorService:
    """Service sinh đáp án nhiễu"""
    
    def generate(self,
                 correct_answer: Any,
                 params: Dict[str, Any],
                 strategies: List[str],
                 count: int = 3,
                 solver_func: Callable = None) -> List[Tuple[Any, str]]:
        """
        Sinh đáp án nhiễu
        Returns: List of (distractor_value, error_type)
        """
        distractors = []
        
        for strategy in strategies:
            if len(distractors) >= count:
                break
            
            result = None
            error_type = strategy
            
            try:
                if strategy == "sign_error":
                    result = self._sign_error(correct_answer)
                elif strategy == "missing_bound":
                    result = self._missing_bound(correct_answer, params)
                elif strategy == "coefficient_error":
                    result = self._coefficient_error(correct_answer, params)
                elif strategy == "adjacent_param":
                    result = self._adjacent_param(correct_answer, params, solver_func)
                elif strategy == "random_variation":
                    result = self._random_variation(correct_answer, params)
                elif strategy == "partial_result":
                    result = self._partial_result(correct_answer, params)
                elif strategy == "swap_operands":
                    result = self._swap_operands(correct_answer)
            except:
                continue
            
            if result is not None:
                # Chỉ simplify nếu không phải string và không phải Matrix
                if not isinstance(result, str) and not isinstance(result, Matrix):
                    try:
                        result = simplify(result)
                    except:
                        pass  # Giữ nguyên result nếu simplify thất bại
                
                # Kiểm tra không trùng
                try:
                    # Xử lý Matrix: không simplify, so sánh trực tiếp
                    if isinstance(correct_answer, Matrix):
                        correct_simplified = correct_answer
                    elif isinstance(correct_answer, str):
                        correct_simplified = correct_answer
                    else:
                        correct_simplified = simplify(correct_answer)
                    
                    # Xử lý result tương tự
                    if isinstance(result, Matrix):
                        result_simplified = result
                    elif isinstance(result, str):
                        result_simplified = result
                    else:
                        result_simplified = simplify(result) if not isinstance(result, str) else result
                    
                    # So sánh: kiểm tra xem result có khác correct_answer không
                    if isinstance(correct_simplified, Matrix) and isinstance(result_simplified, Matrix):
                        # So sánh Matrix: khác nhau nếu không phải zero matrix
                        are_different = not (correct_simplified - result_simplified).is_zero_matrix
                    else:
                        are_different = (result_simplified != correct_simplified)
                    
                    if are_different:
                        is_duplicate = False
                        for d, _ in distractors:
                            if isinstance(d, Matrix):
                                d_simplified = d
                            elif isinstance(d, str):
                                d_simplified = d
                            else:
                                d_simplified = simplify(d) if not isinstance(d, str) else d
                            
                            # So sánh
                            if isinstance(result_simplified, Matrix) and isinstance(d_simplified, Matrix):
                                if (result_simplified - d_simplified).is_zero_matrix:
                                    is_duplicate = True
                                    break
                            else:
                                if d_simplified == result_simplified:
                                    is_duplicate = True
                                    break
                        if not is_duplicate:
                            distractors.append((result, error_type))
                except Exception as e:
                    # Nếu so sánh thất bại, vẫn thêm vào
                    logger.warning(f"Error comparing distractors: {e}")
                    distractors.append((result, error_type))
        
        # Sinh thêm nếu chưa đủ
        attempts = 0
        while len(distractors) < count and attempts < 20:
            result = self._random_variation(correct_answer, params)
            # Chỉ simplify nếu không phải string và không phải Matrix
            if not isinstance(result, str) and not isinstance(result, Matrix):
                try:
                    result = simplify(result)
                except:
                    pass
            
            try:
                # Xử lý Matrix: không simplify, so sánh trực tiếp
                if isinstance(correct_answer, Matrix):
                    correct_simplified = correct_answer
                elif isinstance(correct_answer, str):
                    correct_simplified = correct_answer
                else:
                    correct_simplified = simplify(correct_answer)
                
                # Xử lý result tương tự
                if isinstance(result, Matrix):
                    result_simplified = result
                elif isinstance(result, str):
                    result_simplified = result
                else:
                    result_simplified = simplify(result) if not isinstance(result, str) else result
                
                # So sánh: kiểm tra xem result có khác correct_answer không
                if isinstance(correct_simplified, Matrix) and isinstance(result_simplified, Matrix):
                    # So sánh Matrix: khác nhau nếu không phải zero matrix
                    are_different = not (correct_simplified - result_simplified).is_zero_matrix
                else:
                    are_different = (result_simplified != correct_simplified)
                
                if are_different:
                    is_duplicate = False
                    for d, _ in distractors:
                        if isinstance(d, Matrix):
                            d_simplified = d
                        elif isinstance(d, str):
                            d_simplified = d
                        else:
                            d_simplified = simplify(d) if not isinstance(d, str) else d
                        
                        # So sánh
                        if isinstance(result_simplified, Matrix) and isinstance(d_simplified, Matrix):
                            if (result_simplified - d_simplified).is_zero_matrix:
                                is_duplicate = True
                                break
                        else:
                            if d_simplified == result_simplified:
                                is_duplicate = True
                                break
                    if not is_duplicate:
                        distractors.append((result, "random_variation"))
            except Exception as e:
                # Nếu so sánh thất bại, vẫn thêm vào
                logger.warning(f"Error comparing distractors in random_variation: {e}")
                distractors.append((result, "random_variation"))
            attempts += 1
        
        return distractors[:count]
    
    def _sign_error(self, answer: Any) -> Any:
        """Đổi dấu"""
        if isinstance(answer, Matrix):
            return -answer  # Matrix hỗ trợ phép nhân với -1
        return -answer
    
    def _missing_bound(self, answer: Any, params: Dict) -> Any:
        """Quên cận (phổ biến trong tích phân)"""
        if isinstance(answer, Matrix):
            # Với Matrix, nhân với 2
            return answer * 2
        try:
            numer, denom = fraction(answer)
            if denom != 1:
                # Giả định: bỏ phần hằng số
                # Đây là heuristic đơn giản
                return numer / denom * 2
            return answer * 2
        except:
            # Nếu fraction fail, nhân với 2
            return answer * 2
    
    def _coefficient_error(self, answer: Any, params: Dict) -> Any:
        """Sai hệ số"""
        # Matrix hỗ trợ phép nhân với số
        if 'a' in params and params['a'] != 0:
            return answer * abs(params['a'])
        if 'n' in params and params['n'] != 0:
            return answer * params['n']
        return answer * 2
    
    def _adjacent_param(self, answer: Any, params: Dict, solver_func: Callable = None) -> Any:
        """Tính với tham số lân cận"""
        if solver_func and params:
            # Thử thay đổi một tham số
            new_params = params.copy()
            for key in ['a', 'n', 'b', 'c']:
                if key in new_params:
                    old_val = new_params[key]
                    if isinstance(old_val, int):
                        new_val = old_val + (1 if old_val >= 0 else -1)
                        if new_val == 0 and key == 'a':
                            new_val = old_val - (1 if old_val >= 0 else -1)
                        new_params[key] = new_val
                        try:
                            return solver_func(**new_params)
                        except:
                            new_params[key] = old_val
        
        # Fallback
        return answer * Rational(3, 2)
    
    def _random_variation(self, answer: Any, params: Dict) -> Any:
        """Sinh biến thể ngẫu nhiên"""
        # Xử lý Matrix riêng
        if isinstance(answer, Matrix):
            variation = random.choice(['multiply', 'add_scalar'])
            try:
                if variation == 'multiply':
                    factor = random.choice([Rational(1, 2), Rational(2, 1), Rational(3, 2), -1])
                    return answer * factor
                elif variation == 'add_scalar':
                    # Thêm một số nhỏ vào từng phần tử (không thể cộng trực tiếp, dùng nhân)
                    factor = random.choice([0.9, 1.1, 0.95, 1.05])
                    return answer * factor
            except:
                pass
            # Fallback cho Matrix: nhân với một số
            return answer * random.choice([2, 3, Rational(1, 2)])
        
        # Xử lý các loại khác (số, biểu thức)
        try:
            numer, denom = fraction(answer)
        except:
            # Nếu không phải fraction, dùng answer trực tiếp
            variation = random.choice(['multiply', 'add_const'])
            try:
                if variation == 'multiply':
                    factor = random.choice([Rational(1, 2), Rational(2, 1), Rational(3, 2), -1])
                    return answer * factor
                elif variation == 'add_const':
                    delta = random.choice([-3, -2, -1, 1, 2, 3])
                    return answer + delta
            except:
                pass
            return answer * 2
        
        variation = random.choice(['add_exp', 'add_const', 'multiply', 'change_denom'])
        
        try:
            if variation == 'add_exp' and 'a' in params:
                delta = random.choice([-2, -1, 1, 2])
                a = params['a']
                if denom != 1:
                    return (numer + delta * exp(a)) / denom
                return numer + delta * exp(a)
            
            elif variation == 'add_const':
                delta = random.choice([-3, -2, -1, 1, 2, 3])
                if denom != 1:
                    return (numer + delta) / denom
                return numer + delta
            
            elif variation == 'multiply':
                factor = random.choice([Rational(1, 2), Rational(2, 1), Rational(3, 2), -1])
                return answer * factor
            
            elif variation == 'change_denom' and denom != 1:
                new_denom = denom + random.choice([-1, 1]) * abs(params.get('a', 1))
                if new_denom != 0:
                    return numer / new_denom
        except:
            pass
        
        # Fallback
        try:
            return answer + random.randint(-3, 3)
        except:
            return answer * 2
    
    def _partial_result(self, answer: Any, params: Dict) -> Any:
        """Kết quả trung gian (bỏ một số hạng)"""
        if isinstance(answer, Matrix):
            # Với Matrix, nhân với một hệ số
            return answer * Rational(2, 3)
        try:
            expanded = expand(answer)
            if hasattr(expanded, 'args') and len(expanded.args) > 1:
                # Bỏ một số hạng
                args = list(expanded.args)
                if len(args) > 1:
                    args.pop(random.randint(0, len(args) - 1))
                    return sum(args)
        except:
            pass
        return answer * Rational(2, 3)
    
    def _swap_operands(self, answer: Any) -> Any:
        """Đảo toán hạng"""
        if isinstance(answer, Matrix):
            # Với Matrix, không thể đảo toán hạng, dùng -answer
            return -answer
        try:
            numer, denom = fraction(answer)
            if denom != 1 and numer != 0:
                return denom / numer
            return -answer
        except:
            # Nếu fraction fail, dùng -answer
            return -answer


# ============================================================================
# DATA CLASSES FOR AI ENRICHMENT
# ============================================================================

@dataclass
class QuestionData:
    """Data structure để truyền vào AI Enrichment Service"""
    params: Dict[str, Any]
    correct_answer: Any  # SymPy expression
    correct_answer_latex: str  # LaTeX string từ SymPy
    template: Template
    solver: Solver


@dataclass
class EnrichedContent:
    """Kết quả từ AI Enrichment Service"""
    question_text: str
    distractors: List[Dict[str, Any]]  # List of {value, text, error_type, error_description}
    explanation: str
    ai_used: bool = True
    fallback_reason: Optional[str] = None


# ============================================================================
# LATEX NORMALIZER
# ============================================================================

class LaTeXNormalizer:
    """Normalize LaTeX expressions to preserve SymPy consistency"""
    
    def normalize(self, ai_text: str, sympy_latex: str) -> str:
        """
        Normalize LaTeX in AI-generated text
        
        Strategy:
        1. Extract math expressions from AI text
        2. Replace with SymPy LaTeX if match
        3. Keep non-math text from AI
        
        Args:
            ai_text: Text từ AI có thể chứa LaTeX
            sympy_latex: LaTeX string từ SymPy (chuẩn)
        
        Returns:
            Normalized text với SymPy LaTeX
        """
        if not ai_text or not sympy_latex:
            return ai_text
        
        # Pattern to match LaTeX expressions: $...$, $$...$$, \(...\), \[...\]
        # Hỗ trợ cả inline và display math
        latex_pattern = r'\$\$([^$]+)\$\$|\$([^$]+)\$|\\\[([^\]]+)\\\]|\\\(([^\)]+)\\\)'
        
        def replace_latex(match):
            # Extract LaTeX content từ các patterns
            ai_latex = match.group(1) or match.group(2) or match.group(3) or match.group(4)
            if not ai_latex:
                return match.group(0)
            
            # Check if this matches SymPy expression
            if self._matches_sympy(ai_latex, sympy_latex):
                # Giữ nguyên format của AI (inline hoặc display)
                if match.group(1):  # $$...$$
                    return f"$${sympy_latex}$$"
                elif match.group(3):  # \[...\]
                    return f"\\[{sympy_latex}\\]"
                elif match.group(4):  # \(...\)
                    return f"\\({sympy_latex}\\)"
                else:  # $...$
                    return f"${sympy_latex}$"
            else:
                # Keep AI LaTeX if it's different (e.g., formatting, different expression)
                return match.group(0)
        
        normalized = re.sub(latex_pattern, replace_latex, ai_text)
        return normalized
    
    def normalize_distractor_value(self, distractor_value: str, correct_answer_latex: str) -> str:
        """
        Normalize distractor value (có thể là số hoặc biểu thức)
        
        Args:
            distractor_value: Giá trị distractor từ AI (string)
            correct_answer_latex: LaTeX của đáp án đúng
        
        Returns:
            Normalized distractor value (LaTeX nếu là biểu thức, text nếu là số đơn giản)
        """
        if not distractor_value:
            return distractor_value
        
        # Thử parse như một biểu thức SymPy
        try:
            distractor_expr = sp.sympify(distractor_value)
            distractor_latex = latex(distractor_expr)
            
            # Nếu distractor match với correct answer, dùng correct answer latex
            if self._matches_sympy(distractor_latex, correct_answer_latex):
                return correct_answer_latex
            
            return distractor_latex
        except:
            # Nếu không parse được, giữ nguyên
            return distractor_value
    
    def _matches_sympy(self, ai_latex: str, sympy_latex: str) -> bool:
        """
        Check if AI LaTeX matches SymPy expression
        
        Strategy:
        1. Normalize cả hai strings
        2. So sánh normalized versions
        3. Có thể thử parse và so sánh symbolic nếu cần
        """
        if not ai_latex or not sympy_latex:
            return False
        
        # Normalize both: remove spaces, convert to lowercase
        ai_normalized = self._normalize_latex_string(ai_latex)
        sympy_normalized = self._normalize_latex_string(sympy_latex)
        
        # Direct comparison
        if ai_normalized == sympy_normalized:
            return True
        
        # Thử parse và so sánh symbolic (cho các trường hợp format khác nhau)
        try:
            ai_expr = sp.sympify(ai_latex.replace('$', '').replace('\\[', '').replace('\\]', ''))
            sympy_expr = sp.sympify(sympy_latex.replace('$', '').replace('\\[', '').replace('\\]', ''))
            
            # So sánh symbolic
            if simplify(ai_expr - sympy_expr) == 0:
                return True
        except:
            pass
        
        return False
    
    def _normalize_latex_string(self, latex: str) -> str:
        r"""
        Normalize LaTeX string for comparison
        
        Steps:
        1. Remove LaTeX delimiters ($, $$, \[, \], \(, \))
        2. Remove spaces
        3. Normalize common LaTeX commands
        4. Convert to lowercase
        """
        # Remove LaTeX delimiters
        normalized = re.sub(r'^\$+|\$+$', '', latex)  # Remove $ at start/end
        normalized = re.sub(r'^\\\[|\\\]$', '', normalized)  # Remove \[ \]
        normalized = re.sub(r'^\\\(|\\\)$', '', normalized)  # Remove \( \)
        
        # Remove spaces
        normalized = re.sub(r'\s+', '', normalized)
        
        # Normalize common LaTeX commands (có thể có variation)
        # Ví dụ: \frac{a}{b} vs \dfrac{a}{b} -> cùng một biểu thức
        normalized = re.sub(r'\\dfrac', r'\\frac', normalized)
        normalized = re.sub(r'\\left\(', r'\\(', normalized)
        normalized = re.sub(r'\\right\)', r'\\)', normalized)
        normalized = re.sub(r'\\left\[', r'\\[', normalized)
        normalized = re.sub(r'\\right\]', r'\\]', normalized)
        
        # Convert to lowercase (nhưng giữ nguyên các ký tự trong math)
        normalized = normalized.lower()
        
        return normalized


# ============================================================================
# AI ENRICHMENT SERVICE (V2 - Batch Processing)
# ============================================================================

class AIEnrichmentService:
    """Service làm giàu nội dung câu hỏi bằng AI (Gemini)"""
    
    def __init__(self, gemini_api_key: str = None, batch_size: int = None):
        self.gemini_api_key = gemini_api_key or Config.GEMINI_API_KEY
        self.batch_size = batch_size or Config.GEMINI_BATCH_SIZE
        self.fallback_service = DistractorService()
        self.latex_normalizer = LaTeXNormalizer()
        
        if not self.gemini_api_key:
            logger.warning("GEMINI_API_KEY not configured, AI enrichment will use fallback")
    
    def enrich_batch(self, question_data_list: List[QuestionData], 
                     batch_size: int = None) -> List[EnrichedContent]:
        """
        Batch enrichment - main method
        
        Args:
            question_data_list: List of QuestionData
            batch_size: Số câu hỏi mỗi batch (default: self.batch_size)
        
        Returns:
            List[EnrichedContent]
        """
        if not question_data_list:
            return []
        
        batch_size = batch_size or self.batch_size
        
        # Chunking
        chunks = self._chunk_questions(question_data_list, batch_size)
        
        enriched_list = []
        for chunk_idx, chunk in enumerate(chunks):
            try:
                # Build batch prompt
                prompt = self._build_batch_prompt(chunk)
                
                # Call Gemini with structured output
                response = self._call_gemini_batch(prompt)
                
                # Parse with Pydantic
                parsed = self._parse_batch_response(response, len(chunk))
                
                # Normalize LaTeX và combine với original data
                normalized = []
                for ec, qd in zip(parsed, chunk):
                    # Normalize LaTeX trong question_text và explanation
                    normalized_question_text = self.latex_normalizer.normalize(
                        ec.question_text, qd.correct_answer_latex
                    )
                    normalized_explanation = self.latex_normalizer.normalize(
                        ec.explanation, qd.correct_answer_latex
                    )
                    
                    # Normalize distractors - đảm bảo LaTeX consistency
                    normalized_distractors = []
                    for distractor in ec.distractors:
                        # Normalize distractor value nếu là biểu thức toán
                        normalized_value = self.latex_normalizer.normalize_distractor_value(
                            distractor.get("value", ""),
                            qd.correct_answer_latex
                        )
                        
                        # Normalize distractor text (có thể chứa LaTeX)
                        normalized_text = self.latex_normalizer.normalize(
                            distractor.get("text", ""),
                            qd.correct_answer_latex
                        )
                        
                        normalized_distractors.append({
                            "value": normalized_value,
                            "text": normalized_text,
                            "error_type": distractor.get("error_type", ""),
                            "error_description": distractor.get("error_description", "")
                        })
                    
                    normalized.append(EnrichedContent(
                        question_text=normalized_question_text,
                        distractors=normalized_distractors,
                        explanation=normalized_explanation,
                        ai_used=True
                    ))
                
                enriched_list.extend(normalized)
                
            except Exception as e:
                # Fallback for this chunk
                logger.warning(f"Batch enrichment failed for chunk {chunk_idx + 1}: {e}")
                fallback = self._fallback_batch_enrichment(chunk)
                enriched_list.extend(fallback)
        
        return enriched_list
    
    def _chunk_questions(self, question_data_list: List[QuestionData], 
                        batch_size: int) -> List[List[QuestionData]]:
        """Chia nhóm câu hỏi thành batches"""
        chunks = []
        for i in range(0, len(question_data_list), batch_size):
            chunks.append(question_data_list[i:i + batch_size])
        return chunks
    
    def _build_batch_prompt(self, question_data_list: List[QuestionData]) -> str:
        """Build prompt for batch processing"""
        prompt = f"""Bạn là giáo viên toán chuyên nghiệp. Hãy làm giàu nội dung cho {len(question_data_list)} câu hỏi sau:

"""
        for i, qd in enumerate(question_data_list, 1):
            # Format correct answer
            correct_answer_str = str(qd.correct_answer)
            if hasattr(qd.correct_answer, '__class__'):
                try:
                    correct_answer_str = latex(qd.correct_answer)
                except:
                    pass
            
            prompt += f"""Câu {i}:
- Công thức: {qd.template.math_formula}
- Tham số: {json.dumps(qd.params, ensure_ascii=False)}
- Đáp án đúng: {correct_answer_str} (LaTeX: {qd.correct_answer_latex})
- Loại bài: {qd.template.name}
- Mô tả: {qd.template.description or 'Không có mô tả'}

"""
        
        prompt += """Yêu cầu cho mỗi câu hỏi:
1. Viết lại đề bài tự nhiên, dễ hiểu (tiếng Việt), có ngữ cảnh thực tế
2. Sinh 3 đáp án sai dựa trên lỗi sai tư duy phổ biến của học sinh
3. Viết lời giải chi tiết từng bước, giải thích rõ ràng

Trả về dạng JSON theo schema sau (CHỈ TRẢ VỀ JSON, KHÔNG CÓ TEXT KHÁC):
{
  "questions": [
    {
      "question_text": "Đề bài được viết lại tự nhiên, dễ hiểu...",
      "distractors": [
        {
          "value": "Giá trị đáp án sai (có thể là số hoặc biểu thức)",
          "text": "Mô tả đáp án sai bằng tiếng Việt",
          "error_type": "Loại lỗi (ví dụ: sign_error, missing_bound, coefficient_error)",
          "error_description": "Mô tả tại sao học sinh thường mắc lỗi này"
        }
      ],
      "explanation": "Lời giải chi tiết từng bước..."
    }
  ]
}

Lưu ý QUAN TRỌNG:
- Giữ nguyên các biểu thức LaTeX từ đáp án đúng (không thay đổi công thức toán)
- Chỉ thay đổi phần lời văn, thêm ngữ cảnh
- Đáp án sai phải dựa trên lỗi thường gặp, không phải random
- Lời giải phải chi tiết, từng bước rõ ràng
- Trả về ĐÚNG {len(question_data_list)} câu hỏi trong mảng "questions"
"""
        return prompt
    
    def _call_gemini_batch(self, prompt: str) -> dict:
        """Call Gemini API with structured output"""
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 4000,
                    "response_mime_type": "application/json"  # Structured output
                }
            )
            
            response = model.generate_content(prompt)
            
            # Parse JSON response
            response_text = response.text.strip()
            
            # Remove markdown code blocks nếu có
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            return json.loads(response_text)
            
        except ImportError:
            raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {e}")
            logger.error(f"Response text: {response_text[:500]}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
    
    def _parse_batch_response(self, response_json: dict, 
                              expected_count: int) -> List[EnrichedContent]:
        """Parse response with Pydantic validation"""
        try:
            from pydantic import BaseModel, ValidationError
        except ImportError:
            raise ImportError("pydantic package not installed. Run: pip install pydantic")
        
        class DistractorModel(BaseModel):
            value: str
            text: str
            error_type: str
            error_description: str
        
        class QuestionModel(BaseModel):
            question_text: str
            distractors: List[DistractorModel]
            explanation: str
        
        class BatchResponseModel(BaseModel):
            questions: List[QuestionModel]
        
        try:
            validated = BatchResponseModel(**response_json)
            
            if len(validated.questions) != expected_count:
                raise ValueError(
                    f"Expected {expected_count} questions, got {len(validated.questions)}"
                )
            
            enriched_list = []
            for q in validated.questions:
                # Convert distractors to dict format
                distractors_dict = [
                    {
                        "value": d.value,
                        "text": d.text,
                        "error_type": d.error_type,
                        "error_description": d.error_description
                    }
                    for d in q.distractors
                ]
                
                enriched = EnrichedContent(
                    question_text=q.question_text,
                    distractors=distractors_dict,
                    explanation=q.explanation,
                    ai_used=True
                )
                enriched_list.append(enriched)
            
            return enriched_list
            
        except ValidationError as e:
            logger.error(f"Pydantic validation error: {e}")
            raise ValueError(f"Validation error: {e}")
        except Exception as e:
            logger.error(f"Parse error: {e}")
            raise
    
    def _fallback_batch_enrichment(self, question_data_list: List[QuestionData]) -> List[EnrichedContent]:
        """Fallback to rule-based enrichment when AI fails"""
        enriched_list = []
        
        for qd in question_data_list:
            try:
                # Generate question text từ template
                question_text = qd.template.question_template or qd.template.math_formula
                for key, val in qd.params.items():
                    question_text = question_text.replace(f"{{{{{key}}}}}", str(val))
                
                # Generate distractors bằng rule-based
                distractors_data = self.fallback_service.generate(
                    correct_answer=qd.correct_answer,
                    params=qd.params,
                    strategies=qd.solver.distractor_config.strategies,
                    count=qd.solver.distractor_config.count,
                    solver_func=lambda **p: None  # Không dùng solver_func trong fallback
                )
                
                # Convert to dict format
                distractors_dict = [
                    {
                        "value": str(d[0]),
                        "text": str(d[0]),
                        "error_type": d[1],
                        "error_description": f"Lỗi {d[1]} thường gặp"
                    }
                    for d in distractors_data
                ]
                
                enriched = EnrichedContent(
                    question_text=question_text,
                    distractors=distractors_dict,
                    explanation="",  # Không có explanation trong fallback
                    ai_used=False,
                    fallback_reason="AI enrichment failed"
                )
                enriched_list.append(enriched)
                
            except Exception as e:
                logger.error(f"Fallback enrichment failed: {e}")
                # Tạo empty enriched content
                enriched_list.append(EnrichedContent(
                    question_text="",
                    distractors=[],
                    explanation="",
                    ai_used=False,
                    fallback_reason=f"Fallback error: {e}"
                ))
        
        return enriched_list


# ============================================================================
# QUESTION GENERATION SERVICE (V2 - Batch Processing)
# ============================================================================

class QuestionGenerationService:
    """Service sinh câu hỏi với batch processing (V2)"""
    
    def __init__(self, db: Database):
        self.db = db
        self.template_repo = TemplateRepository(db)
        self.solver_repo = SolverRepository(db)
        self.question_repo = QuestionRepository(db)
        self.solver_service = SolverService(db)
        self.distractor_service = DistractorService()
        # V2: AI Enrichment Service
        try:
            self.ai_enrichment_service = AIEnrichmentService()
        except Exception as e:
            logger.warning(f"Failed to initialize AIEnrichmentService: {e}. Will use fallback only.")
            self.ai_enrichment_service = None
    
    def generate_batch(self,
                      template_ids: List[int],
                      quantity: int = 20,
                      user_difficulty: int = 2,
                      global_range: Dict[str, int] = None,
                      template_configs: Dict[int, Dict] = None) -> Dict[str, Any]:
        """
        Sinh câu hỏi hàng loạt cho nhiều templates (V2 - Batch Processing)
        
        Args:
            template_ids: List template IDs
            quantity: Số lượng câu hỏi mỗi template
            user_difficulty: Độ khó mong muốn (1-4)
            global_range: {"min": -10, "max": 10}
            template_configs: {template_id: {params: {...}, ...}}
        
        Returns:
            {
                "success": bool,
                "questions": List[Question],
                "total_generated": int,
                "stats": {...},
                "warnings": List[str]
            }
        """
        global_range = global_range or {"min": -10, "max": 10}
        template_configs = template_configs or {}
        
        all_questions = []
        all_stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "duplicate": 0,
            "low_quality": 0
        }
        warnings = []
        
        for template_id in template_ids:
            try:
                # Lấy template và solver
                template = self.template_repo.get_by_id(template_id)
                if not template:
                    warnings.append(f"Template {template_id} không tồn tại")
                    all_stats["failed"] += quantity
                    continue
                
                solver = self.solver_repo.get_active_for_template(template_id)
                if not solver:
                    warnings.append(f"Template {template_id} không có solver active")
                    all_stats["failed"] += quantity
                    continue
                
                # Lấy config cho template này
                template_config = template_configs.get(template_id, {})
                
                # Sinh câu hỏi cho template này
                result = self._generate_for_template(
                    template=template,
                    solver=solver,
                    quantity=quantity,
                    user_difficulty=user_difficulty,
                    global_range=global_range,
                    template_config=template_config
                )
                
                all_questions.extend(result["questions"])
                all_stats["success"] += result["stats"]["success"]
                all_stats["failed"] += result["stats"]["failed"]
                all_stats["duplicate"] += result["stats"]["duplicate"]
                all_stats["low_quality"] += result["stats"]["low_quality"]
                
            except Exception as e:
                warnings.append(f"Lỗi khi sinh câu hỏi cho template {template_id}: {str(e)}")
                all_stats["failed"] += quantity
                import traceback
                traceback.print_exc()
        
        all_stats["total"] = len(template_ids) * quantity
        # V2: Thêm review stats
        all_stats["ai_enriched"] = sum(1 for q in all_questions if getattr(q, 'ai_enriched', False))
        all_stats["pending_review"] = sum(1 for q in all_questions if getattr(q, 'review_status', 'DRAFT') == 'AI_GENERATED')
        
        return {
            "success": len(all_questions) > 0,
            "questions": all_questions,
            "total_generated": len(all_questions),
            "stats": all_stats,
            "warnings": warnings
        }
    
    def _generate_for_template(self,
                               template: Template,
                               solver: Solver,
                               quantity: int,
                               user_difficulty: int,
                               global_range: Dict[str, int],
                               template_config: Dict) -> Dict[str, Any]:
        """
        Sinh câu hỏi cho một template (V2 - Batch Processing)
        
        Returns:
            {
                "questions": List[Question],
                "stats": {...}
            }
        """
        stats = {
            "success": 0,
            "failed": 0,
            "duplicate": 0,
            "low_quality": 0,
            "ai_enriched": 0,
            "fallback_used": 0
        }
        
        # PHASE 1: Core Processing (Batch)
        # Step 1: Generate all params upfront
        all_params = self._generate_batch_params(
            template=template,
            quantity=quantity,
            global_range=global_range,
            template_config=template_config,
            user_difficulty=user_difficulty
        )
        
        if not all_params:
            return {"questions": [], "stats": stats}
        
        # Step 2: Batch check duplicates
        unique_params = self._check_batch_duplicates(
            template_id=template.id,
            params_list=all_params
        )
        
        duplicate_count = len(all_params) - len(unique_params)
        stats["duplicate"] = duplicate_count
        
        if not unique_params:
            return {"questions": [], "stats": stats}
        
        # Step 3: Batch execute solver
        correct_answers = self._execute_batch_solver(
            solver=solver,
            params_list=unique_params
        )
        
        # Filter out failed executions
        valid_data = [
            (params, answer) 
            for params, answer in zip(unique_params, correct_answers)
            if answer is not None
        ]
        
        if not valid_data:
            stats["failed"] = len(unique_params)
            return {"questions": [], "stats": stats}
        
        valid_params, valid_answers = zip(*valid_data)
        stats["failed"] = len(unique_params) - len(valid_params)
        
        # PHASE 2: AI Enrichment (Batch)
        # Step 4: Prepare batch data for AI
        question_data_list = [
            QuestionData(
                params=params,
                correct_answer=answer,
                correct_answer_latex=latex(answer) if not isinstance(answer, str) else str(answer),
                template=template,
                solver=solver
            )
            for params, answer in zip(valid_params, valid_answers)
        ]
        
        # Step 5: Batch AI enrichment
        enriched_list = []
        if self.ai_enrichment_service:
            try:
                enriched_list = self.ai_enrichment_service.enrich_batch(
                    question_data_list=question_data_list,
                    batch_size=Config.GEMINI_BATCH_SIZE
                )
                # Track AI enrichment stats
                stats["ai_enriched"] = sum(1 for ec in enriched_list if ec.ai_used)
                stats["fallback_used"] = sum(1 for ec in enriched_list if not ec.ai_used)
            except Exception as e:
                logger.warning(f"AI enrichment failed, using fallback: {e}")
                stats["fallback_used"] = len(question_data_list)
                # Fallback sẽ được xử lý trong _create_batch_questions
                enriched_list = []
        else:
            # Không có AI service, dùng fallback
            stats["fallback_used"] = len(question_data_list)
            enriched_list = []
        
        # PHASE 3: Integration & Persistence
        # Step 6: Create questions
        questions = self._create_batch_questions(
            template=template,
            solver=solver,
            params_list=list(valid_params),
            correct_answers=list(valid_answers),
            enriched_list=enriched_list,
            question_data_list=question_data_list,
            difficulty=user_difficulty
        )
        
        # Step 5: Validate & Save
        validated_questions = []
        for q in questions:
            if self._validate_quality(q):
                try:
                    saved = self.question_repo.create(q)
                    validated_questions.append(saved)
                    stats["success"] += 1
                except Exception as e:
                    # Có thể do duplicate khi save
                    stats["duplicate"] += 1
            else:
                stats["low_quality"] += 1
        
        return {
            "questions": validated_questions,
            "stats": stats
        }
    
    def _generate_batch_params(self,
                              template: Template,
                              quantity: int,
                              global_range: Dict[str, int],
                              template_config: Dict,
                              user_difficulty: int) -> List[Dict[str, Any]]:
        """
        Sinh tất cả params trước (Batch version)
        
        Returns:
            List[Dict[str, Any]] - List of param dictionaries
        """
        params_list = []
        attempts = 0
        max_attempts = quantity * 3  # Cho phép thử nhiều lần
        
        while len(params_list) < quantity and attempts < max_attempts:
            attempts += 1
            
            try:
                params = {}
                valid = True
                
                # Generate params theo schema
                for param_name, param_def in template.param_schema.items():
                    # Kiểm tra template_config có override không
                    if param_name in template_config.get("params", {}):
                        config_value = template_config["params"][param_name]
                        if isinstance(config_value, list):
                            # Chọn ngẫu nhiên từ list
                            params[param_name] = random.choice(config_value)
                        else:
                            params[param_name] = config_value
                        continue
                    
                    # Generate theo param_def
                    if param_def.param_type == "integer":
                        min_val = param_def.min_value if param_def.min_value is not None else global_range["min"]
                        max_val = param_def.max_value if param_def.max_value is not None else global_range["max"]
                        
                        # Điều chỉnh theo difficulty
                        if user_difficulty == 1:  # Dễ
                            max_val = min(max_val, 5)
                        elif user_difficulty == 4:  # Rất khó
                            min_val = max(min_val, -20)
                            max_val = max(max_val, 20)
                        
                        value = random.randint(min_val, max_val)
                        
                        # Kiểm tra exclude
                        if param_def.exclude and value in param_def.exclude:
                            valid = False
                            break
                        
                        params[param_name] = value
                    
                    elif param_def.param_type == "float":
                        min_val = param_def.min_value if param_def.min_value is not None else global_range["min"]
                        max_val = param_def.max_value if param_def.max_value is not None else global_range["max"]
                        value = random.uniform(min_val, max_val)
                        params[param_name] = round(value, 2)
                    
                    elif param_def.param_type == "choice":
                        if param_def.choices:
                            params[param_name] = random.choice(param_def.choices)
                        else:
                            valid = False
                            break
                    
                    elif param_def.param_type == "range":
                        min_val = param_def.min_value if param_def.min_value is not None else global_range["min"]
                        max_val = param_def.max_value if param_def.max_value is not None else global_range["max"]
                        start = random.randint(min_val, max_val - 1)
                        end = random.randint(start + 1, max_val)
                        params[param_name] = (start, end)
                
                if valid:
                    # Tính param_hash để check duplicate trong batch
                    param_hash = Question.compute_param_hash(params)
                    
                    # Kiểm tra không trùng trong batch hiện tại
                    is_duplicate = any(
                        Question.compute_param_hash(p) == param_hash 
                        for p in params_list
                    )
                    
                    if not is_duplicate:
                        params_list.append(params)
            
            except Exception as e:
                logger.warning(f"Error generating params: {e}")
                continue
        
        return params_list
    
    def _check_batch_duplicates(self,
                                template_id: int,
                                params_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Batch check duplicates trong database
        
        Returns:
            List[Dict[str, Any]] - Filtered params list (loại bỏ duplicates)
        """
        if not params_list:
            return []
        
        # Tính param_hash cho tất cả params
        param_hashes = [
            Question.compute_param_hash(params) 
            for params in params_list
        ]
        
        # Batch query: SELECT param_hash FROM questions WHERE template_id = ? AND param_hash IN (...)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(param_hashes))
            cursor.execute(
                f"""
                SELECT DISTINCT param_hash 
                FROM questions 
                WHERE template_id = ? AND param_hash IN ({placeholders})
                """,
                [template_id] + param_hashes
            )
            existing_hashes = {row[0] for row in cursor.fetchall()}
        
        # Filter out duplicates
        unique_params = [
            params for params in params_list
            if Question.compute_param_hash(params) not in existing_hashes
        ]
        
        return unique_params
    
    def _execute_batch_solver(self,
                             solver: Solver,
                             params_list: List[Dict[str, Any]]) -> List[Any]:
        """
        Batch execute solver cho nhiều params
        
        Returns:
            List[Any] - List of correct answers (None nếu fail)
        """
        correct_answers = []
        
        for params in params_list:
            try:
                result = self.solver_service.execute(solver, params)
                # Simplify result
                if not isinstance(result, str) and not isinstance(result, Matrix):
                    try:
                        result = simplify(result)
                    except:
                        pass
                correct_answers.append(result)
            except Exception as e:
                print(f"[WARNING] Solver execution failed for params {params}: {e}")
                correct_answers.append(None)
        
        return correct_answers
    
    def _create_batch_questions(self,
                               template: Template,
                               solver: Solver,
                               params_list: List[Dict[str, Any]],
                               correct_answers: List[Any],
                               enriched_list: List[EnrichedContent] = None,
                               question_data_list: List[QuestionData] = None,
                               difficulty: int = 2) -> List[Question]:
        """
        Tạo nhiều questions cùng lúc (Batch version với AI enrichment)
        
        Args:
            enriched_list: List[EnrichedContent] từ AI (có thể None nếu AI fail)
            question_data_list: List[QuestionData] để fallback
        
        Returns:
            List[Question]
        """
        questions = []
        enriched_list = enriched_list or []
        
        for idx, (params, correct_answer) in enumerate(zip(params_list, correct_answers)):
            try:
                # V2: Sử dụng AI enriched content nếu có
                enriched = enriched_list[idx] if idx < len(enriched_list) else None
                ai_enriched = enriched is not None and enriched.ai_used
                
                if enriched and enriched.question_text:
                    # Dùng question_text từ AI
                    question_text = enriched.question_text
                    explanation = enriched.explanation
                    # Dùng distractors từ AI
                    ai_distractors = enriched.distractors
                else:
                    # Fallback: Generate question text từ template
                    question_text = template.question_template or template.math_formula
                    for key, val in params.items():
                        question_text = question_text.replace(f"{{{{{key}}}}}", str(val))
                    explanation = ""
                    # Generate distractors bằng rule-based
                    distractors_data = self.distractor_service.generate(
                        correct_answer=correct_answer,
                        params=params,
                        strategies=solver.distractor_config.strategies,
                        count=solver.distractor_config.count,
                        solver_func=lambda **p: self.solver_service.execute(solver, p)
                    )
                    # Convert to AI format
                    ai_distractors = [
                        {
                            "value": str(d[0]),
                            "text": str(d[0]),
                            "error_type": d[1],
                            "error_description": f"Lỗi {d[1]} thường gặp"
                        }
                        for d in distractors_data
                    ]
                
                # Tạo Answer objects
                answers = {}
                letters = ['A', 'B', 'C', 'D']
                
                # Shuffle để đáp án đúng không luôn ở A
                correct_pos = random.randint(0, min(len(ai_distractors), 3))
                
                distractor_idx = 0
                for i, letter in enumerate(letters):
                    if i == correct_pos:
                        # Đáp án đúng
                        answer_text = str(correct_answer)
                        answer_latex = latex(correct_answer) if not isinstance(correct_answer, str) else answer_text
                        answers[letter] = Answer(
                            text=answer_text,
                            latex=answer_latex,
                            symbolic=str(correct_answer),
                            is_correct=True
                        )
                    else:
                        # Đáp án nhiễu từ AI hoặc rule-based
                        if distractor_idx < len(ai_distractors):
                            distractor = ai_distractors[distractor_idx]
                            distractor_text = distractor.get("text", str(distractor.get("value", "")))
                            distractor_value = distractor.get("value", "")
                            error_type = distractor.get("error_type", "")
                            
                            # V2: Normalize distractor LaTeX để đảm bảo consistency
                            # Nếu distractor_value đã được normalize trong AIEnrichmentService,
                            # sử dụng nó trực tiếp. Nếu không, thử parse.
                            if isinstance(distractor_value, str) and any(c in distractor_value for c in ['\\', '^', '_', '{']):
                                # Có vẻ là LaTeX, sử dụng trực tiếp
                                distractor_latex = distractor_value
                            else:
                                # Thử parse value như một biểu thức SymPy
                                try:
                                    distractor_expr = sp.sympify(str(distractor_value))
                                    distractor_latex = latex(distractor_expr)
                                except:
                                    # Nếu không parse được, dùng text hoặc value
                                    distractor_latex = distractor_text if distractor_text else str(distractor_value)
                            
                            answers[letter] = Answer(
                                text=distractor_text,
                                latex=distractor_latex,
                                symbolic=str(distractor_value),
                                is_correct=False,
                                error_type=error_type
                            )
                            distractor_idx += 1
                        else:
                            # Nếu không đủ distractors, thêm placeholder
                            answers[letter] = Answer(
                                text="Không xác định",
                                latex="",
                                symbolic="",
                                is_correct=False
                            )
                
                # Tìm correct_answer letter
                correct_answer_letter = letters[correct_pos]
                
                # V2: Normalize LaTeX cho question_latex và explanation_latex
                # Đảm bảo LaTeX consistency trong tất cả các phần
                question_latex_normalized = question_text  # Tạm thời, có thể normalize sau nếu cần
                correct_answer_latex_str = latex(correct_answer) if not isinstance(correct_answer, str) else str(correct_answer)
                
                # Normalize explanation LaTeX nếu có
                if explanation and ai_enriched:
                    # Explanation đã được normalize trong AIEnrichmentService
                    explanation_latex_normalized = explanation
                else:
                    explanation_latex_normalized = explanation
                
                # Tạo Question object
                question = Question(
                    template_id=template.id,
                    solver_id=solver.id,
                    param_values=params,
                    param_hash=Question.compute_param_hash(params),
                    question_text=question_text,
                    question_latex=question_latex_normalized,
                    question_html="",
                    answers=answers,
                    correct_answer=correct_answer_letter,
                    correct_value=str(correct_answer),
                    correct_symbolic=str(correct_answer),
                    solution=explanation,  # V2: Dùng explanation từ AI
                    solution_latex=explanation_latex_normalized,
                    solution_steps=[],
                    difficulty=difficulty,
                    quality_score=1.0 if ai_enriched else 0.8,  # AI enriched có quality cao hơn
                    estimated_time=template.estimated_time or 3,
                    status=QuestionStatus.DRAFT,
                    is_active=True,
                    # V2 fields
                    explanation=explanation,
                    explanation_latex=explanation_latex_normalized,
                    ai_enriched=ai_enriched,
                    review_status="AI_GENERATED" if ai_enriched else "DRAFT"
                )
                
                questions.append(question)
            
            except Exception as e:
                logger.warning(f"Error creating question: {e}")
                continue
        
        return questions
    
    def _validate_quality(self, question: Question) -> bool:
        """Validate chất lượng câu hỏi"""
        # Kiểm tra cơ bản
        if not question.question_text or not question.question_text.strip():
            return False
        
        if len(question.answers) < 2:
            return False
        
        if not question.correct_answer:
            return False
        
        # Kiểm tra có đáp án đúng không
        if question.correct_answer not in question.answers:
            return False
        
        if not question.answers[question.correct_answer].is_correct:
            return False
        
        return True


# ============================================================================
# QUESTION SERVICE
# ============================================================================

class QuestionService:
    """Service quản lý câu hỏi"""
    
    def __init__(self, db: Database):
        self.db = db
        self.repo = QuestionRepository(db)
    
    def get(self, question_id: int) -> Optional[Question]:
        """Lấy câu hỏi theo ID"""
        return self.repo.get_by_id(question_id)
    
    def search(self, **kwargs) -> List[Question]:
        """Tìm kiếm câu hỏi"""
        return self.repo.search(**kwargs)
    
    def count(self, **kwargs) -> int:
        """Đếm số câu hỏi"""
        return self.repo.count(**kwargs)
    
    def approve(self, question_id: int, reviewer_id: int = None, notes: str = "") -> bool:
        """Duyệt câu hỏi (V1 - dùng QuestionStatus)"""
        question = self.repo.get_by_id(question_id)
        if not question:
            return False
        
        question.status = QuestionStatus.APPROVED
        question.reviewed_by = reviewer_id
        question.reviewed_at = datetime.now()
        question.review_notes = notes
        self.repo.update(question)
        return True
    
    def reject(self, question_id: int, reviewer_id: int = None, notes: str = "") -> bool:
        """Từ chối câu hỏi (V1 - dùng QuestionStatus)"""
        question = self.repo.get_by_id(question_id)
        if not question:
            return False
        
        question.status = QuestionStatus.REJECTED
        question.reviewed_by = reviewer_id
        question.reviewed_at = datetime.now()
        question.review_notes = notes
        self.repo.update(question)
        return True
    
    # V2: Review workflow methods
    def review_question(self, question_id: int, action: str, reviewer_id: int = None, 
                       notes: str = "") -> bool:
        """
        Review câu hỏi với review_status (V2)
        
        Args:
            question_id: ID của câu hỏi
            action: "approve" | "reject" | "edit"
            reviewer_id: ID của reviewer
            notes: Ghi chú review
        
        Returns:
            bool: True nếu thành công
        """
        question = self.repo.get_by_id(question_id)
        if not question:
            return False
        
        if action == "approve":
            question.review_status = ReviewStatus.VERIFIED.value
            question.status = QuestionStatus.APPROVED
        elif action == "reject":
            question.review_status = ReviewStatus.REJECTED.value
            question.status = QuestionStatus.REJECTED
        elif action == "edit":
            question.review_status = ReviewStatus.DRAFT.value
            question.status = QuestionStatus.DRAFT
        else:
            raise ValueError(f"Invalid action: {action}. Must be 'approve', 'reject', or 'edit'")
        
        question.reviewed_by = reviewer_id
        question.reviewed_at = datetime.now()
        question.review_notes = notes
        self.repo.update(question)
        return True
    
    def get_pending_review(self, limit: int = 50, offset: int = 0) -> List[Question]:
        """
        Lấy danh sách câu hỏi cần review (V2)
        
        Args:
            limit: Số lượng tối đa
            offset: Offset cho pagination
        
        Returns:
            List[Question]: Danh sách câu hỏi có review_status = AI_GENERATED
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM questions 
                WHERE review_status = 'AI_GENERATED' 
                AND is_active = 1
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return [self.repo._row_to_question(row) for row in cursor.fetchall()]
    
    def count_pending_review(self) -> int:
        """Đếm số câu hỏi cần review"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM questions 
                WHERE review_status = 'AI_GENERATED' 
                AND is_active = 1
            """)
            return cursor.fetchone()[0]
    
    def archive(self, question_id: int) -> bool:
        """Archive câu hỏi"""
        return self.repo.update_status(question_id, QuestionStatus.ARCHIVED)
    
    def delete(self, question_id: int) -> bool:
        """Xóa mềm câu hỏi"""
        return self.repo.delete(question_id)


# ============================================================================
# EXAM SERVICE
# ============================================================================

class ExamService:
    """Service quản lý đề thi"""
    
    def __init__(self, db: Database):
        self.db = db
        self.repo = ExamRepository(db)
        self.question_repo = QuestionRepository(db)
    
    def create(self,
               name: str,
               code: str = None,
               description: str = "",
               config: ExamConfig = None,
               created_by: int = None) -> Exam:
        """Tạo đề thi mới"""
        exam = Exam(
            code=code or str(uuid.uuid4())[:8].upper(),
            name=name,
            description=description,
            config=config or ExamConfig(),
            created_by=created_by
        )
        return self.repo.create(exam)
    
    def get(self, exam_id: int) -> Optional[Exam]:
        """Lấy đề thi"""
        return self.repo.get_by_id(exam_id)
    
    def get_by_code(self, code: str) -> Optional[Exam]:
        """Lấy đề thi theo code"""
        return self.repo.get_by_code(code)
    
    def list(self, status: ExamStatus = None) -> List[Exam]:
        """Liệt kê đề thi"""
        return self.repo.get_all(status)
    
    def add_questions(self, exam_id: int, question_ids: List[int],
                      shuffle_answers: bool = True) -> int:
        """Thêm câu hỏi vào đề thi"""
        exam = self.repo.get_by_id(exam_id, load_questions=True)
        if not exam:
            raise ValueError(f"Exam {exam_id} không tồn tại")
        
        start_position = len(exam.questions) + 1
        added = 0
        
        for i, qid in enumerate(question_ids):
            # Kiểm tra question tồn tại
            question = self.question_repo.get_by_id(qid)
            if not question:
                continue
            
            # Tạo answer mapping (xáo trộn đáp án)
            answer_mapping = {}
            if shuffle_answers:
                letters = ['A', 'B', 'C', 'D']
                shuffled = letters.copy()
                random.shuffle(shuffled)
                answer_mapping = {orig: new for orig, new in zip(letters, shuffled)}
            
            try:
                self.repo.add_question(
                    exam_id=exam_id,
                    question_id=qid,
                    position=start_position + i,
                    answer_mapping=answer_mapping
                )
                self.question_repo.increment_usage(qid)
                added += 1
            except Exception as e:
                # Bỏ qua nếu đã tồn tại
                continue
        
        return added
    
    def auto_select_questions(self,
                              exam_id: int,
                              total: int = None,
                              template_ids: List[int] = None,
                              category_ids: List[int] = None,
                              difficulty_distribution: Dict[int, int] = None,
                              exclude_exam_ids: List[int] = None) -> List[Question]:
        """Tự động chọn câu hỏi theo tiêu chí"""
        exam = self.repo.get_by_id(exam_id)
        if not exam:
            raise ValueError(f"Exam {exam_id} không tồn tại")
        
        if total is None:
            total = exam.config.total_questions
        
        if difficulty_distribution is None:
            difficulty_distribution = exam.config.difficulty_distribution
        
        selected = []
        selected_ids = set()
        
        if difficulty_distribution:
            # Chọn theo phân bố độ khó
            for difficulty, count in difficulty_distribution.items():
                questions = self.question_repo.search(
                    difficulty=int(difficulty),
                    status=QuestionStatus.APPROVED,
                    exclude_exam_ids=exclude_exam_ids,
                    order_by="usage_count ASC, RANDOM()",
                    limit=count * 2
                )
                
                if template_ids:
                    questions = [q for q in questions if q.template_id in template_ids]
                if category_ids:
                    # Cần join với template để filter theo category
                    pass
                
                for q in questions[:count]:
                    if q.id not in selected_ids:
                        selected.append(q)
                        selected_ids.add(q.id)
        else:
            # Chọn ngẫu nhiên
            questions = self.question_repo.search(
                status=QuestionStatus.APPROVED,
                exclude_exam_ids=exclude_exam_ids,
                order_by="RANDOM()",
                limit=total * 2
            )
            
            if template_ids:
                questions = [q for q in questions if q.template_id in template_ids]
            
            selected = questions[:total]
        
        return selected
    
    def shuffle(self, exam_id: int) -> bool:
        """Xáo trộn thứ tự câu hỏi"""
        exam = self.repo.get_by_id(exam_id, load_questions=True)
        if not exam or not exam.questions:
            return False
        
        # Lấy danh sách question_ids và xáo trộn
        question_ids = [eq.question_id for eq in exam.questions]
        random.shuffle(question_ids)
        
        # Xóa và thêm lại
        self.repo.clear_questions(exam_id)
        self.add_questions(exam_id, question_ids)
        
        return True
    
    def publish(self, exam_id: int) -> bool:
        """Publish đề thi"""
        return self.repo.publish(exam_id)
    
    def delete(self, exam_id: int) -> bool:
        """Xóa đề thi"""
        return self.repo.delete(exam_id)


# ============================================================================
# CATEGORY SERVICE
# ============================================================================

class CategoryService:
    """Service quản lý chủ đề"""
    
    def __init__(self, db: Database):
        self.db = db
        self.repo = CategoryRepository(db)
    
    def create(self, name: str, description: str = "", 
               parent_id: int = None) -> Category:
        """Tạo category"""
        # Tính level
        level = 0
        if parent_id:
            parent = self.repo.get_by_id(parent_id)
            if parent:
                level = parent.level + 1
        
        category = Category(
            name=name,
            description=description,
            parent_id=parent_id,
            level=level
        )
        return self.repo.create(category)
    
    def get(self, category_id: int) -> Optional[Category]:
        """Lấy category"""
        return self.repo.get_by_id(category_id)
    
    def list(self) -> List[Category]:
        """Liệt kê categories"""
        return self.repo.get_all()
    
    def get_tree(self) -> List[Category]:
        """Lấy categories dạng cây"""
        all_cats = self.repo.get_all()
        
        # Tạo mapping
        by_id = {c.id: c for c in all_cats}
        roots = []
        
        for cat in all_cats:
            if cat.parent_id is None:
                roots.append(cat)
            else:
                parent = by_id.get(cat.parent_id)
                if parent:
                    parent.children.append(cat)
        
        return roots
    
    def delete(self, category_id: int) -> bool:
        """Xóa category"""
        return self.repo.delete(category_id)
