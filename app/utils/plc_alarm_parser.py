#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PLC报警数据解析工具函数
根据alarms.log文件中的定义解析PLC报警数据
"""

# 报警映射字典，将ErrWord编号和比特位号映射到告警描述
# 格式: {ErrWord编号: {比特位号: 告警描述}}
ALARM_MAPPING_DICT = {
    0: {  # ErrWord0
        0: "电源相序故障",   # PowerPhaseError
        1: "润化系统油位低",   # OilLevelLow
        2: "电源线盘位置不合适",  # WireDiscPosition
        3: "驱动器未全部就绪",  # DriveNotReady
        4: "系统急停触发",  # EmergencyTriggered
        5: "真空除尘系统压力异常",  # VacuumPressureAbnormal
        8: "主电源丢失",   # MainPower
        9: "支腿未全部抬起",   # LegsNotUp
        10: "俯仰和偏航凸轮曲线未生成",  # YawPitchCam
        11: "上下单元 Y 轴接近报警",  # YDistance_Warning
        12: "上下单元 Y 轴接近故障",  # YDistance_Error
        13: "铣磨程序铣磨次数超限",  # MillTimeLimit
        14: "支腿未下落",  # LegsNotDown
        15: "叶片ID为空",  # BladeIDEmpty
    },
    1: {  # ErrWord1
        0: "上部 偏航 YAW 轴未使能",  # UU2_YAWNotEnabled
        8: "X 轴未使能",  # XNotEnabled
        9: "下部 Y 轴未使能",  # DU1_YNotEnabled
        10: "下部 Z 轴未使能", # DU1_ZNotEnabled
        11: "下部 俯仰 PIT 轴未使能", # DU1_PITNotEnabled
        12: "下部 偏航 YAW 轴未使能", # DU1_YAWNotEnabled
        13: "上部 Y 轴未使能", # UU2_YNotEnabled
        14: "上部 Z 轴未使能", # UU2_ZNotEnabled
        15: "上部 俯仰 PIT 轴未使能", # UU2_PITNotEnabled
    },
    2: {  # ErrWord2
        0: "上部 偏航 YAW 轴未回零",  # UU2_YAWNotHomed
        8: "X 轴未回零",  # XNotHomed
        9: "下部 Y 轴未回零",  # DU1_YNotHomed
        10: "下部 Z 轴未回零", # DU1_ZNotHomed
        11: "下部 俯仰 PIT 轴未回零", # DU1_PITHomed
        12: "下部 偏航 YAW 轴未回零", # DU1_YAWNotHomed
        13: "上部 Y 轴未回零", # UU2_YNotHomed
        14: "上部 Z 轴未回零", # UU2_ZNotHomed
        15: "上部 俯仰 PIT 轴未回零", # UU2_PITHomed
    },
    3: {  # ErrWord3
        0: "上部 偏航 YAW 轴故障",  # UU2_YAWError
        8: "X 轴故障",  # XError
        9: "下部 Y 轴故障",  # DU1_YError
        10: "下部 Z 轴故障", # DU1_ZError
        11: "下部 俯仰 PIT 轴故障", # DU1_PITEError
        12: "下部 偏航 YAW 轴故障", # DU1_YAWError
        13: "上部 Y 轴故障", # UU2_YError
        14: "上部 Z 轴故障", # UU2_ZError
        15: "上部 俯仰 PIT 轴故障", # UU2_PITEError
    },
    4: {  # ErrWord4
        8: "下部铣磨单元变频器故障",  # MillDownFCError
        9: "下部铣磨单元 RPM 故障",  # MillDownRPMError
        10: "下部铣磨单元堵转故障", # MillDownBlockedError
        11: "下部铣磨单元功率过高警告", # MillDownPowerWarning
        12: "下部铣磨单元功率过高故障", # MillDownPowerError
    },
    5: {  # ErrWord5
        8: "上部铣磨单元变频器故障",  # MillUpFCError
        9: "上部铣磨单元 RPM 故障",  # MillUpRPMError
        10: "上部铣磨单元堵转故障", # MillUpBlockedError
        11: "上部铣磨单元功率过高警告", # MillUpPowerWarning
        12: "上部铣磨单元功率过高故障", # MillUpPowerError
    },
    6: {  # ErrWord6
        8: "扫描范围超出单元正负限位",  # ScanOutOfRange
        9: "扫描器通信超时",  # ScannerErr
        10: "扫描结果计算出错", # ScanResultCalcError
        11: "扫描结果叶片半径估计偏差过大", # ScanResultRadiusError
        12: "铣磨深度大于 3.5mm，需要确认", # MillDepthOver
        13: "扫描螺栓套数量过少", # ScrewCountLow
    },
    7: {  # ErrWord7
        8: "下部单元铣磨运动故障",  # MillDownMotionError
        9: "铣磨路径超出单元正负限制",  # MillPathOver
        10: "下部单元圆弧运动路径出错", # MillDownArcMotionError
        11: "上部单元铣磨运动故障", # MillUpMotionError
        12: "上部单元凸轮曲线未创建", # MillUpCurveNotCreated
        13: "上部单元同步未完成", # MillUpSyncNotComplete
    }
}