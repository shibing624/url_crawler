# url_crawler
url网页批量抓取工具。

该服务基于 FastAPI 构建，可并发抓取一组 URL，抽取网页正文文本，并返回结构化结果，适合作为下游 NLP / RAG 组件的前置 Reader。

## 功能亮点
- 限流 + 超时：默认并发 10、单个请求 15s，可通过环境变量调整（最大并发可达 64+），有效保护外部服务。
- 文本抽取：使用 BeautifulSoup 去除 `script/style/noscript` 等噪声节点，仅输出纯文本。
- 结构化响应：逐条记录 `ok` 状态、`status_code`、`charset`、`text`、`bytes_downloaded`、`elapsed_ms` 与错误信息，方便追踪。
- 健康检查：`/health` 端点可用于探活与运维监控。
- 多种部署方式：支持 Uvicorn、Gunicorn、Docker、Systemd 等多种生产部署方案。

## 环境准备
```bash
pip install -r requirements.txt
```

## 启动服务

### 开发模式
直接使用 `uvicorn` 启动，支持代码热重载：
```bash
uvicorn crawler:app --host 0.0.0.0 --port 8000 --reload
```

### 生产部署

#### 方案 1：Uvicorn 直接部署

**单进程模式**（适合低流量场景）：
```bash
uvicorn crawler:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level info
```

**多进程模式**（推荐，利用多核CPU）：
```bash
uvicorn crawler:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info \
  --access-log
```

参数说明：
- `--workers`: 进程数，通常设置为 `CPU核心数 * 2 + 1`
- `--log-level`: 日志级别（debug/info/warning/error）
- `--access-log`: 启用访问日志

#### 方案 2：Gunicorn + Uvicorn Workers（推荐生产环境）

**直接启动**：
```bash
gunicorn crawler:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 30 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
```

**使用配置文件** `gunicorn_config.py`：
```python
# gunicorn_config.py
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
```

启动命令：
```bash
gunicorn -c gunicorn_config.py crawler:app
```

#### 方案 3：Docker 容器化部署

**创建 `Dockerfile`**：
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
```

**构建镜像**：
```bash
docker build -t url-crawler:latest .
```

**运行容器**：
```bash
docker run -d \
  --name url-crawler \
  -p 8000:8000 \
  --restart unless-stopped \
  -e URL_CRAWLER_DEFAULT_CONCURRENCY=20 \
  -e URL_CRAWLER_MAX_CONCURRENCY=100 \
  url-crawler:latest
```

**查看日志**：
```bash
docker logs -f url-crawler
```

#### 方案 4：Systemd 服务管理

创建服务文件 `/etc/systemd/system/url-crawler.service`：
```ini
[Unit]
Description=URL Crawler Service
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/url_crawler
Environment="PATH=/opt/url_crawler/venv/bin"
ExecStart=/opt/url_crawler/venv/bin/gunicorn crawler:app \
          --workers 4 \
          --worker-class uvicorn.workers.UvicornWorker \
          --bind 0.0.0.0:8000 \
          --timeout 30
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

管理命令：
```bash
# 启动服务
sudo systemctl start url-crawler

# 开机自启
sudo systemctl enable url-crawler

# 查看状态
sudo systemctl status url-crawler

# 重启服务
sudo systemctl restart url-crawler

# 查看日志
sudo journalctl -u url-crawler -f
```

### 反向代理配置（可选）

建议在 Uvicorn/Gunicorn 前部署 Nginx 或 Caddy，提供 TLS、限流、缓存等功能。

**Nginx 配置示例**：
```nginx
upstream url_crawler {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name crawler.example.com;

    location / {
        proxy_pass http://url_crawler;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
```

## API 说明
### `POST /fetch`
- 请求体
  ```json
  {
    "urls": ["https://example.com", "https://www.python.org"],
    "timeout": 15.0
  }
  ```
- 响应体
  ```json
  {
    "total": 2,
    "results": [
      {
        "url": "https://example.com",
        "ok": true,
        "status_code": 200,
        "charset": "utf-8",
        "text": "Example Domain...",
        "error": null
      },
      {
        "url": "https://www.python.org",
        "ok": false,
        "status_code": 403,
        "charset": null,
        "text": null,
        "error": "403 Client Error: Forbidden for url"
      }
    ]
  }
  ```

### `GET /health`
返回 `{ "status": "ok" }`，可用于健康检查。

## 使用示例

### curl 调用（推荐）

**健康检查**：
```bash
curl http://127.0.0.1:8000/health
```

**抓取单个 URL**：
```bash
curl -X POST http://127.0.0.1:8000/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "timeout": 15.0
  }'
```

**抓取多个 URL（并发）**：
```bash
curl -X POST http://127.0.0.1:8000/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://www.python.org",
      "https://github.com",
      "https://example.com"
    ],
    "timeout": 15.0,
    "concurrency": 10
  }'
```

**格式化输出（使用 jq）**：
```bash
curl -X POST http://127.0.0.1:8000/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "timeout": 15.0
  }' | jq .
```

**保存结果到文件**：
```bash
curl -X POST http://127.0.0.1:8000/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com", "https://www.python.org"],
    "timeout": 15.0
  }' -o result.json
```

### Python 客户端

`demo.py` 提供了一个命令行示例：
```bash
python demo.py \
  --urls https://example.com https://www.python.org \
  --timeout 12 \
  --concurrency 32
```

### Shell 脚本客户端（最简单）

使用 `fetch.sh` 快速抓取：
```bash
# 抓取单个 URL
./fetch.sh https://example.com

# 抓取多个 URL
./fetch.sh https://example.com https://www.python.org https://github.com

# 自定义配置（通过环境变量）
CRAWLER_TIMEOUT=20 CRAWLER_CONCURRENCY=20 ./fetch.sh https://example.com
```

## 目录结构
```
url_crawler/
├── crawler.py           # FastAPI 主服务
├── demo.py              # Python 客户端示例
├── fetch.sh             # Shell 脚本客户端（推荐）
├── requirements.txt     # Python 依赖
├── gunicorn_config.py   # Gunicorn 配置文件
├── Dockerfile           # Docker 镜像构建文件
├── README.md            # 使用文档
└── LICENSE              # 开源协议
```

欢迎根据生产需求扩展重试策略、持久化以及鉴权逻辑。


## Contact

- Issue(建议)：[![GitHub issues](https://img.shields.io/github/issues/shibing624/url_crawler.svg)](https://github.com/shibing624/url_crawler/issues)
- 邮件我：xuming: xuming624@qq.com
- 微信我：加我*微信号：xuming624, 备注：姓名-公司-NLP* 进NLP交流群。


<img src="https://github.com/shibing624/pycorrector/blob/master/docs/git_image/wechat.jpeg" width="200" />

## Citation

如果你在研究中使用了url_crawler，请按如下格式引用：

APA:
```latex
Xu, M. url_crawler: Crawl url content (Version 0.0.1) [Computer software]. https://github.com/shibing624/url_crawler
```

BibTeX:
```latex
@misc{url_crawler,
  author = {Ming Xu},
  title = {url_crawler: Crawl url content},
  year = {2025},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/shibing624/url_crawler}},
}
```

## License


授权协议为 [The Apache License 2.0](LICENSE)，可免费用做商业用途。请在产品说明中附加url_crawler的链接和授权协议。


## Contribute
项目代码还很粗糙，如果大家对代码有所改进，欢迎提交回本项目。