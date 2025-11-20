FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --timeout=60

# 复制代码
COPY crawler.py .

# 暴露端口
EXPOSE 8000

# 启动服务（使用 Uvicorn 多进程模式）
CMD ["uvicorn", "crawler:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "info", \
     "--access-log"]
