import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# LINE BOT設定（暫時留空，稍後填入）
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', '')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', '')

# 資料庫設定（暫時使用本地設定）
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/english_grammar_bot')

# 應用程式設定
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

# 圖片資源URL基礎路徑（稍後會設定）
IMAGES_BASE_URL = 'https://your-domain.com/images/'

# 分頁設定
SECTIONS_PER_PAGE = 3