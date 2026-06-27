
def safe_float_convert(value):
    """
    安全地将值转换为浮点数，如果值类型不正确或为空，则返回0
    """
    if value is None or value == '':
        return 0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0