#!/bin/bash

echo "=== LINE Bot 啟動檢查 ==="

# 檢查環境變數檔案
if [ ! -f .env ]; then
    echo "錯誤: .env 檔案不存在"
    exit 1
fi

# 檢查 Python 檔案
if [ ! -f app.py ]; then
    echo "錯誤: app.py 檔案不存在" 
    exit 1
fi

# 檢查書籍資料檔案
if [ ! -f book.json ]; then
    echo "錯誤: book.json 檔案不存在"
    exit 1
fi

echo "所有檔案檢查完成"

# 檢查網路端口
if lsof -i:8080 > /dev/null 2>&1; then
    echo "警告: 端口 8080 已被占用"
    echo "現有進程:"
    lsof -i:8080
    echo "是否要停止現有進程? (y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        pkill -f "python.*app.py"
        sleep 2
    fi
fi

echo "啟動 LINE Bot..."
python app.py
