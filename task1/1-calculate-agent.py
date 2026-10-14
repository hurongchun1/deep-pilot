import ast
import math
import operator
import os
import re
from collections.abc import Callable
from typing import Any
from langchain_openai import ChatOpenAI
from langchain_core.tracers.langchain import get_client
from deepagents import create_deep_agent

# 安全白名单：允许的运算符（二元 + 一元）
_ALLOWED_OPERATORS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# 安全白名单：允许调用的函数
_ALLOWED_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "pow": pow,
    "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),  # 实数立方根（支持负数）
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "exp": math.exp,
}

# 安全白名单：允许的数学常量
_ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "tau": math.tau,
    "e": math.e,
}

# 上标字符 -> 普通字符（用于 10² -> 10**2）
_SUPERSCRIPT_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁻": "-",
}

# 全角/特殊符号 -> 半角 Python 运算符
_SYMBOL_TRANSLATION = str.maketrans({
    "＋": "+", "－": "-", "−": "-", "–": "-", "﹣": "-",
    "＊": "*", "×": "*", "·": "*", "✕": "*",
    "／": "/", "÷": "/",
    "（": "(", "）": ")", "【": "(", "】": ")",
    "。": ".", "，": ",", "；": ",", "％": "%", "＝": "=",
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "　": " ",
})


def _normalize(expression: str) -> str:
    """把模型可能输出的非标准写法归一成标准 Python 表达式"""
    text = expression.strip()
    # 1) 全角/特殊符号转半角：（1＋2）×3 -> (1+2)*3
    text = text.translate(_SYMBOL_TRANSLATION)
    # 2) 上标幂：10² -> 10**2，2⁻¹ -> 2**-1，(1+2)² -> (1+2)**2
    text = re.sub(
        r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+",
        lambda m: "**" + "".join(_SUPERSCRIPT_MAP[ch] for ch in m.group(0)),
        text,
    )
    # 3) ^ 按幂运算处理：2^10 -> 2**10
    text = text.replace("^", "**")
    # 4) 根号：√16 -> sqrt(16)，∛27 -> cbrt(27)，√-16 -> sqrt(-16)，√(16) -> sqrt((16))
    text = re.sub(r"∛\s*(-?\d+(?:\.\d+)?)", r"cbrt(\1)", text)
    text = re.sub(r"√\s*(-?\d+(?:\.\d+)?)", r"sqrt(\1)", text)
    text = text.replace("∛", "cbrt(").replace("√", "sqrt")
    # 5) 圆周率：π -> pi
    text = text.replace("π", "pi").replace("Π", "pi")
    return text


def _eval_node(node: ast.AST) -> float | int:
    """递归解析 AST 节点并计算，只放行白名单内的语法"""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"不支持的常量: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        return _ALLOWED_OPERATORS[type(node.op)](left, right)  # type: ignore[operator]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_eval_node(node.operand))  # type: ignore[operator]
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
            raise ValueError("不支持的函数调用（仅限白名单内的数学函数）")
        args = [_eval_node(arg) for arg in node.args]
        return _ALLOWED_FUNCTIONS[node.func.id](*args)
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]
        raise ValueError(f"不支持的变量: {node.id}（仅支持数字和 pi/e 等数学常量）")
    raise ValueError("不支持的表达式，仅支持算术运算和数学函数")

# 通过deepseek的openAI方式接入模型
model = ChatOpenAI(
    model= "deepseek-flash",
    api_key= os.environ["DEEPSEEK_API_KEY"],  # pyright: ignore[reportArgumentType]
    base_url="https://api.deepseek.com/v1"
)

# 实现计算器工具
def calculate_tool(expression:str) -> str:
    """
    提供计算公式，帮助模型计算返回计算结果

    Args:
        expression: 数学表达式，例如：(1+2)*3、10²、√16、2^10、100÷4、（1＋2）×3
                    （自动兼容上标幂、根号、^ 幂、全角符号等写法）
    """
    try:
        normalized = _normalize(expression)
        tree = ast.parse(normalized, mode="eval")
        result = _eval_node(tree)
    except ZeroDivisionError:
        return "计算失败：除数不能为零"
    except (ValueError, SyntaxError, TypeError) as e:
        return f"计算失败：{e}"
    # 整数值的浮点结果去掉小数点，如 9.0 -> 9
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"计算结果：{expression} = {result}"


# 固定汇率表：以 USD 为基准的近似汇率（非实时行情，长期不更新会偏离市场价）
_FIXED_RATES_TO_USD = {
    "USD": 1.0,      # 美元
    "CNY": 7.16,     # 人民币
    "EUR": 0.92,     # 欧元
    "GBP": 0.78,     # 英镑
    "JPY": 152.0,    # 日元
    "HKD": 7.80,     # 港币
    "KRW": 1380.0,   # 韩元
    "SGD": 1.32,     # 新加坡元
    "AUD": 1.53,     # 澳元
    "CAD": 1.37,     # 加元
    "CHF": 0.88,     # 瑞士法郎
    "TWD": 32.1,     # 新台币
    "THB": 34.5,     # 泰铢
    "MYR": 4.42,     # 马来西亚林吉特
    "PHP": 58.5,     # 菲律宾比索
    "INR": 84.0,     # 印度卢比
    "RUB": 92.0,     # 俄罗斯卢布
    "NZD": 1.66,     # 新西兰元
    "SEK": 10.6,     # 瑞典克朗
    "NOK": 10.8,     # 挪威克朗
    "DKK": 6.85,     # 丹麦克朗
    "AED": 3.67,     # 阿联酋迪拉姆
    "SAR": 3.75,     # 沙特里亚尔
    "BRL": 5.75,     # 巴西雷亚尔
    "ZAR": 18.2,     # 南非兰特
    "MXN": 18.5,     # 墨西哥比索
    "TRY": 34.2,     # 土耳其里拉
    "PLN": 3.95,     # 波兰兹罗提
    "VND": 25400.0,  # 越南盾
    "IDR": 15800.0,  # 印尼卢比
}

# 无小数位的货币（国际惯例）
_ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "VND", "IDR"}


# 实现汇率计算
def convert_currency(amount: float, from_currency: str, to_currency: str = "CNY") -> str:
    """
    将金额从一种货币转换为另一种货币（使用内置固定汇率，非实时行情）。

    Args:
        amount: 要转换的金额
        from_currency: 源货币代码，例如："USD"
        to_currency: 目标货币代码，默认为："CNY"
    """
    src = from_currency.strip().upper()
    dst = to_currency.strip().upper()

    unsupported = [c for c in (src, dst) if c not in _FIXED_RATES_TO_USD]
    if unsupported:
        supported = "、".join(sorted(_FIXED_RATES_TO_USD))
        return f"不支持的货币代码：{'、'.join(unsupported)}，目前仅支持：{supported}"

    if src == dst:
        return f"换算结果：{amount} {src} = {amount} {dst}（同种货币无需转换）"

    try:
        # 统一折算成 USD 再转目标货币：amount / rate_src * rate_dst
        result = amount / _FIXED_RATES_TO_USD[src] * _FIXED_RATES_TO_USD[dst]
    except ZeroDivisionError:
        return "计算失败：汇率表数据异常"

    rate = _FIXED_RATES_TO_USD[dst] / _FIXED_RATES_TO_USD[src]
    if dst in _ZERO_DECIMAL_CURRENCIES:
        result = round(result)  # 日元/韩元等无小数位
    else:
        result = round(result, 2)
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"换算结果：{amount} {src} = {result} {dst}（固定汇率 1 {src} = {rate:.4f} {dst}）"


# 将模型，工具，系统提示词整合到agent中
agent = create_deep_agent(
    model = model,
    tools= [calculate_tool,convert_currency],
    system_prompt="你是一个乐于助人的助手"
)


# 运行信息得出结果
# 标准的消息格式：
# {"messages": [{"role": "user", "content": "你的问题"}]}
result = agent.invoke(
    {"messages":[
        {"role":"user","content":"帮我把 100 美元换算成人民币，再用它乘以 1.08 的通胀系数。"}
    ]}
)


# 打印结果
print(result["messages"][-1].content)

# 短命令结束前等待 trace 上传，并关闭 LangSmith 后台线程
if os.getenv("LANGSMITH_TRACING", "").lower() in {"true", "1"}:
    get_client().close(timeout=10)
