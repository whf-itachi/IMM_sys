from datetime import datetime


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


def convert_datetime_to_timestamp(date_value):
    """
    将日期时间值转换为时间戳（毫秒）
    :param date_value: Excel中的日期时间值
    :return: 时间戳（毫秒），如果转换失败则返回None
    """
    if date_value is None:
        return None

    try:
        # 如果已经是datetime对象
        if isinstance(date_value, datetime):
            return int(date_value.timestamp() * 1000)

        # 如果是字符串，尝试解析
        if isinstance(date_value, str):
            parsed_date = datetime.strptime(date_value, "%Y-%m-%d %H:%M:%S")
            return int(parsed_date.timestamp() * 1000)

        # 其他情况返回原值
        return date_value
    except Exception:
        # 如果转换失败，返回原始值
        return date_value