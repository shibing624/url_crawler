#!/bin/bash
# URL Crawler 快速调用脚本
# 用法: sh fetch.sh 

curl -X POST http://127.0.0.1:8000/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://www.python.org",
      "https://www.cctv.com"
    ]
  }'