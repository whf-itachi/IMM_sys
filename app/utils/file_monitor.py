import os
import threading
import time
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
            target=self._wait_and_process_file,
            args=(file_path, filename)
        )
        thread.daemon = True
        thread.start()

    def _wait_and_process_file(self, file_path, filename):
        """
        等待文件不再被占用后再处理文件
        """
        max_retries = 10
        retry_delay = 0.5  # 初始延迟0.5秒
        
        for attempt in range(max_retries):
            if self._is_file_ready_for_processing(file_path):
                logger.info(f"文件 {filename} 已准备好，开始处理")
                
                # 使用线程异步处理文件，避免阻塞文件监控
                thread = threading.Thread(
                    target=self.process_new_file,
                    args=(filename,)
                )
                thread.daemon = True
                thread.start()
                
                return  # 成功启动处理线程后退出循环
            else:
                # 文件仍然被占用或正在写入，等待一段时间后重试
                logger.info(f"文件 {filename} 正在被写入，等待 {retry_delay}s 后重试... ({attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                # 增加延迟时间（指数退避）
                retry_delay *= 1.5
                
        # 如果达到最大重试次数仍未成功，则记录错误
        logger.error(f"达到最大重试次数，无法处理文件 {filename}，可能仍在写入中")

    def _is_file_ready_for_processing(self, file_path):
        """
        检查文件是否准备好进行处理
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return False
            
            # 检查文件大小是否稳定
            initial_size = os.path.getsize(file_path)
            time.sleep(0.1)  # 短暂等待
            current_size = os.path.getsize(file_path)
            
            if initial_size != current_size:
                # 文件大小仍在变化，说明仍在写入
                return False
            
            # 尝试以独占模式打开文件（仅在支持的系统上有效）
            # 在Windows上，如果文件正在被写入，这将失败
            with open(file_path, 'rb'):
                pass
            
            # 检查文件扩展名是否为Excel格式
            if not (file_path.lower().endswith('.xlsx') or file_path.lower().endswith('.xls')):
                return False
                
            # 检查文件头部是否为Excel格式
            with open(file_path, 'rb') as f:
                header = f.read(32)  # 读取前32字节检查文件头
                if not self._is_excel_file_header(header):
                    return False
                    
            return True
            
        except (IOError, OSError):
            # 文件被占用或无法访问
            return False

    def process_new_file(self, filename):
        """
        处理新创建的Excel文件
        """
        try:
            # 再次检查文件是否存在且可访问
            file_path = os.path.join(REPORTS_DIR, filename)
            if not os.path.exists(file_path):
                logger.error(f"文件 {filename} 不存在，跳过处理")
                return

            # 检查文件大小，确保文件完全写入
            initial_size = os.path.getsize(file_path)
            logger.info(f"初始文件大小: {initial_size} bytes")
            
            # 等待文件大小稳定，防止文件仍在写入
            for i in range(10):  # 最多等待约5秒
                time.sleep(0.5)  # 等待0.5秒
                current_size = os.path.getsize(file_path)
                logger.debug(f"检查文件大小: {current_size} bytes")
                
                if initial_size == current_size:
                    logger.info(f"文件大小已稳定，继续处理: {current_size} bytes")
                    break
                else:
                    logger.info(f"文件大小仍在变化: {initial_size} -> {current_size}, 继续等待...")
                    initial_size = current_size

            # 确保文件不是被其他进程锁定的状态
            try:
                with open(file_path, 'rb') as f:
                    # 尝试读取一点内容确认文件完整性
                    chunk = f.read(1024)
                    if len(chunk) > 0:
                        # 检查是否是Excel文件的头部特征
                        if not self._is_excel_file_header(chunk):
                            logger.error(f"文件 {filename} 不是有效的Excel文件格式")
                            return
            except (IOError, OSError) as e:
                logger.error(f"文件 {filename} 仍被占用或无法访问: {str(e)}")
                return

            # 获取文件中的工作表信息，添加重试机制
            worksheets_info = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    worksheets_info = get_available_worksheets(filename)
                    logger.info(f"文件 {filename} 包含的工作表: {worksheets_info['worksheets']}")
                    break  # 成功读取，跳出循环
                except Exception as e:
                    logger.warning(f"第 {attempt + 1} 次尝试读取文件 {filename} 工作表时出错: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(1)  # 等待1秒后重试
                    else:
                        logger.error(f"无法读取文件 {filename} 的工作表，已达到最大重试次数")
                        return  # 退出整个函数

            # 初始化加工前后的数据变量
            flatness_after_data = None
            flatness_before_data = None
            # 初始化叶片加工日志数据变量
            blade_result_info = None

            # 检查是否存在Flatness或FlatnessBefore工作表，一次性读取数据
            if worksheets_info['has_flatness']:
                logger.info(f"处理文件 {filename} 的 Flatness 工作表")
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        flatness_after_data = get_flatness_data_by_filename(filename, 'Flatness')
                        break  # 成功读取，跳出循环
                    except Exception as e:
                        logger.warning(f"第 {attempt + 1} 次尝试读取文件 {filename} Flatness数据时出错: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(1)  # 等待1秒后重试
                        else:
                            logger.error(f"无法读取文件 {filename} 的Flatness数据，已达到最大重试次数")
                            # 不返回，继续处理其他可能存在的工作表

            if worksheets_info['has_flatness_before']:
                logger.info(f"处理文件 {filename} 的 FlatnessBefore 工作表")
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        flatness_before_data = get_flatness_data_by_filename(filename, 'FlatnessBefore')
                        break  # 成功读取，跳出循环
                    except Exception as e:
                        logger.warning(f"第 {attempt + 1} 次尝试读取文件 {filename} FlatnessBefore数据时出错: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(1)  # 等待1秒后重试
                        else:
                            logger.error(f"无法读取文件 {filename} 的FlatnessBefore数据，已达到最大重试次数")
                            # 不返回，继续处理其他可能存在的工作表

            # 检查是否有BladeResult工作表，并处理
            if worksheets_info['has_blade_result']:
                logger.info(f"处理文件 {filename} 的 BladeResult 工作表")
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # 获取BladeResult数据但暂不处理，传递给process_flatness_results统一处理
                        blade_result_info = get_blade_result_data(filename)
                        break  # 成功读取，跳出循环
                    except Exception as e:
                        logger.warning(f"第 {attempt + 1} 次尝试读取文件 {filename} BladeResult数据时出错: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(1)  # 等待1秒后重试
                        else:
                            logger.error(f"无法读取文件 {filename} 的BladeResult数据，已达到最大重试次数")
                            # 不返回，继续处理其他可能存在的工作表

            # 给平面度扫描报告添加统一的叶片名称,如果没有则生成一个当前日期的字符串作为叶片名称
            if blade_result_info and blade_result_info.get('blade_id', ''):
                blade_id = blade_result_info.get('blade_id', '')
                flatness_after_data.report.bladeId = blade_id
                flatness_before_data.report.bladeId = blade_id
            else:
                # 生成当前日期的字符串作为叶片名称 (格式: YYYYMMDDHHMMSS)
                current_datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")
                blade_id = f"BLADE_{current_datetime_str}"
                
                if blade_result_info:
                    blade_result_info['blade_id'] = blade_id
                else:
                    # 如果没有blade_result_info，则创建一个新的字典
                    blade_result_info = {'blade_id': blade_id}
                
                if flatness_after_data:
                    flatness_after_data.report.bladeId = blade_id
                if flatness_before_data:
                    flatness_before_data.report.bladeId = blade_id

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

    def _is_excel_file_header(self, header_bytes):
        """
        检查字节头是否符合Excel文件格式
        """
        # Excel文件通常以特定的字节序列开头
        # XLSX文件以ZIP格式存储，开头是PK标志
        # XLS文件有特定的BOF（Beginning of File）记录
        pk_signature = b'PK'
        xls_biff_signature = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'  # OLE2复合文档格式
        
        if header_bytes.startswith(pk_signature):
            return True
        if header_bytes.startswith(xls_biff_signature):
            return True
        
        return False

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