import os

# 基本配置
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1  # 單一 worker 完全避免資料庫鎖定
timeout = 120  # 增加超時時間
worker_class = "sync"

# 性能優化
preload_app = True
max_requests = 1000
max_requests_jitter = 50
keepalive = 2

# 日誌配置
accesslog = "-"
errorlog = "-" 
loglevel = "info"
