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

    def send_alarm_events(self, alarm_descriptions):
        """发送报警事件到物联网平台"""
        try:
            # 检查是否有报警
            if not hasattr(self, '_previous_active_alarms'):
                self._previous_active_alarms = set()

            current_active_alarms = set(alarm_descriptions)
            
            # 计算新增的报警和解除的报警
            new_alarms = current_active_alarms - self._previous_active_alarms
            resolved_alarms = self._previous_active_alarms - current_active_alarms

            # 将报警描述转换为markdown格式的富文本字符串
            alarms_markdown = "\n".join([f"- {desc}" for desc in sorted(current_active_alarms)])

            # 创建报警事件数据 - 发送当前所有激活的报警
            alarm_event_data = {
                "alarms": alarms_markdown
            }

            # 发送报警事件
            result = self.mqtt_publisher.publish_event("alarm_log", alarm_event_data)
            if result:
                if new_alarms:
                    logger.info(f"新增报警: {sorted(list(new_alarms))}")
                if resolved_alarms:
                    logger.info(f"解除报警: {sorted(list(resolved_alarms))}")
                logger.info(f"报警事件成功发送到物联网平台: {sorted(list(current_active_alarms))}")
            else:
                logger.error(f"发送报警事件到物联网平台失败: {sorted(list(current_active_alarms))}")

            # 更新上一次的报警状态
            self._previous_active_alarms = current_active_alarms

        except Exception as e:
            logger.error(f"发送报警事件到物联网平台时出错: {e}")

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

    def get_activated_bits(self, alarm_bytes):
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

    def get_alarm_descriptions_from_bits(self, activated_bits):
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

    def collect_loop(self):
        """数据采集主循环"""
        logger.info("开始报警数据采集循环")
        
        # 初始化上一次的激活位状态
        previous_activated_bits = set()

        while self.running_event.is_set():
            try:
                # 读取PLC原始报警数据（字节数组）
                raw_alarm_data = self.snap7_client.db_read(2, 0, 52)

                # 第一步：获取告警的数据，有哪些字节组的哪些比特位值为1
                activated_bits = self.get_activated_bits(raw_alarm_data)
                
                # 将当前激活的位转换为集合，便于比较
                current_activated_bits = set(activated_bits)

                # 检查激活的位是否发生了变化
                if current_activated_bits != previous_activated_bits:
                    # 更新上一次的激活位状态
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
