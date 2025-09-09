# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()

import os
import json
import sqlite3
import requests
import time
import logging
from urllib.parse import parse_qs
from flask import Flask, request, abort, g
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage, ImageMessage, PostbackAction,
    TemplateMessage, ButtonsTemplate, CarouselTemplate, CarouselColumn,
    QuickReply, QuickReplyItem
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent, FollowEvent
from functools import wraps
import threading

# ===== 日誌設定 =====
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/linebot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ===== 環境變數檢查 =====
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'linebot.db')
MAX_DB_CONNECTIONS = int(os.environ.get('MAX_DB_CONNECTIONS', '10'))

logger.info("=== 系統啟動 ===")
logger.info(f"CHANNEL_SECRET: {'已設定' if CHANNEL_SECRET else '未設定'}")
logger.info(f"CHANNEL_ACCESS_TOKEN: {'已設定' if CHANNEL_ACCESS_TOKEN else '未設定'}")
logger.info(f"MAIN_RICH_MENU_ID: {'已設定' if MAIN_RICH_MENU_ID else '未設定'}")
logger.info(f"DATABASE_NAME: {DATABASE_NAME}")

required_env_vars = [CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID]
if not all(required_env_vars):
    logger.error("錯誤：缺少必要的環境變數")
    exit(1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ===== 資料庫連接管理 =====
_local = threading.local()

def get_db_connection():
    """取得資料庫連接（執行緒安全）"""
    if not hasattr(_local, 'connection'):
        _local.connection = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        _local.connection.row_factory = sqlite3.Row
        _local.connection.execute('PRAGMA journal_mode=WAL')
        _local.connection.execute('PRAGMA synchronous=NORMAL')
        _local.connection.execute('PRAGMA cache_size=10000')
    return _local.connection

# ===== 資料庫初始化 =====
def init_database():
    """初始化資料庫表格（加強版）"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT UNIQUE NOT NULL,
                display_name TEXT,
                current_chapter_id INTEGER,
                current_section_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_interactions INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT NOT NULL,
                chapter_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(line_user_id, chapter_id, section_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT NOT NULL,
                chapter_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                user_answer TEXT NOT NULL,
                is_correct BOOLEAN NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_data TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE NOT NULL,
                active_users INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0,
                new_users INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 建立索引提升查詢效能
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_line_id ON users(line_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_users_active ON users(last_active)",
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON bookmarks(line_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_quiz_user ON quiz_attempts(line_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_actions_user_time ON user_actions(line_user_id, timestamp)"
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except sqlite3.OperationalError as e:
                if "already exists" not in str(e):
                    logger.warning(f"索引建立失敗: {e}")
        
        conn.commit()
        logger.info("資料庫初始化完成")
        
    except Exception as e:
        logger.error(f"資料庫初始化失敗: {e}")
        raise

# ===== 請求監控 =====
@app.before_request
def before_request():
    g.start_time = time.time()
    g.user_id = None

@app.after_request
def after_request(response):
    try:
        total_time = time.time() - g.start_time
        user_id = getattr(g, 'user_id', 'N/A')
        
        logger.info(f"Request: {request.method} {request.path} | "
                   f"Status: {response.status_code} | "
                   f"Time: {total_time:.3f}s | "
                   f"User: {user_id}")
        
        if total_time > 3.0:
            logger.warning(f"慢請求警告: {total_time:.3f}s - {request.path}")
            
    except Exception as e:
        logger.error(f"請求監控失敗: {e}")
    
    return response

# ===== 防重複點擊機制 =====
def is_duplicate_action(user_id, action_data, cooldown=2):
    """檢查是否為重複操作（改進版）"""
    current_time = time.time()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM user_actions WHERE timestamp < ?", 
            (current_time - cooldown * 10,)
        )
        
        cursor.execute(
            "SELECT timestamp FROM user_actions WHERE line_user_id = ? AND action_data = ? AND timestamp > ?",
            (user_id, action_data, current_time - cooldown)
        )
        
        if cursor.fetchone():
            logger.info(f"重複操作被阻止: {user_id} - {action_data}")
            return True
        
        cursor.execute(
            "INSERT INTO user_actions (line_user_id, action_type, action_data, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, "postback", action_data, current_time)
        )
        conn.commit()
        return False
        
    except Exception as e:
        logger.error(f"重複操作檢查錯誤: {e}")
        return False

# ===== 使用者活動追蹤 =====
def update_user_activity(user_id):
    """更新使用者活動狀態"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """UPDATE users 
               SET last_active = CURRENT_TIMESTAMP, 
                   total_interactions = total_interactions + 1 
               WHERE line_user_id = ?""",
            (user_id,)
        )
        
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT OR IGNORE INTO users (line_user_id, total_interactions) VALUES (?, 1)",
                (user_id,)
            )
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"使用者活動更新失敗: {e}")

# ===== 錯誤處理裝飾器 =====
def handle_errors(func):
    """統一錯誤處理裝飾器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"函數 {func.__name__} 發生錯誤: {e}")
            raise
    return wrapper

# ===== 載入書籍資料 =====
@handle_errors
def load_book_data():
    try:
        with open('book.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"book.json 載入成功，包含 {len(data.get('chapters', []))} 章節")
        return data
    except FileNotFoundError:
        logger.error("book.json 檔案不存在")
        return {"chapters": []}
    except json.JSONDecodeError as e:
        logger.error(f"book.json 格式錯誤: {e}")
        return {"chapters": []}
    except Exception as e:
        logger.error(f"載入 book.json 失敗: {e}")
        return {"chapters": []}

# ===== 健康檢查 =====
@app.route("/health", methods=['GET'])
def health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE last_active > datetime('now', '-1 day')"
        )
        active_users_24h = cursor.fetchone()[0]
        
        chapter_count = len(book_data.get('chapters', []))
        
        return {
            "status": "healthy",
            "database": "connected",
            "total_users": user_count,
            "active_users_24h": active_users_24h,
            "chapters": chapter_count,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        return {"status": "unhealthy", "error": str(e)}, 500

# ===== 統計收集函數 =====
def collect_daily_stats():
    """收集每日統計（簡化版）"""
    try:
        today = time.strftime('%Y-%m-%d')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT COUNT(DISTINCT line_user_id) FROM user_actions WHERE date(created_at) = ?",
            (today,)
        )
        active_users = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM user_actions WHERE date(created_at) = ?",
            (today,)
        )
        total_messages = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE date(created_at) = ?",
            (today,)
        )
        new_users = cursor.fetchone()[0]
        
        cursor.execute(
            """INSERT OR REPLACE INTO daily_stats 
               (date, active_users, total_messages, new_users) 
               VALUES (?, ?, ?, ?)""",
            (today, active_users, total_messages, new_users)
        )
        
        conn.commit()
        logger.info(f"每日統計: {active_users} 活躍使用者, {total_messages} 訊息, {new_users} 新使用者")
        
    except Exception as e:
        logger.error(f"統計收集失敗: {e}")

# ===== 管理員統計功能 =====
def get_admin_stats():
    """取得管理員統計資訊"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE date(last_active) = date('now')"
        )
        today_active = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE last_active > datetime('now', '-7 days')"
        )
        week_active = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM quiz_attempts")
        total_quiz = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM bookmarks")
        total_bookmarks = cursor.fetchone()[0]
        
        return f"""📊 系統統計報告

👥 使用者統計：
• 總註冊用戶：{total_users}
• 今日活躍：{today_active}
• 本週活躍：{week_active}

📝 學習統計：
• 總測驗次數：{total_quiz}
• 總書籤數：{total_bookmarks}

📅 報告時間：{time.strftime('%Y-%m-%d %H:%M:%S')}"""
        
    except Exception as e:
        logger.error(f"統計查詢失敗: {e}")
        return "統計查詢失敗"

# ===== 圖文選單處理 =====
def switch_rich_menu(user_id, rich_menu_id):
    """使用純 HTTP API 切換圖文選單"""
    try:
        headers = {
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        }
        url = f'https://api.line.me/v2/bot/user/{user_id}/richmenu/{rich_menu_id}'
        response = requests.post(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"圖文選單切換成功: {rich_menu_id}")
            return True
        else:
            logger.warning(f"圖文選單切換失敗: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"切換圖文選單錯誤: {e}")
        return False

# ===== Webhook 路由 =====
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        abort(400)
    except Exception as e:
        logger.error(f"處理錯誤: {e}")
        abort(500)
    
    return 'OK'

@app.route("/", methods=['GET'])
def index():
    return {"message": "LINE Bot is running", "status": "healthy", "version": "小規模多人版 v1.0"}

# ===== 事件處理 =====
@handler.add(FollowEvent)
@handle_errors
def handle_follow(event):
    user_id = event.source.user_id
    g.user_id = user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        try:
            profile = line_api.get_profile(user_id)
            display_name = profile.display_name
        except:
            display_name = f"User_{user_id[-6:]}"
        
        logger.info(f"新使用者關注: {display_name} ({user_id})")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", 
            (user_id, display_name)
        )
        conn.commit()
        
        update_user_activity(user_id)
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        
        welcome_text = """歡迎使用五分鐘英文文法攻略！

🎯 快速開始：
• 閱讀內容 - 從第一章開始學習
• 章節選擇 - 選擇想學的章節
• 幫助 - 查看所有文字指令

💡 使用提示：
📱 手機版：使用下方圖文選單
💻 電腦版：輸入文字指令操作

輸入「幫助」查看完整指令說明"""
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=welcome_text)]
            )
        )
        
    except Exception as e:
        logger.error(f"處理關注事件錯誤: {e}")

@handler.add(MessageEvent, message=TextMessageContent)
@handle_errors
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    g.user_id = user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    update_user_activity(user_id)
    logger.info(f"收到訊息: {user_id} - {text}")
    
    try:
        # 標準化指令（移除空格、轉小寫）
        cmd = text.replace(" ", "").lower()
        
        # 文字指令處理
        if cmd in ['閱讀內容', '開始閱讀', '開始學習', '閱讀', '開始']:
            handle_start_reading(user_id, event.reply_token, line_api)
            
        elif cmd in ['章節選擇', '選擇章節', '章節', '選章']:
            handle_show_chapter_carousel(user_id, event.reply_token, line_api)
            
        elif cmd in ['我的書籤', '書籤', '收藏']:
            handle_bookmarks(user_id, event.reply_token, line_api)
            
        elif cmd in ['上次進度', '繼續學習', '進度', '繼續']:
            handle_resume_reading(user_id, event.reply_token, line_api)
            
        elif cmd in ['本章測驗題', '測驗', '測驗題', '本章測驗']:
            handle_chapter_quiz(user_id, event.reply_token, line_api)
            
        elif cmd in ['錯誤分析', '分析', '學習狀況']:
            handle_error_analytics(user_id, event.reply_token, line_api)
            
        # 章節直接選擇（數字）
        elif text.isdigit() and 1 <= int(text) <= 7:
            chapter_number = int(text)
            handle_direct_chapter_selection(user_id, chapter_number, event.reply_token, line_api)
            
        # 導航指令
        elif cmd in ['下一段', '下一頁', '繼續', 'next']:
            handle_navigation_command(user_id, 'next', event.reply_token, line_api)
            
        elif cmd in ['上一段', '上一頁', '返回', 'prev', 'previous']:
            handle_navigation_command(user_id, 'prev', event.reply_token, line_api)
            
        elif cmd in ['標記', '收藏', 'bookmark']:
            handle_bookmark_current(user_id, event.reply_token, line_api)
            
        # 幫助和指令列表
        elif cmd in ['幫助', 'help', '指令', '說明']:
            help_text = """📖 文字指令說明

📚 學習指令：
• 閱讀內容 - 從第一章開始
• 章節選擇 - 選擇要學習的章節
• 上次進度 - 繼續上次學習位置
• 1-7 - 直接跳到指定章節

📝 測驗指令：
• 本章測驗題 - 練習當前章節測驗
• 錯誤分析 - 查看學習弱點分析

🔖 管理指令：
• 我的書籤 - 查看收藏的內容
• 標記 - 收藏當前段落

⏯️ 導航指令：
• 下一段 - 進入下一段內容
• 上一段 - 回到上一段內容

💡 其他指令：
• 進度 - 查看學習統計
• 幫助 - 顯示此說明

📱 手機用戶也可使用下方圖文選單"""
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=help_text)]
                )
            )
            
        # 學習進度查詢
        elif cmd in ['進度', 'progress', '統計']:
            handle_progress_inquiry(user_id, event.reply_token, line_api)
            
        # 管理員功能
        elif 'admin' in cmd and '統計' in text:
            stats_text = get_admin_stats()
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=stats_text)]
                )
            )
            
        # 未知指令
        else:
            suggestion_text = """❓ 指令無法識別

常用指令：
• 閱讀內容 - 開始學習
• 章節選擇 - 選擇章節  
• 我的書籤 - 查看收藏
• 本章測驗題 - 練習測驗
• 幫助 - 查看所有指令

💡 提示：
📱 手機版可使用下方圖文選單
💻 電腦版輸入文字指令即可"""
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=suggestion_text)]
                )
            )
            
    except Exception as e:
        logger.error(f"處理文字訊息錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="系統暫時忙碌，請稍後再試，或輸入「幫助」查看可用指令")]
            )
        )

# ===== 導航指令處理函數 =====
def handle_navigation_command(user_id, direction, reply_token, line_api):
    """處理導航指令（上一段/下一段）"""
    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        
        if not user or not user['current_chapter_id']:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請先選擇章節開始學習\n\n輸入「閱讀內容」開始第一章\n或輸入「章節選擇」選擇章節")]
                )
            )
            return
        
        chapter_id = user['current_chapter_id']
        current_section_id = user['current_section_id'] or 0
        
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="章節資料發生錯誤，請重新選擇章節")]
                )
            )
            return
        
        content_sections = sorted([s for s in chapter['sections'] if s['type'] == 'content'], 
                                key=lambda x: x['section_id'])
        has_image = bool(chapter.get('image_url'))
        
        if direction == 'next':
            if current_section_id == 0 and has_image:
                if content_sections:
                    next_section_id = content_sections[0]['section_id']
                    handle_navigation(user_id, chapter_id, next_section_id, reply_token, line_api)
                else:
                    line_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text="本章節沒有更多內容")]
                        )
                    )
            else:
                current_index = next((i for i, s in enumerate(content_sections) 
                                    if s['section_id'] == current_section_id), -1)
                
                if current_index < len(content_sections) - 1:
                    next_section_id = content_sections[current_index + 1]['section_id']
                    handle_navigation(user_id, chapter_id, next_section_id, reply_token, line_api)
                else:
                    quiz_sections = [s for s in chapter['sections'] if s['type'] == 'quiz']
                current_quiz = next((i+1 for i, s in enumerate(quiz_sections) if s['section_id'] == section_id), 1)
                
                quiz_text = f"📝 測驗 {current_quiz}/{len(quiz_sections)}\n\n{quiz['question']}"
                
                messages.append(TextMessage(
                    text=quiz_text,
                    quick_reply=QuickReply(items=quick_items)
                ))
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=messages[:5]
            )
        )
        
    except Exception as e:
        logger.error(f"導覽錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="載入內容失敗，請稍後再試")]
            )
        )

@handle_errors
def handle_add_bookmark(params, user_id, reply_token, line_api):
    """新增書籤"""
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        
        conn = get_db_connection()
        existing = conn.execute(
            "SELECT id FROM bookmarks WHERE line_user_id = ? AND chapter_id = ? AND section_id = ?",
            (user_id, chapter_id, section_id)
        ).fetchone()
        
        if existing:
            if section_id == 0:
                text = "📌 章節圖片已在書籤中\n\n點擊「我的書籤」查看所有收藏"
            else:
                text = "📌 此段已在書籤中\n\n點擊「我的書籤」查看所有收藏"
        else:
            conn.execute(
                "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                (user_id, chapter_id, section_id)
            )
            conn.commit()
            if section_id == 0:
                text = f"✅ 已加入書籤\n\n第 {chapter_id} 章圖片"
            else:
                text = f"✅ 已加入書籤\n\n第 {chapter_id} 章第 {section_id} 段"
            
        conn.close()
        line_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )
        
    except Exception as e:
        logger.error(f"書籤錯誤: {e}")

@handle_errors
def handle_answer(params, user_id, reply_token, line_api):
    """處理答題"""
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        user_answer = params.get('answer', [None])[0]
        
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
        
        if section and section['type'] == 'quiz':
            correct = section['content']['answer']
            is_correct = user_answer == correct
            
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)",
                (user_id, chapter_id, section_id, user_answer, is_correct)
            )
            conn.commit()
            conn.close()
            
            if is_correct:
                result_text = "✅ 答對了！"
                emoji = "🎉"
            else:
                correct_option = section['content']['options'].get(correct, correct)
                result_text = f"❌ 答錯了\n\n正確答案是 {correct}: {correct_option}"
                emoji = "💪"
            
            actions = []
            next_section_id = section_id + 1
            next_section = next((s for s in chapter['sections'] if s['section_id'] == next_section_id), None)
            
            if next_section:
                if next_section['type'] == 'quiz':
                    actions.append(PostbackAction(
                        label="➡️ 下一題",
                        data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                    ))
                else:
                    actions.append(PostbackAction(
                        label="📖 繼續閱讀",
                        data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                    ))
            else:
                actions.append(PostbackAction(
                    label="📖 選擇章節",
                    data="action=show_chapter_menu"
                ))
            
            actions.append(PostbackAction(label="📊 查看分析", data="action=view_analytics"))
            
            template = ButtonsTemplate(
                title=f"作答結果 {emoji}",
                text=result_text,
                actions=actions[:4]
            )
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TemplateMessage(alt_text="答題結果", template=template)]
                )
            )
        
    except Exception as e:
        logger.error(f"答題錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="答題處理失敗，請稍後再試")]
            )
        )

# ===== 初始化和啟動 =====
if __name__ == "__main__":
    # 載入書籍資料
    book_data = load_book_data()
    
    # 初始化資料庫
    init_database()
    
    # 收集啟動統計
    collect_daily_stats()
    
    logger.info("=== LINE Bot 啟動完成 ===")
    logger.info(f"載入 {len(book_data.get('chapters', []))} 章節")
    logger.info("小規模多人架構版本 v1.0")
    logger.info("支援最多 1000 人同時使用")
    logger.info("支援手機圖文選單和電腦版文字指令")
    
    # 啟動應用（支援 Render 的 PORT 環境變數）
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True) = [s for s in chapter['sections'] if s['type'] == 'quiz']
                    if quiz_sections:
                        line_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text="內容已全部完成！\n\n輸入「本章測驗題」開始測驗\n或輸入「章節選擇」選擇其他章節")]
                            )
                        )
                    else:
                        line_api.reply_message(
                            ReplyMessageRequest(
                                reply_token=reply_token,
                                messages=[TextMessage(text="本章節已完成！\n\n輸入「章節選擇」選擇其他章節")]
                            )
                        )
                        
        elif direction == 'prev':
            if current_section_id == 0:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="已經是本章節的第一段")]
                    )
                )
            else:
                current_index = next((i for i, s in enumerate(content_sections) 
                                    if s['section_id'] == current_section_id), -1)
                
                if current_index > 0:
                    prev_section_id = content_sections[current_index - 1]['section_id']
                    handle_navigation(user_id, chapter_id, prev_section_id, reply_token, line_api)
                elif has_image:
                    handle_navigation(user_id, chapter_id, 0, reply_token, line_api)
                else:
                    line_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text="已經是本章節的第一段")]
                        )
                    )
                    
    except Exception as e:
        logger.error(f"導航指令錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="導航發生錯誤，請重新嘗試")]
            )
        )

# ===== 快速標記功能 =====
def handle_bookmark_current(user_id, reply_token, line_api):
    """標記當前位置"""
    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()
        
        if not user or not user['current_chapter_id']:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請先開始學習才能標記\n\n輸入「閱讀內容」或「章節選擇」")]
                )
            )
            conn.close()
            return
        
        chapter_id = user['current_chapter_id']
        section_id = user['current_section_id'] or 0
        
        existing = conn.execute(
            "SELECT id FROM bookmarks WHERE line_user_id = ? AND chapter_id = ? AND section_id = ?",
            (user_id, chapter_id, section_id)
        ).fetchone()
        
        if existing:
            text = f"📌 此位置已在書籤中\n第 {chapter_id} 章"
            if section_id == 0:
                text += " 章節圖片"
            else:
                text += f"第 {section_id} 段"
        else:
            conn.execute(
                "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                (user_id, chapter_id, section_id)
            )
            conn.commit()
            text = f"✅ 標記成功\n第 {chapter_id} 章"
            if section_id == 0:
                text += " 章節圖片"
            else:
                text += f"第 {section_id} 段"
        
        conn.close()
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )
        
    except Exception as e:
        logger.error(f"標記錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="標記失敗，請稍後再試")]
            )
        )

# ===== Postback 事件處理 =====
@handler.add(PostbackEvent)
@handle_errors
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    g.user_id = user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    logger.info(f"收到 Postback: {user_id} - {data}")
    
    update_user_activity(user_id)
    
    if is_duplicate_action(user_id, data):
        logger.info(f"重複操作已忽略: {data}")
        return
    
    try:
        # 直接章節選擇（數字 1-7）
        if data.isdigit():
            chapter_number = int(data)
            logger.info(f"數字章節選擇: 第 {chapter_number} 章")
            handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api)
            return
        
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        logger.info(f"解析的動作: {action}")
        
        if action == 'read_content':
            handle_start_reading(user_id, reply_token, line_api)
            
        elif action == 'show_chapter_menu':
            handle_show_chapter_carousel(user_id, reply_token, line_api)
            
        elif action == 'view_bookmarks':
            handle_bookmarks(user_id, reply_token, line_api)
            
        elif action == 'continue_reading':
            handle_resume_reading(user_id, reply_token, line_api)
            
        elif action == 'chapter_quiz':
            handle_chapter_quiz(user_id, reply_token, line_api)
            
        elif action == 'view_analytics':
            handle_error_analytics(user_id, reply_token, line_api)
            
        elif action == 'navigate':
            chapter_id = int(params.get('chapter_id', [1])[0])
            section_id = int(params.get('section_id', [1])[0])
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
            
        elif action == 'add_bookmark':
            handle_add_bookmark(params, user_id, reply_token, line_api)
            
        elif action == 'submit_answer':
            handle_answer(params, user_id, reply_token, line_api)
            
        elif action == 'select_chapter':
            chapter_id = int(params.get('chapter_id', [1])[0])
            handle_direct_chapter_selection(user_id, chapter_id, reply_token, line_api)
            
    except Exception as e:
        logger.error(f"Postback 處理錯誤: {e}")
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="操作發生錯誤，請稍後再試")]
                )
            )
        except:
            pass

# ===== 學習功能處理函數 =====
@handle_errors
def handle_progress_inquiry(user_id, reply_token, line_api):
    """處理進度查詢"""
    try:
        conn = get_db_connection()
        
        total_sections = sum(len(ch['sections']) for ch in book_data['chapters'])
        
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()
        
        completed_sections = 0
        if user and user['current_chapter_id']:
            for chapter in book_data['chapters']:
                if chapter['chapter_id'] < user['current_chapter_id']:
                    completed_sections += len([s for s in chapter['sections'] if s['type'] == 'content'])
                elif chapter['chapter_id'] == user['current_chapter_id']:
                    completed_sections += len([s for s in chapter['sections'] 
                                            if s['type'] == 'content' and s['section_id'] < (user['current_section_id'] or 1)])
        
        quiz_attempts = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()[0]
        
        if quiz_attempts > 0:
            correct_answers = conn.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 1",
                (user_id,)
            ).fetchone()[0]
            accuracy = (correct_answers / quiz_attempts) * 100
        else:
            accuracy = 0
        
        bookmark_count = conn.execute(
            "SELECT COUNT(*) FROM bookmarks WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()[0]
        
        conn.close()
        
        progress_text = "📊 學習進度報告\n\n"
        if user and user['current_chapter_id']:
            progress_text += f"📍 目前位置：第 {user['current_chapter_id']} 章第 {user['current_section_id'] or 1} 段\n"
        else:
            progress_text += "📍 目前位置：尚未開始\n"
            
        progress_text += f"📖 閱讀進度：{completed_sections}/{total_sections} 段\n"
        progress_text += f"📝 測驗次數：{quiz_attempts} 次\n"
        progress_text += f"🎯 答題正確率：{accuracy:.1f}%\n"
        progress_text += f"🔖 書籤數量：{bookmark_count} 個"
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=progress_text)]
            )
        )
        
    except Exception as e:
        logger.error(f"進度查詢錯誤: {e}")

@handle_errors
def handle_start_reading(user_id, reply_token, line_api):
    """閱讀內容：從第一章開始（如果有圖片先顯示圖片）"""
    try:
        chapter = next((ch for ch in book_data['chapters'] if ch['chapter_id'] == 1), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="第一章尚未開放")]
                )
            )
            return
        
        if chapter.get('image_url'):
            start_section_id = 0  # 圖片段落
        else:
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            start_section_id = content_sections[0]['section_id'] if content_sections else 1
        
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = 1, current_section_id = ? WHERE line_user_id = ?", 
            (start_section_id, user_id)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"使用者 {user_id} 開始閱讀第一章，起始段落: {start_section_id}")
        handle_navigation(user_id, 1, start_section_id, reply_token, line_api)
        
    except Exception as e:
        logger.error(f"開始閱讀錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="開始閱讀失敗，請稍後再試")]
            )
        )

@handle_errors
def handle_show_chapter_carousel(user_id, reply_token, line_api):
    """章節選擇：顯示橫式輪播選單"""
    try:
        columns = []
        
        for chapter in book_data['chapters']:
            chapter_id = chapter['chapter_id']
            title = chapter['title']
            
            if len(title) > 35:
                title = title[:32] + "..."
            
            content_count = len([s for s in chapter['sections'] if s['type'] == 'content'])
            quiz_count = len([s for s in chapter['sections'] if s['type'] == 'quiz'])
            
            thumbnail_url = chapter.get('image_url', 'https://via.placeholder.com/400x200/4A90E2/FFFFFF?text=Chapter+' + str(chapter_id))
            
            columns.append(
                CarouselColumn(
                    thumbnail_image_url=thumbnail_url,
                    title=f"第 {chapter_id} 章",
                    text=f"{title}\n\n內容：{content_count}段\n測驗：{quiz_count}題",
                    actions=[
                        PostbackAction(
                            label=f"選擇第{chapter_id}章",
                            data=f"action=select_chapter&chapter_id={chapter_id}"
                        )
                    ]
                )
            )
        
        carousel = CarouselTemplate(columns=columns)
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TemplateMessage(alt_text="選擇章節", template=carousel)]
            )
        )
        
    except Exception as e:
        logger.error(f"章節輪播錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="章節選單載入失敗，請稍後再試")]
            )
        )

@handle_errors
def handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api):
    """直接選擇章節"""
    try:
        chapter = next((ch for ch in book_data['chapters'] if ch['chapter_id'] == chapter_number), None)
        
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=f"第 {chapter_number} 章尚未開放")]
                )
            )
            return
        
        if chapter.get('image_url'):
            start_section_id = 0  # 圖片段落
        else:
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            start_section_id = content_sections[0]['section_id'] if content_sections else 1
        
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?", 
            (chapter_number, start_section_id, user_id)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"使用者 {user_id} 選擇第 {chapter_number} 章，起始段落: {start_section_id}")
        handle_navigation(user_id, chapter_number, start_section_id, reply_token, line_api)
        
    except Exception as e:
        logger.error(f"章節選擇錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="選擇章節失敗，請稍後再試")]
            )
        )

@handle_errors
def handle_resume_reading(user_id, reply_token, line_api):
    """上次進度：跳到上次位置"""
    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        conn.close()
        
        if user and user['current_chapter_id']:
            chapter_id = user['current_chapter_id']
            section_id = user['current_section_id'] or 0
            
            logger.info(f"繼續閱讀: CH {chapter_id}, SEC {section_id}")
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚未開始任何章節\n\n請點擊「閱讀內容」開始學習，或「章節選擇」選擇想要的章節")]
                )
            )
    except Exception as e:
        logger.error(f"繼續閱讀錯誤: {e}")

@handle_errors
def handle_chapter_quiz(user_id, reply_token, line_api):
    """本章測驗題：需要先進入章節才能使用"""
    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT current_chapter_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        conn.close()
        
        if not user or not user['current_chapter_id']:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請先選擇章節才能進行測驗\n\n點擊「章節選擇」選擇要測驗的章節")]
                )
            )
            return
            
        chapter_id = user['current_chapter_id']
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        
        if chapter:
            first_quiz = next((s for s in chapter['sections'] if s['type'] == 'quiz'), None)
            if first_quiz:
                handle_navigation(user_id, chapter_id, first_quiz['section_id'], reply_token, line_api)
            else:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=f"第 {chapter_id} 章目前沒有測驗題目")]
                    )
                )
                    
    except Exception as e:
        logger.error(f"章節測驗錯誤: {e}")

@handle_errors
def handle_error_analytics(user_id, reply_token, line_api):
    """錯誤分析：顯示答錯統計，錯誤多的排前面"""
    try:
        conn = get_db_connection()
        
        total_attempts = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()[0]
        
        if total_attempts == 0:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚未有測驗記錄\n\n完成測驗後可以查看詳細的錯誤分析")]
                )
            )
            conn.close()
            return
        
        correct_attempts = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 1", 
            (user_id,)
        ).fetchone()[0]
        
        wrong_attempts = total_attempts - correct_attempts
        accuracy = (correct_attempts / total_attempts) * 100
        
        error_stats = conn.execute(
            """SELECT chapter_id, section_id, COUNT(*) as error_count,
                      COUNT(*) * 100.0 / (SELECT COUNT(*) FROM quiz_attempts qa2 
                                          WHERE qa2.line_user_id = qa.line_user_id 
                                          AND qa2.chapter_id = qa.chapter_id 
                                          AND qa2.section_id = qa.section_id) as error_rate
               FROM quiz_attempts qa
               WHERE line_user_id = ? AND is_correct = 0
               GROUP BY chapter_id, section_id
               ORDER BY error_count DESC, error_rate DESC
               LIMIT 5""",
            (user_id,)
        ).fetchall()
        
        conn.close()
        
        analysis_text = f"📊 錯誤分析報告\n\n"
        analysis_text += f"總答題次數：{total_attempts} 次\n"
        analysis_text += f"答對次數：{correct_attempts} 次\n"
        analysis_text += f"答錯次數：{wrong_attempts} 次\n"
        analysis_text += f"正確率：{accuracy:.1f}%\n\n"
        
        if error_stats:
            analysis_text += "❌ 最需要加強的題目：\n"
            for i, stat in enumerate(error_stats, 1):
                chapter_id = stat['chapter_id']
                section_id = stat['section_id']
                error_count = stat['error_count']
                analysis_text += f"{i}. 第{chapter_id}章第{section_id}段 (錯{error_count}次)\n"
            
            quick_items = []
            for stat in error_stats[:3]:
                ch_id = stat['chapter_id']
                sec_id = stat['section_id']
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=f"複習 第{ch_id}章第{sec_id}段",
                            data=f"action=navigate&chapter_id={ch_id}&section_id={sec_id}"
                        )
                    )
                )
            
            if quick_items:
                analysis_text += "\n點擊下方快速複習最需要加強的題目"
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(
                            text=analysis_text,
                            quick_reply=QuickReply(items=quick_items)
                        )]
                    )
                )
            else:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=analysis_text)]
                    )
                )
        else:
            analysis_text += "🎉 太棒了！目前沒有答錯的題目"
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=analysis_text)]
                )
            )
        
    except Exception as e:
        logger.error(f"錯誤分析錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="錯誤分析載入失敗，請稍後再試")]
            )
        )

@handle_errors
def handle_bookmarks(user_id, reply_token, line_api):
    """我的書籤：查看標記內容"""
    try:
        conn = get_db_connection()
        bookmarks = conn.execute(
            """SELECT chapter_id, section_id
               FROM bookmarks
               WHERE line_user_id = ?
               ORDER BY chapter_id, section_id""", 
            (user_id,)
        ).fetchall()
        conn.close()
        
        if not bookmarks:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚無書籤內容\n\n閱讀時可以點擊「標記」按鈕收藏重要段落")]
                )
            )
        else:
            bookmark_text = f"📚 我的書籤 ({len(bookmarks)} 個)\n\n"
            
            quick_reply_items = []
            for i, bm in enumerate(bookmarks[:10], 1):
                ch_id, sec_id = bm['chapter_id'], bm['section_id']
                if sec_id == 0:
                    bookmark_text += f"{i}. 第{ch_id}章圖片\n"
                else:
                    bookmark_text += f"{i}. 第{ch_id}章第{sec_id}段\n"
                
                quick_reply_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=f"第{ch_id}章第{sec_id}段" if sec_id > 0 else f"第{ch_id}章圖片",
                            data=f"action=navigate&chapter_id={ch_id}&section_id={sec_id}"
                        )
                    )
                )
            
            if len(bookmarks) > 10:
                bookmark_text += f"... 還有 {len(bookmarks) - 10} 個書籤"
            
            bookmark_text += "\n點擊下方快速跳轉到書籤位置"
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(
                        text=bookmark_text,
                        quick_reply=QuickReply(items=quick_reply_items)
                    )]
                )
            )
            
    except Exception as e:
        logger.error(f"書籤錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="書籤載入失敗，請稍後再試")]
            )
        )

@handle_errors
def handle_navigation(user_id, chapter_id, section_id, reply_token, line_api):
    """處理內容導覽 - 修正圖片段落邏輯"""
    try:
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",
            (chapter_id, section_id, user_id)
        )
        conn.commit()
        conn.close()
        
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=f"找不到第 {chapter_id} 章")]
                )
            )
            return
        
        content_sections = sorted([s for s in chapter['sections'] if s['type'] == 'content'], 
                                key=lambda x: x['section_id'])
        has_chapter_image = bool(chapter.get('image_url'))
        
        messages = []
        
        # section_id = 0 表示顯示章節圖片
        if section_id == 0 and has_chapter_image:
            messages.append(ImageMessage(
                original_content_url=chapter['image_url'],
                preview_image_url=chapter['image_url']
            ))
            
            quick_items = []
            
            if content_sections:
                next_section_id = content_sections[0]['section_id']
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="➡️ 下一段",
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                        )
                    )
                )
            
            quick_items.append(
                QuickReplyItem(
                    action=PostbackAction(
                        label="🔖 標記",
                        data=f"action=add_bookmark&chapter_id={chapter_id}&section_id=0"
                    )
                )
            )
            
            total_content = len(content_sections) + 1
            progress_text = f"📖 {chapter['title']}\n\n第 1/{total_content} 段 (章節圖片)"
            
            messages.append(TextMessage(
                text=progress_text,
                quick_reply=QuickReply(items=quick_items)
            ))
        
        else:
            section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
            
            if not section:
                total_content = len(content_sections) + (1 if has_chapter_image else 0)
                
                template = ButtonsTemplate(
                    title="🎉 章節完成",
                    text=f"完成 {chapter['title']}\n\n已閱讀 {total_content} 段內容\n恭喜完成本章節！",
                    actions=[
                        PostbackAction(label="📊 查看分析", data="action=view_analytics"),
                        PostbackAction(label="📖 選擇章節", data="action=show_chapter_menu")
                    ]
                )
                messages.append(TemplateMessage(alt_text="章節完成", template=template))
                
            elif section['type'] == 'content':
                content = section['content']
                if len(content) > 1000:
                    content = content[:1000] + "\n\n...(內容較長，請點擊下一段繼續)"
                    
                messages.append(TextMessage(text=content))
                
                quick_items = []
                
                current_index = next((i for i, s in enumerate(content_sections) if s['section_id'] == section_id), -1)
                
                if current_index > 0:
                    prev_section_id = content_sections[current_index - 1]['section_id']
                    quick_items.append(
                        QuickReplyItem(
                            action=PostbackAction(
                                label="⬅️ 上一段",
                                data=f"action=navigate&chapter_id={chapter_id}&section_id={prev_section_id}"
                            )
                        )
                    )
                elif has_chapter_image:
                    quick_items.append(
                        QuickReplyItem(
                            action=PostbackAction(
                                label="⬅️ 上一段",
                                data=f"action=navigate&chapter_id={chapter_id}&section_id=0"
                            )
                        )
                    )
                
                if current_index < len(content_sections) - 1:
                    next_section_id = content_sections[current_index + 1]['section_id']
                    quick_items.append(
                        QuickReplyItem(
                            action=PostbackAction(
                                label="➡️ 下一段",
                                data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                            )
                        )
                    )
                else:
                    quiz_sections = [s for s in chapter['sections'] if s['type'] == 'quiz']
                    if quiz_sections:
                        first_quiz_id = min(quiz_sections, key=lambda x: x['section_id'])['section_id']
                        quick_items.append(
                            QuickReplyItem(
                                action=PostbackAction(
                                    label="📝 開始測驗",
                                    data=f"action=navigate&chapter_id={chapter_id}&section_id={first_quiz_id}"
                                )
                            )
                        )
                
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="🔖 標記",
                            data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"
                        )
                    )
                )
                
                content_position = current_index + 1
                if has_chapter_image:
                    display_position = content_position + 1
                    total_content = len(content_sections) + 1
                else:
                    display_position = content_position
                    total_content = len(content_sections)
                
                progress_text = f"📖 第 {display_position}/{total_content} 段"
                
                messages.append(TextMessage(
                    text=progress_text,
                    quick_reply=QuickReply(items=quick_items)
                ))
                
            elif section['type'] == 'quiz':
                quiz = section['content']
                quick_items = []
                
                for key, text in quiz['options'].items():
                    label = f"{key}. {text}"
                    if len(label) > 20:
                        label = label[:17] + "..."
                        
                    quick_items.append(
                        QuickReplyItem(
                            action=PostbackAction(
                                label=label,
                                display_text=f"選 {key}",
                                data=f"action=submit_answer&chapter_id={chapter_id}&section_id={section_id}&answer={key}"
                            )
                        )
                    )
                
                quiz_sections