import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from app.config.app_config import LOG_DIR

def setup_logger():
    # 创建logger
    logger = logging.getLogger('programLog')
    logger.setLevel(logging.INFO)

    # 创建日志目录（如果不存在）
    os.makedirs(LOG_DIR, exist_ok=True)

    # 定义日志格式
    formatter = logging.Formatter(
        '[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d:%(funcName)s]：%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 创建文件处理器，使用循环日志
    log_file_path = os.path.join(LOG_DIR, 'programLog.log')
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(
        '[%(asctime)s][%(levelname)s]：%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # 清除已有的处理器，避免重复日志
    logger.handlers.clear()

    # 添加处理器到logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger