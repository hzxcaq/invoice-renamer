import os

DEFAULT_TEMPLATE = "{name}_¥{amount}{ext}"


def build_new_filename(original_name: str, fields: dict, template: str = DEFAULT_TEMPLATE) -> str:
    """根据模板和字段字典生成新文件名。

    fields 中的键对应模板中的 {key} 占位符。
    原文件名的 name 和 ext 自动补充。
    """
    base, ext = os.path.splitext(original_name)
    # fields 中的 None 值不覆盖默认值
    merged = {"name": base, "ext": ext, "symbol": "¥"}
    merged.update({k: v for k, v in fields.items() if v is not None})

    result = template
    for key, val in merged.items():
        result = result.replace(f"{{{key}}}", str(val) if val else "")
    return result


def rename_file(pdf_path: str, fields: dict, template: str = DEFAULT_TEMPLATE,
                dry_run: bool = False) -> tuple[bool, str, str | None]:
    """重命名 PDF 文件。

    Returns:
        (成功与否, 新文件名或原文件名, 错误信息)
    """
    directory = os.path.dirname(pdf_path)
    original_name = os.path.basename(pdf_path)
    new_name = build_new_filename(original_name, fields, template)

    if new_name == original_name:
        return True, new_name, None

    new_path = os.path.join(directory, new_name)

    if os.path.exists(new_path):
        return False, original_name, f"目标文件已存在: {new_name}"

    if dry_run:
        return True, new_name, None

    try:
        os.rename(pdf_path, new_path)
        return True, new_name, None
    except OSError as e:
        return False, original_name, f"重命名失败: {e}"
