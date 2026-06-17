from app.api.routes import reports

def register_routes(app):
    """注册所有API路由"""
    app.register_blueprint(reports.bp, url_prefix='/api/report')