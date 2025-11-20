FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout=60

# 复制代码
COPY crawler.py .

# 暴露端口
EXPOSE 8000

# 启动服务（使用 Gunicorn + Uvicorn Workers）
CMD ["gunicorn", "crawler:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
