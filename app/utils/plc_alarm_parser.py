#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PLC报警数据解析工具函数
根据alarms.log文件中的定义解析PLC报警数据
"""

ALARM_DEFINITIONS = {
    # ErrWord0 (字节 0-1)
    0: ("MainPower", "主电源丢失", 0, 8),  # alarm_1
    1: ("LegsNotUp", "支腿未全部抬起", 0, 9),  # alarm_2
    2: ("YawPitchCam", "俯仰和偏航凸轮曲线未生成", 0, 10),  # alarm_3
    3: ("YDistance_Warning", "上下单元 Y 轴接近报警", 0, 11),  # alarm_4
    4: ("YDistance_Error", "上下单元 Y 轴接近故障", 0, 12),  # alarm_5
    5: ("MillTimeLimit", "铣磨程序铣磨次数超限", 0, 13),  # alarm_52
    6: ("LegsNotDown", "支腿未下落", 0, 14),  # alarm_53
    7: ("BladeIDEmpty", "叶片ID为空", 0, 15),  # alarm_55
    8: ("PowerPhaseError", "电源相序故障", 0, 0),  # alarm_58 - 在ErrWord0第0位
    9: ("OilLevelLow", "润化系统油位低", 0, 1),  # alarm_59 - 在ErrWord0第1位
    10: ("WireDiscPosition", "电源线盘位置不合适", 0, 2),  # alarm_56 - 在ErrWord0第2位
    11: ("DriveNotReady", "驱动器未全部就绪", 0, 3),  # alarm_57 - 在ErrWord0第3位
    12: ("EmergencyTriggered", "系统急停触发", 0, 4),  # alarm_60 - 在ErrWord0第4位
    13: ("VacuumPressureAbnormal", "真空除尘系统压力异常", 0, 5),  # alarm_63 - 在ErrWord0第5位
    # 注意: 位6未定义 (字节0的第6位，即ErrWord0的第6位)

    # ErrWord1 (字节 2-3)
    14: ("XNotEnabled", "X 轴未使能", 1, 8),  # alarm_6
    15: ("DU1_YNotEnabled", "下部 Y 轴未使能", 1, 9),  # alarm_7
    16: ("DU1_ZNotEnabled", "下部 Z 轴未使能", 1, 10),  # alarm_8
    17: ("DU1_PITNotEnabled", "下部 俯仰 PIT 轴未使能", 1, 11),  # alarm_9
    18: ("DU1_YAWNotEnabled", "下部 偏航 YAW 轴未使能", 1, 12),  # alarm_10
    19: ("UU2_YNotEnabled", "上部 Y 轴未使能", 1, 13),  # alarm_11
    20: ("UU2_ZNotEnabled", "上部 Z 轴未使能", 1, 14),  # alarm_12
    21: ("UU2_PITNotEnabled", "上部 俯仰 PIT 轴未使能", 1, 15),  # alarm_13
    22: ("UU2_YAWNotEnabled", "上部 偏航 YAW 轴未使能", 1, 0),  # alarm_14

    # ErrWord2 (字节 4-5)
    23: ("XNotHomed", "X 轴未回零", 2, 8),  # alarm_15
    24: ("DU1_YNotHomed", "下部 Y 轴未回零", 2, 9),  # alarm_16
    25: ("DU1_ZNotHomed", "下部 Z 轴未回零", 2, 10),  # alarm_17
    26: ("DU1_PITHomed", "下部 俯仰 PIT 轴未回零", 2, 11),  # alarm_18
    27: ("DU1_YAWNotHomed", "下部 偏航 YAW 轴未回零", 2, 12),  # alarm_19
    28: ("UU2_YNotHomed", "上部 Y 轴未回零", 2, 13),  # alarm_20
    29: ("UU2_ZNotHomed", "上部 Z 轴未回零", 2, 14),  # alarm_21
    30: ("UU2_PITHomed", "上部 俯仰 PIT 轴未回零", 2, 15),  # alarm_22
    31: ("UU2_YAWNotHomed", "上部 偏航 YAW 轴未回零", 2, 0),  # alarm_23

    # ErrWord3 (字节 6-7)
    32: ("XError", "X 轴故障", 3, 8),  # alarm_24
    33: ("DU1_YError", "下部 Y 轴故障", 3, 9),  # alarm_25
    34: ("DU1_ZError", "下部 Z 轴故障", 3, 10),  # alarm_26
    35: ("DU1_PITEError", "下部 俯仰 PIT 轴故障", 3, 11),  # alarm_27
    36: ("DU1_YAWError", "下部 偏航 YAW 轴故障", 3, 12),  # alarm_28
    37: ("UU2_YError", "上部 Y 轴故障", 3, 13),  # alarm_29
    38: ("UU2_ZError", "上部 Z 轴故障", 3, 14),  # alarm_30
    39: ("UU2_PITEError", "上部 俯仰 PIT 轴故障", 3, 15),  # alarm_31
    40: ("UU2_YAWError", "上部 偏航 YAW 轴故障", 3, 0),  # alarm_32

    # ErrWord4 (字节 8-9)
    41: ("MillDownFCError", "下部铣磨单元变频器故障", 4, 8),  # alarm_33
    42: ("MillDownRPMError", "下部铣磨单元 RPM 故障", 4, 9),  # alarm_34
    43: ("MillDownBlockedError", "下部铣磨单元堵转故障", 4, 10),  # alarm_35
    44: ("MillDownPowerWarning", "下部铣磨单元功率过高警告", 4, 11),  # alarm_36
    45: ("MillDownPowerError", "下部铣磨单元功率过高故障", 4, 12),  # alarm_37

    # ErrWord5 (字节 10-11)
    46: ("MillUpFCError", "上部铣磨单元变频器故障", 5, 8),  # alarm_38
    47: ("MillUpRPMError", "上部铣磨单元 RPM 故障", 5, 9),  # alarm_39
    48: ("MillUpBlockedError", "上部铣磨单元堵转故障", 5, 10),  # alarm_40
    49: ("MillUpPowerWarning", "上部铣磨单元功率过高警告", 5, 11),  # alarm_41
    50: ("MillUpPowerError", "上部铣磨单元功率过高故障", 5, 12),  # alarm_42

    # ErrWord6 (字节 12-13)
    51: ("ScanOutOfRange", "扫描范围超出单元正负限位", 6, 8),  # alarm_43
    52: ("ScannerErr", "扫描器通信超时", 6, 9),  # alarm_44
    53: ("ScanResultCalcError", "扫描结果计算出错", 6, 10),  # alarm_45
    54: ("ScanResultRadiusError", "扫描结果叶片半径估计偏差过大", 6, 11),  # alarm_54
    55: ("MillDepthOver", "铣磨深度大于 3.5mm，需要确认", 6, 12),  # alarm_61
    56: ("ScrewCountLow", "扫描螺栓套数量过少", 6, 13),  # alarm_62

    # ErrWord7 (字节 14-15)
    57: ("MillDownMotionError", "下部单元铣磨运动故障", 7, 8),  # alarm_46
    58: ("MillPathOver", "铣磨路径超出单元正负限制", 7, 9),  # alarm_47
    59: ("MillDownArcMotionError", "下部单元圆弧运动路径出错", 7, 10),  # alarm_48
    60: ("MillUpMotionError", "上部单元铣磨运动故障", 7, 11),  # alarm_49
    61: ("MillUpCurveNotCreated", "上部单元凸轮曲线未创建", 7, 12),  # alarm_50
    62: ("MillUpSyncNotComplete", "上部单元同步未完成", 7, 13),  # alarm_51
}

# 报警映射字典，将ErrWord编号和比特位号映射到告警编号
# 格式: {ErrWord编号: {比特位号: 告警编号}}
ALARM_MAPPING_DICT = {
    0: {  # ErrWord0
        0: 8,   # PowerPhaseError - 电源相序故障
        1: 9,   # OilLevelLow - 润化系统油位低
        2: 10,  # WireDiscPosition - 电源线盘位置不合适
        3: 11,  # DriveNotReady - 驱动器未全部就绪
        4: 12,  # EmergencyTriggered - 系统急停触发
        5: 13,  # VacuumPressureAbnormal - 真空除尘系统压力异常
        8: 0,   # MainPower - 主电源丢失
        9: 1,   # LegsNotUp - 支腿未全部抬起
        10: 2,  # YawPitchCam - 俯仰和偏航凸轮曲线未生成
        11: 3,  # YDistance_Warning - 上下单元 Y 轴接近报警
        12: 4,  # YDistance_Error - 上下单元 Y 轴接近故障
        13: 5,  # MillTimeLimit - 铣磨程序铣磨次数超限
        14: 6,  # LegsNotDown - 支腿未下落
        15: 7,  # BladeIDEmpty - 叶片ID为空
    },
    1: {  # ErrWord1
        0: 22,  # UU2_YAWNotEnabled - 上部 偏航 YAW 轴未使能
        8: 14,  # XNotEnabled - X 轴未使能
        9: 15,  # DU1_YNotEnabled - 下部 Y 轴未使能
        10: 16, # DU1_ZNotEnabled - 下部 Z 轴未使能
        11: 17, # DU1_PITNotEnabled - 下部 俯仰 PIT 轴未使能
        12: 18, # DU1_YAWNotEnabled - 下部 偏航 YAW 轴未使能
        13: 19, # UU2_YNotEnabled - 上部 Y 轴未使能
        14: 20, # UU2_ZNotEnabled - 上部 Z 轴未使能
        15: 21, # UU2_PITNotEnabled - 上部 俯仰 PIT 轴未使能
    },
    2: {  # ErrWord2
        0: 31,  # UU2_YAWNotHomed - 上部 偏航 YAW 轴未回零
        8: 23,  # XNotHomed - X 轴未回零
        9: 24,  # DU1_YNotHomed - 下部 Y 轴未回零
        10: 25, # DU1_ZNotHomed - 下部 Z 轴未回零
        11: 26, # DU1_PITHomed - 下部 俯仰 PIT 轴未回零
        12: 27, # DU1_YAWNotHomed - 下部 偏航 YAW 轴未回零
        13: 28, # UU2_YNotHomed - 上部 Y 轴未回零
        14: 29, # UU2_ZNotHomed - 上部 Z 轴未回零
        15: 30, # UU2_PITHomed - 上部 俯仰 PIT 轴未回零
    },
    3: {  # ErrWord3
        0: 40,  # UU2_YAWError - 上部 偏航 YAW 轴故障
        8: 32,  # XError - X 轴故障
        9: 33,  # DU1_YError - 下部 Y 轴故障
        10: 34, # DU1_ZError - 下部 Z 轴故障
        11: 35, # DU1_PITEError - 下部 俯仰 PIT 轴故障
        12: 36, # DU1_YAWError - 下部 偏航 YAW 轴故障
        13: 37, # UU2_YError - 上部 Y 轴故障
        14: 38, # UU2_ZError - 上部 Z 轴故障
        15: 39, # UU2_PITEError - 上部 俯仰 PIT 轴故障
    },
    4: {  # ErrWord4
        8: 41,  # MillDownFCError - 下部铣磨单元变频器故障
        9: 42,  # MillDownRPMError - 下部铣磨单元 RPM 故障
        10: 43, # MillDownBlockedError - 下部铣磨单元堵转故障
        11: 44, # MillDownPowerWarning - 下部铣磨单元功率过高警告
        12: 45, # MillDownPowerError - 下部铣磨单元功率过高故障
    },
    5: {  # ErrWord5
        8: 46,  # MillUpFCError - 上部铣磨单元变频器故障
        9: 47,  # MillUpRPMError - 上部铣磨单元 RPM 故障
        10: 48, # MillUpBlockedError - 上部铣磨单元堵转故障
        11: 49, # MillUpPowerWarning - 上部铣磨单元功率过高警告
        12: 50, # MillUpPowerError - 上部铣磨单元功率过高故障
    },
    6: {  # ErrWord6
        8: 51,  # ScanOutOfRange - 扫描范围超出单元正负限位
        9: 52,  # ScannerErr - 扫描器通信超时
        10: 53, # ScanResultCalcError - 扫描结果计算出错
        11: 54, # ScanResultRadiusError - 扫描结果叶片半径估计偏差过大
        12: 55, # MillDepthOver - 铣磨深度大于 3.5mm，需要确认
        13: 56, # ScrewCountLow - 扫描螺栓套数量过少
    },
    7: {  # ErrWord7
        8: 57,  # MillDownMotionError - 下部单元铣磨运动故障
        9: 58,  # MillPathOver - 铣磨路径超出单元正负限制
        10: 59, # MillDownArcMotionError - 下部单元圆弧运动路径出错
        11: 60, # MillUpMotionError - 上部单元铣磨运动故障
        12: 61, # MillUpCurveNotCreated - 上部单元凸轮曲线未创建
        13: 62, # MillUpSyncNotComplete - 上部单元同步未完成
    }
}