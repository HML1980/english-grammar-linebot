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
from linebot.v3.messaging import (Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, ImageMessage, PostbackAction, TemplateMessage, ButtonsTemplate, CarouselTemplate, CarouselColumn, QuickReply, QuickReplyItem)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent, FollowEvent
import threading

os.makedirs('logs', exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler('logs/linebot.log', encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)
app = Flask(__name__)

CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'linebot.db')

logger.info("=== 系統啟動 ===")
logger.info(f"CHANNEL_SECRET: {'已設定' if CHANNEL_SECRET else '未設定'}")
logger.info(f"CHANNEL_ACCESS_TOKEN: {'已設定' if CHANNEL_ACCESS_TOKEN else '未設定'}")
logger.info(f"MAIN_RICH_MENU_ID: {'已設定' if MAIN_RICH_MENU_ID else '未設定'}")

required_env_vars = [CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID]
if not all(required_env_vars):
    logger.error("錯誤：缺少必要的環境變數")
    exit(1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
_local = threading.local()

def get_db_connection():
    if not hasattr(_local, 'connection'):
        _local.connection = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        _local.connection.row_factory = sqlite3.Row
        _local.connection.execute('PRAGMA journal_mode=WAL')
        _local.connection.execute('PRAGMA synchronous=NORMAL')
    return _local.connection

def init_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, line_user_id TEXT UNIQUE NOT NULL, display_name TEXT, current_chapter_id INTEGER, current_section_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP, total_interactions INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS bookmarks (id INTEGER PRIMARY KEY AUTOINCREMENT, line_user_id TEXT NOT NULL, chapter_id INTEGER NOT NULL, section_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(line_user_id, chapter_id, section_id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, line_user_id TEXT NOT NULL, chapter_id INTEGER NOT NULL, section_id INTEGER NOT NULL, user_answer TEXT NOT NULL, is_correct BOOLEAN NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, line_user_id TEXT NOT NULL, action_type TEXT NOT NULL, action_data TEXT NOT NULL, timestamp REAL NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        logger.info("資料庫初始化完成")
    except Exception as e:
        logger.error(f"資料庫初始化失敗: {e}")
        raise

@app.before_request
def before_request():
    g.start_time = time.time()
    g.user_id = None

@app.after_request
def after_request(response):
    try:
        total_time = time.time() - g.start_time
        user_id = getattr(g, 'user_id', 'N/A')
        logger.info(f"Request: {request.method} {request.path} | Status: {response.status_code} | Time: {total_time:.3f}s | User: {user_id}")
    except Exception as e:
        logger.error(f"請求監控失敗: {e}")
    return response

def is_duplicate_action(user_id, action_data, cooldown=2):
    current_time = time.time()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM user_actions WHERE line_user_id = ? AND action_data = ? AND timestamp > ?", (user_id, action_data, current_time - cooldown))
        if cursor.fetchone():
            return True
        cursor.execute("INSERT INTO user_actions (line_user_id, action_type, action_data, timestamp) VALUES (?, ?, ?, ?)", (user_id, "postback", action_data, current_time))
        conn.commit()
        return False
    except Exception as e:
        logger.error(f"重複操作檢查錯誤: {e}")
        return False

def update_user_activity(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP, total_interactions = total_interactions + 1 WHERE line_user_id = ?", (user_id,))
        if cursor.rowcount == 0:
            cursor.execute("INSERT OR IGNORE INTO users (line_user_id, total_interactions) VALUES (?, 1)", (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"使用者活動更新失敗: {e}")

def load_book_data():
    try:
        with open('book.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"book.json 載入成功，包含 {len(data.get('chapters', []))} 章節")
        return data
    except Exception as e:
        logger.error(f"載入 book.json 失敗: {e}")
        return {"chapters": []}

def switch_rich_menu(user_id, rich_menu_id):
    try:
        headers = {'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'}
        url = f'https://api.line.me/v2/bot/user/{user_id}/richmenu/{rich_menu_id}'
        response = requests.post(url, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"切換圖文選單錯誤: {e}")
        return False

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

@app.route("/health", methods=['GET'])
def health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        return {"status": "healthy", "total_users": user_count, "timestamp": time.time()}
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        return {"status": "unhealthy", "error": str(e)}, 500

@app.route("/", methods=['GET'])
def index():
    return {"message": "LINE Bot is running", "status": "healthy", "version": "v1.0"}

@handler.add(FollowEvent)
def handle_follow(event):
    try:
        user_id = event.source.user_id
        g.user_id = user_id
        line_api = MessagingApi(ApiClient(configuration))
        try:
            profile = line_api.get_profile(user_id)
            display_name = profile.display_name
        except:
            display_name = f"User_{user_id[-6:]}"
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", (user_id, display_name))
        conn.commit()
        update_user_activity(user_id)
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="歡迎使用五分鐘英文文法攻略！\n\n請使用下方圖文選單開始學習：\n\n📚 閱讀內容：從第一章開始\n📖 章節選擇：選擇想學的章節\n🔖 我的書籤：查看收藏內容\n⏯️ 上次進度：繼續上次學習\n📝 本章測驗題：練習測驗\n📊 錯誤分析：檢視學習狀況\n\n💡 電腦版用戶可直接輸入文字指令，如「閱讀內容」、「章節選擇」等\n輸入「幫助」查看所有可用指令")]))
    except Exception as e:
        logger.error(f"處理關注事件錯誤: {e}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    try:
        text = event.message.text.strip()
        user_id = event.source.user_id
        g.user_id = user_id
        line_api = MessagingApi(ApiClient(configuration))
        update_user_activity(user_id)
        logger.info(f"收到訊息: {user_id} - {text}")
        cmd = text.replace(" ", "").lower()
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
        elif text.isdigit() and 1 <= int(text) <= 7:
            handle_direct_chapter_selection(user_id, int(text), event.reply_token, line_api)
        elif cmd in ['下一段', '下一頁', '繼續', 'next', '下一']:
            handle_navigation_command(user_id, 'next', event.reply_token, line_api)
        elif cmd in ['上一段', '上一頁', '返回', 'prev', 'previous', '上一']:
            handle_navigation_command(user_id, 'prev', event.reply_token, line_api)
        elif cmd in ['標記', '收藏', 'bookmark']:
            handle_bookmark_current(user_id, event.reply_token, line_api)
        elif cmd in ['幫助', 'help', '指令', '說明']:
            help_text = """📖 文字指令說明\n\n📚 學習指令：\n• 閱讀內容 - 從第一章開始\n• 章節選擇 - 選擇要學習的章節\n• 上次進度 - 繼續上次學習位置\n• 1-7 - 直接跳到指定章節\n\n📝 測驗指令：\n• 本章測驗題 - 練習當前章節測驗\n• 錯誤分析 - 查看學習弱點分析\n\n🔖 管理指令：\n• 我的書籤 - 查看收藏的內容\n• 標記 - 收藏當前段落\n\n⏯️ 導航指令：\n• 下一段 - 進入下一段內容\n• 上一段 - 回到上一段內容\n\n💡 其他指令：\n• 進度 - 查看學習統計\n• 幫助 - 顯示此說明\n\n📱 提示：手機版可使用下方圖文選單操作"""
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=help_text)]))
        else:
            suggestion_text = """❓ 指令無法識別\n\n常用指令：\n• 閱讀內容 - 開始學習\n• 章節選擇 - 選擇章節  \n• 我的書籤 - 查看收藏\n• 本章測驗題 - 練習測驗\n• 幫助 - 查看所有指令\n\n💡 提示：手機版可使用下方圖文選單"""
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=suggestion_text)]))
    except Exception as e:
        logger.error(f"處理文字訊息錯誤: {e}")
        try:
            line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text="系統暫時忙碌，請稍後再試")]))
        except:
            pass

@handler.add(PostbackEvent)
def handle_postback(event):
    try:
        data = event.postback.data
        user_id = event.source.user_id
        g.user_id = user_id
        line_api = MessagingApi(ApiClient(configuration))
        logger.info(f"收到 Postback: {user_id} - {data}")
        update_user_activity(user_id)
        if is_duplicate_action(user_id, data):
            return
        if data.isdigit():
            handle_direct_chapter_selection(user_id, int(data), event.reply_token, line_api)
            return
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        if action == 'read_content':
            handle_start_reading(user_id, event.reply_token, line_api)
        elif action == 'show_chapter_menu':
            handle_show_chapter_carousel(user_id, event.reply_token, line_api)
        elif action == 'view_bookmarks':
            handle_bookmarks(user_id, event.reply_token, line_api)
        elif action == 'continue_reading':
            handle_resume_reading(user_id, event.reply_token, line_api)
        elif action == 'chapter_quiz':
            handle_chapter_quiz(user_id, event.reply_token, line_api)
        elif action == 'view_analytics':
            handle_error_analytics(user_id, event.reply_token, line_api)
        elif action == 'navigate':
            chapter_id = int(params.get('chapter_id', [1])[0])
            section_id = int(params.get('section_id', [1])[0])
            handle_navigation(user_id, chapter_id, section_id, event.reply_token, line_api)
        elif action == 'add_bookmark':
            handle_add_bookmark(params, user_id, event.reply_token, line_api)
        elif action == 'submit_answer':
            handle_answer(params, user_id, event.reply_token, line_api)
        elif action == 'select_chapter':
            chapter_id = int(params.get('chapter_id', [1])[0])
            handle_direct_chapter_selection(user_id, chapter_id, event.reply_token, line_api)
    except Exception as e:
        logger.error(f"Postback 處理錯誤: {e}")

def handle_start_reading(user_id, reply_token, line_api):
    try:
        chapter = next((ch for ch in book_data['chapters'] if ch['chapter_id'] == 1), None)
        if not chapter:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="第一章尚未開放")]))
            return
        start_section_id = 0 if chapter.get('image_url') else 1
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET current_chapter_id = 1, current_section_id = ? WHERE line_user_id = ?", (start_section_id, user_id))
        conn.commit()
        handle_navigation(user_id, 1, start_section_id, reply_token, line_api)
    except Exception as e:
        logger.error(f"開始閱讀錯誤: {e}")

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
            columns.append(CarouselColumn(thumbnail_image_url=chapter.get('image_url', f'https://via.placeholder.com/400x200/4A90E2/FFFFFF?text=Chapter+{chapter_id}'), title=f"第 {chapter_id} 章", text=f"{title}\n\n內容：{content_count}段\n測驗：{quiz_count}題", actions=[PostbackAction(label=f"選擇第{chapter_id}章", data=f"action=select_chapter&chapter_id={chapter_id}")]))
        carousel = CarouselTemplate(columns=columns)
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TemplateMessage(alt_text="選擇章節", template=carousel)]))
    except Exception as e:
        logger.error(f"章節輪播錯誤: {e}")

def handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api):
    try:
        chapter = next((ch for ch in book_data['chapters'] if ch['chapter_id'] == chapter_number), None)
        if not chapter:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=f"第 {chapter_number} 章尚未開放")]))
            return
        start_section_id = 0 if chapter.get('image_url') else 1
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?", (chapter_number, start_section_id, user_id))
        conn.commit()
        handle_navigation(user_id, chapter_number, start_section_id, reply_token, line_api)
    except Exception as e:
        logger.error(f"章節選擇錯誤: {e}")

def handle_resume_reading(user_id, reply_token, line_api):
    try:
        conn = get_db_connection()
        user = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        if user and user['current_chapter_id']:
            chapter_id = user['current_chapter_id']
            section_id = user['current_section_id'] or 0
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
        else:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="尚未開始任何章節\n\n請點擊「閱讀內容」開始學習")]))
    except Exception as e:
        logger.error(f"繼續閱讀錯誤: {e}")

def handle_chapter_quiz(user_id, reply_token, line_api):
    try:
        conn = get_db_connection()
        user = conn.execute("SELECT current_chapter_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        if not user or not user['current_chapter_id']:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="請先選擇章節才能進行測驗")]))
            return
        chapter_id = user['current_chapter_id']
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if chapter:
            first_quiz = next((s for s in chapter['sections'] if s['type'] == 'quiz'), None)
            if first_quiz:
                handle_navigation(user_id, chapter_id, first_quiz['section_id'], reply_token, line_api)
            else:
                line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=f"第 {chapter_id} 章目前沒有測驗題目")]))
    except Exception as e:
        logger.error(f"章節測驗錯誤: {e}")

def handle_error_analytics(user_id, reply_token, line_api):
    try:
        conn = get_db_connection()
        total_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", (user_id,)).fetchone()[0]
        if total_attempts == 0:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="尚未有測驗記錄\n\n完成測驗後可以查看詳細的錯誤分析")]))
            return
        correct_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 1", (user_id,)).fetchone()[0]
        accuracy = (correct_attempts / total_attempts) * 100
        analysis_text = f"📊 錯誤分析報告\n\n總答題次數：{total_attempts} 次\n答對次數：{correct_attempts} 次\n答錯次數：{total_attempts - correct_attempts} 次\n正確率：{accuracy:.1f}%"
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=analysis_text)]))
    except Exception as e:
        logger.error(f"錯誤分析錯誤: {e}")

def handle_bookmarks(user_id, reply_token, line_api):
    try:
        conn = get_db_connection()
        bookmarks = conn.execute("SELECT chapter_id, section_id FROM bookmarks WHERE line_user_id = ? ORDER BY chapter_id, section_id", (user_id,)).fetchall()
        if not bookmarks:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="尚無書籤內容\n\n閱讀時可以點擊「標記」按鈕收藏重要段落")]))
        else:
            bookmark_text = f"📚 我的書籤 ({len(bookmarks)} 個)\n\n"
            for i, bm in enumerate(bookmarks[:10], 1):
                ch_id, sec_id = bm['chapter_id'], bm['section_id']
                if sec_id == 0:
                    bookmark_text += f"{i}. 第{ch_id}章圖片\n"
                else:
                    bookmark_text += f"{i}. 第{ch_id}章第{sec_id}段\n"
            if len(bookmarks) > 10:
                bookmark_text += f"... 還有 {len(bookmarks) - 10} 個書籤"
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=bookmark_text)]))
    except Exception as e:
        logger.error(f"書籤錯誤: {e}")

def handle_navigation_command(user_id, direction, reply_token, line_api):
    try:
        conn = get_db_connection()
        user = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        if not user or not user['current_chapter_id']:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="請先選擇章節開始學習")]))
            return
        chapter_id = user['current_chapter_id']
        current_section_id = user['current_section_id'] or 0
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if not chapter:
            return
        content_sections = sorted([s for s in chapter['sections'] if s['type'] == 'content'], key=lambda x: x['section_id'])
        if direction == 'next':
            current_index = next((i for i, s in enumerate(content_sections) if s['section_id'] == current_section_id), -1)
            if current_index < len(content_sections) - 1:
                next_section_id = content_sections[current_index + 1]['section_id']
                handle_navigation(user_id, chapter_id, next_section_id, reply_token, line_api)
            else:
                line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="已經是最後一段")]))
        elif direction == 'prev':
            current_index = next((i for i, s in enumerate(content_sections) if s['section_id'] == current_section_id), -1)
            if current_index > 0:
                prev_section_id = content_sections[current_index - 1]['section_id']
                handle_navigation(user_id, chapter_id, prev_section_id, reply_token, line_api)
            else:
                line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="已經是第一段")]))
    except Exception as e:
        logger.error(f"導航指令錯誤: {e}")

def handle_bookmark_current(user_id, reply_token, line_api):
    try:
        conn = get_db_connection()
        user = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        if not user or not user['current_chapter_id']:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="請先開始學習才能標記")]))
            return
        chapter_id = user['current_chapter_id']
        section_id = user['current_section_id'] or 0
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)", (user_id, chapter_id, section_id))
        conn.commit()
        text = f"✅ 標記成功\n第 {chapter_id} 章"
        if section_id == 0:
            text += " 章節圖片"
        else:
            text += f"第 {section_id} 段"
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)]))
    except Exception as e:
        logger.error(f"標記錯誤: {e}")

def handle_navigation(user_id, chapter_id, section_id, reply_token, line_api):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?", (chapter_id, section_id, user_id))
        conn.commit()
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if not chapter:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=f"找不到第 {chapter_id} 章")]))
            return
        content_sections = sorted([s for s in chapter['sections'] if s['type'] == 'content'], key=lambda x: x['section_id'])
        has_chapter_image = bool(chapter.get('image_url'))
        messages = []
        if section_id == 0 and has_chapter_image:
            messages.append(ImageMessage(original_content_url=chapter['image_url'], preview_image_url=chapter['image_url']))
            quick_items = []
            if content_sections:
                next_section_id = content_sections[0]['section_id']
                quick_items.append(QuickReplyItem(action=PostbackAction(label="➡️ 下一段", data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}")))
            quick_items.append(QuickReplyItem(action=PostbackAction(label="🔖 標記", data=f"action=add_bookmark&chapter_id={chapter_id}&section_id=0")))
            total_content = len(content_sections) + 1
            progress_text = f"📖 {chapter['title']}\n\n第 1/{total_content} 段 (章節圖片)"
            messages.append(TextMessage(text=progress_text, quick_reply=QuickReply(items=quick_items)))
        else:
            section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
            if not section:
                total_content = len(content_sections) + (1 if has_chapter_image else 0)
                template = ButtonsTemplate(title="🎉 章節完成", text=f"完成 {chapter['title']}\n\n已閱讀 {total_content} 段內容\n恭喜完成本章節！", actions=[PostbackAction(label="📖 選擇章節", data="action=show_chapter_menu")])
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
                    quick_items.append(QuickReplyItem(action=PostbackAction(label="⬅️ 上一段", data=f"action=navigate&chapter_id={chapter_id}&section_id={prev_section_id}")))
                elif has_chapter_image:
                    quick_items.append(QuickReplyItem(action=PostbackAction(label="⬅️ 上一段", data=f"action=navigate&chapter_id={chapter_id}&section_id=0")))
                if current_index < len(content_sections) - 1:
                    next_section_id = content_sections[current_index + 1]['section_id']
                    quick_items.append(QuickReplyItem(action=PostbackAction(label="➡️ 下一段", data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}")))
                else:
                    quiz_sections = [s for s in chapter['sections'] if s['type'] == 'quiz']
                    if quiz_sections:
                        first_quiz_id = min(quiz_sections, key=lambda x: x['section_id'])['section_id']
                        quick_items.append(QuickReplyItem(action=PostbackAction(label="📝 開始測驗", data=f"action=navigate&chapter_id={chapter_id}&section_id={first_quiz_id}")))
                quick_items.append(QuickReplyItem(action=PostbackAction(label="🔖 標記", data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}")))
                content_position = current_index + 1
                if has_chapter_image:
                    display_position = content_position + 1
                    total_content = len(content_sections) + 1
                else:
                    display_position = content_position
                    total_content = len(content_sections)
                progress_text = f"📖 第 {display_position}/{total_content} 段"
                messages.append(TextMessage(text=progress_text, quick_reply=QuickReply(items=quick_items)))
            elif section['type'] == 'quiz':
                quiz = section['content']
                quick_items = []
                for key, text in quiz['options'].items():
                    label = f"{key}. {text}"
                    if len(label) > 20:
                        label = label[:17] + "..."
                    quick_items.append(QuickReplyItem(action=PostbackAction(label=label, display_text=f"選 {key}", data=f"action=submit_answer&chapter_id={chapter_id}&section_id={section_id}&answer={key}")))
                quiz_sections = [s for s in chapter['sections'] if s['type'] == 'quiz']
                current_quiz = next((i+1 for i, s in enumerate(quiz_sections) if s['section_id'] == section_id), 1)
                quiz_text = f"📝 測驗 {current_quiz}/{len(quiz_sections)}\n\n{quiz['question']}"
                messages.append(TextMessage(text=quiz_text, quick_reply=QuickReply(items=quick_items)))
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=messages[:5]))
    except Exception as e:
        logger.error(f"導覽錯誤: {e}")
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="載入內容失敗，請稍後再試")]))

def handle_add_bookmark(params, user_id, reply_token, line_api):
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        conn = get_db_connection()
        cursor = conn.cursor()
        existing = cursor.execute("SELECT id FROM bookmarks WHERE line_user_id = ? AND chapter_id = ? AND section_id = ?", (user_id, chapter_id, section_id)).fetchone()
        if existing:
            text = "📌 此段已在書籤中\n\n點擊「我的書籤」查看所有收藏"
        else:
            cursor.execute("INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)", (user_id, chapter_id, section_id))
            conn.commit()
            text = f"✅ 已加入書籤\n\n第 {chapter_id} 章第 {section_id} 段"
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)]))
    except Exception as e:
        logger.error(f"書籤錯誤: {e}")

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
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)", (user_id, chapter_id, section_id, user_answer, is_correct))
            conn.commit()
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
                    actions.append(PostbackAction(label="➡️ 下一題", data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"))
                else:
                    actions.append(PostbackAction(label="📖 繼續閱讀", data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"))
            else:
                actions.append(PostbackAction(label="📖 選擇章節", data="action=show_chapter_menu"))
            template = ButtonsTemplate(title=f"作答結果 {emoji}", text=result_text, actions=actions[:4])
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TemplateMessage(alt_text="答題結果", template=template)]))
    except Exception as e:
        logger.error(f"答題錯誤: {e}")

if __name__ == "__main__":
    book_data = load_book_data()
    init_database()
    logger.info("=== LINE Bot 啟動完成 ===")
    logger.info(f"載入 {len(book_data.get('chapters', []))} 章節")
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)