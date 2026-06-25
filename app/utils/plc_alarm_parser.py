#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PLC报警数据解析工具函数
根据alarms.log文件中的定义解析PLC报警数据
"""

def get_alarm_definitions():
    """
    根据alarms.log文件内容定义报警结构
    格式: (报警名称, 描述, ErrWord索引, 位位置)
    """
    alarm_definitions = [
        # ErrWord0 (字节 0-1)
        ("MainPower", "主电源丢失", 0, 8),      # alarm_1
        ("LegsNotUp", "支腿未全部抬起", 0, 9),  # alarm_2
        ("YawPitchCam", "俯仰和偏航凸轮曲线未生成", 0, 10),  # alarm_3
        ("YDistance_Warning", "上下单元 Y 轴接近报警", 0, 11),  # alarm_4
        ("YDistance_Error", "上下单元 Y 轴接近故障", 0, 12),  # alarm_5
        ("MillTimeLimit", "铣磨程序铣磨次数超限", 0, 13), # alarm_52
        ("LegsNotDown", "支腿未下落", 0, 14), # alarm_53
        ("BladeIDEmpty", "叶片ID为空", 0, 15), # alarm_55
        ("PowerPhaseError", "电源相序故障", 0, 0), # alarm_58 - 在ErrWord0第0位
        ("OilLevelLow", "润化系统油位低", 0, 1), # alarm_59 - 在ErrWord0第1位
        ("WireDiscPosition", "电源线盘位置不合适", 0, 2), # alarm_56 - 在ErrWord0第2位
        ("DriveNotReady", "驱动器未全部就绪", 0, 3), # alarm_57 - 在ErrWord0第3位
        ("EmergencyTriggered", "系统急停触发", 0, 4), # alarm_60 - 在ErrWord0第4位
        ("VacuumPressureAbnormal", "真空除尘系统压力异常", 0, 5), # alarm_63 - 在ErrWord0第5位
        # 注意: 位6未定义 (字节0的第6位，即ErrWord0的第6位)
        
        # ErrWord1 (字节 2-3)
        ("XNotEnabled", "X 轴未使能", 1, 8),    # alarm_6
        ("DU1_YNotEnabled", "下部 Y 轴未使能", 1, 9),  # alarm_7
        ("DU1_ZNotEnabled", "下部 Z 轴未使能", 1, 10),  # alarm_8
        ("DU1_PITNotEnabled", "下部 俯仰 PIT 轴未使能", 1, 11),  # alarm_9
        ("DU1_YAWNotEnabled", "下部 偏航 YAW 轴未使能", 1, 12),  # alarm_10
        ("UU2_YNotEnabled", "上部 Y 轴未使能", 1, 13),  # alarm_11
        ("UU2_ZNotEnabled", "上部 Z 轴未使能", 1, 14),  # alarm_12
        ("UU2_PITNotEnabled", "上部 俯仰 PIT 轴未使能", 1, 15),  # alarm_13
        ("UU2_YAWNotEnabled", "上部 偏航 YAW 轴未使能", 1, 0),  # alarm_14
        
        # ErrWord2 (字节 4-5)
        ("XNotHomed", "X 轴未回零", 2, 8),      # alarm_15
        ("DU1_YNotHomed", "下部 Y 轴未回零", 2, 9),  # alarm_16
        ("DU1_ZNotHomed", "下部 Z 轴未回零", 2, 10),  # alarm_17
        ("DU1_PITHomed", "下部 俯仰 PIT 轴未回零", 2, 11),  # alarm_18
        ("DU1_YAWNotHomed", "下部 偏航 YAW 轴未回零", 2, 12),  # alarm_19
        ("UU2_YNotHomed", "上部 Y 轴未回零", 2, 13),  # alarm_20
        ("UU2_ZNotHomed", "上部 Z 轴未回零", 2, 14),  # alarm_21
        ("UU2_PITHomed", "上部 俯仰 PIT 轴未回零", 2, 15),  # alarm_22
        ("UU2_YAWNotHomed", "上部 偏航 YAW 轴未回零", 2, 0),  # alarm_23
        
        # ErrWord3 (字节 6-7)
        ("XError", "X 轴故障", 3, 8),           # alarm_24
        ("DU1_YError", "下部 Y 轴故障", 3, 9),  # alarm_25
        ("DU1_ZError", "下部 Z 轴故障", 3, 10), # alarm_26
        ("DU1_PITEError", "下部 俯仰 PIT 轴故障", 3, 11), # alarm_27
        ("DU1_YAWError", "下部 偏航 YAW 轴故障", 3, 12), # alarm_28
        ("UU2_YError", "上部 Y 轴故障", 3, 13), # alarm_29
        ("UU2_ZError", "上部 Z 轴故障", 3, 14), # alarm_30
        ("UU2_PITEError", "上部 俯仰 PIT 轴故障", 3, 15), # alarm_31
        ("UU2_YAWError", "上部 偏航 YAW 轴故障", 3, 0), # alarm_32
        
        # ErrWord4 (字节 8-9)
        ("MillDownFCError", "下部铣磨单元变频器故障", 4, 8), # alarm_33
        ("MillDownRPMError", "下部铣磨单元 RPM 故障", 4, 9), # alarm_34
        ("MillDownBlockedError", "下部铣磨单元堵转故障", 4, 10), # alarm_35
        ("MillDownPowerWarning", "下部铣磨单元功率过高警告", 4, 11), # alarm_36
        ("MillDownPowerError", "下部铣磨单元功率过高故障", 4, 12), # alarm_37
        
        # ErrWord5 (字节 10-11)
        ("MillUpFCError", "上部铣磨单元变频器故障", 5, 8), # alarm_38
        ("MillUpRPMError", "上部铣磨单元 RPM 故障", 5, 9), # alarm_39
        ("MillUpBlockedError", "上部铣磨单元堵转故障", 5, 10), # alarm_40
        ("MillUpPowerWarning", "上部铣磨单元功率过高警告", 5, 11), # alarm_41
        ("MillUpPowerError", "上部铣磨单元功率过高故障", 5, 12), # alarm_42
        
        # ErrWord6 (字节 12-13)
        ("ScanOutOfRange", "扫描范围超出单元正负限位", 6, 8), # alarm_43
        ("ScannerErr", "扫描器通信超时", 6, 9), # alarm_44
        ("ScanResultCalcError", "扫描结果计算出错", 6, 10), # alarm_45
        ("ScanResultRadiusError", "扫描结果叶片半径估计偏差过大", 6, 11), # alarm_54
        ("MillDepthOver", "铣磨深度大于 3.5mm，需要确认", 6, 12), # alarm_61
        ("ScrewCountLow", "扫描螺栓套数量过少", 6, 13), # alarm_62
        
        # ErrWord7 (字节 14-15)
        ("MillDownMotionError", "下部单元铣磨运动故障", 7, 8), # alarm_46
        ("MillPathOver", "铣磨路径超出单元正负限制", 7, 9), # alarm_47
        ("MillDownArcMotionError", "下部单元圆弧运动路径出错", 7, 10), # alarm_48
        ("MillUpMotionError", "上部单元铣磨运动故障", 7, 11), # alarm_49
        ("MillUpCurveNotCreated", "上部单元凸轮曲线未创建", 7, 12), # alarm_50
        ("MillUpSyncNotComplete", "上部单元同步未完成", 7, 13), # alarm_51
    ]
    
    return alarm_definitions


def parse_alarm_bytes(alarm_bytes):
    """
    根据预定义的报警结构解析字节数组
    :param alarm_bytes: 从PLC读取的字节数组
    :return: 解析后的报警状态字典
    """
    alarm_defs = get_alarm_definitions()
    
    # 初始化结果字典
    result = {
        'Env': 0,  # ErrWord0 (字节0-1)
        'Units_Enabled': 0,  # ErrWord1 (字节2-3)
        'Units_Homed': 0,  # ErrWord2 (字节4-5)
        'Units_Errors': 0,  # ErrWord3 (字节6-7)
        'Units_MillDown': 0,  # ErrWord4 (字节8-9)
        'Units_MillUp': 0,  # ErrWord5 (字节10-11)
        'Scan': 0,  # ErrWord6 (字节12-13)
        'Mill': 0,  # ErrWord7 (字节14-15)
        'EnvAlarms': {},
        'EnabledAlarms': {},
        'HomedAlarms': {},
        'ErrorAlarms': {},
        'MillDownAlarms': {},
        'MillUpAlarms': {},
        'ScanAlarms': {},
        'MillAlarms': {},
        'UndefinedBits': []  # 记录未定义的位
    }
    
    # 按照ErrWord分组计算整体值
    # 使用大端序（Big Endian）：高位字节在前
    # 这样两个字节组合成16位字，例如 [0x00, 0x80] -> 0x0080 (二进制: 0000 0000 1000 0000)
    # 位位置从右到左编号（从0开始）：15 14 13 12 11 10 9 8 7 6 5 4 3 2 1 0
    # 如果从左往右数，第8位是1，对应从右往左数的第7位
    for i in range(0, min(len(alarm_bytes)//2, 8)):  # 最多8个ErrWord (0-7)
        first_byte = alarm_bytes[i*2] if i*2 < len(alarm_bytes) else 0
        second_byte = alarm_bytes[i*2+1] if i*2+1 < len(alarm_bytes) else 0
        
        # 大端序：高位字节在前，低位字节在后
        # 根据您的观察，使用 (first_byte << 8) | second_byte 来正确解析
        word_value = (first_byte << 8) | second_byte
        
        # 根据ErrWord索引设置对应的汇总值
        if i == 0:  # ErrWord0
            result['Env'] = word_value
        elif i == 1:  # ErrWord1
            result['Units_Enabled'] = word_value
        elif i == 2:  # ErrWord2
            result['Units_Homed'] = word_value
        elif i == 3:  # ErrWord3
            result['Units_Errors'] = word_value
        elif i == 4:  # ErrWord4
            result['Units_MillDown'] = word_value
        elif i == 5:  # ErrWord5
            result['Units_MillUp'] = word_value
        elif i == 6:  # ErrWord6
            result['Scan'] = word_value
        elif i == 7:  # ErrWord7
            result['Mill'] = word_value

    # 创建一个字典来快速查找已定义的位
    defined_bits = {}
    for name, desc, word_index, bit_position in alarm_defs:
        if word_index not in defined_bits:
            defined_bits[word_index] = {}
        defined_bits[word_index][bit_position] = (name, desc)

    # 解析每个可能的位
    for word_index in range(8):  # 处理ErrWord0到ErrWord7
        start_byte = word_index * 2
        if start_byte >= len(alarm_bytes):
            break
        
        # 获取这两个字节
        low_byte = alarm_bytes[start_byte] if start_byte < len(alarm_bytes) else 0
        high_byte = alarm_bytes[start_byte + 1] if start_byte + 1 < len(alarm_bytes) else 0
        
        # 检查所有16位
        for bit_pos in range(16):
            # 计算实际字节和位的位置
            # 在小端序中，位0-7对应低字节（偶数字节），位8-15对应高字节（奇数字节）
            byte_idx = start_byte + (bit_pos // 8)  # 每个ErrWord包含2个字节
            bit_idx = bit_pos % 8  # 位位置
            
            if byte_idx >= len(alarm_bytes):
                continue
                
            # 检查该位是否被设置
            byte_val = alarm_bytes[byte_idx]
            is_active = bool(byte_val & (1 << bit_idx))
            
            if not is_active:
                continue  # 如果位没有被设置，跳过
            
            # 检查这个位是否在定义中
            if word_index in defined_bits and bit_pos in defined_bits[word_index]:
                # 这是一个已定义的报警
                name, desc = defined_bits[word_index][bit_pos]
                
                # 将报警添加到相应的组中
                group_map = {
                    0: 'EnvAlarms',
                    1: 'EnabledAlarms',
                    2: 'HomedAlarms',
                    3: 'ErrorAlarms',
                    4: 'MillDownAlarms',
                    5: 'MillUpAlarms',
                    6: 'ScanAlarms',
                    7: 'MillAlarms'
                }
                
                group_name = group_map.get(word_index)
                if group_name:
                    result[group_name][name] = {
                        'description': desc,
                        'active': True,
                        'byte': byte_idx,
                        'bit': bit_idx,
                        'raw_byte': alarm_bytes[byte_idx],
                        'word_index': word_index
                    }
            else:
                # 这是一个未定义的位
                result['UndefinedBits'].append({
                    'word_index': word_index,
                    'bit_position': bit_pos,
                    'byte_index': byte_idx,
                    'bit_index': bit_idx,
                    'raw_byte': alarm_bytes[byte_idx]
                })

    return result


def print_parsed_alarms(parsed_alarms):
    """
    打印解析后的报警信息
    """
    print("=== 解析后的报警数据 ===")
    
    # 打印汇总值
    print(f"环境故障 (Env): {parsed_alarms.get('Env', 0)} (0x{parsed_alarms.get('Env', 0):04X})")
    print(f"轴使能状态 (Units_Enabled): {parsed_alarms.get('Units_Enabled', 0)} (0x{parsed_alarms.get('Units_Enabled', 0):04X})")
    print(f"轴回零状态 (Units_Homed): {parsed_alarms.get('Units_Homed', 0)} (0x{parsed_alarms.get('Units_Homed', 0):04X})")
    print(f"轴故障状态 (Units_Errors): {parsed_alarms.get('Units_Errors', 0)} (0x{parsed_alarms.get('Units_Errors', 0):04X})")
    print(f"下部铣磨故障 (Units_MillDown): {parsed_alarms.get('Units_MillDown', 0)} (0x{parsed_alarms.get('Units_MillDown', 0):04X})")
    print(f"上部铣磨故障 (Units_MillUp): {parsed_alarms.get('Units_MillUp', 0)} (0x{parsed_alarms.get('Units_MillUp', 0):04X})")
    print(f"扫描故障 (Scan): {parsed_alarms.get('Scan', 0)} (0x{parsed_alarms.get('Scan', 0):04X})")
    print(f"铣磨运动故障 (Mill): {parsed_alarms.get('Mill', 0)} (0x{parsed_alarms.get('Mill', 0):04X})")
    
    # 打印详细报警状态
    for category, data in parsed_alarms.items():
        if category.endswith('Alarms'):
            print(f"\n--- {category} ---")
            for alarm_name, alarm_info in data.items():
                status = "激活" if alarm_info['active'] else "未激活"
                print(f"  {alarm_name} ({alarm_info['description']}): {status} "
                      f"[字节:{alarm_info['byte']}, 位:{alarm_info['bit']}]")
    
    # 打印未定义的位
    undefined_bits = parsed_alarms.get('UndefinedBits', [])
    if undefined_bits:
        print(f"\n--- 未定义的位 ---")
        for bit_info in undefined_bits:
            print(f"  ErrWord{bit_info['word_index']} 位{bit_info['bit_position']} "
                  f"被设置 [字节{bit_info['byte_index']}, 位{bit_info['bit_index']}] "
                  f"(字节值: 0x{bit_info['raw_byte']:02X})")