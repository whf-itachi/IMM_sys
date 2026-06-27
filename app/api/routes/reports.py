from flask import Blueprint, request, jsonify, send_file
import os

from app.schemas.report_schemas import ReportListResponse, FileItem
from app.utils.file_operations import get_reports_list, get_flatness_data_by_filename, get_available_worksheets
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

    # 从查询参数获取工作表名称，默认为 'Flatness'
    worksheet_name = request.args.get('worksheet', 'Flatness')

    try:
        result = get_flatness_data_by_filename(filename, worksheet_name)

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


@bp.route('/worksheets/<filename>', methods=['GET'])
def get_worksheets_api(filename):
    """
    获取Excel文件中可用的工作表名称
    """
    logger.info(f"获取文件 {filename} 的工作表列表")

    if not filename:
        logger.warning("文件名参数为空")
        return jsonify({"detail": "文件名参数不能为空"}), 400

    try:
        worksheets_info = get_available_worksheets(filename)
        return jsonify(worksheets_info)

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