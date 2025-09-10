import os

# 單一 worker 配置
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
worker_class = "sync"
worker_connections = 1
threads = 1

# 超時設定
timeout = 120
keepalive = 2
graceful_timeout = 30

# 預載和記憶體設定
preload_app = True
max_requests = 1000
max_requests_jitter = 50

# 日誌
accesslog = "-"
errorlog = "-"
loglevel = "info"
