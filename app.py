# -*- coding: utf-8 -*-
import os
import json
import sqlite3
import requests
import time
from urllib.parse import parse_qs
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

app = Flask(__name__)

# --- 資料庫設定 ---
DATABASE_NAME = 'linebot.db'

def init_database():
    """初始化資料庫表格"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_user_id TEXT UNIQUE NOT NULL,
            display_name TEXT,
            current_chapter_id INTEGER,
            current_section_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    conn.commit()
    conn.close()
    print(">>> 資料庫初始化完成")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- 防重複點擊機制 ---
def is_duplicate_action(user_id, action_data, cooldown=2):
    """檢查是否為重複操作"""
    current_time = time.time()
    
    try:
        conn = get_db_connection()
        
        conn.execute(
            "DELETE FROM user_actions WHERE timestamp < ?", 
            (current_time - cooldown * 2,)
        )
        
        recent_action = conn.execute(
            "SELECT timestamp FROM user_actions WHERE line_user_id = ? AND action_data = ? AND timestamp > ?",
            (user_id, action_data, current_time - cooldown)
        ).fetchone()
        
        if recent_action:
            conn.close()
            return True
        
        conn.execute(
            "INSERT INTO user_actions (line_user_id, action_data, timestamp) VALUES (?, ?, ?)",
            (user_id, action_data, current_time)
        )
        conn.commit()
        conn.close()
        return False
        
    except Exception as e:
        print(f">>> 檢查重複操作錯誤: {e}")
        return False

# --- 環境變數 ---
CHANNEL_SECRET = os.environ.get('161e72c092551ea4b27b284d04b23083')
CHANNEL_ACCESS_TOKEN = os.environ.get('5BvBNjyt6NrqujdHjczXYOSYvbF/WQIbhzsnrJKzcHqBoc2n12y34Ccc5IzOWRsKe/zqRtZuSprwjBlYR9PcPbO2PH/s8ZVsaBNMIXrU7GyAqpDSTrWaGbQbdg8vBd27ynXcqOKT8UfSC4r1gBwynwdB04t89/1O/w1cDnyilFU=')
MAIN_RICH_MENU_ID = os.environ.get('richmenu-41b3077662217b0a11b8ced9ec0eb404')

required_env_vars = [CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID]
if not all(required_env_vars):
    print("錯誤：缺少必要的環境變數")
    exit(1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# --- 載入書籍資料 ---
def load_book_data():
    try:
        with open('book.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(">>> book.json 載入成功")
        return data
    except Exception as e:
        print(f">>> 載入 book.json 失敗: {e}")
        return {"chapters": []}

book_data = load_book_data()
init_database()

# --- 圖文選單處理 ---
def switch_rich_menu(user_id, rich_menu_id):
    """使用純 HTTP API 切換圖文選單"""
    try:
        headers = {
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        }
        url = f'https://api.line.me/v2/bot/user/{user_id}/richmenu/{rich_menu_id}'
        response = requests.post(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print(f">>> 圖文選單切換成功: {rich_menu_id}")
            return True
        else:
            print(f">>> 切換失敗: {response.status_code}")
            return False
    except Exception as e:
        print(f">>> 切換圖文選單錯誤: {e}")
        return False

# --- Webhook 路由 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f">>> 處理錯誤: {e}")
        abort(500)
    
    return 'OK'

@app.route("/health", methods=['GET'])
def health_check():
    return {"status": "healthy", "chapters": len(book_data.get('chapters', []))}

@app.route("/", methods=['GET'])
def index():
    return {"message": "LINE Bot is running", "status": "healthy"}

# --- 事件處理 ---
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
        
        print(f">>> 新使用者: {display_name}")
        
        conn = get_db_connection()
        conn.execute(
            "INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", 
            (user_id, display_name)
        )
        conn.commit()
        conn.close()
        
        # 設定統一圖文選單
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="歡迎使用五分鐘英文文法攻略！\n\n請使用下方圖文選單開始學習：\n\n📚 閱讀內容：從第一章開始\n📖 章節選擇：選擇想學的章節\n🔖 我的書籤：查看收藏內容\n⏯️ 上次進度：繼續上次學習\n📝 本章測驗題：練習測驗\n📊 錯誤分析：檢視學習狀況")]
            )
        )
        
    except Exception as e:
        print(f">>> 處理關注事件錯誤: {e}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        if '進度' in text or 'progress' in text.lower():
            handle_progress_inquiry(user_id, event.reply_token, line_api)
        elif '幫助' in text or 'help' in text.lower():
            help_text = "📖 使用說明：\n\n📚 閱讀內容：從第一章第一段開始閱讀\n📖 章節選擇：選擇 1-7 章節\n🔖 我的書籤：查看標記的重要內容\n⏯️ 上次進度：跳到上次閱讀位置\n📝 本章測驗題：練習當前章節測驗\n📊 錯誤分析：查看答錯統計\n\n💡 小技巧：\n• 閱讀時可以標記重要段落\n• 完成測驗會自動記錄進度\n• 錯誤分析會顯示最需要加強的題目"
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=help_text)]
                )
            )
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請使用下方圖文選單操作\n\n或輸入「進度」查看學習進度\n輸入「幫助」查看使用說明")]
                )
            )
    except Exception as e:
        print(f">>> 處理文字訊息錯誤: {e}")

def handle_progress_inquiry(user_id, reply_token, line_api):
    """處理進度查詢"""
    try:
        conn = get_db_connection()
        
        total_sections = sum(len(ch['sections']) for ch in book_data['chapters'])
        
        # 取得當前進度
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()
        
        # 計算完成的內容段落數（非測驗）
        completed_sections = 0
        if user and user['current_chapter_id']:
            for chapter in book_data['chapters']:
                if chapter['chapter_id'] < user['current_chapter_id']:
                    completed_sections += len([s for s in chapter['sections'] if s['type'] == 'content'])
                elif chapter['chapter_id'] == user['current_chapter_id']:
                    completed_sections += len([s for s in chapter['sections'] 
                                            if s['type'] == 'content' and s['section_id'] < (user['current_section_id'] or 1)])
        
        # 計算測驗統計
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
        
        # 書籤數量
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
        print(f">>> 進度查詢錯誤: {e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    print(f">>> 收到來自 {user_id} 的 Postback: {data}")
    
    if is_duplicate_action(user_id, data):
        print(f">>> 重複操作已忽略: {data}")
        return
    
    try:
        # 直接章節選擇（數字 1-7）
        if data.isdigit():
            chapter_number = int(data)
            print(f">>> 數字章節選擇: 第 {chapter_number} 章")
            handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api)
            return
        
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        print(f">>> 解析的動作: {action}")
        
        if action == 'read_content':
            # 閱讀內容：從第一章第一段開始
            handle_start_reading(user_id, reply_token, line_api)
            
        elif action == 'show_chapter_menu':
            # 章節選擇：顯示橫式輪播選單
            handle_show_chapter_carousel(user_id, reply_token, line_api)
            
        elif action == 'view_bookmarks':
            # 我的書籤：查看標記內容
            handle_bookmarks(user_id, reply_token, line_api)
            
        elif action == 'continue_reading':
            # 上次進度：跳到上次位置
            handle_resume_reading(user_id, reply_token, line_api)
            
        elif action == 'chapter_quiz':
            # 本章測驗題：需要先進入章節
            handle_chapter_quiz(user_id, reply_token, line_api)
            
        elif action == 'view_analytics':
            # 錯誤分析：顯示答錯統計
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
        print(f">>> Postback 處理錯誤: {e}")
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
    """閱讀內容：從第一章第一段開始"""
    try:
        # 更新使用者進度到第一章第一段
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = 1, current_section_id = 1 WHERE line_user_id = ?", 
            (user_id,)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 使用者 {user_id} 開始閱讀第一章")
        
        # 直接導航到第一章第一段
        handle_navigation(user_id, 1, 1, reply_token, line_api)
        
    except Exception as e:
        print(f">>> 開始閱讀錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="開始閱讀失敗，請稍後再試")]
            )
        )

def handle_show_chapter_carousel(user_id, reply_token, line_api):
    """章節選擇：顯示橫式輪播選單"""
    try:
        columns = []
        
        for chapter in book_data['chapters']:
            chapter_id = chapter['chapter_id']
            title = chapter['title']
            
            # 截斷標題避免過長
            if len(title) > 35:
                title = title[:32] + "..."
            
            # 計算章節進度
            content_count = len([s for s in chapter['sections'] if s['type'] == 'content'])
            quiz_count = len([s for s in chapter['sections'] if s['type'] == 'quiz'])
            
            # 使用章節圖片，如果沒有則使用預設圖片
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
        print(f">>> 章節輪播錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="章節選單載入失敗，請稍後再試")]
            )
        )

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
        
        # 更新使用者當前章節，但不更新段落（保持在該章節的開始）
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = 1 WHERE line_user_id = ?", 
            (chapter_number, user_id)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 使用者 {user_id} 選擇第 {chapter_number} 章")
        
        # 顯示章節資訊並開始閱讀第一段
        handle_navigation(user_id, chapter_number, 1, reply_token, line_api)
        
    except Exception as e:
        print(f">>> 章節選擇錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="選擇章節失敗，請稍後再試")]
            )
        )

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
            section_id = user['current_section_id'] or 1
            
            print(f">>> 繼續閱讀: CH {chapter_id}, SEC {section_id}")
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚未開始任何章節\n\n請點擊「閱讀內容」開始學習，或「章節選擇」選擇想要的章節")]
                )
            )
    except Exception as e:
        print(f">>> 繼續閱讀錯誤: {e}")

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
            # 找到第一個測驗題
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
        print(f">>> 章節測驗錯誤: {e}")

def handle_error_analytics(user_id, reply_token, line_api):
    """錯誤分析：顯示答錯統計，錯誤多的排前面"""
    try:
        conn = get_db_connection()
        
        # 計算總體統計
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
        
        # 找出錯誤最多的題目（按章節和段落分組）
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
        
        # 建立分析報告
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
            
            # 加入快速複習按鈕
            quick_items = []
            for stat in error_stats[:3]:  # 只顯示前3個
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
        print(f">>> 錯誤分析錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="錯誤分析載入失敗，請稍後再試")]
            )
        )

def handle_bookmarks(user_id, reply_token, line_api):
    """我的書籤：查看標記內容"""
    try:
        conn = get_db_connection()
        bookmarks = conn.execute(
            """SELECT b.chapter_id, b.section_id, b.created_at
               FROM bookmarks b
               WHERE b.line_user_id = ?
               ORDER BY b.chapter_id, b.section_id""", 
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
            # 顯示書籤列表並提供快速跳轉
            bookmark_text = f"📚 我的書籤 ({len(bookmarks)} 個)\n\n"
            
            quick_reply_items = []
            for i, bm in enumerate(bookmarks[:10], 1):  # 最多顯示10個
                ch_id, sec_id = bm['chapter_id'], bm['section_id']
                bookmark_text += f"{i}. 第{ch_id}章第{sec_id}段\n"
                
                quick_reply_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=f"第{ch_id}章第{sec_id}段",
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
        print(f">>> 書籤錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="書籤載入失敗，請稍後再試")]
            )
        )

def handle_navigation(user_id, chapter_id, section_id, reply_token, line_api):
    """處理內容導覽 - 支援圖片作為第一段"""
    try:
        # 更新使用者進度
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",
            (chapter_id, section_id, user_id)
        )
        conn.commit()
        conn.close()
        
        # 找章節和段落
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=f"找不到第 {chapter_id} 章")]
                )
            )
            return
            
        section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
        messages = []
        
        # 如果是第一段且有章節圖片，圖片視為第一段
        if section_id == 1 and chapter.get('image_url'):
            messages.append(ImageMessage(
                original_content_url=chapter['image_url'],
                preview_image_url=chapter['image_url']
            ))
            
            # 為圖片段落建立導航按鈕（圖片是第一段，下面只有下一段和標記）
            quick_items = []
            
            # 檢查是否有下一段
            if any(s['section_id'] == section_id + 1 for s in chapter['sections']):
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="➡️ 下一段",
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id+1}"
                        )
                    )
                )
            
            # 標記按鈕
            quick_items.append(
                QuickReplyItem(
                    action=PostbackAction(
                        label="🔖 標記",
                        data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"
                    )
                )
            )
            
            # 顯示章節標題和進度
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            progress_text = f"📖 {chapter['title']}\n\n第 1/{len(content_sections) + 1} 段 (章節圖片)"
            
            messages.append(TextMessage(
                text=progress_text,
                quick_reply=QuickReply(items=quick_items)
            ))
        
        elif not section:
            # 章節結束
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            completed_content = len(content_sections) + (1 if chapter.get('image_url') else 0)  # +1 for image
            
            template = ButtonsTemplate(
                title="🎉 章節完成",
                text=f"完成 {chapter['title']}\n\n已閱讀 {completed_content} 段內容\n恭喜完成本章節！",
                actions=[
                    PostbackAction(label="📊 查看分析", data="action=view_analytics"),
                    PostbackAction(label="📖 選擇章節", data="action=show_chapter_menu")
                ]
            )
            messages.append(TemplateMessage(alt_text="章節完成", template=template))
            
        elif section['type'] == 'content':
            # 一般內容段落
            content = section['content']
            if len(content) > 1000:
                content = content[:1000] + "\n\n...(內容較長，請點擊下一段繼續)"
                
            messages.append(TextMessage(text=content))
            
            # 建立導航按鈕
            quick_items = []
            
            # 上一段按鈕（如果不是第一段）
            if section_id > 1:
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="⬅️ 上一段",
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id-1}"
                        )
                    )
                )
            
            # 下一段按鈕（如果有下一段）
            if any(s['section_id'] == section_id + 1 for s in chapter['sections']):
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="➡️ 下一段",
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id+1}"
                        )
                    )
                )
            
            # 標記按鈕
            quick_items.append(
                QuickReplyItem(
                    action=PostbackAction(
                        label="🔖 標記",
                        data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"
                    )
                )
            )
            
            # 計算進度（包含圖片段落）
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            current_pos = next((i+1 for i, s in enumerate(content_sections) if s['section_id'] == section_id), 1)
            if chapter.get('image_url'):
                current_pos += 1  # 圖片算一段
                total_content = len(content_sections) + 1
            else:
                total_content = len(content_sections)
            
            progress_text = f"📖 第 {current_pos}/{total_content} 段"
            
            messages.append(TextMessage(
                text=progress_text,
                quick_reply=QuickReply(items=quick_items)
            ))
            
        elif section['type'] == 'quiz':
            # 測驗題目
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
            
            # 計算測驗進度
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
                messages=messages[:5]  # LINE 限制最多5個訊息
            )
        )
        
    except Exception as e:
        print(f">>> 導覽錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="載入內容失敗，請稍後再試")]
            )
        )

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
            text = "📌 此段已在書籤中\n\n點擊「我的書籤」查看所有收藏"
        else:
            conn.execute(
                "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                (user_id, chapter_id, section_id)
            )
            conn.commit()
            text = f"✅ 已加入書籤\n\n第 {chapter_id} 章第 {section_id} 段"
            
        conn.close()
        line_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )
        
    except Exception as e:
        print(f">>> 書籤錯誤: {e}")

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
            
            # 記錄答題
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)",
                (user_id, chapter_id, section_id, user_answer, is_correct)
            )
            conn.commit()
            conn.close()
            
            # 建立結果訊息
            if is_correct:
                result_text = "✅ 答對了！"
                emoji = "🎉"
            else:
                correct_option = section['content']['options'].get(correct, correct)
                result_text = f"❌ 答錯了\n\n正確答案是 {correct}: {correct_option}"
                emoji = "💪"
            
            # 檢查下一段
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
                actions=actions[:4]  # 最多4個按鈕
            )
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TemplateMessage(alt_text="答題結果", template=template)]
                )
            )
        
    except Exception as e:
        print(f">>> 答題錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="答題處理失敗，請稍後再試")]
            )
        )

if __name__ == "__main__":
    print(">>> LINE Bot 啟動")
    print(f">>> 載入 {len(book_data.get('chapters', []))} 章節")
    print(">>> 五分鐘英文文法攻略 - 統一圖文選單版本 v2.0")
    app.run(host='0.0.0.0', port=8080, debug=False)