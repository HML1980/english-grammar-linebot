import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

timeout = 120
keepalive = 2
graceful_timeout = 30

preload_app = True
worker_tmp_dir = "/dev/shm"

accesslog = "-"
errorlog = "-"
loglevel = "info"

limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
