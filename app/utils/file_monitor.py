import os
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

from app.config.app_config import REPORTS_DIR
from app.utils.file_operations import get_available_worksheets, get_flatness_data_by_filename, get_blade_result_data
from app.utils.logging_config import setup_logger
from app.utils.public_fun import safe_float_convert

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

            # 初始化加工前后的数据变量
            flatness_after_data = None
            flatness_before_data = None
            # 初始化叶片加工日志数据变量
            blade_result_info = None

            # 检查是否存在Flatness或FlatnessBefore工作表，一次性读取数据
            if worksheets_info['has_flatness']:
                logger.info(f"处理文件 {filename} 的 Flatness 工作表")
                flatness_after_data = get_flatness_data_by_filename(filename, 'Flatness')

            if worksheets_info['has_flatness_before']:
                logger.info(f"处理文件 {filename} 的 FlatnessBefore 工作表")
                flatness_before_data = get_flatness_data_by_filename(filename, 'FlatnessBefore')

            # 检查是否有BladeResult工作表，并处理
            if worksheets_info['has_blade_result']:
                logger.info(f"处理文件 {filename} 的 BladeResult 工作表")
                # 获取BladeResult数据但暂不处理，传递给process_flatness_results统一处理
                blade_result_info = get_blade_result_data(filename)

            if flatness_after_data:
                # 处理工作表并发布 加工后的flatness_data事件
                self.process_worksheet_with_data(filename, 'Flatness', 'after', flatness_after_data)
            if flatness_before_data:
                # 处理工作表并发布 加工后的flatness_data事件
                self.process_worksheet_with_data(filename, 'FlatnessBefore', 'before', flatness_before_data)
            if blade_result_info:
                # 处理process_log_report事件
                self.process_blade_result(filename, blade_result_info)

            # 处理汇总结果并发送钉钉通知，统一处理所有数据
            self.process_flatness_results(filename, flatness_after_data, flatness_before_data, blade_result_info)

        except Exception as e:
            logger.error(f"处理新文件 {filename} 时出错: {str(e)}")

    # 发送平面度测量结果事件
    def process_worksheet_with_data(self, filename, worksheet_name, process_stage, flatness_data):
        """
        处理已读取的平面度数据并发布事件
        """
        try:
            # 发布遥测数据到MQTT
            if self.mqtt_publisher and self.mqtt_publisher.is_connected:
                # 准备孔角度和孔测量值数组
                hole_angles = [item.holeAngle for item in flatness_data.flatness_data]
                hole_values = [item.flatness for item in flatness_data.flatness_data]

                # 构造平面度测量数据事件字典
                event_data = {
                    "measure_time": flatness_data.statistics.measure_time,
                    "blade_id": flatness_data.report.bladeId,  # 叶片ID
                    "max_value": flatness_data.statistics.max_value,
                    "min_value": flatness_data.statistics.min_value,
                    "pv_value": flatness_data.statistics.peak_to_peak,
                    "rms": flatness_data.statistics.rms_value,
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

    # 发送叶片加工日志事件
    def process_blade_result(self, filename, blade_result_info):
        """
        处理BladeResult工作表数据并上报process_log_report事件
        所有数据均依赖于传入的blade_result_info
        """
        try:
            # 上报process_log_report事件
            if self.mqtt_publisher and self.mqtt_publisher.is_connected:
                # 构建process_log_report事件所需的数据
                event_data = dict()
                
                # 基本信息
                event_data["blade_id"] = blade_result_info.get('blade_id', '')
                event_data["operator"] = blade_result_info.get('operator', '')
                event_data["process_start_time"] = blade_result_info.get('process_start_time', '')
                event_data["process_end_time"] = blade_result_info.get('process_end_time', '')
                event_data["total_duration"] = blade_result_info.get('total_duration', '')
                event_data["factory"] = blade_result_info.get('factory', '')
                event_data["device_type_code"] = blade_result_info.get('device_type_code', '')
                
                # 扫描相关数据
                event_data["scan_result"] = blade_result_info.get('scan_result', '')
                event_data["bolt_sleeve_max"] = safe_float_convert(blade_result_info.get('bolt_sleeve_max'))
                event_data["bolt_sleeve_min"] = safe_float_convert(blade_result_info.get('bolt_sleeve_min'))
                event_data["pitch_angle"] = safe_float_convert(blade_result_info.get('pitch_angle'))
                event_data["yaw_angle"] = safe_float_convert(blade_result_info.get('yaw_angle'))
                event_data["bcd_estimate"] = safe_float_convert(blade_result_info.get('bcd_estimate'))
                event_data["before_flatness"] = blade_result_info.get('before_flatness', '')

                # 铣磨结果
                event_data["mill_depth"] = blade_result_info.get('mill_depth', '')
                event_data["mill_cycles"] = blade_result_info.get('mill_cycles', '')
                event_data["mill_result"] = blade_result_info.get('mill_result', '')
                event_data["after_flatness"] = blade_result_info.get('after_flatness', '')
                # process time
                event_data["adjust_leg_time"] = safe_float_convert(blade_result_info.get('adjust_leg_time'))
                event_data["laser_adjust_time"] = safe_float_convert(blade_result_info.get('laser_adjust_time'))
                event_data["rough_scan_time"] = safe_float_convert(blade_result_info.get('rough_scan_time'))
                event_data["fine_scan_time"] = safe_float_convert(blade_result_info.get('fine_scan_time'))
                event_data["mill_time"] = safe_float_convert(blade_result_info.get('mill_time'))
                event_data["scan_report_time"] = safe_float_convert(blade_result_info.get('scan_report_time'))
                
                # 功率相关数据
                event_data["upper_avg_power"] = safe_float_convert(blade_result_info.get('upper_avg_power'))
                event_data["upper_max_power"] = safe_float_convert(blade_result_info.get('upper_max_power'))
                event_data["lower_avg_power"] = safe_float_convert(blade_result_info.get('lower_avg_power'))
                event_data["lower_max_power"] = safe_float_convert(blade_result_info.get('lower_max_power'))

                # 发布process_log_report事件
                self.mqtt_publisher.publish_event("process_log_report", event_data)
                logger.info(f"已发布 process_log_report 叶片加工日志事件，文件: {filename}")
            else:
                logger.warning(f"MQTT发布器未连接，跳过发布 {filename} 的 process_log_report 事件")

        except Exception as e:
            logger.error(f"处理BladeResult工作表 {filename} 时出错: {str(e)}")

    @staticmethod
    def _build_process_result_data(flatness_before_data, flatness_after_data, blade_result_info):
        """
        构建process_result事件所需的数据
        """
        # 构建富文本字符串
        flatness_info_parts = []

        if flatness_before_data:
            before_stats = flatness_before_data.statistics
            before_part = (
                f"**加工前平面度测量结果**\n"
                f"- 最大值: {before_stats.max_value:.2f} mm\n"
                f"- 最小值: {before_stats.min_value:.2f} mm\n"
                f"- 峰峰值: {before_stats.peak_to_peak:.2f} mm\n"
                f"- RMS值: {before_stats.rms_value:.2f} mm"
            )
            flatness_info_parts.append(before_part)

        if flatness_after_data:
            after_stats = flatness_after_data.statistics
            after_part = (
                f"**加工后平面度测量结果**\n"
                f"- 最大值: {after_stats.max_value:.2f} mm\n"
                f"- 最小值: {after_stats.min_value:.2f} mm\n"
                f"- 峰峰值: {after_stats.peak_to_peak:.2f} mm\n"
                f"- RMS值: {after_stats.rms_value:.2f} mm"
            )
            flatness_info_parts.append(after_part)

        # 合并所有部分
        flatness_info_markdown = "\n\n".join(flatness_info_parts)

        # 构建加工信息的富文本字符串
        if blade_result_info:
            # 处理总时长，如果存在则加上单位"分钟"并转换为整数
            total_duration = blade_result_info.get('total_duration', '')
            if total_duration is not None and total_duration != '':
                try:
                    total_duration_int = int(float(total_duration))  # 先转为浮点数再转为整数，处理可能的字符串数字
                    total_duration_display = f"{total_duration_int} min"
                except (ValueError, TypeError):
                    total_duration_display = f"{total_duration} min"  # 如果转换失败，保持原样
            else:
                total_duration_display = ""

            process_info_markdown = (
                f"**加工信息统计**\n"
                f"- 叶片ID: {blade_result_info.get('blade_id', '')}\n"
                f"- 铣磨圈数: {blade_result_info.get('mill_cycles', '')}\n"
                f"- 铣磨深度: {float(blade_result_info.get('mill_depth', 0)):.2f} mm\n"
                f"- 加工开始时间: {blade_result_info.get('process_start_time', '')}\n"
                f"- 加工结束时间: {blade_result_info.get('process_end_time', '')}\n"
                f"- 总时长: {total_duration_display}\n"
            )
        else:
            process_info_markdown = ""

        # 获取叶片名称
        blade_name = ''
        if blade_result_info and blade_result_info.get('blade_id'):
            blade_name = blade_result_info.get('blade_id', '')
        elif flatness_after_data:
            blade_name = flatness_after_data.report.bladeId
        elif flatness_before_data:
            blade_name = flatness_before_data.report.bladeId

        return {
            "blade_name": blade_name,
            "flatness_info": flatness_info_markdown,
            "process_info": process_info_markdown
        }

    # 发送汇总叶片加工日志事件
    def process_flatness_results(self, filename, flatness_after_data=None, flatness_before_data=None, blade_result_info=None):
        """
        处理叶片加工结果并发送汇总事件
        """
        try:
            # 构建process_result事件数据
            process_result_data = self._build_process_result_data(flatness_before_data, flatness_after_data, blade_result_info)

            # 发布平面度结果到钉钉通知
            if self.mqtt_publisher and self.mqtt_publisher.is_connected:
                # 发布平面度结果事件
                self.mqtt_publisher.publish_event("process_result", process_result_data)
                logger.info(f"已发布平面度结果数据事件，文件: {filename}")
            else:
                logger.warning(f"MQTT发布器未连接，跳过发布 {filename} 的平面度结果数据")

        except Exception as e:
            logger.error(f"处理平面度结果 {filename} 时出错: {str(e)}")


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