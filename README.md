# IMM_sys

基于Flask的工业测量管理系统(Industrial Measurement Management System)，用于处理和展示平整度测量报告。

## 功能特性

- 通过API获取平整度测量报告列表
- 根据文件名获取详细的平整度数据
- Excel文件下载功能
- 支持跨域访问

## 环境要求

- Python 3.8+
- pandas
- openpyxl
- Flask
- paho-mqtt

## 安装步骤

1. 克隆项目：
   ```
   git clone <repository-url>
   cd IMM_sys
   ```

2. 创建虚拟环境并安装依赖：
   ```
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   venv\Scripts\activate  # Windows

   pip install -r requirements.txt
   ```

3. 配置环境变量：
   ```
   export REPORTS_DIR=/path/to/your/reports/directory
   export LOG_DIR=/path/to/your/log/directory
   ```


## 运行应用

```
python run_server.py
```

或者使用环境变量指定端口和主机：
```
PORT=8080 HOST=0.0.0.0 python run_server.py
```

## API接口

- `GET /` - 根路径，返回欢迎信息
- `GET /api/report/flatness/` - 获取所有平整度报告列表
- `GET /api/report/flatness/by-filename/?filename=xxx.xlsx` - 根据文件名获取平整度数据
- `GET /api/report/download/?filename=xxx.xlsx` - 下载Excel文件

## 项目结构

```
IMM_sys/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   └── reports.py
│   │   └── __init__.py
│   ├── config/
│   │   └── app_config.py
│   ├── schemas/
│   │   ├── report_schemas.py
│   │   └── __init__.py
│   ├── utils/
│   │   ├── file_operations.py
│   │   ├── logging_config.py
│   │   └── __init__.py
│   ├── main.py
│   └── __init__.py
├── certs/
├── log/
├── run_server.py
├── requirements.txt
└── README.md
```

## 日志

应用会自动在`log`目录下创建`programLog.log`文件记录日志信息。