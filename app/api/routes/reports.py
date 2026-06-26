from flask import Blueprint, request, jsonify, send_file, current_app
import os
from datetime import datetime

from app.schemas.report_schemas import ReportListResponse, FileItem
from app.utils.file_operations import get_reports_list, get_flatness_data_by_filename
from app.utils.logging_config import setup_logger

bp = Blueprint('reports', __name__)

# 创建全局logger
logger = setup_logger()


@bp.route('/flatness/', methods=['GET'])
def flatness_report_list():
    """
    获取所有平整度报告列表（直接从文件目录读取）
    """
    try:
        reports_data = get_reports_list()
        logger.info(f"获取平整度报告列表成功，共{len(reports_data)}个Excel文件")

        file_items = []
        for item in reports_data:
            file_item = FileItem(
                id=item['id'],
                file_name=item['file_name'],
                created_at=item['created_at'],
                file_size=item['file_size'],
                flatness_count=item['flatness_count']
            )
            file_items.append(file_item)

        response_data = ReportListResponse(reports=file_items)
        return jsonify(response_data.model_dump())

    except Exception as e:
        logger.error(f"获取报告列表时发生错误: {str(e)}")
        return jsonify({"detail": "服务器内部错误"}), 500


@bp.route('/<filename>', methods=['GET'], endpoint='flatness_detail')
def flatness_report_detail_api(filename):
    """
    根据文件名获取报告的详细平整度数据（返回JSON）
    """
    logger.info(f"通过文件名获取平整度数据，文件名: {filename}")

    if not filename:
        logger.warning("文件名参数为空")
        return jsonify({"detail": "文件名参数不能为空"}), 400

    try:
        result = get_flatness_data_by_filename(filename)

        # 发布遥测数据到MQTT
        try:
            logger.info(f"Attempting to access MQTT publisher for file {filename}")
            # 修复：使用current_app访问mqtt_publisher
            mqtt_publisher = current_app.mqtt_publisher
            logger.info(f"MQTT publisher retrieved, connected: {mqtt_publisher.is_connected if mqtt_publisher else 'None'}")
            
            if mqtt_publisher and mqtt_publisher.is_connected:
                logger.info("进入到事件处理逻辑")
                # 准备孔角度和孔测量值数组
                hole_angles = [item.holeAngle for item in result.flatness_data]
                hole_values = [item.flatness for item in result.flatness_data]

                # 构造平面度测量数据事件字典
                event_data = {
                    "measure_time": int(datetime.now().timestamp() * 1000),  # 毫秒时间戳
                    "blade_id": result.report.bladeId,  # 叶片ID
                    "max_value": result.statistics.max_value,
                    "min_value": result.statistics.min_value,
                    "pv_value": result.statistics.peak_to_peak,
                    "rms": result.statistics.rms_value,
                    "hole_angle": hole_angles,
                    "hole_value": hole_values
                }
                logger.info(str(event_data))
                # 发布平面度测量数据事件
                mqtt_publisher.publish_event("flatness_data", event_data)
                logger.info(f"Published flatness data event for file {filename} to MQTT")
            else:
                logger.warning(f"MQTT publisher is not available or not connected for file {filename}")
        except AttributeError as attr_error:
            logger.error(f"AttributeError accessing MQTT publisher for file {filename}: {attr_error}")
            logger.error("This may indicate that current_app is not pointing to the correct application instance.")
        except Exception as mqtt_error:
            logger.error(f"Failed to publish data for file {filename} to MQTT: {mqtt_error}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

        return jsonify(result.dict())

    except FileNotFoundError:
        logger.error(f"文件不存在: {filename}")
        return jsonify({"detail": f'文件"{filename}"不存在'}), 404

    except ValueError as ve:
        logger.error(f"文件处理错误: {str(ve)}")
        return jsonify({"detail": str(ve)}), 400

    except Exception as e:
        logger.error(f"服务器错误: {str(e)}")
        return jsonify({"detail": f'服务器错误: {str(e)}'}), 500


@bp.route('/download/', methods=['GET'])
def download_excel_file():
    """
    下载Excel文件
    """
    from app.config.app_config import REPORTS_DIR

    filename = request.args.get('filename', '')
    logger.info(f"请求下载Excel文件，文件名: {filename}")

    if not filename:
        logger.warning("文件名参数为空")
        return jsonify({"detail": "文件名参数不能为空"}), 400

    # 构建完整的文件路径
    excel_dir_path = REPORTS_DIR
    file_path = os.path.join(excel_dir_path, filename)

    # 检查文件是否存在
    if not os.path.exists(file_path):
        logger.error(f"文件不存在: {file_path}")
        return jsonify({"detail": f'文件"{filename}"不存在'}), 404

    # 检查文件是否为Excel文件
    if not filename.endswith(('.xlsx', '.xls')):
        logger.error(f"文件不是有效的Excel文件: {filename}")
        return jsonify({"detail": f'文件"{filename}"不是有效的Excel文件'}), 400

    logger.info(f"准备下载文件: {filename}")

    return send_file(
        file_path,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )