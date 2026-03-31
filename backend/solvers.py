"""
solvers.py - Các solver mẫu cho nhiều dạng bài toán
"""

# ============================================================================
# SOLVER 1: TÍCH PHÂN ∫ x^n e^(ax) dx
# ============================================================================

SOLVER_INT_XN_EXP = '''
import sympy as sp
from sympy import symbols, integrate, exp, simplify

def solve(n, a, lower=0, upper=1):
    """
    Giải tích phân ∫_lower^upper x^n e^(ax) dx
    
    Tham số:
        n: số mũ của x (integer >= 1)
        a: hệ số trong e^(ax) (integer != 0)
        lower: cận dưới (default 0)
        upper: cận trên (default 1)
    
    Trả về:
        Kết quả dạng SymPy expression
    """
    x = symbols('x')
    integrand = x**n * exp(a * x)
    result = integrate(integrand, (x, lower, upper))
    return simplify(result)
'''

SOLVER_INT_XN_EXP_CONFIG = {
    "code": "INT_XN_EXP",
    "name": "Tích phân ∫ x^n e^(ax) dx",
    "math_formula": "\\int_{{{lower}}}^{{{upper}}} x^{{{n}}} \\cdot e^{{{a}x}} \\, dx",
    "param_schema": {
        "n": {"type": "integer", "min": 1, "max": 4, "description": "Số mũ của x"},
        "a": {"type": "integer", "min": -5, "max": 5, "exclude": [0], "description": "Hệ số trong e^(ax)"},
        "lower": {"type": "integer", "min": 0, "max": 0, "default": 0, "description": "Cận dưới"},
        "upper": {"type": "integer", "min": 1, "max": 1, "default": 1, "description": "Cận trên"}
    },
    "tags": ["tích phân", "tích phân từng phần", "hàm mũ", "tabular method"],
    "test_cases": [
        {"input": {"n": 2, "a": 3, "lower": 0, "upper": 1}, "expected": "-2/27 + 5*exp(3)/27"},
        {"input": {"n": 1, "a": 1, "lower": 0, "upper": 1}, "expected": "1"},
        {"input": {"n": 1, "a": -1, "lower": 0, "upper": 1}, "expected": "1 - 2*exp(-1)"}
    ],
    "solution_template": """Sử dụng phương pháp tích phân từng phần (Tabular Method):

Với $\\int x^{n} e^{{{a}x}} dx$, ta lập bảng:
- Cột đạo hàm: $x^{n}$, ${n}x^{n-1}$, ...
- Cột nguyên hàm: $e^{{{a}x}}$, $\\frac{{e^{{{a}x}}}}{{{a}}}$, ...

Kết quả: {answer}"""
}


# ============================================================================
# SOLVER 2: TÍCH PHÂN ∫ x^n ln(x) dx
# ============================================================================

SOLVER_INT_XN_LN = '''
import sympy as sp
from sympy import symbols, integrate, ln, simplify

def solve(n, lower=1, upper=None):
    """
    Giải tích phân ∫ x^n ln(x) dx (không xác định hoặc xác định)
    
    Tham số:
        n: số mũ của x (integer >= 0, n != -1)
        lower: cận dưới (default 1)
        upper: cận trên (default None = tích phân không xác định)
    """
    x = symbols('x')
    integrand = x**n * ln(x)
    
    if upper is not None:
        result = integrate(integrand, (x, lower, upper))
    else:
        result = integrate(integrand, x)
    
    return simplify(result)
'''

SOLVER_INT_XN_LN_CONFIG = {
    "code": "INT_XN_LN",
    "name": "Tích phân ∫ x^n ln(x) dx",
    "math_formula": "\\int_{{{lower}}}^{{{upper}}} x^{{{n}}} \\ln(x) \\, dx",
    "param_schema": {
        "n": {"type": "integer", "min": 0, "max": 4, "exclude": [-1], "description": "Số mũ của x"},
        "lower": {"type": "integer", "min": 1, "max": 1, "default": 1, "description": "Cận dưới"},
        "upper": {"type": "integer", "min": 2, "max": 5, "default": 2, "description": "Cận trên"}
    },
    "tags": ["tích phân", "tích phân từng phần", "logarit"],
    "test_cases": [
        {"input": {"n": 1, "lower": 1, "upper": 2}, "expected": "-3/4 + 2*log(2)"},
        {"input": {"n": 2, "lower": 1, "upper": 2}, "expected": "-7/27 + 8*log(2)/3"}
    ]
}


# ============================================================================
# SOLVER 3: TÍCH PHÂN ∫ x^n sin(ax) dx
# ============================================================================

SOLVER_INT_XN_SIN = '''
import sympy as sp
from sympy import symbols, integrate, sin, simplify

def solve(n, a, lower=0, upper=None):
    """
    Giải tích phân ∫ x^n sin(ax) dx
    """
    x = symbols('x')
    integrand = x**n * sin(a * x)
    
    if upper is not None:
        result = integrate(integrand, (x, lower, upper))
    else:
        result = integrate(integrand, x)
    
    return simplify(result)
'''

SOLVER_INT_XN_SIN_CONFIG = {
    "code": "INT_XN_SIN",
    "name": "Tích phân ∫ x^n sin(ax) dx",
    "math_formula": "\\int_{{{lower}}}^{{{upper}}} x^{{{n}}} \\sin({{{a}}}x) \\, dx",
    "param_schema": {
        "n": {"type": "integer", "min": 1, "max": 3, "description": "Số mũ của x"},
        "a": {"type": "integer", "min": 1, "max": 4, "description": "Hệ số trong sin(ax)"},
        "lower": {"type": "integer", "min": 0, "max": 0, "default": 0, "description": "Cận dưới"},
        "upper": {"type": "choice", "choices": ["pi", "pi/2"], "default": "pi", "description": "Cận trên"}
    },
    "tags": ["tích phân", "tích phân từng phần", "lượng giác"]
}


# ============================================================================
# SOLVER 4: ĐẠO HÀM f(g(x)) - HÀM HỢP
# ============================================================================

SOLVER_DERIVATIVE_COMPOSITE = '''
import sympy as sp
from sympy import symbols, diff, exp, sin, cos, ln, sqrt, simplify

def solve(f_type, g_type, a=1, b=1, point=None):
    """
    Tính đạo hàm hàm hợp f(g(x))
    
    Tham số:
        f_type: loại hàm ngoài ('exp', 'sin', 'cos', 'ln', 'sqrt', 'square')
        g_type: loại hàm trong ('linear', 'quadratic', 'trig')
        a, b: hệ số
        point: điểm tính giá trị (nếu cần)
    """
    x = symbols('x')
    
    # Hàm trong
    if g_type == 'linear':
        g = a * x + b
    elif g_type == 'quadratic':
        g = a * x**2 + b
    elif g_type == 'trig':
        g = sin(a * x)
    else:
        g = x
    
    # Hàm ngoài
    if f_type == 'exp':
        f = exp(g)
    elif f_type == 'sin':
        f = sin(g)
    elif f_type == 'cos':
        f = cos(g)
    elif f_type == 'ln':
        f = ln(g)
    elif f_type == 'sqrt':
        f = sqrt(g)
    elif f_type == 'square':
        f = g**2
    else:
        f = g
    
    result = diff(f, x)
    result = simplify(result)
    
    if point is not None:
        result = result.subs(x, point)
        result = simplify(result)
    
    return result
'''

SOLVER_DERIVATIVE_COMPOSITE_CONFIG = {
    "code": "DERIV_COMPOSITE",
    "name": "Đạo hàm hàm hợp f(g(x))",
    "math_formula": "\\frac{d}{dx} f(g(x))",
    "param_schema": {
        "f_type": {"type": "choice", "choices": ["exp", "sin", "cos", "ln", "sqrt", "square"]},
        "g_type": {"type": "choice", "choices": ["linear", "quadratic"]},
        "a": {"type": "integer", "min": 1, "max": 5},
        "b": {"type": "integer", "min": -3, "max": 3}
    },
    "tags": ["đạo hàm", "hàm hợp", "chain rule"]
}


# ============================================================================
# SOLVER 5: GIỚI HẠN DẠY 0/0
# ============================================================================

SOLVER_LIMIT_ZERO_ZERO = '''
import sympy as sp
from sympy import symbols, limit, sin, cos, tan, exp, ln, sqrt, simplify, oo

def solve(numer_type, denom_type, a=1, b=1, approach=0):
    """
    Tính giới hạn dạng 0/0
    
    Tham số:
        numer_type: dạng tử số ('sin_x', 'tan_x', 'exp_minus_1', 'ln_1_plus_x', 'poly')
        denom_type: dạng mẫu số ('x', 'sin_x', 'tan_x', 'poly')
        a, b: hệ số
        approach: x tiến tới (default 0)
    """
    x = symbols('x')
    
    # Tử số
    if numer_type == 'sin_x':
        numer = sin(a * x)
    elif numer_type == 'tan_x':
        numer = tan(a * x)
    elif numer_type == 'exp_minus_1':
        numer = exp(a * x) - 1
    elif numer_type == 'ln_1_plus_x':
        numer = ln(1 + a * x)
    elif numer_type == 'poly':
        numer = a * x + b * x**2
    else:
        numer = x
    
    # Mẫu số
    if denom_type == 'x':
        denom = b * x
    elif denom_type == 'sin_x':
        denom = sin(b * x)
    elif denom_type == 'tan_x':
        denom = tan(b * x)
    elif denom_type == 'poly':
        denom = b * x
    else:
        denom = x
    
    result = limit(numer / denom, x, approach)
    return simplify(result)
'''

SOLVER_LIMIT_ZERO_ZERO_CONFIG = {
    "code": "LIMIT_ZERO_ZERO",
    "name": "Giới hạn dạng 0/0",
    "math_formula": "\\lim_{{x \\to 0}} \\frac{{f(x)}}{{g(x)}}",
    "param_schema": {
        "numer_type": {"type": "choice", "choices": ["sin_x", "tan_x", "exp_minus_1", "ln_1_plus_x"]},
        "denom_type": {"type": "choice", "choices": ["x", "sin_x"]},
        "a": {"type": "integer", "min": 1, "max": 5},
        "b": {"type": "integer", "min": 1, "max": 5}
    },
    "tags": ["giới hạn", "dạng vô định", "L'Hopital"]
}


# ============================================================================
# SOLVER 6: TÍCH PHÂN HỮU TỈ
# ============================================================================

SOLVER_INT_RATIONAL = '''
import sympy as sp
from sympy import symbols, integrate, simplify, apart

def solve(a, b, c, d, lower=0, upper=1):
    """
    Tính tích phân ∫ (ax + b) / (cx + d) dx
    """
    x = symbols('x')
    numer = a * x + b
    denom = c * x + d
    
    integrand = numer / denom
    
    if upper is not None:
        result = integrate(integrand, (x, lower, upper))
    else:
        result = integrate(integrand, x)
    
    return simplify(result)
'''

SOLVER_INT_RATIONAL_CONFIG = {
    "code": "INT_RATIONAL",
    "name": "Tích phân hàm hữu tỉ (ax+b)/(cx+d)",
    "math_formula": "\\int_{{{lower}}}^{{{upper}}} \\frac{{{a}x + {b}}}{{{c}x + {d}}} \\, dx",
    "param_schema": {
        "a": {"type": "integer", "min": 1, "max": 3},
        "b": {"type": "integer", "min": -2, "max": 2},
        "c": {"type": "integer", "min": 1, "max": 3},
        "d": {"type": "integer", "min": 1, "max": 5},
        "lower": {"type": "integer", "min": 0, "max": 0, "default": 0},
        "upper": {"type": "integer", "min": 1, "max": 2, "default": 1}
    },
    "tags": ["tích phân", "hàm hữu tỉ", "phân tích"]
}


# ============================================================================
# SOLVER 7: MA TRẬN - ĐỊNH THỨC 2x2
# ============================================================================

SOLVER_DET_2X2 = '''
import sympy as sp
from sympy import Matrix

def solve(a11, a12, a21, a22):
    """
    Tính định thức ma trận 2x2
    |a11  a12|
    |a21  a22|
    """
    M = Matrix([[a11, a12], [a21, a22]])
    return M.det()
'''

SOLVER_DET_2X2_CONFIG = {
    "code": "DET_2X2",
    "name": "Định thức ma trận 2x2",
    "math_formula": "\\begin{vmatrix} {a11} & {a12} \\\\ {a21} & {a22} \\end{vmatrix}",
    "question_template": "Tính định thức $D = \\begin{vmatrix} {{{a11}}} & {{{a12}}} \\\\ {{{a21}}} & {{{a22}}} \\end{vmatrix}$",
    "param_schema": {
        "a11": {"type": "integer", "min": -5, "max": 5},
        "a12": {"type": "integer", "min": -5, "max": 5},
        "a21": {"type": "integer", "min": -5, "max": 5},
        "a22": {"type": "integer", "min": -5, "max": 5}
    },
    "tags": ["đại số tuyến tính", "ma trận", "định thức"]
}


# ============================================================================
# SOLVER 8: MA TRẬN - ĐỊNH THỨC 3x3
# ============================================================================

SOLVER_DET_3X3 = '''
import sympy as sp
from sympy import Matrix

def solve(a11, a12, a13, a21, a22, a23, a31, a32, a33):
    """
    Tính định thức ma trận 3x3
    """
    M = Matrix([
        [a11, a12, a13],
        [a21, a22, a23],
        [a31, a32, a33]
    ])
    return M.det()
'''

SOLVER_DET_3X3_CONFIG = {
    "code": "DET_3X3",
    "name": "Định thức ma trận 3x3",
    "math_formula": "\\begin{vmatrix} {a11} & {a12} & {a13} \\\\ {a21} & {a22} & {a23} \\\\ {a31} & {a32} & {a33} \\end{vmatrix}",
    "param_schema": {
        "a11": {"type": "integer", "min": -3, "max": 3},
        "a12": {"type": "integer", "min": -3, "max": 3},
        "a13": {"type": "integer", "min": -3, "max": 3},
        "a21": {"type": "integer", "min": -3, "max": 3},
        "a22": {"type": "integer", "min": -3, "max": 3},
        "a23": {"type": "integer", "min": -3, "max": 3},
        "a31": {"type": "integer", "min": -3, "max": 3},
        "a32": {"type": "integer", "min": -3, "max": 3},
        "a33": {"type": "integer", "min": -3, "max": 3}
    },
    "tags": ["đại số tuyến tính", "ma trận", "định thức"]
}


# ============================================================================
# DANH SÁCH TẤT CẢ SOLVERS
# ============================================================================

ALL_SOLVERS = [
    {
        "code": SOLVER_INT_XN_EXP,
        "config": SOLVER_INT_XN_EXP_CONFIG
    },
    {
        "code": SOLVER_INT_XN_LN,
        "config": SOLVER_INT_XN_LN_CONFIG
    },
    {
        "code": SOLVER_INT_RATIONAL,
        "config": SOLVER_INT_RATIONAL_CONFIG
    },
    {
        "code": SOLVER_DET_2X2,
        "config": SOLVER_DET_2X2_CONFIG
    },
    {
        "code": SOLVER_DET_3X3,
        "config": SOLVER_DET_3X3_CONFIG
    }
]


def get_solver_by_code(code: str):
    """Lấy solver theo mã"""
    for solver in ALL_SOLVERS:
        if solver["config"]["code"] == code:
            return solver
    return None


def list_available_solvers():
    """Liệt kê các solver có sẵn"""
    return [
        {
            "code": s["config"]["code"],
            "name": s["config"]["name"],
            "tags": s["config"].get("tags", [])
        }
        for s in ALL_SOLVERS
    ]
