import time
import threading
from opcua import ua, Client
import ctypes as ct
import pandas as pd
import numpy as np
from enum import IntEnum
import math
import os
from app.utils.mqtt_utils.publisher import JetLinksMQTTPublisher
from app.utils.logging_config import setup_logger

logger = setup_logger()

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # Project root
# global variables
# -----
LASERIP = (192, 168, 2, 10)
LASERID = 0
PLCUA_IP = '192.168.3.1'
PLCUA_PORT = '4840'
COM_INTERVAL = 2.0                  # check shutdown windows and scan command interval
BEFOREMILL_RAW_DATA_FILE = os.path.join(BASE_DIR, 'test', 'raw_data.csv')        # before mill raw data saved path
BEFOREMILL_CIRCLE_FILE = os.path.join(BASE_DIR, 'test', 'cir_data.csv')          # before mill circle data saved path
AFTERMILL_RAW_DATA_FILE = os.path.join(BASE_DIR, 'test', 'raw_data_a.csv')        # after mill raw data saved path
AFTERMILL_CIRCLE_FILE = os.path.join(BASE_DIR, 'test', 'cir_data_a.csv')          # after mill circle data saved path
TEMPLATE_FILE = os.path.join(BASE_DIR, 'test', 'Flatness.xlsx')
COMPEN_FILE = os.path.join(BASE_DIR, 'test', 'compTable.csv')                     # Compensation file

LASER_RESOLUTION = 160              ## scancontrol # laser resolution used
SCANNER_TYPE = ct.c_int(0)          ## scancontrol # scanner type

# SCANNER_RANGE = [190.0, 290.0]      ## scancontrol # range of the laser
SCANNER_RANGE = [156.0, 444.0]      ## sincevision # range of the laser

MIN_LINE_WINDOW = 10                # minimum line width
ZCHANGE_DETECT_SET = 5.0            # consider as value change for z

BOLTS_DISTANCE = 44.0 + 4.0               # length to distinguish a bolt
BOLT_RADIUS = [(BOLTS_DISTANCE - 10.0)/2.0 , (BOLTS_DISTANCE + 8.0)/2.0]              # the blot Radius range

BOLT_SURFACE_DIFF = 2.0             # blot surface maximum differenc
MIN_CIRCLE_PTS = 8                 # minimum points for find circle center
COMP_XOFFSET = 200.0                # Compensation x distance
COMP_YOFFSET = 180.0                # Compensation y distance
MAX_MILL_DEEPTH = 16.0              # maximum milling deepth
FLATNESS_RATIO = 0.40               # Flatness reduce Ratio
BOLT_AMOUNT = 188                   # bolt amount

# Scan motion enum
class ScanMotion(IntEnum):
    Idle = 0
    Prepare = 1
    Move = 2
    Record = 3
    Stop = 4
    Finish = 6
    Stop_WithoutCalc = 14
    Stop_WithFlatness = 24

# Scan motion enum
class ScanResult(IntEnum):
    Idle = 0
    RecordSaved = 1
    Compute = 2
    Succuss = 3
    Failure = 4

class PLCDataCollector:
    """
    PLC数据采集器，运行在独立线程中
    """
    def __init__(self, plc_ip='192.168.3.1', plc_port='4840', scan_interval=2.0, mqtt_publisher=None):
        self.plc_ip = plc_ip
        self.plc_port = plc_port
        self.scan_interval = scan_interval
        self.client = None
        self.nodes = {}
        self.running = False
        self.thread = None
        self.mqtt_publisher = mqtt_publisher  # 外部传入的MQTT实例

        # 定义需要监控的节点
        self.node_definitions = {
            'ShutdownPC': 'ns=3;s="GDB_Config"."ShutdownPC"',
            'XAxis': 'ns=3;s="GDB_X"."Status_XAxis"."ActualPosition"',
            'YAxis': 'ns=3;s="GDB_UU2"."Status_YAxis"."ActualPosition"',  # UPUNIT condition
            'ZAxis': 'ns=3;s="GDB_UU2"."Status_ZAxis"."ActualPosition"',  # UPUNIT condition
            'ScanStatus': 'ns=3;s="GDB_ScanPoints"."ScanStatus"',
            'ScannerOK': 'ns=3;s="GDB_ScanPoints"."ScannerOK"',
            'ScanResult': 'ns=3;s="GDB_ScanPoints"."ScanResult"',
            'ScannerZ': 'ns=3;s="GDB_ScanPoints"."ScannerZ"',
            'BladeZ': 'ns=3;s="GDB_ScanPoints"."ScannerBladeZ"',
            'BoltZ': 'ns=3;s="GDB_ScanPoints"."ScannerBoltZ"',
            'Center_x': 'ns=3;s="GDB_Config"."BladeInfo"."Center"."x"',
            'Center_y': 'ns=3;s="GDB_Config"."BladeInfo"."Center"."y"',
            'Center_z': 'ns=3;s="GDB_Config"."BladeInfo"."Center"."z"',
            'Yaw': 'ns=3;s="GDB_Config"."BladeInfo"."Yaw"',
            'Pitch': 'ns=3;s="GDB_Config"."BladeInfo"."Pitch"',
            'RadiusEst': 'ns=3;s="GDB_Config"."BladeInfo"."RadiusEst"',
            'Max_z': 'ns=3;s="GDB_Config"."BladeInfo"."MAX_Z"',
            'Min_z': 'ns=3;s="GDB_Config"."BladeInfo"."MIN_Z"',
            'Bolt_Diameter': 'ns=3;s="GDB_Status"."BladeSettings"."BoltInnerDiameter"',
            'Bolt_Height': 'ns=3;s="GDB_Status"."BladeSettings"."BoltHeight"',
            'Bolt_Amount': 'ns=3;s="GDB_Status"."BladeSettings"."BoltAmount"',
            'Bolt_Found': 'ns=3;s="GDB_Status"."ScanResult"."BoltFound"',
            'Balde_ID': 'ns=3;s="GDB_BladeSettings"."BladeID"',
            'Peak_Valley': 'ns=3;s="GDB_BladeSettings"."PeakValley"'
        }

    def connect_plc(self):
        """连接到PLC"""
        try:
            url = f"opc.tcp://{self.plc_ip}:{self.plc_port}"
            self.client = Client(url)
            self.client.connect()
            
            # 获取所有需要监控的节点
            for name, node_id in self.node_definitions.items():
                try:
                    self.nodes[name] = self.client.get_node(node_id)
                except Exception as e:
                    logger.error(f"获取节点 {name} ({node_id}) 失败: {e}")
            
            logger.info(f"成功连接到PLC at {url}")
            return True
        except Exception as e:
            logger.error(f"连接PLC失败: {e}")
            return False

    def disconnect_plc(self):
        """断开PLC连接"""
        if self.client and self.client.is_connected():
            self.client.disconnect()
            logger.info("已断开PLC连接")

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
                "plc_data": data
            }

            # 确保MQTT已连接
            if not self.mqtt_publisher or not self.mqtt_publisher.is_connected:
                logger.warning("MQTT未连接")
                return False

            # 发布到MQTT主题
            result = self.mqtt_publisher.publish_telemetry(telemetry_data)
            if result:
                logger.info("PLC数据成功发送到物联网平台")
            else:
                logger.error("发送PLC数据到物联网平台失败")

        except Exception as e:
            logger.error(f"发送数据到物联网平台时出错: {e}")

    def read_plc_data(self):
        """读取PLC数据"""
        plc_data = {}
        for name, node in self.nodes.items():
            try:
                value = node.get_value()
                plc_data[name] = value
            except Exception as e:
                logger.error(f"读取节点 {name} 的值失败: {e}")
        
        return plc_data

    def collect_loop(self):
        """数据采集主循环"""
        logger.info("开始PLC数据采集循环")
        while self.running:
            try:
                # 读取PLC数据
                plc_data = self.read_plc_data()

                # 发送数据到物联网平台
                self.send_data_to_iot_platform(plc_data)

                # 等待下一个采集周期
                time.sleep(self.scan_interval)

            except Exception as e:
                logger.error(f"数据采集循环中出现错误: {e}")
                time.sleep(self.scan_interval)  # 继续尝试

        logger.info("PLC数据采集循环已停止")

    def start(self):
        """启动数据采集线程"""
        if self.running:
            logger.warning("PLC数据采集器已经在运行")
            return

        # 连接到PLC
        if not self.connect_plc():
            logger.error("无法连接到PLC，无法启动采集器")
            return

        # 不再连接MQTT，因为使用的是外部传入的实例

        self.running = True
        self.thread = threading.Thread(target=self.collect_loop, daemon=True)
        self.thread.start()
        logger.info("PLC数据采集器已启动")

    def stop(self):
        """停止数据采集线程"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)  # 等待最多5秒让线程结束
        self.disconnect_plc()
        # 不再断开MQTT连接，因为那是主应用的责任
        logger.info("PLC数据采集器已停止")


# 全局实例（将在main.py中初始化）
plc_collector = None


def initialize_plc_collector(mqtt_publisher=None):
    """初始化PLC数据采集器，接收MQTT发布器实例"""
    global plc_collector
    plc_collector = PLCDataCollector(mqtt_publisher=mqtt_publisher)
    return plc_collector


def start_plc_collection():
    """启动PLC数据采集"""
    if plc_collector:
        plc_collector.start()
    else:
        logger.error("PLC采集器未初始化")


def stop_plc_collection():
    """停止PLC数据采集"""
    if plc_collector:
        plc_collector.stop()


# 为了保持向后兼容性，提供一个函数来运行旧的server.py风格的循环
def run_old_server_style():
    """
    此函数是为了向后兼容而保留的，模拟旧的server.py行为
    但现在推荐使用PLCDataCollector类
    """
    print("注意：此函数已过时，建议使用PLCDataCollector类进行数据采集")
    if plc_collector:
        plc_collector.start()


# 添加来自server.py的数据处理函数
def findLines(z_s2):
    """
    从扫描数据中查找线条
    """
    # remove bad points
    for i in range(len(z_s2)):
        if z_s2[i] < SCANNER_RANGE[0] or z_s2[i] > SCANNER_RANGE[1]:
            # z_s2[i] = 0.0
            pass

    # find lines, stored in lines_z
    cur_zindex, lines_z = 0, [[z_s2[0], 0]]
    for z in z_s2:
        if abs(z - lines_z[cur_zindex][0]) < ZCHANGE_DETECT_SET:
            lines_z[cur_zindex][0] = (z + lines_z[cur_zindex][0] * lines_z[cur_zindex][1]) / \
                                        (lines_z[cur_zindex][1] + 1.0)
            lines_z[cur_zindex][1] += 1
            continue
        else:
            exist_already = False
            for lz_ind in range(len(lines_z)):
                if abs(z - lines_z[lz_ind][0]) < ZCHANGE_DETECT_SET:
                    exist_already = True
                    cur_zindex = lz_ind
                    break
            if not exist_already:
                lines_z.append([z, 0])
                cur_zindex = -1
            lines_z[cur_zindex][0] = (z + lines_z[cur_zindex][0] * lines_z[cur_zindex][1]) / \
                                        (lines_z[cur_zindex][1] + 1.0)
            lines_z[cur_zindex][1] += 1

    # sort by the points amount
    lines_z = sorted(lines_z, key=lambda x: x[1], reverse=True)

    z_avg, z_blade, z_bolt = 0.0, 0.0, 0.0
    if len(lines_z) == 1:
        z_avg, z_blade = lines_z[0][0], lines_z[0][0]
    elif len(lines_z) >= 2:
        if lines_z[1][0] > SCANNER_RANGE[0]:
            if lines_z[0][0] > SCANNER_RANGE[0]:
                if lines_z[1][0] > lines_z[0][0]:
                    z_avg = lines_z[1][0]
                else:
                    z_avg = lines_z[0][0]
            else:
                z_avg = lines_z[1][0]
        else:
            z_avg = lines_z[0][0]

        cnt_blade, cnt_bolt = 0.0, 0.0
        for z in z_s2:
            if z >= z_avg and z < (z_avg + ZCHANGE_DETECT_SET):
                z_blade = (z_blade * cnt_blade + z) / (cnt_blade + 1.0)
                cnt_blade += 1.0
            elif z < z_avg and z > SCANNER_RANGE[0]:
                z_bolt = (z_bolt * cnt_bolt + z) / (cnt_bolt + 1.0)
                cnt_bolt += 1.0

    return (lines_z, z_avg, z_blade, z_bolt)


def fitcircle(circle):
    """
    拟合圆形
    """
    Mat_A = np.zeros((len(circle), 3))
    Vec_y = np.zeros(len(circle))
    Vec_z = np.zeros(len(circle))
    indx, z_avg = 0, 0.0
    for item in circle:
        Mat_A[indx, 0] = item['x']
        Mat_A[indx, 1] = item['y']
        Mat_A[indx, 2] = 1.0
        Vec_y[indx] = -1.0 * (item['x'] ** 2 + item['y'] ** 2)
        Vec_z[indx] = item['z']
        indx += 1
    Mat_AT = Mat_A.T
    (a, b, c) = np.linalg.inv(Mat_AT @ Mat_A) @ (Mat_AT @ Vec_y)
    (x0, y0, r) = (-a / 2.0, -b / 2.0, np.sqrt(a * a / 4.0 + b * b / 4.0 - c))
    return (x0, y0, np.median(Vec_z), r)


def findBladeInfo(df):
    """
    查找叶片信息
    """
    amount = len(df)
    circle_A1 = np.zeros((3, amount))
    circle = []
    for key, value in df.iterrows():
        circle.append({'x': value['x'], 'y': value['y'], 'z': value['z']})
        circle_A1[0][key], circle_A1[1][key], circle_A1[2][key] = value['x'], value['y'], value['z']

    # find 2D circle
    (x0, y0, z_avg, r) = fitcircle(circle)

    norm_vec = np.linalg.inv(np.dot(circle_A1, circle_A1.T)) @ circle_A1 @ np.ones(amount)
    d_err = ((norm_vec @ circle_A1) - 1.) / np.sqrt((norm_vec**2).sum())

    # estimated angle
    angle_x_est = np.arctan2(-norm_vec[1], norm_vec[2])
    angle_y_est = np.arctan2(norm_vec[0], np.sqrt(np.square(norm_vec[1]) + np.square(norm_vec[2])))

    # estimate 3D circle center
    circle_A_2sum = (circle_A1**2).sum(axis=0)
    Delta_L = ((circle_A_2sum[1:] - circle_A_2sum[:amount-1])/2.).reshape(amount-1, 1)
    Delta_B = circle_A1[:, 1:] - circle_A1[:, :amount-1]
    D = np.hstack((np.vstack((Delta_B @ Delta_B.T, norm_vec)),
                np.array([[norm_vec[0]], [norm_vec[1]], [norm_vec[2]], [0.]])))
    L = np.vstack((Delta_B @ Delta_L, np.array([[1.]])))
    center = np.linalg.inv(D) @ L

    # estimate circle radius
    r_i = np.sqrt(((circle_A1 - center[:3])**2).sum(axis=0))
    r_est = r_i.mean()
    r_err = (r_i - r_est)/r_est * 100.0

    flatness = pd.DataFrame(columns=['x', 'y', 'z', 'd_err'])
    for key, value in df.iterrows():
        flatness.loc[len(flatness)] = [value['x'], value['y'], value['z'], d_err[key]]

    # angle_x_est is yaw, angle_y_est is pitch, d_err is flatness
    return center[:3], r_est,  math.degrees(angle_x_est), math.degrees(angle_y_est), [d_err.min(), d_err.max()], flatness, norm_vec


# 全局实例
plc_collector = PLCDataCollector()


def start_plc_collection():
    """启动PLC数据采集"""
    plc_collector.start()


def stop_plc_collection():
    """停止PLC数据采集"""
    plc_collector.stop()


# 为了保持向后兼容性，提供一个函数来运行旧的server.py风格的循环
def run_old_server_style():
    """
    此函数是为了向后兼容而保留的，模拟旧的server.py行为
    但现在推荐使用PLCDataCollector类
    """
    print("注意：此函数已过时，建议使用PLCDataCollector类进行数据采集")
    plc_collector.start()