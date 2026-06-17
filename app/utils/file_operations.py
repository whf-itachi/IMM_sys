import os
import pandas as pd
import openpyxl
from datetime import datetime
from typing import List, Tuple
import pytz
from app.schemas.report_schemas import FlatnessResponse, ReportItem, ReportStatistics, FlatnessData       


from app.config.app_config import REPORTS_DIR

def get_reports_list() -> List[dict]:
    """
    获取报告目录下的所有Excel文件列表
    """
    excel_dir_path = REPORTS_DIR

    # 确保目录存在
    if not os.path.exists(excel_dir_path):
        print(f"报告目录不存在: {excel_dir_path}")
        return []

    data = []
    for filename in os.listdir(excel_dir_path):
        file_path = os.path.join(excel_dir_path, filename)

        # 只处理Excel文件
        if os.path.isfile(file_path) and filename.endswith(('.xlsx', '.xls')):
            try:
                # 获取文件创建时间
                file_create_time = os.path.getctime(file_path)
                file_create_dt_naive = datetime.fromtimestamp(file_create_time)

                # 使用pytz设置时区
                tz = pytz.timezone('Asia/Shanghai')
                file_create_dt = tz.localize(file_create_dt_naive)

                # 获取文件大小
                file_size = os.path.getsize(file_path)

                # 添加到数据列表
                data.append({
                    'id': 0,  # 由于不依赖数据库，ID设为0
                    'file_name': filename,
                    'created_at': file_create_dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'file_size': file_size,
                    'flatness_count': 0,  # 需要读取文件才能知道具体数据条数
                    'sort_timestamp': file_create_time  # 用于排序的时间戳
                })
            except Exception as e:
                print(f"处理文件 {filename} 时发生错误: {str(e)}")
                continue

    # 按创建时间倒序排列（后创建的在前面）
    data.sort(key=lambda x: x['sort_timestamp'], reverse=True)

    # 移除排序用的时间戳字段，只保留需要的字段
    for item in data:
        del item['sort_timestamp']

    return data


def read_flatness_measure_data(file_path: str) -> Tuple[pd.DataFrame, dict]:
    """
    读取平面度报告Excel文件中的测量数据
    """
    try:
        # 加载工作簿
        wb = openpyxl.load_workbook(filename=file_path, data_only=True)
        ws = wb.worksheets[0]  # 获取第一个工作表

        # 读取报告基本信息
        report_info = {
            'Balde_ID': ws["A2"].value,
            'Report_Time': ws["C2"].value,
            'UserName': ws["B3"].value,
            'MachineStartTime': ws["B4"].value,
            'MachineEndTime': ws["B5"].value,
            'Duration': ws["B6"].value,
            'DeepthSum': ws["B12"].value
        }

        # 读取测量数据（从第29行开始，对应row_index=29）
        measure_data = []
        current_row = 29  # 数据起始行
        # 循环读取数据直到遇到空行
        while True:
            # 检查当前行是否有数据
            index_cell = ws[f"A{current_row}"]
            angle_cell = ws[f"B{current_row}"]
            a_cell = ws[f"C{current_row}"]

            # 如果角度单元格为空，说明已到数据末尾
            if angle_cell.value is None:
                break

            # 添加数据到列表
            measure_data.append({
                'Index': index_cell.value,  # 排序信息（行号-26）
                'Angle': angle_cell.value,
                'A': a_cell.value
            })

            current_row += 1

        # 转换为DataFrame
        df = pd.DataFrame(measure_data)

        # 关闭工作簿
        wb.close()

        return df, report_info

    except Exception as e:
        raise Exception(f"读取Excel文件时发生错误: {str(e)}")


def get_flatness_data_by_filename(filename: str) -> FlatnessResponse:
    """
    根据文件名获取平整度数据
    """
    excel_dir_path = os.getenv('REPORTS_DIR', 'D:/whf_test/report')
    file_path = os.path.join(excel_dir_path, filename)

    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    # 检查文件是否为Excel文件
    if not filename.endswith(('.xlsx', '.xls')):
        raise ValueError(f"文件不是有效的Excel文件: {filename}")

    # 读取Excel文件数据
    measure_df, report_info = read_flatness_measure_data(file_path)

    if measure_df is None or report_info is None:
        raise Exception("无法读取Excel文件数据")

    # 使用从Excel文件中读取的Report_Time作为报告创建时间
    report_time_str = report_info.get('Report_Time')

    # 使用pytz设置时区
    tz = pytz.timezone('Asia/Shanghai')

    if report_time_str:
        try:
            # 尝试解析报告时间字符串
            if isinstance(report_time_str, datetime):       
                report_created_at = report_time_str
            else:
                # 假设格式为"YYYY-MM-DD HH:MM"
                report_created_at = datetime.strptime(str(report_time_str), "%Y-%m-%d %H:%M")
                report_created_at = tz.localize(report_created_at)
        except (ValueError, TypeError):
            # 如果解析失败，使用文件创建时间作为备选
            file_create_time = os.path.getctime(file_path)
            file_create_dt_naive = datetime.fromtimestamp(file_create_time)
            report_created_at = tz.localize(file_create_dt_naive)
    else:
        # 如果没有Report_Time，使用文件创建时间
        file_create_time = os.path.getctime(file_path)
        file_create_dt_naive = datetime.fromtimestamp(file_create_time)
        report_created_at = tz.localize(file_create_dt_naive)

    # 提取平面度值用于统计计算
    flatness_values = [float(row['A']) for _, row in measure_df.iterrows() if 'A' in row and row['A'] is not None]

    # 计算统计值
    if flatness_values:
        max_value = max(flatness_values)
        min_value = min(flatness_values)
        peak_to_peak = max_value - min_value  # 峰峰值
        # RMS值计算：平方和的平均值的平方根
        rms_value = (sum(x**2 for x in flatness_values) / len(flatness_values)) ** 0.5
    else:
        max_value = min_value = peak_to_peak = rms_value = 0

    # 构建返回数据
    report_item = ReportItem(
        id=0,  # 由于直接从文件读取，没有数据库ID
        file_name=filename,
        bladeId=report_info.get('Balde_ID', '未知叶片ID'),
        created_at=report_created_at.strftime('%Y-%m-%d %H:%M:%S')
    )

    statistics = ReportStatistics(
        max_value=round(max_value, 6),
        min_value=round(min_value, 6),
        peak_to_peak=round(peak_to_peak, 6),
        rms_value=round(rms_value, 6),
        data_count=len(flatness_values)
    )

    flatness_data = [
        FlatnessData(
            holeIndex=int(row['Index']) if row['Index'] is not None else 0,  # 叶片孔的排序信息    
            holeAngle=float(row['Angle']),
            flatness=float(row['A'])
        ) for _, row in measure_df.iterrows()
        if 'Index' in row and 'Angle' in row and 'A' in row
        and row['Index'] is not None and row['Angle'] is not None and row['A'] is not None
    ]

    return FlatnessResponse(
        report=report_item,
        statistics=statistics,
        flatness_data=flatness_data
    )