import os
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from app.config.app_config import REPORTS_DIR
from app.utils.file_operations import get_available_worksheets, get_flatness_data_by_filename
from app.utils.logging_config import setup_logger


logger = setup_logger()


class ReportFileHandler(PatternMatchingEventHandler):
    """
    监听报告文件夹中新增的Excel文件并处理
    """
    def __init__(self, mqtt_publisher):
        # 只监控Excel文件
        super().__init__(patterns=['*.xlsx', '*.xls'], ignore_directories=True)
        self.mqtt_publisher = mqtt_publisher

    def on_created(self, event):
        """
        当文件被创建时触发
        """
        if event.is_directory:
            return

        file_path = event.src_path
        filename = os.path.basename(file_path)

        logger.info(f"检测到新的Excel文件: {filename}")
        # 使用线程异步处理文件，避免阻塞文件监控
        thread = threading.Thread(
            target=self.process_new_file,
            args=(filename,)
        )
        thread.daemon = True
        thread.start()

    def process_new_file(self, filename):
        """
        处理新创建的Excel文件
        """
        try:
            # 获取文件中的工作表信息
            worksheets_info = get_available_worksheets(filename)
            logger.info(f"文件 {filename} 包含的工作表: {worksheets_info['worksheets']}")

            # 检查是否存在Flatness或FlatnessBefore工作表
            if worksheets_info['has_flatness']:
                logger.info(f"处理文件 {filename} 的 Flatness 工作表")
                self.process_worksheet(filename, 'Flatness', 'after')

            if worksheets_info['has_flatness_before']:
                logger.info(f"处理文件 {filename} 的 FlatnessBefore 工作表")
                self.process_worksheet(filename, 'FlatnessBefore', 'before')

        except Exception as e:
            logger.error(f"处理新文件 {filename} 时出错: {str(e)}")

    def process_worksheet(self, filename, worksheet_name, process_stage):
        """
        处理指定的工作表
        """
        try:
            # 读取工作表数据
            result = get_flatness_data_by_filename(filename, worksheet_name)

            # 发布遥测数据到MQTT
            if self.mqtt_publisher and self.mqtt_publisher.is_connected:
                # 准备孔角度和孔测量值数组
                hole_angles = [item.holeAngle for item in result.flatness_data]
                hole_values = [item.flatness for item in result.flatness_data]

                # 构造平面度测量数据事件字典
                event_data = {
                    "measure_time": int(datetime.now().timestamp() * 1000),  # 毫秒时间戳
                    "blade_id": result.report.bladeId,  # 叶片ID
                    "max_value": result.statistics.max_value,
                    "min_value": result.statistics.min_value,
                    "pv_value": result.statistics.peak_to_peak,
                    "rms": result.statistics.rms_value,
                    "hole_angle": hole_angles,
                    "hole_value": hole_values,
                    "process_stage": process_stage  # 使用process_stage替代worksheet
                }
                
                # 发布平面度测量数据事件
                self.mqtt_publisher.publish_event("flatness_data", event_data)
                logger.info(f"已发布 {process_stage} 阶段的平面度数据事件，文件: {filename}")
            else:
                logger.warning(f"MQTT发布器未连接，跳过发布 {filename} 的数据")

        except Exception as e:
            logger.error(f"处理工作表 {worksheet_name} 时出错: {str(e)}")


class FileMonitor:
    """
    文件监控器，监听REPORTS_DIR文件夹中的文件变化
    """
    def __init__(self, mqtt_publisher):
        self.observer = Observer()
        self.handler = ReportFileHandler(mqtt_publisher)
        self.is_running = False

    def start(self):
        """
        开始监控文件夹
        """
        if self.is_running:
            logger.warning("文件监控器已在运行中")
            return

        self.observer.schedule(self.handler, REPORTS_DIR, recursive=False)
        self.observer.start()
        self.is_running = True
        logger.info(f"开始监控文件夹: {REPORTS_DIR}")

    def stop(self):
        """
        停止监控文件夹
        """
        if not self.is_running:
            logger.warning("文件监控器未运行")
            return

        self.observer.stop()
        self.observer.join()
        self.is_running = False
        logger.info("已停止文件监控")