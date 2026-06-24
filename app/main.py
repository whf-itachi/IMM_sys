from flask import Flask, render_template
from flask_cors import CORS
import atexit
from app.utils.logging_config import setup_logger
from app.utils.mqtt_utils.publisher import JetLinksMQTTPublisher
from app.utils.plc_data_collector import plc_collector

# 创建全局logger
logger = setup_logger()

def create_app():
    # 创建Flask实例
    app = Flask(__name__, template_folder='../templates', static_folder='../static')

    # 配置CORS
    CORS(app, resources={r"/*": {"origins": "*"}})  # 在生产环境中应限制为具体的域名

    # 初始化MQTT发布器
    mqtt_publisher = JetLinksMQTTPublisher()

    # 将mqtt_publisher存储在应用上下文中
    app.mqtt_publisher = mqtt_publisher

    # 初始化PLC数据采集器
    app.plc_collector = plc_collector

    # 连接到MQTT代理
    logger.info("Starting up IMM Report API...")
    try:
        logger.info("Attempting to connect to MQTT broker...")
        app.mqtt_publisher.connect()
        if app.mqtt_publisher.is_connected:
            logger.info("MQTT publisher initialized and connected successfully")
        else:
            logger.warning("MQTT publisher initialized but not connected")
            
        # 启动PLC数据采集器
        logger.info("Attempting to start PLC data collector...")
        app.plc_collector.start()
        logger.info("PLC data collector started successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize MQTT publisher or PLC collector: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        

    # 注册API路由
    from app.api.routes import register_routes
    register_routes(app)

    # 主页路由 - 渲染模板
    @app.route("/")
    def index():
        from app.utils.file_operations import get_reports_list
        reports_data = get_reports_list()
        
        # 准备报告数据用于模板
        from app.schemas.report_schemas import ReportListResponse, FileItem
        file_items = []
        for item in reports_data:
            file_item = FileItem(
                id=item['id'],
                file_name=item['file_name'],
                created_at=item['created_at'],
                file_size=item['file_size'],
                flatness_count=item['flatness_count']
            )
            file_items.append(file_item)
        
        response_data = ReportListResponse(reports=file_items)
        return render_template('index.html', reports=response_data.reports)

    @app.route("/image")
    def serve_image():
        from flask import send_from_directory
        import os
        directory_path = os.path.join(app.static_folder, 'images')
        filename = 'xy_projection.png'
        return send_from_directory(directory_path, filename)

    # 注册退出时的清理函数
    def shutdown_event():
        logger.info("Shutting down IMM Report API...")
        # 停止PLC数据采集器
        app.plc_collector.stop()
        logger.info("PLC data collector stopped")
        # 断开MQTT连接
        app.mqtt_publisher.disconnect()
        logger.info("MQTT publisher disconnected")

    atexit.register(shutdown_event)

    return app