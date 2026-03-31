# Hệ thống Quản lý Ngân hàng Câu hỏi Trắc nghiệm

Hệ thống tự động hóa việc tạo và quản lý ngân hàng câu hỏi trắc nghiệm Toán học.

## 🎯 Tính năng

### ✅ Quản lý Template
- Định nghĩa dạng bài với tham số hóa
- Hỗ trợ nhiều loại tham số: integer, float, choice
- Tự động validate tham số
- Phân loại theo chủ đề/chương

### ✅ Sinh câu hỏi tự động
- Giải bài toán với SymPy
- Sinh đáp án nhiễu thông minh (dựa trên lỗi thường gặp)
- Sinh hàng loạt với kiểm tra trùng lặp
- Tính toán độ khó tự động

### ✅ Quản lý đề thi
- Tạo đề thi với cấu hình linh hoạt
- Tự động chọn câu hỏi theo tiêu chí
- Xáo trộn câu hỏi và đáp án
- Phân bố theo độ khó/chủ đề

### ✅ Xuất đa định dạng
- **LaTeX** → PDF chất lượng cao
- **JSON** → Tích hợp hệ thống khác
- **Markdown** → Xem nhanh
- **HTML** → Xem trên web
- **Moodle XML** → Import vào LMS

## 📁 Cấu trúc thư mục

```
question_bank_system/
├── src/
│   ├── __init__.py      # Package init
│   ├── config.py        # Cấu hình hệ thống
│   ├── models.py        # Định nghĩa model dữ liệu
│   ├── database.py      # Quản lý database (SQLite)
│   ├── services.py      # Logic nghiệp vụ
│   ├── export.py        # Các engine xuất file
│   ├── solvers.py       # Các solver mẫu
│   ├── utils.py         # Hàm tiện ích
│   ├── cli.py           # Command Line Interface
│   └── main.py          # Demo và chương trình chính
├── requirements.txt
└── README.md
```

## 🚀 Cài đặt

### Yêu cầu
- Python 3.8+
- SymPy 1.12+

### Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### Chạy demo
```bash
cd src

# Demo đầy đủ
python main.py full

# Demo nhanh
python main.py quick

# Menu tương tác
python main.py
```

## 💻 Sử dụng CLI

### Template
```bash
# Liệt kê templates
python cli.py template list

# Xem chi tiết template
python cli.py template show 1

# Import solver từ thư viện
python cli.py template import INT_XN_EXP
```

### Câu hỏi
```bash
# Sinh 20 câu hỏi từ template ID 1
python cli.py question generate 1 -n 20

# Liệt kê câu hỏi
python cli.py question list --template 1 --limit 10

# Xem chi tiết câu hỏi
python cli.py question show 1 --solution

# Duyệt câu hỏi
python cli.py question approve 1 2 3 4 5
```

### Đề thi
```bash
# Tạo đề thi
python cli.py exam create "Đề thi Giữa kỳ" -n 30 -d 60

# Tự động chọn câu hỏi
python cli.py exam fill 1 --templates 1 2

# Xuất đề thi
python cli.py exam export 1 -f latex -o de_thi.tex --answers
python cli.py exam export 1 -f json -o de_thi.json
python cli.py exam export 1 -f html -o de_thi.html --solutions
```

### Thống kê
```bash
python cli.py stats
```

## 📚 Sử dụng trong Code

### Tạo template và solver

```python
from database import Database
from services import TemplateService, SolverService

db = Database("question_bank.db")
template_service = TemplateService(db)
solver_service = SolverService(db)

# Tạo template
template = template_service.create(
    code="INT_X_EXP",
    name="Tích phân ∫ x e^(ax) dx",
    math_formula="\\int_{0}^{1} x e^{{{a}x}} dx",
    param_schema={
        "a": {
            "type": "integer",
            "min": -5,
            "max": 5,
            "exclude": [0],
            "description": "Hệ số trong e^(ax)"
        }
    },
    tags=["tích phân", "hàm mũ"]
)

# Đăng ký solver
solver_code = '''
from sympy import symbols, integrate, exp, simplify

def solve(a):
    x = symbols('x')
    result = integrate(x * exp(a * x), (x, 0, 1))
    return simplify(result)
'''

solver = solver_service.register(
    template_id=template.id,
    code=solver_code,
    version="1.0.0"
)
```

### Sinh câu hỏi

```python
from services import QuestionGeneratorService

generator = QuestionGeneratorService(db)

# Sinh một câu với tham số cụ thể
question = generator.generate_single(
    template_id=template.id,
    params={"a": 3}
)

print(f"Câu hỏi: {question.question_text}")
print(f"Đáp án đúng: {question.correct_answer}")

# Sinh hàng loạt
questions, errors = generator.generate_batch(
    template_id=template.id,
    count=30,
    constraints={
        "a": {"min": -3, "max": 3, "exclude": [0]}
    }
)
```

### Tạo và xuất đề thi

```python
from services import ExamService
from export import ExportService
from models import ExamConfig

exam_service = ExamService(db)
export_service = ExportService(db)

# Tạo đề thi
config = ExamConfig(
    total_questions=30,
    duration_minutes=60,
    shuffle_questions=True,
    shuffle_answers=True
)

exam = exam_service.create(
    name="Đề thi Giải tích",
    code="GIAI_TICH_01",
    config=config
)

# Tự động chọn câu hỏi
questions = exam_service.auto_select_questions(
    exam_id=exam.id,
    total=30
)
exam_service.add_questions(exam.id, [q.id for q in questions])

# Xuất file
export_service.export_to_file(
    exam_id=exam.id,
    format='latex',
    output_path='de_thi.tex',
    include_answers=True
)
```

## 🧮 Các Solver có sẵn

| Code | Tên | Mô tả |
|------|-----|-------|
| `INT_XN_EXP` | ∫ x^n e^(ax) dx | Tích phân xác định |
| `INT_XN_LN` | ∫ x^n ln(x) dx | Tích phân logarit |
| `INT_RATIONAL` | ∫ (ax+b)/(cx+d) dx | Tích phân hữu tỉ |
| `DET_2X2` | Định thức 2×2 | Ma trận 2×2 |
| `DET_3X3` | Định thức 3×3 | Ma trận 3×3 |

## 🔧 Tùy chỉnh

### Thêm solver mới

1. Viết code solver trong file `solvers.py`:

```python
SOLVER_MY_TYPE = '''
from sympy import symbols, ...

def solve(param1, param2):
    # Logic giải bài toán
    return result
'''

SOLVER_MY_TYPE_CONFIG = {
    "code": "MY_TYPE",
    "name": "Tên dạng bài",
    "math_formula": "Công thức LaTeX",
    "param_schema": {
        "param1": {"type": "integer", "min": 1, "max": 10},
        "param2": {"type": "choice", "choices": [1, 2, 3]}
    },
    "tags": ["tag1", "tag2"],
    "test_cases": [
        {"input": {"param1": 1, "param2": 2}, "expected": "kết quả"}
    ]
}
```

2. Thêm vào danh sách `ALL_SOLVERS`

### Thêm định dạng xuất mới

Kế thừa `BaseExporter` trong file `export.py`:

```python
class MyExporter(BaseExporter):
    def export(self, exam, questions, **options):
        # Logic xuất file
        return content
```

## 📊 Chiến lược sinh đáp án nhiễu

| Chiến lược | Mô tả |
|------------|-------|
| `sign_error` | Đổi dấu kết quả |
| `missing_bound` | Quên cận tích phân |
| `coefficient_error` | Sai hệ số |
| `adjacent_param` | Dùng tham số lân cận |
| `random_variation` | Biến thể ngẫu nhiên |

## 🗄️ Schema Database

```
categories          # Chủ đề/Chương
templates           # Dạng bài tham số hóa
solvers             # Code giải cho template
questions           # Câu hỏi đã sinh
exams               # Đề thi
exam_questions      # Liên kết đề thi - câu hỏi
generation_logs     # Log sinh câu hỏi
```

## 📄 License

MIT License

## 🤝 Đóng góp

Mọi đóng góp đều được hoan nghênh! Vui lòng tạo Issue hoặc Pull Request.
