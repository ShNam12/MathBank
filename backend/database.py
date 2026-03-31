"""
database.py - Quản lý lưu trữ dữ liệu với SQLite
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path

from models import (
    Subject, Category, Template, ParamDefinition, Solver,
    Question, Answer, Exam, ExamQuestion, ExamConfig,
    QuestionStatus, ExamStatus, DistractorConfig, TestCase,
    GenerationLog
)


class Database:
    """Quản lý kết nối và thao tác với database SQLite"""
    
    def __init__(self, db_path: str = "question_bank.db"):
        self.db_path = db_path
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager cho database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_database(self):
        """Khởi tạo schema database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # ================================================================
            # BẢNG SUBJECTS (Môn học)
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subjects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100) NOT NULL,
                    code VARCHAR(20) UNIQUE,
                    description TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # ================================================================
            # BẢNG CATEGORY
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT DEFAULT '',
                    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                    level INTEGER DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Thêm cột subject_id vào categories nếu chưa có (migration)
            try:
                cursor.execute("ALTER TABLE categories ADD COLUMN subject_id INTEGER REFERENCES subjects(id)")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise  # Re-raise nếu không phải lỗi duplicate column
                pass  # Cột đã tồn tại
            
            # ================================================================
            # BẢNG TEMPLATE
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
                    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    description TEXT DEFAULT '',
                    math_formula TEXT NOT NULL,
                    question_template TEXT DEFAULT '',
                    param_schema JSON NOT NULL,
                    difficulty_base INTEGER DEFAULT 3,
                    estimated_time INTEGER DEFAULT 3,
                    tags JSON DEFAULT '[]',
                    hints JSON DEFAULT '[]',
                    is_active BOOLEAN DEFAULT 1,
                    is_verified BOOLEAN DEFAULT 0,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Thêm cột subject_id vào templates nếu chưa có (migration)
            try:
                cursor.execute("ALTER TABLE templates ADD COLUMN subject_id INTEGER REFERENCES subjects(id)")
            except sqlite3.OperationalError:
                pass  # Cột đã tồn tại
            
            conn.commit()
            
            # ================================================================
            # BẢNG SOLVER
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS solvers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
                    version VARCHAR(20) NOT NULL,
                    language VARCHAR(20) DEFAULT 'python',
                    code TEXT NOT NULL,
                    entry_function VARCHAR(50) DEFAULT 'solve',
                    dependencies JSON DEFAULT '[]',
                    distractor_config JSON DEFAULT '{}',
                    solution_template TEXT DEFAULT '',
                    test_cases JSON DEFAULT '[]',
                    is_active BOOLEAN DEFAULT 1,
                    is_validated BOOLEAN DEFAULT 0,
                    validation_log TEXT DEFAULT '',
                    last_validated_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(template_id, version)
                )
            """)
            
            # ================================================================
            # BẢNG QUESTION
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
                    solver_id INTEGER REFERENCES solvers(id) ON DELETE SET NULL,
                    param_values JSON NOT NULL,
                    param_hash VARCHAR(64) NOT NULL,
                    question_text TEXT NOT NULL,
                    question_latex TEXT DEFAULT '',
                    question_html TEXT DEFAULT '',
                    answers JSON NOT NULL,
                    correct_answer CHAR(1) NOT NULL,
                    correct_value TEXT,
                    correct_symbolic TEXT DEFAULT '',
                    solution TEXT DEFAULT '',
                    solution_latex TEXT DEFAULT '',
                    solution_steps JSON DEFAULT '[]',
                    difficulty INTEGER DEFAULT 3,
                    quality_score FLOAT DEFAULT 0,
                    estimated_time INTEGER DEFAULT 3,
                    status VARCHAR(20) DEFAULT 'draft',
                    is_active BOOLEAN DEFAULT 1,
                    reviewed_by INTEGER,
                    reviewed_at TIMESTAMP,
                    review_notes TEXT DEFAULT '',
                    usage_count INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    correct_rate FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(template_id, param_hash)
                )
            """)
            
            # ================================================================
            # BẢNG EXAM
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(50) UNIQUE,
                    name VARCHAR(200) NOT NULL,
                    description TEXT DEFAULT '',
                    config JSON DEFAULT '{}',
                    status VARCHAR(20) DEFAULT 'draft',
                    is_published BOOLEAN DEFAULT 0,
                    published_at TIMESTAMP,
                    created_by INTEGER,
                    times_used INTEGER DEFAULT 0,
                    average_score FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # ================================================================
            # BẢNG EXAM_QUESTIONS (Liên kết N-M)
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exam_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
                    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    points FLOAT DEFAULT 1.0,
                    answer_mapping JSON DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(exam_id, question_id),
                    UNIQUE(exam_id, position)
                )
            """)
            
            # ================================================================
            # BẢNG GENERATION_LOG
            # ================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS generation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER REFERENCES templates(id) ON DELETE SET NULL,
                    solver_id INTEGER REFERENCES solvers(id) ON DELETE SET NULL,
                    batch_id VARCHAR(50) DEFAULT '',
                    param_values JSON DEFAULT '{}',
                    status VARCHAR(20) NOT NULL,
                    question_id INTEGER REFERENCES questions(id) ON DELETE SET NULL,
                    error_message TEXT DEFAULT '',
                    execution_time FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # ================================================================
            # INDEXES
            # ================================================================
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(category_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_code ON templates(code)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_solvers_template ON solvers(template_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_template ON questions(template_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_param_hash ON questions(param_hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_exam_questions_exam ON exam_questions(exam_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_generation_logs_batch ON generation_logs(batch_id)")
            
            # V2: Migration - Thêm V2 columns nếu chưa có
            cursor.execute("PRAGMA table_info(questions)")
            existing_columns = [row[1] for row in cursor.fetchall()]
            
            # Thêm explanation column
            if 'explanation' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE questions ADD COLUMN explanation TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass  # Column có thể đã tồn tại
            
            # Thêm explanation_latex column
            if 'explanation_latex' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE questions ADD COLUMN explanation_latex TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    pass  # Column có thể đã tồn tại
            
            # Thêm ai_enriched column
            if 'ai_enriched' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE questions ADD COLUMN ai_enriched BOOLEAN DEFAULT 0")
                except sqlite3.OperationalError:
                    pass  # Column có thể đã tồn tại
            
            # Thêm review_status column
            if 'review_status' not in existing_columns:
                try:
                    cursor.execute("ALTER TABLE questions ADD COLUMN review_status VARCHAR(20) DEFAULT 'DRAFT'")
                    # Cập nhật review_status cho questions cũ
                    cursor.execute("UPDATE questions SET review_status = 'DRAFT' WHERE review_status IS NULL OR review_status = ''")
                except sqlite3.OperationalError:
                    pass  # Column có thể đã tồn tại
            
            # V2: Indexes cho AI enrichment và review workflow
            # Refresh existing_columns sau khi thêm columns
            cursor.execute("PRAGMA table_info(questions)")
            existing_columns_after = [row[1] for row in cursor.fetchall()]
            
            if 'review_status' in existing_columns_after:
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_review_status ON questions(review_status)")
                except sqlite3.OperationalError:
                    pass  # Index có thể đã tồn tại
            
            if 'ai_enriched' in existing_columns_after:
                try:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_questions_ai_enriched ON questions(ai_enriched)")
                except sqlite3.OperationalError:
                    pass  # Index có thể đã tồn tại


# ============================================================================
# REPOSITORY BASE CLASS
# ============================================================================

class BaseRepository:
    """Base class cho các repository"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Thực thi query và trả về cursor"""
        with self.db.get_connection() as conn:
            return conn.execute(query, params)

# ============================================================================
# SUBJECT REPOSITORY
# ============================================================================

class SubjectRepository(BaseRepository):
    """Repository cho Subject"""
    
    def create(self, subject: Subject) -> Subject:
        """Tạo subject mới"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO subjects (name, code, description, is_active)
                VALUES (?, ?, ?, ?)
            """, (subject.name, subject.code, subject.description, subject.is_active))
            subject.id = cursor.lastrowid
        return subject
    
    def get_by_id(self, id: int) -> Optional[Subject]:
        """Lấy subject theo ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subjects WHERE id = ?", (id,))
            row = cursor.fetchone()
            return self._row_to_subject(row) if row else None
    
    def get_all(self, active_only: bool = True) -> List[Subject]:
        """Lấy tất cả subjects"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute("SELECT * FROM subjects WHERE is_active = 1 ORDER BY name")
            else:
                cursor.execute("SELECT * FROM subjects ORDER BY name")
            return [self._row_to_subject(row) for row in cursor.fetchall()]
            
    def update(self, subject: Subject) -> Subject:
        """Cập nhật subject"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE subjects SET
                    name = ?, code = ?, description = ?,
                    is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (subject.name, subject.code, subject.description, subject.is_active, subject.id))
        return subject
    
    def delete(self, id: int) -> bool:
        """Xóa mềm subject"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE subjects SET is_active = 0 WHERE id = ?", (id,))
            return cursor.rowcount > 0
            
    def _row_to_subject(self, row: sqlite3.Row) -> Subject:
        try:
            created_at = datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.now()
        except (KeyError, ValueError):
            created_at = datetime.now()
        
        try:
            updated_at = datetime.fromisoformat(row['updated_at']) if row['updated_at'] else datetime.now()
        except (KeyError, ValueError):
            updated_at = datetime.now()
        
        return Subject(
            id=row['id'],
            name=row['name'],
            code=row['code'],
            description=row['description'] or '',
            is_active=bool(row['is_active']),
            created_at=created_at,
            updated_at=updated_at
        )
# ============================================================================
# CATEGORY REPOSITORY
# ============================================================================

class CategoryRepository(BaseRepository):
    """Repository cho Category"""
    
    def create(self, category: Category) -> Category:
        """Tạo category mới"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO categories (subject_id, name, description, parent_id, level, sort_order, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                category.subject_id, category.name, category.description, category.parent_id,
                category.level, category.sort_order, category.is_active
            ))
            category.id = cursor.lastrowid
        return category
    
    def get_by_id(self, id: int) -> Optional[Category]:
        """Lấy category theo ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories WHERE id = ?", (id,))
            row = cursor.fetchone()
            return self._row_to_category(row) if row else None
    
    def get_all(self, active_only: bool = True) -> List[Category]:
        """Lấy tất cả categories"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute("SELECT * FROM categories WHERE is_active = 1 ORDER BY level, sort_order")
            else:
                cursor.execute("SELECT * FROM categories ORDER BY level, sort_order")
            return [self._row_to_category(row) for row in cursor.fetchall()]
    
    def get_by_parent(self, parent_id: Optional[int]) -> List[Category]:
        """Lấy categories theo parent"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if parent_id is None:
                cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL AND is_active = 1 ORDER BY sort_order")
            else:
                cursor.execute("SELECT * FROM categories WHERE parent_id = ? AND is_active = 1 ORDER BY sort_order", (parent_id,))
            return [self._row_to_category(row) for row in cursor.fetchall()]
    
    def update(self, category: Category) -> Category:
        """Cập nhật category"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE categories SET
                    subject_id = ?, name = ?, description = ?, parent_id = ?, level = ?,
                    sort_order = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                category.subject_id, category.name, category.description, category.parent_id,
                category.level, category.sort_order, category.is_active, category.id
            ))
        return category
    
    def delete(self, id: int) -> bool:
        """Xóa mềm category"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (id,))
            return cursor.rowcount > 0
    
    def get_by_subject(self, subject_id: int, active_only: bool = True) -> List[Category]:
        """Lấy tất cả categories của một subject"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute("""
                    SELECT * FROM categories 
                    WHERE subject_id = ? AND is_active = 1 
                    ORDER BY level, sort_order
                """, (subject_id,))
            else:
                cursor.execute("""
                    SELECT * FROM categories 
                    WHERE subject_id = ? 
                    ORDER BY level, sort_order
                """, (subject_id,))
            return [self._row_to_category(row) for row in cursor.fetchall()]
    
    def get_chapters_by_subject(self, subject_id: int) -> List[Category]:
        """Lấy tất cả chương (level=1) của một subject"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM categories 
                WHERE subject_id = ? AND level = 1 AND is_active = 1 
                ORDER BY sort_order
            """, (subject_id,))
            return [self._row_to_category(row) for row in cursor.fetchall()]
    
    def get_sections_by_chapter(self, chapter_id: int) -> List[Category]:
        """Lấy tất cả mục (level=2+) của một chương"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM categories 
                WHERE parent_id = ? AND is_active = 1 
                ORDER BY sort_order
            """, (chapter_id,))
            return [self._row_to_category(row) for row in cursor.fetchall()]
    
    def get_all_children_recursive(self, category_id: int) -> List[Category]:
        """Lấy tất cả categories con (đệ quy)"""
        result = []
        children = self.get_by_parent(category_id)
        for child in children:
            result.append(child)
            result.extend(self.get_all_children_recursive(child.id))
        return result
    
    def _row_to_category(self, row: sqlite3.Row) -> Category:
        try:
            subject_id = row['subject_id']
        except KeyError:
            subject_id = None
        
        try:
            created_at = datetime.fromisoformat(row['created_at']) if row['created_at'] else datetime.now()
        except (KeyError, ValueError):
            created_at = datetime.now()
        
        return Category(
            id=row['id'],
            subject_id=subject_id,
            name=row['name'],
            description=row['description'] or '',
            parent_id=row['parent_id'],
            level=row['level'],
            sort_order=row['sort_order'],
            is_active=bool(row['is_active']),
            created_at=created_at
        )


# ============================================================================
# TEMPLATE REPOSITORY
# ============================================================================

class TemplateRepository(BaseRepository):
    """Repository cho Template"""
    
    def create(self, template: Template) -> Template:
        """Tạo template mới"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            param_schema_json = json.dumps({
                name: p.to_dict() for name, p in template.param_schema.items()
            })
            
            cursor.execute("""
                INSERT INTO templates (
                    subject_id, category_id, code, name, description, math_formula,
                    question_template, param_schema, difficulty_base, estimated_time,
                    tags, hints, is_active, is_verified, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                template.subject_id, template.category_id, template.code, template.name,
                template.description, template.math_formula, template.question_template,
                param_schema_json, template.difficulty_base, template.estimated_time,
                json.dumps(template.tags), json.dumps(template.hints),
                template.is_active, template.is_verified, template.created_by
            ))
            template.id = cursor.lastrowid
        return template
    
    def get_by_id(self, id: int) -> Optional[Template]:
        """Lấy template theo ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM templates WHERE id = ?", (id,))
            row = cursor.fetchone()
            return self._row_to_template(row) if row else None
    
    def get_by_code(self, code: str) -> Optional[Template]:
        """Lấy template theo code"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM templates WHERE code = ?", (code,))
            row = cursor.fetchone()
            return self._row_to_template(row) if row else None
    
    def get_all(self, category_id: Optional[int] = None, active_only: bool = True) -> List[Template]:
        """Lấy danh sách templates"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if active_only:
                conditions.append("is_active = 1")
            if category_id is not None:
                conditions.append("category_id = ?")
                params.append(category_id)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            cursor.execute(f"SELECT * FROM templates{where_clause} ORDER BY name", params)
            
            return [self._row_to_template(row) for row in cursor.fetchall()]
    
    def search(self, query: str, limit: int = 50) -> List[Template]:
        """Tìm kiếm templates"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT * FROM templates
                WHERE is_active = 1 AND (
                    name LIKE ? OR code LIKE ? OR description LIKE ? OR tags LIKE ?
                )
                ORDER BY name LIMIT ?
            """, (search_pattern, search_pattern, search_pattern, search_pattern, limit))
            return [self._row_to_template(row) for row in cursor.fetchall()]
    
    def update(self, template: Template) -> Template:
        """Cập nhật template"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            param_schema_json = json.dumps({
                name: p.to_dict() for name, p in template.param_schema.items()
            })
            
            cursor.execute("""
                UPDATE templates SET
                    subject_id = ?, category_id = ?, name = ?, description = ?, math_formula = ?,
                    question_template = ?, param_schema = ?, difficulty_base = ?,
                    estimated_time = ?, tags = ?, hints = ?, is_active = ?,
                    is_verified = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                template.subject_id, template.category_id, template.name, template.description,
                template.math_formula, template.question_template, param_schema_json,
                template.difficulty_base, template.estimated_time,
                json.dumps(template.tags), json.dumps(template.hints),
                template.is_active, template.is_verified, template.id
            ))
        return template
    
    def delete(self, id: int) -> bool:
        """Xóa template khỏi database (hard delete)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Xóa thực sự khỏi database
            # Các bản ghi liên quan (questions, solvers) sẽ tự động bị xóa nhờ ON DELETE CASCADE
            cursor.execute("DELETE FROM templates WHERE id = ?", (id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def _row_to_template(self, row: sqlite3.Row) -> Template:
        param_schema_data = json.loads(row['param_schema']) if row['param_schema'] else {}
        param_schema = {
            name: ParamDefinition.from_dict(name, p)
            for name, p in param_schema_data.items()
        }
        
        return Template(
            id=row['id'],
            category_id=row['category_id'],
            code=row['code'],
            name=row['name'],
            description=row['description'] or '',
            math_formula=row['math_formula'],
            question_template=row['question_template'] or '',
            param_schema=param_schema,
            difficulty_base=row['difficulty_base'],
            estimated_time=row['estimated_time'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            hints=json.loads(row['hints']) if row['hints'] else [],
            is_active=bool(row['is_active']),
            is_verified=bool(row['is_verified']),
            created_by=row['created_by']
        )


# ============================================================================
# SOLVER REPOSITORY
# ============================================================================

class SolverRepository(BaseRepository):
    """Repository cho Solver"""
    
    def create(self, solver: Solver) -> Solver:
        """Tạo solver mới"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            distractor_config_json = json.dumps({
                "strategies": solver.distractor_config.strategies,
                "count": solver.distractor_config.count,
                "validate_distinctness": solver.distractor_config.validate_distinctness
            })
            
            test_cases_json = json.dumps([tc.to_dict() for tc in solver.test_cases])
            
            cursor.execute("""
                INSERT INTO solvers (
                    template_id, version, language, code, entry_function,
                    dependencies, distractor_config, solution_template,
                    test_cases, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                solver.template_id, solver.version, solver.language,
                solver.code, solver.entry_function, json.dumps(solver.dependencies),
                distractor_config_json, solver.solution_template,
                test_cases_json, solver.is_active
            ))
            solver.id = cursor.lastrowid
        return solver
    
    def get_by_id(self, id: int) -> Optional[Solver]:
        """Lấy solver theo ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM solvers WHERE id = ?", (id,))
            row = cursor.fetchone()
            return self._row_to_solver(row) if row else None
    
    def get_active_for_template(self, template_id: int) -> Optional[Solver]:
        """Lấy solver active của template"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM solvers
                WHERE template_id = ? AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
            """, (template_id,))
            row = cursor.fetchone()
            return self._row_to_solver(row) if row else None
    
    def get_all_for_template(self, template_id: int) -> List[Solver]:
        """Lấy tất cả solver của template"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM solvers WHERE template_id = ? ORDER BY version DESC
            """, (template_id,))
            return [self._row_to_solver(row) for row in cursor.fetchall()]
    
    def update(self, solver: Solver) -> Solver:
        """Cập nhật solver"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            distractor_config_json = json.dumps({
                "strategies": solver.distractor_config.strategies,
                "count": solver.distractor_config.count,
                "validate_distinctness": solver.distractor_config.validate_distinctness
            })
            test_cases_json = json.dumps([tc.to_dict() for tc in solver.test_cases])
            
            cursor.execute("""
                UPDATE solvers SET
                    code = ?, entry_function = ?, dependencies = ?,
                    distractor_config = ?, solution_template = ?, test_cases = ?,
                    is_active = ?, is_validated = ?, validation_log = ?,
                    last_validated_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                solver.code, solver.entry_function, json.dumps(solver.dependencies),
                distractor_config_json, solver.solution_template, test_cases_json,
                solver.is_active, solver.is_validated, solver.validation_log,
                solver.last_validated_at, solver.id
            ))
        return solver
    
    def set_validated(self, id: int, is_validated: bool, log: str = "") -> bool:
        """Cập nhật trạng thái validated"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE solvers SET
                    is_validated = ?, validation_log = ?,
                    last_validated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (is_validated, log, id))
            return cursor.rowcount > 0
    
    def _row_to_solver(self, row: sqlite3.Row) -> Solver:
        distractor_data = json.loads(row['distractor_config']) if row['distractor_config'] else {}
        test_cases_data = json.loads(row['test_cases']) if row['test_cases'] else []
        
        return Solver(
            id=row['id'],
            template_id=row['template_id'],
            version=row['version'],
            language=row['language'],
            code=row['code'],
            entry_function=row['entry_function'] or 'solve',
            dependencies=json.loads(row['dependencies']) if row['dependencies'] else [],
            distractor_config=DistractorConfig(
                strategies=distractor_data.get('strategies', []),
                count=distractor_data.get('count', 3),
                validate_distinctness=distractor_data.get('validate_distinctness', True)
            ),
            solution_template=row['solution_template'] or '',
            test_cases=[
                TestCase(
                    input_params=tc.get('input', {}),
                    expected_output=tc.get('expected', ''),
                    description=tc.get('description', '')
                )
                for tc in test_cases_data
            ],
            is_active=bool(row['is_active']),
            is_validated=bool(row['is_validated']),
            validation_log=row['validation_log'] or ''
        )


# ============================================================================
# QUESTION REPOSITORY
# ============================================================================

class QuestionRepository(BaseRepository):
    """Repository cho Question"""
    
    def create(self, question: Question) -> Question:
        """Tạo question mới"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            answers_json = json.dumps({
                letter: ans.to_dict() for letter, ans in question.answers.items()
            })
            
            # V2: Include new fields (explanation, explanation_latex, ai_enriched, review_status)
            cursor.execute("""
                INSERT INTO questions (
                    template_id, solver_id, param_values, param_hash,
                    question_text, question_latex, question_html,
                    answers, correct_answer, correct_value, correct_symbolic,
                    solution, solution_latex, solution_steps,
                    difficulty, quality_score, estimated_time, status,
                    explanation, explanation_latex, ai_enriched, review_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                question.template_id, question.solver_id,
                json.dumps(question.param_values), question.param_hash,
                question.question_text, question.question_latex, question.question_html,
                answers_json, question.correct_answer,
                str(question.correct_value) if question.correct_value else '',
                question.correct_symbolic,
                question.solution, question.solution_latex,
                json.dumps(question.solution_steps),
                question.difficulty, question.quality_score, question.estimated_time,
                question.status.value if isinstance(question.status, QuestionStatus) else question.status,
                # V2 fields
                getattr(question, 'explanation', '') or '',
                getattr(question, 'explanation_latex', '') or '',
                1 if getattr(question, 'ai_enriched', False) else 0,
                getattr(question, 'review_status', None) or 'DRAFT'
            ))
            question.id = cursor.lastrowid
        return question
    
    def get_by_id(self, id: int) -> Optional[Question]:
        """Lấy question theo ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions WHERE id = ?", (id,))
            row = cursor.fetchone()
            return self._row_to_question(row) if row else None
    
    def get_by_ids(self, ids: List[int]) -> List[Question]:
        """Lấy nhiều questions theo IDs"""
        if not ids:
            return []
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(ids))
            cursor.execute(f"SELECT * FROM questions WHERE id IN ({placeholders})", ids)
            return [self._row_to_question(row) for row in cursor.fetchall()]
    
    def exists(self, template_id: int, param_hash: str) -> bool:
        """Kiểm tra question đã tồn tại chưa"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM questions WHERE template_id = ? AND param_hash = ?",
                (template_id, param_hash)
            )
            return cursor.fetchone() is not None
    
    def search(self,
               template_id: Optional[int] = None,
               category_id: Optional[int] = None,
               difficulty: Optional[int] = None,
               difficulty_range: Optional[Tuple[int, int]] = None,
               status: Optional[QuestionStatus] = None,
               exclude_ids: Optional[List[int]] = None,
               exclude_exam_ids: Optional[List[int]] = None,
               active_only: bool = True,
               order_by: str = "created_at DESC",
               limit: int = 100,
               offset: int = 0) -> List[Question]:
        """Tìm kiếm questions với nhiều tiêu chí"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if active_only:
                conditions.append("q.is_active = 1")
            if template_id is not None:
                conditions.append("q.template_id = ?")
                params.append(template_id)
            if category_id is not None:
                conditions.append("q.template_id IN (SELECT id FROM templates WHERE category_id = ?)")
                params.append(category_id)
            if difficulty is not None:
                conditions.append("q.difficulty = ?")
                params.append(difficulty)
            if difficulty_range:
                conditions.append("q.difficulty BETWEEN ? AND ?")
                params.extend(difficulty_range)
            if status is not None:
                conditions.append("q.status = ?")
                params.append(status.value if isinstance(status, QuestionStatus) else status)
            if exclude_ids:
                placeholders = ','.join(['?'] * len(exclude_ids))
                conditions.append(f"q.id NOT IN ({placeholders})")
                params.extend(exclude_ids)
            if exclude_exam_ids:
                placeholders = ','.join(['?'] * len(exclude_exam_ids))
                conditions.append(f"""
                    q.id NOT IN (
                        SELECT question_id FROM exam_questions WHERE exam_id IN ({placeholders})
                    )
                """)
                params.extend(exclude_exam_ids)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            query = f"""
                SELECT q.* FROM questions q
                {where_clause}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [self._row_to_question(row) for row in cursor.fetchall()]
    
    def count(self,
              template_id: Optional[int] = None,
              status: Optional[QuestionStatus] = None,
              active_only: bool = True) -> int:
        """Đếm số questions"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if active_only:
                conditions.append("is_active = 1")
            if template_id is not None:
                conditions.append("template_id = ?")
                params.append(template_id)
            if status is not None:
                conditions.append("status = ?")
                params.append(status.value if isinstance(status, QuestionStatus) else status)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            cursor.execute(f"SELECT COUNT(*) FROM questions{where_clause}", params)
            return cursor.fetchone()[0]
    
    def update(self, question: Question) -> Question:
        """Cập nhật question"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            answers_json = json.dumps({
                letter: ans.to_dict() for letter, ans in question.answers.items()
            })
            
            # V2: Include new fields in update
            cursor.execute("""
                UPDATE questions SET
                    question_text = ?, question_latex = ?, answers = ?,
                    correct_answer = ?, solution = ?, solution_latex = ?,
                    difficulty = ?, quality_score = ?, status = ?,
                    is_active = ?, reviewed_by = ?, reviewed_at = ?,
                    review_notes = ?, 
                    explanation = ?, explanation_latex = ?, 
                    ai_enriched = ?, review_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                question.question_text, question.question_latex, answers_json,
                question.correct_answer, question.solution, question.solution_latex,
                question.difficulty, question.quality_score,
                question.status.value if isinstance(question.status, QuestionStatus) else question.status,
                question.is_active, question.reviewed_by, question.reviewed_at,
                question.review_notes,
                # V2 fields
                getattr(question, 'explanation', '') or '',
                getattr(question, 'explanation_latex', '') or '',
                1 if getattr(question, 'ai_enriched', False) else 0,
                getattr(question, 'review_status', None) or 'DRAFT',
                question.id
            ))
        return question
    
    def update_status(self, id: int, status: QuestionStatus) -> bool:
        """Cập nhật trạng thái"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE questions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status.value, id)
            )
            return cursor.rowcount > 0
    
    def increment_usage(self, question_id: int) -> bool:
        """Tăng usage_count"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE questions SET
                    usage_count = usage_count + 1,
                    last_used_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (question_id,))
            return cursor.rowcount > 0
    
    def delete(self, id: int) -> bool:
        """Xóa mềm question"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE questions SET is_active = 0 WHERE id = ?", (id,))
            return cursor.rowcount > 0
    
    def hard_delete(self, id: int) -> bool:
        """Xóa trực tiếp question khỏi database (hard delete)"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM questions WHERE id = ?", (id,))
            return cursor.rowcount > 0
    
    def _row_to_question(self, row: sqlite3.Row) -> Question:
        answers_data = json.loads(row['answers']) if row['answers'] else {}
        answers = {
            letter: Answer(
                text=ans.get('text', ''),
                latex=ans.get('latex', ''),
                symbolic=ans.get('symbolic', ''),
                is_correct=ans.get('is_correct', False),
                error_type=ans.get('error_type')
            )
            for letter, ans in answers_data.items()
        }
        
        # V2: Parse new fields (with fallback for backward compatibility)
        # sqlite3.Row không có method .get(), phải dùng row['key'] với kiểm tra
        explanation = row['explanation'] if 'explanation' in row.keys() else ''
        explanation_latex = row['explanation_latex'] if 'explanation_latex' in row.keys() else ''
        ai_enriched = bool(row['ai_enriched']) if 'ai_enriched' in row.keys() else False
        review_status = row['review_status'] if 'review_status' in row.keys() else 'DRAFT'
        
        return Question(
            id=row['id'],
            template_id=row['template_id'],
            solver_id=row['solver_id'],
            param_values=json.loads(row['param_values']) if row['param_values'] else {},
            param_hash=row['param_hash'],
            question_text=row['question_text'],
            question_latex=row['question_latex'] or '',
            question_html=row['question_html'] or '',
            answers=answers,
            correct_answer=row['correct_answer'],
            correct_value=row['correct_value'],
            correct_symbolic=row['correct_symbolic'] or '',
            solution=row['solution'] or '',
            solution_latex=row['solution_latex'] or '',
            solution_steps=json.loads(row['solution_steps']) if row['solution_steps'] else [],
            difficulty=row['difficulty'],
            quality_score=row['quality_score'] or 0.0,
            # V2 fields
            explanation=explanation,
            explanation_latex=explanation_latex,
            ai_enriched=ai_enriched,
            review_status=review_status,
            estimated_time=row['estimated_time'],
            status=QuestionStatus(row['status']),
            is_active=bool(row['is_active']),
            usage_count=row['usage_count'],
            last_used_at=datetime.fromisoformat(row['last_used_at']) if row['last_used_at'] else None,

        )


# ============================================================================
# EXAM REPOSITORY
# ============================================================================

class ExamRepository(BaseRepository):
    """Repository cho Exam"""
    
    def create(self, exam: Exam) -> Exam:
        """Tạo exam mới"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO exams (code, name, description, config, status, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                exam.code, exam.name, exam.description,
                json.dumps(exam.config.to_dict()),
                exam.status.value if isinstance(exam.status, ExamStatus) else exam.status,
                exam.created_by
            ))
            exam.id = cursor.lastrowid
        return exam
    
    def get_by_id(self, id: int, load_questions: bool = True) -> Optional[Exam]:
        """Lấy exam theo ID"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM exams WHERE id = ?", (id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            exam = self._row_to_exam(row)
            
            if load_questions:
                cursor.execute("""
                    SELECT * FROM exam_questions WHERE exam_id = ? ORDER BY position
                """, (id,))
                exam.questions = [
                    ExamQuestion(
                        id=eq['id'],
                        exam_id=eq['exam_id'],
                        question_id=eq['question_id'],
                        position=eq['position'],
                        points=eq['points'],
                        answer_mapping=json.loads(eq['answer_mapping']) if eq['answer_mapping'] else {}
                    )
                    for eq in cursor.fetchall()
                ]
            
            return exam
    
    def get_by_code(self, code: str) -> Optional[Exam]:
        """Lấy exam theo code"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM exams WHERE code = ?", (code,))
            row = cursor.fetchone()
            return self._row_to_exam(row) if row else None
    
    def get_all(self, status: Optional[ExamStatus] = None, limit: int = 100) -> List[Exam]:
        """Lấy danh sách exams"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute(
                    "SELECT * FROM exams WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status.value, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM exams ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            
            return [self._row_to_exam(row) for row in cursor.fetchall()]
    
    def add_question(self, exam_id: int, question_id: int, position: int,
                     points: float = 1.0, answer_mapping: Dict[str, str] = None) -> int:
        """Thêm câu hỏi vào đề thi"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO exam_questions (exam_id, question_id, position, points, answer_mapping)
                VALUES (?, ?, ?, ?, ?)
            """, (
                exam_id, question_id, position, points,
                json.dumps(answer_mapping) if answer_mapping else '{}'
            ))
            return cursor.lastrowid
    
    def remove_question(self, exam_id: int, question_id: int) -> bool:
        """Xóa câu hỏi khỏi đề thi"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM exam_questions WHERE exam_id = ? AND question_id = ?",
                (exam_id, question_id)
            )
            return cursor.rowcount > 0
    
    def clear_questions(self, exam_id: int) -> int:
        """Xóa tất cả câu hỏi khỏi đề thi"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM exam_questions WHERE exam_id = ?", (exam_id,))
            return cursor.rowcount
    
    def update(self, exam: Exam) -> Exam:
        """Cập nhật exam"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE exams SET
                    name = ?, description = ?, config = ?, status = ?,
                    is_published = ?, published_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                exam.name, exam.description, json.dumps(exam.config.to_dict()),
                exam.status.value if isinstance(exam.status, ExamStatus) else exam.status,
                exam.is_published, exam.published_at, exam.id
            ))
        return exam
    
    def update_status(self, id: int, status: ExamStatus) -> bool:
        """Cập nhật trạng thái"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE exams SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status.value, id)
            )
            return cursor.rowcount > 0
    
    def publish(self, id: int) -> bool:
        """Publish exam"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE exams SET
                    status = 'published', is_published = 1,
                    published_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (id,))
            return cursor.rowcount > 0
    
    def delete(self, id: int) -> bool:
        """Xóa exam"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM exam_questions WHERE exam_id = ?", (id,))
            cursor.execute("DELETE FROM exams WHERE id = ?", (id,))
            return cursor.rowcount > 0
    
    def _row_to_exam(self, row: sqlite3.Row) -> Exam:
        config_data = json.loads(row['config']) if row['config'] else {}
        
        return Exam(
            id=row['id'],
            code=row['code'],
            name=row['name'],
            description=row['description'] or '',
            config=ExamConfig(
                total_questions=config_data.get('total_questions', 30),
                duration_minutes=config_data.get('duration_minutes', 60),
                passing_score=config_data.get('passing_score', 50.0),
                shuffle_questions=config_data.get('shuffle_questions', True),
                shuffle_answers=config_data.get('shuffle_answers', True),
                difficulty_distribution=config_data.get('difficulty_distribution', {}),
                category_distribution=config_data.get('category_distribution', {}),
                template_distribution=config_data.get('template_distribution', {})
            ),
            status=ExamStatus(row['status']),
            is_published=bool(row['is_published']),
            published_at=datetime.fromisoformat(row['published_at']) if row['published_at'] else None,
            created_by=row['created_by'],
            times_used=row['times_used'],
            average_score=row['average_score'] or 0.0
        )


# ============================================================================
# GENERATION LOG REPOSITORY
# ============================================================================

class GenerationLogRepository(BaseRepository):
    """Repository cho GenerationLog"""
    
    def create(self, log: GenerationLog) -> GenerationLog:
        """Tạo log mới"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO generation_logs (
                    template_id, solver_id, batch_id, param_values,
                    status, question_id, error_message, execution_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log.template_id, log.solver_id, log.batch_id,
                json.dumps(log.param_values), log.status, log.question_id,
                log.error_message, log.execution_time
            ))
            log.id = cursor.lastrowid
        return log
    
    def get_by_batch(self, batch_id: str) -> List[GenerationLog]:
        """Lấy logs theo batch_id"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM generation_logs WHERE batch_id = ? ORDER BY created_at",
                (batch_id,)
            )
            return [self._row_to_log(row) for row in cursor.fetchall()]
    
    def get_stats(self, template_id: Optional[int] = None) -> Dict:
        """Lấy thống kê sinh câu hỏi"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            where_clause = "WHERE template_id = ?" if template_id else ""
            params = (template_id,) if template_id else ()
            
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'duplicate' THEN 1 ELSE 0 END) as duplicate,
                    AVG(execution_time) as avg_time
                FROM generation_logs {where_clause}
            """, params)
            
            row = cursor.fetchone()
            return {
                "total": row['total'] or 0,
                "success": row['success'] or 0,
                "failed": row['failed'] or 0,
                "duplicate": row['duplicate'] or 0,
                "avg_execution_time": row['avg_time'] or 0
            }
    
    def _row_to_log(self, row: sqlite3.Row) -> GenerationLog:
        return GenerationLog(
            id=row['id'],
            template_id=row['template_id'],
            solver_id=row['solver_id'],
            batch_id=row['batch_id'] or '',
            param_values=json.loads(row['param_values']) if row['param_values'] else {},
            status=row['status'],
            question_id=row['question_id'],
            error_message=row['error_message'] or '',
            execution_time=row['execution_time']
        )
