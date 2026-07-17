import time
import threading
import snap7
from app.utils.logging_config import setup_logger
from app.utils.plc_alarm_parser import ALARM_MAPPING_DICT

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
        self._shutting_down = False

        self._initialized = True

    def connect_plc(self):
        """连接到PLC"""
        try:
            if self.protocol == 'snap7':
                # 检查是否已有连接
                if self.snap7_client and hasattr(self.snap7_client, 'get_connected') and self.snap7_client.get_connected():
                    logger.info("PLC已经连接，无需重复连接")
                    return True

                # 断开旧连接（如果有），再创建新连接
                self.disconnect_plc()
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

        except Exception as e:
            logger.error(f"连接PLC失败: {e}")
            import traceback
            logger.error(f"连接PLC完整错误堆栈: {traceback.format_exc()}")
            return False

    def disconnect_plc(self):
        """断开PLC连接，内部异常已保护，不会向外抛出"""
        if self.protocol == 'snap7':
            if self.snap7_client:
                try:
                    self.snap7_client.disconnect()
                    logger.info("已断开Snap7 PLC连接")
                except Exception as e:
                    logger.warning(f"断开PLC连接时出现异常(忽略): {e}")
            self.snap7_client = None

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

    def send_alarm_events(self, alarm_descriptions):
        """发送报警事件到物联网平台"""
        try:
            # 将报警描述转换为markdown格式的富文本字符串
            alarms_markdown = "\n".join([f"- {desc}" for desc in sorted(alarm_descriptions)])

            # 创建报警事件数据 - 发送当前所有激活的报警
            alarm_event_data = {
                "alarms": alarms_markdown
            }

            # 发送报警事件
            result = self.mqtt_publisher.publish_event("alarm_log", alarm_event_data)
            if result:
                logger.info(f"报警事件成功发送到物联网平台: {sorted(list(alarm_descriptions))}")
            else:
                logger.error(f"发送报警事件到物联网平台失败: {sorted(list(alarm_descriptions))}")

        except Exception as e:
            logger.error(f"发送报警事件到物联网平台时出错: {e}")

    @staticmethod
    def get_activated_bits(alarm_bytes):
        """获取激活的位信息，返回格式为[(ErrWord_index, bit_position), ...]"""
        activated_bits = []
        
        # 记录ErrWord的解析（使用大端序）
        for i in range(min(len(alarm_bytes)//2, 8)):  # 最多8个ErrWord
            first_byte = alarm_bytes[i*2] if i*2 < len(alarm_bytes) else 0
            second_byte = alarm_bytes[i*2+1] if i*2+1 < len(alarm_bytes) else 0
            word_value = (first_byte << 8) | second_byte  # 大端序

            for bit_pos in range(16):
                # 检查从右往左的第bit_pos位是否为1（标准位编号方式）
                if (word_value >> bit_pos) & 1:
                    activated_bits.append((i, bit_pos))
                    
        logger.info(f"激活的位: {activated_bits}")
        return activated_bits

    @staticmethod
    def get_alarm_descriptions_from_bits(activated_bits):
        """根据激活的位信息查询ALARM_MAPPING_DICT，返回对应的报警描述列表"""
        alarm_descriptions = []

        for word_idx, bit_pos in activated_bits:
            # 检查ErrWord索引是否在ALARM_MAPPING_DICT中存在
            if word_idx in ALARM_MAPPING_DICT:
                # 检查该位是否在映射字典中定义
                if bit_pos in ALARM_MAPPING_DICT[word_idx]:
                    alarm_desc = ALARM_MAPPING_DICT[word_idx][bit_pos]
                    alarm_descriptions.append(alarm_desc)
                    logger.info(f"ErrWord{word_idx}的第{bit_pos}位对应报警描述: {alarm_desc}")
                else:
                    logger.warning(f"ErrWord{word_idx}的第{bit_pos}位未在ALARM_MAPPING_DICT中定义")
            else:
                logger.warning(f"ErrWord{word_idx}未在ALARM_MAPPING_DICT中定义")

        logger.info(f"查询到的报警描述: {alarm_descriptions}")
        return alarm_descriptions

    def _start_collection(self):
        """实际启动采集循环"""
        if self._shutting_down:
            return
        self.running_event.set()
        self.thread = threading.Thread(target=self.collect_loop, daemon=True)
        self.thread.start()
        logger.info("报警数据采集器已启动")

    def _start_connect_retry(self):
        """后台重试连接PLC，成功后自动启动采集"""
        def retry_loop():
            delay = 2
            while not self._shutting_down and self.running_event.is_set() is False:
                time.sleep(delay)
                logger.info(f"尝试重新连接PLC ({self.plc_ip})...")
                if self.connect_plc():
                    if self._shutting_down:
                        self.disconnect_plc()
                        return
                    logger.info("PLC重连成功，启动采集")
                    self._start_collection()
                    return
                delay = min(delay * 2, 60)
                logger.warning(f"PLC重连失败，{delay}s后重试")

        t = threading.Thread(target=retry_loop, daemon=True, name="plc-connect-retry")
        t.start()

    def collect_loop(self):
        """数据采集主循环"""
        logger.info("开始报警数据采集循环")

        previous_activated_bits = set()
        consecutive_errors = 0

        while self.running_event.is_set() and not self._shutting_down:
            try:
                # 读取PLC原始报警数据（字节数组）
                raw_alarm_data = self.snap7_client.db_read(2, 0, 52)

                consecutive_errors = 0  # 成功读取，重置错误计数

                # 第一步：获取告警的数据，有哪些字节组的哪些比特位值为1
                activated_bits = self.get_activated_bits(raw_alarm_data)

                # 将当前激活的位转换为集合，便于比较
                current_activated_bits = set(activated_bits)

                # 检查激活的位是否发生了变化
                if current_activated_bits != previous_activated_bits:
                    previous_activated_bits = current_activated_bits

                    # 第二步：在ALARM_MAPPING_DICT查询该值对应的报警描述并返回为数组
                    alarm_descriptions = self.get_alarm_descriptions_from_bits(activated_bits)

                    # 第三步：调用mqtt方法发送事件到物联网平台
                    self.send_alarm_events(alarm_descriptions)
                else:
                    logger.debug("报警状态无变化，跳过处理")

                # 等待下一个采集周期
                time.sleep(self.scan_interval)

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"报警数据采集循环错误(连续{consecutive_errors}次): {e}")

                # 连续失败3次，尝试重连PLC
                if consecutive_errors >= 3:
                    logger.warning("PLC连续读取失败，尝试重连...")
                    try:
                        self.disconnect_plc()
                    except Exception as disc_e:
                        logger.error(f"重连过程中断开PLC异常(忽略，继续重连): {disc_e}")
                    time.sleep(2)
                    try:
                        if self.connect_plc():
                            logger.info("PLC重连成功，恢复采集")
                        else:
                            logger.error("PLC重连失败，等待下次重试")
                            time.sleep(10)
                    except Exception as conn_e:
                        logger.error(f"重连PLC时出现异常: {conn_e}")
                        time.sleep(10)
                    consecutive_errors = 0  # 无论成败都重置，避免每次循环都重连
                else:
                    time.sleep(self.scan_interval)

        logger.info("报警数据采集循环已停止")

    def start(self):
        """启动数据采集线程（支持 stop 后重新启动）"""
        # 检查是否已有健康运行的线程
        if self.running_event.is_set() and self.thread and self.thread.is_alive():
            logger.warning("报警数据采集器已经在运行")
            return

        # 如果有僵尸线程（flag true 但线程已死），清理状态
        if self.running_event.is_set() and (self.thread is None or not self.thread.is_alive()):
            logger.warning("检测到采集线程已意外退出，重置状态重新启动")
            self.running_event.clear()

        # 重置关闭标志，支持 stop 后重新 start
        self._shutting_down = False

        # 尝试连接PLC，失败则后台重试
        if not self.connect_plc():
            logger.warning("首次连接PLC失败，启动后台重连...")
            self._start_connect_retry()
            return

        self._start_collection()

    def stop(self):
        """停止数据采集线程"""
        self._shutting_down = True

        if not self.running_event.is_set():
            logger.info("报警数据采集器未在运行状态")
            self.disconnect_plc()
            return

        # 清除运行标志
        self.running_event.clear()
        logger.info("正在停止报警数据采集器...")

        # 等待采集线程结束
        if self.thread:
            self.thread.join(timeout=5)

        # 断开PLC连接
        self.disconnect_plc()
        logger.info("报警数据采集器已停止")

    def is_healthy(self):
        """健康检查：采集线程是否正常运行"""
        if not self.running_event.is_set():
            return False, "采集器未启动"
        if self.thread is None:
            return False, "采集线程为空"
        if not self.thread.is_alive():
            return False, "采集线程已意外退出"
        # 检查 PLC 连接状态
        try:
            if self.snap7_client and hasattr(self.snap7_client, 'get_connected'):
                if not self.snap7_client.get_connected():
                    return False, "PLC 连接已断开"
        except Exception:
            return False, "无法检查 PLC 连接状态"
        return True, "正常"

    def get_status(self):
        """获取采集器完整状态信息"""
        healthy, reason = self.is_healthy()
        return {
            "running": self.running_event.is_set(),
            "healthy": healthy,
            "reason": reason,
            "plc_ip": self.plc_ip,
            "plc_connected": self.snap7_client is not None and (
                not hasattr(self.snap7_client, 'get_connected') or 
                self.snap7_client.get_connected()
            ) if self.snap7_client else False,
            "scan_interval": self.scan_interval,
            "shutting_down": self._shutting_down,
        }

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
