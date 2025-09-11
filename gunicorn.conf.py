import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 4
worker_class = "sync"
worker_connections = 1000
threads = 1

timeout = 120
keepalive = 2
graceful_timeout = 30

preload_app = True
max_requests = 1000
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = "info"
