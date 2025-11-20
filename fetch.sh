#!/bin/bash
# URL Crawler 快速调用脚本
# 用法: ./fetch.sh <url1> [url2] [url3] ...

# 默认配置
ENDPOINT="${CRAWLER_ENDPOINT:-http://127.0.0.1:8000/fetch}"
TIMEOUT="${CRAWLER_TIMEOUT:-15.0}"
CONCURRENCY="${CRAWLER_CONCURRENCY:-10}"

# 检查参数
if [ $# -eq 0 ]; then
    echo "用法: $0 <url1> [url2] [url3] ..."
    echo ""
    echo "示例:"
    echo "  $0 https://example.com"
    echo "  $0 https://example.com https://www.python.org"
    echo ""
    echo "环境变量:"
    echo "  CRAWLER_ENDPOINT    - 服务端点 (默认: http://127.0.0.1:8000/fetch)"
    echo "  CRAWLER_TIMEOUT     - 超时秒数 (默认: 15.0)"
    echo "  CRAWLER_CONCURRENCY - 并发数 (默认: 10)"
    exit 1
fi

# 构建 URL 数组
URLS=""
for url in "$@"; do
    if [ -z "$URLS" ]; then
        URLS="\"$url\""
    else
        URLS="$URLS, \"$url\""
    fi
done

# 构建 JSON payload
JSON_DATA="{\"urls\": [$URLS], \"timeout\": $TIMEOUT, \"concurrency\": $CONCURRENCY}"

# 发送请求
echo "正在抓取 $# 个 URL..."
curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d "$JSON_DATA" \
  -s | jq '.' 2>/dev/null || curl -X POST "$ENDPOINT" \
  -H "Content-Type: application/json" \
  -d "$JSON_DATA"

echo ""
