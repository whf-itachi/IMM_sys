import configparser
import os

# 配置文件路径
CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.ini')

# 创建配置解析器实例
config_parser = configparser.ConfigParser()

# 检查配置文件是否存在
if os.path.exists(CONFIG_FILE_PATH):
    # 读取配置文件
    config_parser.read(CONFIG_FILE_PATH, encoding='utf-8')
else:
    # 如果配置文件不存在，尝试创建默认配置
    print(f"配置文件 {CONFIG_FILE_PATH} 不存在，将使用默认配置。")

# 读取应用程序配置
LOG_DIR = config_parser.get('APP', 'LOG_DIR', fallback='./log')
REPORTS_DIR = config_parser.get('APP', 'REPORTS_DIR', fallback='D:/whf_test/report')
HOST = config_parser.get('APP', 'HOST', fallback='0.0.0.0')
PORT = config_parser.getint('APP', 'PORT', fallback=8000)
DEBUG = config_parser.getboolean('APP', 'DEBUG', fallback=False)

# 读取MQTT配置
MQTT_BROKER_HOST = config_parser.get('MQTT', 'BROKER_HOST', fallback='localhost')
MQTT_BROKER_PORT = config_parser.getint('MQTT', 'BROKER_PORT', fallback=1883)
MQTT_USE_TLS = config_parser.getboolean('MQTT', 'USE_TLS', fallback=False)

# 设备认证信息
MQTT_PRODUCT_ID = config_parser.get('MQTT', 'PRODUCT_ID', fallback='your_product_id')
MQTT_CUSTOM_SECURE_ID = config_parser.get('MQTT', 'CUSTOM_SECURE_ID', fallback='your_secure_id')
MQTT_CUSTOM_SECURE_KEY = config_parser.get('MQTT', 'CUSTOM_SECURE_KEY', fallback='your_secure_key')
MQTT_CUSTOM_DEVICE_ID = config_parser.get('MQTT', 'CUSTOM_DEVICE_ID', fallback='your_device_id')

# 主题格式
MQTT_PROPERTIES_TOPIC_FORMAT = config_parser.get('MQTT', 'PROPERTIES_TOPIC_FORMAT',
                                                 fallback=f"/{MQTT_PRODUCT_ID}/{MQTT_CUSTOM_DEVICE_ID}/properties/report")
MQTT_TELEMETRY_TOPIC_FORMAT = config_parser.get('MQTT', 'TELEMETRY_TOPIC_FORMAT',
                                                fallback=f"/{MQTT_PRODUCT_ID}/{MQTT_CUSTOM_DEVICE_ID}/telemetry")
MQTT_EVENT_TOPIC_FORMAT = config_parser.get('MQTT', 'EVENT_TOPIC_FORMAT',
                                            fallback=f"/{MQTT_PRODUCT_ID}/{MQTT_CUSTOM_DEVICE_ID}/event/{{event_id}}")

# 确保主题格式中使用实际的产品ID和设备ID值
MQTT_PROPERTIES_TOPIC_FORMAT = MQTT_PROPERTIES_TOPIC_FORMAT.replace('{PRODUCT_ID}', MQTT_PRODUCT_ID)
MQTT_PROPERTIES_TOPIC_FORMAT = MQTT_PROPERTIES_TOPIC_FORMAT.replace('{CUSTOM_DEVICE_ID}', MQTT_CUSTOM_DEVICE_ID)
MQTT_TELEMETRY_TOPIC_FORMAT = MQTT_TELEMETRY_TOPIC_FORMAT.replace('{PRODUCT_ID}', MQTT_PRODUCT_ID)
MQTT_TELEMETRY_TOPIC_FORMAT = MQTT_TELEMETRY_TOPIC_FORMAT.replace('{CUSTOM_DEVICE_ID}', MQTT_CUSTOM_DEVICE_ID)
MQTT_EVENT_TOPIC_FORMAT = MQTT_EVENT_TOPIC_FORMAT.replace('{PRODUCT_ID}', MQTT_PRODUCT_ID)
MQTT_EVENT_TOPIC_FORMAT = MQTT_EVENT_TOPIC_FORMAT.replace('{CUSTOM_DEVICE_ID}', MQTT_CUSTOM_DEVICE_ID)

# 连接配置
MQTT_KEEP_ALIVE = config_parser.getint('MQTT', 'KEEP_ALIVE', fallback=60)

# TLS证书路径
MQTT_CA_CERT_FILE = config_parser.get('MQTT', 'CA_CERT_FILE', fallback='./certs/server.crt')

# 属性映射
PROPERTY_MAPPING = {}  # 可以添加本地属性到JetLinks平台属性的映射