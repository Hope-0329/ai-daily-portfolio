# Render Docker部署 — 完全受控的构建环境
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN pip install --no-cache-dir --upgrade pip

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8765

# 启动
CMD ["python", "web_demo_cloud.py"]
