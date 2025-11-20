# -*- coding: utf-8 -*-
"""
Gunicorn 配置文件
使用方法: gunicorn -c gunicorn_config.py crawler:app
"""
import multiprocessing

# 服务器绑定
bind = "0.0.0.0:8000"

# Worker 配置
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"

# 超时设置
timeout = 30
keepalive = 5

# 日志配置
accesslog = "-"  # 输出到 stdout
errorlog = "-"   # 输出到 stderr
loglevel = "info"

# 进程命名
proc_name = "url_crawler"

# 优雅重启
graceful_timeout = 30
