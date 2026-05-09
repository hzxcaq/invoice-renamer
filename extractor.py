import re
import pdfplumber

# 可用模板字段定义
FIELD_DEFINITIONS = {
    "name":    "原文件名（不含扩展名）",
    "amount":  "价税合计金额",
    "symbol":  "¥ 符号",
    "ext":     "扩展名（含点号）",
    "inv_no":  "发票号码",
    "inv_date":"开票日期",
    "buyer":   "购买方名称",
    "seller":  "销售方名称",
    "item":    "项目名称",
    "tax":     "税额",
    "subtotal":"金额（不含税）",
    "drawer":  "开票人",
}

# 正则模式集合
_PATTERNS = {
    "inv_no":   re.compile(r'发票号码[：:]\s*(\d+)'),
    "inv_date": re.compile(r'开票日期[：:]\s*([\d年月日]+)'),
    "buyer":    re.compile(r'买\s*方.*?名称[：:]\s*(.+?)(?:\s+统|$)', re.DOTALL),
    "seller":   re.compile(r'售\s*方.*?名称[：:]\s*(.+?)(?:\s+统|$)', re.DOTALL),
    "amount":   re.compile(r'[（(]小写[）)]\s*[¥￥]\s*([\d,]+\.?\d*)'),
    "tax":      re.compile(r'合\s*计\s+[¥￥][\d,.]+\s+[¥￥]([\d,.]+)'),
    "subtotal": re.compile(r'合\s*计\s+[¥￥]([\d,.]+)'),
    "drawer":   re.compile(r'开票人[：:]\s*(\S+)'),
    "item":     re.compile(r'\*([^*]+)\*'),
}

# 购买方/销售方模式 — 同行双列（PDF 文本提取可能断字）
_BUYER_SELLER_SAME_LINE = re.compile(
    r'购\s*(?:买\s*)?(?:方\s*)?名\s*称[：:]\s*(.+?)\s+销\s*(?:售\s*)?(?:方\s*)?名\s*称[：:]\s*(.+?)$',
    re.MULTILINE,
)
# 单列格式
_BUYER_ONLY = re.compile(r'购\s*(?:买\s*)?(?:方\s*)?名\s*称[：:]\s*(.+?)$', re.MULTILINE)
_SELLER_ONLY = re.compile(r'销\s*(?:售\s*)?(?:方\s*)?名\s*称[：:]\s*(.+?)$', re.MULTILINE)


def _clean(s: str) -> str:
    """清理提取的字段值。"""
    return s.strip().replace("\n", " ").replace("  ", " ")


def extract_invoice_data(pdf_path: str) -> dict[str, str | None]:
    """从 PDF 发票中提取所有可用字段。

    Returns:
        字段字典，键为 FIELD_DEFINITIONS 中的键，值为提取的字符串或 None。
    """
    result = {k: None for k in FIELD_DEFINITIONS}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

        if not full_text.strip():
            return result

        # 提取各字段
        for key in ("inv_no", "inv_date", "tax", "subtotal", "drawer", "amount"):
            m = _PATTERNS[key].search(full_text)
            if m:
                val = m.group(1) or m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
                if val:
                    result[key] = _clean(val).replace(",", "")

        # 项目名称（取第一个匹配）
        items = _PATTERNS["item"].findall(full_text)
        if items:
            result["item"] = _clean(items[0])

        # 购买方/销售方
        m = _BUYER_SELLER_SAME_LINE.search(full_text)
        if m:
            result["buyer"] = _clean(m.group(1))
            result["seller"] = _clean(m.group(2))
        else:
            for key, pat in [("buyer", _BUYER_ONLY), ("seller", _SELLER_ONLY)]:
                mp = pat.search(full_text)
                if mp:
                    result[key] = _clean(mp.group(1))

    except Exception:
        pass

    return result


def extract_amount(pdf_path: str) -> tuple[str | None, str | None]:
    """兼容旧接口：仅提取价税合计金额。"""
    data = extract_invoice_data(pdf_path)
    amount = data.get("amount")
    if amount:
        return amount, None
    return None, "未找到价税合计金额字段"
