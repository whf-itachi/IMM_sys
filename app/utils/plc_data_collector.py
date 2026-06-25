import time
import threading
import snap7
import os
from app.utils.logging_config import setup_logger

logger = setup_logger()

# PLC数据采集相关常量
PLC_IP = '192.168.3.1'  # 默认PLC IP地址
PLC_RACK = 0            # PLC机架号
PLC_SLOT = 1            # PLC插槽号

class PLCDataCollector:
    """
    PLC数据采集器，运行在独立线程中
    专门处理GDB_Errors (DB2)报警数据
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """
        单例模式实现
        """
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    # 只在创建新实例时初始化属性
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, plc_ip='192.168.3.1', scan_interval=2.0, mqtt_publisher=None, protocol='snap7'):
        # 防止重复初始化
        if self._initialized:
            return

        # 只有第一次初始化时才设置这些属性
        self.plc_ip = plc_ip
        self.scan_interval = scan_interval
        self.client = None
        self.running_event = threading.Event()  # 使用Event代替布尔标志
        self.thread = None
        self.mqtt_publisher = mqtt_publisher  # 外部传入的MQTT实例
        self.protocol = protocol  # 当前仅支持 'snap7'
        self.snap7_client = None

        self._initialized = True

    def connect_plc(self):
        """连接到PLC"""
        try:
            if self.protocol == 'snap7':
                # 检查是否已有连接
                if self.snap7_client and hasattr(self.snap7_client, 'get_connected') and self.snap7_client.get_connected():
                    logger.info("PLC已经连接，无需重复连接")
                    return True

                # 使用Snap7协议连接
                self.snap7_client = snap7.client.Client()
                
                # 设置连接参数，增加超时时间
                self.snap7_client.set_param(snap7.types.PingTimeout, 5000)  # ping超时时间5秒
                self.snap7_client.set_param(snap7.types.SendTimeout, 5000)  # 发送超时时间5秒
                self.snap7_client.set_param(snap7.types.RecvTimeout, 5000)  # 接收超时时间5秒
                
                logger.info(f"尝试连接到Snap7 PLC at {self.plc_ip}:{PLC_RACK}/{PLC_SLOT}")
                self.snap7_client.connect(self.plc_ip, PLC_RACK, PLC_SLOT)

                # 验证连接
                if hasattr(self.snap7_client, 'get_connected') and self.snap7_client.get_connected():
                    logger.info(f"成功连接到Snap7 PLC at {self.plc_ip}")
                    return True
                else:
                    logger.error("连接Snap7 PLC失败 - 未能建立连接")
                    return False
            else:
                logger.error(f"不支持的协议类型: {self.protocol}")
                return False

        except snap7.snap7exceptions.Snap7Exception as se:
            logger.error(f"Snap7连接异常: {se}")
            return False
        except Exception as e:
            logger.error(f"连接PLC失败: {e}")
            import traceback
            logger.error(f"连接PLC完整错误堆栈: {traceback.format_exc()}")
            return False

    def disconnect_plc(self):
        """断开PLC连接"""
        if self.protocol == 'snap7':
            if self.snap7_client:
                self.snap7_client.disconnect()
                logger.info("已断开Snap7 PLC连接")

    def connect_mqtt(self):
        """连接到MQTT服务器（使用外部传入的实例）"""
        try:
            if self.mqtt_publisher and not self.mqtt_publisher.is_connected:
                self.mqtt_publisher.connect()
                logger.info("成功连接到MQTT服务器")
                return True
            elif self.mqtt_publisher and self.mqtt_publisher.is_connected:
                logger.info("MQTT已经连接")
                return True
            else:
                logger.error("MQTT发布器实例为空")
                return False
        except Exception as e:
            logger.error(f"连接MQTT服务器失败: {e}")
            return False

    def send_data_to_iot_platform(self, data):
        """将数据发送到物联网平台"""
        try:
            # 格式化数据为适合物联网平台传输的格式
            telemetry_data = {
                "timestamp": time.time(),
                "alarm_data": data
            }

            # 确保MQTT已连接
            if not self.mqtt_publisher or not self.mqtt_publisher.is_connected:
                logger.warning("MQTT未连接")
                return False

            # 发布到MQTT主题
            result = self.mqtt_publisher.publish_telemetry(telemetry_data)
            if result:
                logger.info("报警数据成功发送到物联网平台")
            else:
                logger.error("发送报警数据到物联网平台失败")

        except Exception as e:
            logger.error(f"发送数据到物联网平台时出错: {e}")

    def read_plc_data(self):
        """读取PLC报警数据"""
        if self.protocol == 'snap7':
            try:
                # 读取报警数据块(DB2)，获取报警信息
                alarm_data = self.read_alarm_data()
                return alarm_data
            except Exception as e:
                logger.error(f"读取Snap7报警数据失败: {e}")
                raise RuntimeError("Failed to get alarm data.") from e
        else:
            logger.error(f"不支持的协议类型: {self.protocol}")
            return {}

    def read_alarm_data(self):
        """读取报警数据块(DB2)"""
        try:
            # 读取GDB_Errors数据块(DB2)，总共52字节
            # 即使我们只解析前16字节（ErrWord0-ErrWord7），仍需读取完整数据块以确保数据完整性
            alarm_bytes = self.snap7_client.db_read(2, 0, 52)

            # 记录原始字节信息到日志（包括十六进制和二进制表示）
            hex_repr = [hex(b) for b in alarm_bytes]
            bin_repr = [format(b, '08b') for b in alarm_bytes]
            
            logger.info(f"从PLC读取的原始字节 (前16字节十六进制): {hex_repr[:16]}")
            logger.info(f"从PLC读取的原始字节 (前16字节二进制): {bin_repr[:16]}")
            
            # 记录ErrWord的解析（使用大端序）
            logger.info("=== ErrWord解析（使用大端序）===")
            for i in range(min(len(alarm_bytes)//2, 8)):  # 最多8个ErrWord
                first_byte = alarm_bytes[i*2] if i*2 < len(alarm_bytes) else 0
                second_byte = alarm_bytes[i*2+1] if i*2+1 < len(alarm_bytes) else 0
                word_value = (first_byte << 8) | second_byte  # 大端序
                logger.info(f"  ErrWord{i} (字节{i*2}-{i*2+1}): 0x{word_value:04X} = {format(word_value, '016b')}")
                # 详细显示位状态
                bits_on = []
                for j in range(16):
                    if (word_value >> j) & 1:
                        bits_on.append(str(j))
                if bits_on:
                    logger.info(f"    激活的位: [{', '.join(bits_on)}]")

            # 使用新的解析方法（基于alarms.log文件定义）
            from app.utils.plc_alarm_parser import parse_alarm_bytes
            parsed_alarms = parse_alarm_bytes(alarm_bytes)

            # 打印到控制台（开发阶段每次都显示）
            print("=== 解析后的报警数据 ===")
            from app.utils.plc_alarm_parser import print_parsed_alarms
            print_parsed_alarms(parsed_alarms)

            # 记录解析结果到日志，记录所有激活的报警
            active_alarms = []
            for category, data in parsed_alarms.items():
                if category.endswith('Alarms'):
                    for alarm_name, alarm_info in data.items():
                        if alarm_info['active']:
                            active_alarms.append(f"{alarm_name}({alarm_info['description']})")
                elif category == 'UndefinedBits':
                    # 记录未定义的位
                    if data:
                        # 将未定义的位也加入到活动报警列表中，以便在摘要中显示
                        for bit_info in data:
                            active_alarms.append(f"UndefinedBit_ErrWord{bit_info['word_index']}_Pos{bit_info['bit_position']}")
            
            # 记录所有激活的报警
            if active_alarms:
                logger.warning(f"检测到激活的报警: {', '.join(active_alarms)}")
            else:
                logger.info("未检测到激活的报警")

            return parsed_alarms
        except Exception as e:
            logger.error(f"读取报警数据失败: {e}")
            import traceback
            logger.error(f"读取报警数据完整错误堆栈: {traceback.format_exc()}")
            return {}

    def collect_loop(self):
        """数据采集主循环"""
        logger.info("开始报警数据采集循环")
        
        while self.running_event.is_set():
            try:
                # 读取报警数据
                alarm_data = self.read_plc_data()

                # 发送数据到物联网平台
                self.send_data_to_iot_platform(alarm_data)

                # 等待下一个采集周期
                time.sleep(self.scan_interval)

            except Exception as e:
                logger.error(f"报警数据采集循环中出现错误: {e}")
                time.sleep(self.scan_interval)  # 继续尝试

        logger.info("报警数据采集循环已停止")

    def start(self):
        """启动数据采集线程"""
        if self.running_event.is_set():
            logger.warning("报警数据采集器已经在运行")
            return

        # 连接到PLC
        if not self.connect_plc():
            logger.error("无法连接到PLC，无法启动采集器")
            return

        # 不再连接MQTT，因为使用的是外部传入的实例

        # 使用Event设置运行标志
        self.running_event.set()
        self.thread = threading.Thread(target=self.collect_loop, daemon=True)
        self.thread.start()
        logger.info("报警数据采集器已启动")

    def stop(self):
        """停止数据采集线程"""
        if not self.running_event.is_set():
            logger.info("报警数据采集器已经停止")
            return

        # 清除运行标志
        self.running_event.clear()
        logger.info("正在停止报警数据采集器...")
        
        # 等待采集线程结束
        if self.thread:
            self.thread.join(timeout=5)  # 等待最多5秒让线程结束
            
        # 断开PLC连接
        self.disconnect_plc()
        # 不再断开MQTT连接，因为那是主应用的责任
        logger.info("报警数据采集器已停止")

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()


def initialize_plc_collector(mqtt_publisher=None, protocol='snap7', plc_ip='192.168.3.1', scan_interval=2.0):
    """
    初始化PLC数据采集器，接收MQTT发布器实例
    """
    return PLCDataCollector(plc_ip=plc_ip, scan_interval=scan_interval, mqtt_publisher=mqtt_publisher, protocol=protocol)
