import os
import json
import sqlite3
import requests
import time
import re
from urllib.parse import parse_qs
from contextlib import contextmanager
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage, ImageMessage, PostbackAction,
    TemplateMessage, ButtonsTemplate, CarouselTemplate, CarouselColumn,
    QuickReply, QuickReplyItem
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent, FollowEvent
import threading
from datetime import datetime, timedelta

app = Flask(__name__)
DATABASE_NAME = 'linebot.db'
CONNECTION_POOL_SIZE = 10
connection_pool = []
pool_lock = threading.Lock()

@contextmanager
def get_db_connection():
    conn = None
    try:
        with pool_lock:
            if connection_pool:
                conn = connection_pool.pop()
            else:
                conn = sqlite3.connect(DATABASE_NAME, timeout=20.0)
                conn.row_factory = sqlite3.Row
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            try:
                conn.commit()
                with pool_lock:
                    if len(connection_pool) < CONNECTION_POOL_SIZE:
                        connection_pool.append(conn)
                    else:
                        conn.close()
            except:
                conn.close()

def init_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT UNIQUE NOT NULL,
                display_name TEXT,
                current_chapter_id INTEGER,
                current_section_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                action_data TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_user_id ON user_actions(line_user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_timestamp ON user_actions(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(line_user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_id ON quiz_attempts(line_user_id)')

def cleanup_old_actions():
    current_time = time.time()
    cutoff_time = current_time - 3600
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM user_actions WHERE timestamp < ?", (cutoff_time,))
    except Exception as e:
        print(f"Cleanup error: {e}")

def is_duplicate_action(user_id, action_data, cooldown=2):
    current_time = time.time()
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM user_actions WHERE timestamp < ?", (current_time - cooldown * 2,))
            recent_action = conn.execute(
                "SELECT timestamp FROM user_actions WHERE line_user_id = ? AND action_data = ? AND timestamp > ?",
                (user_id, action_data, current_time - cooldown)
            ).fetchone()
            if recent_action:
                return True
            conn.execute(
                "INSERT INTO user_actions (line_user_id, action_data, timestamp) VALUES (?, ?, ?)",
                (user_id, action_data, current_time)
            )
            return False
    except Exception as e:
        print(f"Duplicate check error: {e}")
        return False

def update_user_activity(user_id):
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE line_user_id = ?",
                (user_id,)
            )
    except:
        pass

def check_new_user_guidance(user_id):
    try:
        with get_db_connection() as conn:
            action_count = conn.execute(
                "SELECT COUNT(*) FROM user_actions WHERE line_user_id = ?", 
                (user_id,)
            ).fetchone()[0]
        if action_count < 5:
            return "\n\n🌟 小提示：輸入「1」快速開始第一章，「幫助」查看所有指令"
        return ""
    except:
        return ""

CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')

required_env_vars = [CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID]
if not all(required_env_vars):
    print("Missing required environment variables")
    exit(1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

def load_book_data():
    try:
        with open('book.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Load book.json failed: {e}")
        return {"chapters": []}

book_data = load_book_data()
init_database()

def switch_rich_menu(user_id, rich_menu_id):
    try:
        headers = {'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
        url = f'https://api.line.me/v2/bot/user/{user_id}/richmenu/{rich_menu_id}'
        response = requests.post(url, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Rich menu switch error: {e}")
        return False
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f"Callback error: {e}")
        abort(500)
    return 'OK'

@app.route("/health", methods=['GET'])
def health_check():
    cleanup_old_actions()
    return {"status": "healthy", "chapters": len(book_data.get('chapters', []))}

@app.route("/", methods=['GET'])
def index():
    return {"message": "LINE Bot is running", "status": "healthy"}

@app.route("/ping", methods=['GET'])
def ping():
    return "pong"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    update_user_activity(user_id)
    
    try:
        normalized_text = text.replace(' ', '').lower()
        
        if any(keyword in normalized_text for keyword in ['閱讀內容', '開始閱讀', '閱讀', 'read', 'start']):
            handle_start_reading(user_id, event.reply_token, line_api)
        elif any(keyword in normalized_text for keyword in ['章節選擇', '選擇章節', 'chapter', 'chapters']):
            handle_show_chapter_carousel(user_id, event.reply_token, line_api)
        elif any(keyword in normalized_text for keyword in ['我的書籤', '書籤', 'bookmark', 'bookmarks']):
            handle_bookmarks(user_id, event.reply_token, line_api)
        elif any(keyword in normalized_text for keyword in ['上次進度', '繼續閱讀', '進度', 'continue', 'resume']):
            handle_resume_reading(user_id, event.reply_token, line_api)
        elif any(keyword in normalized_text for keyword in ['本章測驗', '測驗題', '測驗', 'quiz', 'test']):
            handle_chapter_quiz(user_id, event.reply_token, line_api)
        elif any(keyword in normalized_text for keyword in ['錯誤分析', '分析', 'analytics', 'analysis']):
            handle_error_analytics(user_id, event.reply_token, line_api)
        elif text.isdigit() and 1 <= int(text) <= 7:
            chapter_number = int(text)
            handle_direct_chapter_selection(user_id, chapter_number, event.reply_token, line_api)
        elif text.lower() in ['n', 'next', '下', '下一段', '下一']:
            handle_quick_navigation(user_id, 'next', event.reply_token, line_api)
        elif text.lower() in ['b', 'back', 'prev', '上', '上一段', '上一']:
            handle_quick_navigation(user_id, 'prev', event.reply_token, line_api)
        elif text.startswith('第') and text.endswith('章') and len(text) == 3:
            try:
                chapter_num = int(text[1])
                if 1 <= chapter_num <= 7:
                    handle_direct_chapter_selection(user_id, chapter_num, event.reply_token, line_api)
                else:
                    raise ValueError("章節號碼超出範圍")
            except:
                handle_unknown_command(user_id, event.reply_token, line_api, text)
        elif '跳到' in normalized_text or '跳轉' in normalized_text:
            match = re.search(r'第?(\d+)章.*?第?(\d+)段', text)
            if match:
                ch, sec = int(match.group(1)), int(match.group(2))
                handle_navigation(user_id, ch, sec, event.reply_token, line_api)
            else:
                handle_unknown_command(user_id, event.reply_token, line_api, text)
        elif any(keyword in normalized_text for keyword in ['學習進度', '我的進度', 'progress']):
            handle_progress_inquiry(user_id, event.reply_token, line_api)
        elif any(keyword in normalized_text for keyword in ['狀態', '資訊', 'status', 'info']):
            handle_status_inquiry(user_id, event.reply_token, line_api)
        elif any(keyword in normalized_text for keyword in ['幫助', '說明', '指令', 'help', 'command']):
            handle_help_message(user_id, event.reply_token, line_api)
        else:
            handle_unknown_command(user_id, event.reply_token, line_api, text)
            
    except Exception as e:
        print(f"Handle message error: {e}")
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="指令處理發生錯誤，請稍後再試\n\n輸入「幫助」查看可用指令" + check_new_user_guidance(user_id))]
                )
            )
        except:
            pass

def handle_help_message(user_id, reply_token, line_api):
    help_text = """📖 指令說明：

📱 **快速指令**
• 閱讀內容 / 開始閱讀 → 從第一章開始
• 章節選擇 → 選擇 1-7 章節
• 我的書籤 → 查看收藏內容
• 上次進度 / 繼續閱讀 → 跳到上次位置
• 本章測驗 → 練習當前章節測驗
• 錯誤分析 → 查看答錯統計

🔢 **數字快捷**
• 直接輸入 1-7 → 快速跳到該章節
• 第1章、第2章... → 另一種章節選擇方式

⚡ **快速導航**
• n / next / 下 / 下一段 → 下一段內容
• b / back / 上 / 上一段 → 上一段內容
• 跳到第2章第3段 → 直接跳轉

📊 **學習追蹤**
• 學習進度 → 詳細進度報告
• 狀態 → 顯示當前學習狀態

💡 **操作技巧**
✓ 可使用中文或英文指令
✓ 閱讀時點擊「標記」收藏重要段落
✓ 完成測驗自動記錄學習進度
✓ 支援上下段落快速切換"""
    
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=help_text)]
        )
    )

def handle_status_inquiry(user_id, reply_token, line_api):
    try:
        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT current_chapter_id, current_section_id, display_name FROM users WHERE line_user_id = ?",
                (user_id,)
            ).fetchone()
            
            bookmark_count = conn.execute(
                "SELECT COUNT(*) FROM bookmarks WHERE line_user_id = ?",
                (user_id,)
            ).fetchone()[0]
            
            quiz_count = conn.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?",
                (user_id,)
            ).fetchone()[0]
        
        if user:
            status_text = f"👤 {user['display_name'] or '學習者'}\n\n"
            if user['current_chapter_id']:
                status_text += f"📍 目前位置：第 {user['current_chapter_id']} 章第 {user['current_section_id'] or 1} 段\n"
            else:
                status_text += "📍 目前位置：尚未開始\n"
            status_text += f"🔖 書籤數量：{bookmark_count} 個\n"
            status_text += f"📝 測驗記錄：{quiz_count} 次\n\n"
            status_text += "輸入「幫助」查看所有可用指令"
        else:
            status_text = "使用者資料讀取失敗，請稍後再試"
            
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=status_text)]
            )
        )
    except Exception as e:
        print(f"Status inquiry error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="狀態查詢失敗，請稍後再試")]
            )
        )
def handle_unknown_command(user_id, reply_token, line_api, original_text):
    suggestions = [
        "📚 閱讀內容 - 開始學習",
        "📖 章節選擇 - 選擇章節", 
        "🔖 我的書籤 - 查看收藏",
        "⏯️ 上次進度 - 繼續學習",
        "📝 本章測驗 - 練習測驗",
        "📊 錯誤分析 - 學習分析",
        "💡 幫助 - 查看說明"
    ]
    suggestion_text = "請嘗試以下指令：\n\n" + "\n".join(suggestions)
    suggestion_text += "\n\n或直接輸入數字 1-7 選擇章節"
    suggestion_text += check_new_user_guidance(user_id)
    
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=suggestion_text)]
        )
    )

def handle_quick_navigation(user_id, direction, reply_token, line_api):
    try:
        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
                (user_id,)
            ).fetchone()
        
        if not user or not user['current_chapter_id']:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請先選擇章節開始學習\n\n輸入「1」快速開始第一章，或「章節選擇」選擇其他章節")]
                )
            )
            return
            
        current_chapter = user['current_chapter_id']
        current_section = user['current_section_id'] or 0
        
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == current_chapter), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="章節資料錯誤，請重新選擇章節")]
                )
            )
            return
        
        has_image = bool(chapter.get('image_url'))
        content_sections = sorted([s for s in chapter['sections'] if s['type'] == 'content'], 
                                key=lambda x: x['section_id'])
        
        all_sections = []
        if has_image:
            all_sections.append(0)
        all_sections.extend([s['section_id'] for s in content_sections])
        
        try:
            current_index = all_sections.index(current_section)
        except ValueError:
            current_index = 0
            
        if direction == 'next':
            target_index = current_index + 1
            if target_index >= len(all_sections):
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="已經是最後一段了\n\n輸入「本章測驗」開始測驗，或「章節選擇」選擇其他章節")]
                    )
                )
                return
        else:
            target_index = current_index - 1
            if target_index < 0:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="已經是第一段了\n\n輸入「章節選擇」選擇其他章節")]
                    )
                )
                return
        
        target_section = all_sections[target_index]
        handle_navigation(user_id, current_chapter, target_section, reply_token, line_api)
        
    except Exception as e:
        print(f"Quick navigation error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="導航失敗，請稍後再試")]
            )
        )

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        try:
            profile = line_api.get_profile(user_id)
            display_name = profile.display_name
        except:
            display_name = f"User_{user_id[-6:]}"
        
        with get_db_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", 
                (user_id, display_name)
            )
        
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        
        welcome_text = """歡迎使用五分鐘英文文法攻略！

📱 **手機用戶**：使用下方圖文選單操作
💻 **電腦用戶**：可直接輸入指令

🚀 **快速開始**
• 輸入「1」→ 立即開始第一章
• 輸入「幫助」→ 查看所有指令

📚 **主要功能**
• 閱讀內容：從第一章開始
• 章節選擇：選擇想學的章節  
• 我的書籤：查看收藏內容
• 上次進度：繼續上次學習
• 本章測驗：練習測驗題目
• 錯誤分析：檢視學習狀況"""
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=welcome_text)]
            )
        )
        
    except Exception as e:
        print(f"Follow event error: {e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    update_user_activity(user_id)
    
    if is_duplicate_action(user_id, data):
        return
    
    try:
        if data.isdigit():
            chapter_number = int(data)
            handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api)
            return
        
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        
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
        print(f"Postback error: {e}")
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="操作發生錯誤，請稍後再試")]
                )
            )
        except:
            pass

def handle_start_reading(user_id, reply_token, line_api):
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
            start_section_id = 0
        else:
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            start_section_id = content_sections[0]['section_id'] if content_sections else 1
        
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE users SET current_chapter_id = 1, current_section_id = ? WHERE line_user_id = ?", 
                (start_section_id, user_id)
            )
        
        handle_navigation(user_id, 1, start_section_id, reply_token, line_api)
        
    except Exception as e:
        print(f"Start reading error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="開始閱讀失敗，請稍後再試")]
            )
        )
def handle_show_chapter_carousel(user_id, reply_token, line_api):
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
        print(f"Chapter carousel error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="章節選單載入失敗，請稍後再試")]
            )
        )

def handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api):
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
            start_section_id = 0
        else:
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            start_section_id = content_sections[0]['section_id'] if content_sections else 1
        
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?", 
                (chapter_number, start_section_id, user_id)
            )
        
        handle_navigation(user_id, chapter_number, start_section_id, reply_token, line_api)
        
    except Exception as e:
        print(f"Chapter selection error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="選擇章節失敗，請稍後再試")]
            )
        )

def handle_resume_reading(user_id, reply_token, line_api):
    try:
        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
                (user_id,)
            ).fetchone()
        
        if user and user['current_chapter_id']:
            chapter_id = user['current_chapter_id']
            section_id = user['current_section_id'] or 0
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚未開始任何章節\n\n請輸入「閱讀內容」開始學習，或「章節選擇」選擇想要的章節" + check_new_user_guidance(user_id))]
                )
            )
    except Exception as e:
        print(f"Resume reading error: {e}")

def handle_chapter_quiz(user_id, reply_token, line_api):
    try:
        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT current_chapter_id FROM users WHERE line_user_id = ?", 
                (user_id,)
            ).fetchone()
        
        if not user or not user['current_chapter_id']:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請先選擇章節才能進行測驗\n\n輸入「章節選擇」選擇要測驗的章節，或輸入「1」快速開始第一章")]
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
        print(f"Chapter quiz error: {e}")

def handle_progress_inquiry(user_id, reply_token, line_api):
    try:
        with get_db_connection() as conn:
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
        print(f"Progress inquiry error: {e}")

def handle_error_analytics(user_id, reply_token, line_api):
    try:
        with get_db_connection() as conn:
            total_attempts = conn.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", 
                (user_id,)
            ).fetchone()[0]
            
            if total_attempts == 0:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="尚未有測驗記錄\n\n完成測驗後可以查看詳細的錯誤分析" + check_new_user_guidance(user_id))]
                    )
                )
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
        print(f"Error analytics error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="錯誤分析載入失敗，請稍後再試")]
            )
        )
def handle_bookmarks(user_id, reply_token, line_api):
    try:
        with get_db_connection() as conn:
            bookmarks = conn.execute(
                """SELECT chapter_id, section_id
                   FROM bookmarks
                   WHERE line_user_id = ?
                   ORDER BY chapter_id, section_id""", 
                (user_id,)
            ).fetchall()
        
        if not bookmarks:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚無書籤內容\n\n閱讀時可以點擊「標記」按鈕收藏重要段落" + check_new_user_guidance(user_id))]
                )
            )
        else:
            bookmark_text = f"📚 我的書籤 ({len(bookmarks)} 個)\n\n"
            
            quick_reply_items = []
            for i, bm in enumerate(bookmarks[:10], 1):
                ch_id, sec_id = bm['chapter_id'], bm['section_id']
                if sec_id == 0:
                    bookmark_text += f"{i}. 第{ch_id}章圖片\n"
                    label = f"第{ch_id}章圖片"
                else:
                    bookmark_text += f"{i}. 第{ch_id}章第{sec_id}段\n"
                    label = f"第{ch_id}章第{sec_id}段"
                
                quick_reply_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=label if len(label) <= 20 else label[:17] + "...",
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
        print(f"Bookmarks error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="書籤載入失敗，請稍後再試")]
            )
        )

def handle_add_bookmark(params, user_id, reply_token, line_api):
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        
        with get_db_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM bookmarks WHERE line_user_id = ? AND chapter_id = ? AND section_id = ?",
                (user_id, chapter_id, section_id)
            ).fetchone()
            
            if existing:
                if section_id == 0:
                    text = "📌 章節圖片已在書籤中\n\n輸入「我的書籤」查看所有收藏"
                else:
                    text = "📌 此段已在書籤中\n\n輸入「我的書籤」查看所有收藏"
            else:
                conn.execute(
                    "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                    (user_id, chapter_id, section_id)
                )
                if section_id == 0:
                    text = f"✅ 已加入書籤\n\n第 {chapter_id} 章圖片"
                else:
                    text = f"✅ 已加入書籤\n\n第 {chapter_id} 章第 {section_id} 段"
        
        line_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )
        
    except Exception as e:
        print(f"Add bookmark error: {e}")

def handle_answer(params, user_id, reply_token, line_api):
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        user_answer = params.get('answer', [None])[0]
        
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
        
        if section and section['type'] == 'quiz':
            correct = section['content']['answer']
            is_correct = user_answer == correct
            
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)",
                    (user_id, chapter_id, section_id, user_answer, is_correct)
                )
            
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
        print(f"Answer error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="答題處理失敗，請稍後再試")]
            )
        )

def start_keep_alive():
    def keep_alive():
        while True:
            try:
                requests.get('https://your-app-name.onrender.com/ping', timeout=30)
                time.sleep(840)
            except:
                time.sleep(840)
    
    import threading
    thread = threading.Thread(target=keep_alive)
    thread.daemon = True
    thread.start()
def handle_navigation(user_id, chapter_id, section_id, reply_token, line_api):
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",
                (chapter_id, section_id, user_id)
            )
        
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
            progress_text = f"📖 {chapter['title']}\n\n第 1/{total_content} 段 (章節圖片)\n\n💡 輸入 n=下一段"
            
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
                
                progress_text = f"📖 第 {display_position}/{total_content} 段\n\n💡 輸入 n=下一段 b=上一段"
                
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
        print(f"Navigation error: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="載入內容失敗，請稍後再試")]
            )
        )

if __name__ == "__main__":
    start_keep_alive()
    print("LINE Bot 啟動")
    print(f"載入 {len(book_data.get('chapters', []))} 章節")
    print("五分鐘英文文法攻略 - 優化版 v5.0")
    print("支援100人小規模使用，防休眠機制已啟用")
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)