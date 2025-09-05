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
    
    # 新增：防重複點擊表
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
    """檢查是否為重複操作（使用資料庫記錄）"""
    current_time = time.time()
    
    try:
        conn = get_db_connection()
        
        # 清理舊記錄
        conn.execute(
            "DELETE FROM user_actions WHERE timestamp < ?", 
            (current_time - cooldown * 2,)
        )
        
        # 檢查是否有重複操作
        recent_action = conn.execute(
            "SELECT timestamp FROM user_actions WHERE line_user_id = ? AND action_data = ? AND timestamp > ?",
            (user_id, action_data, current_time - cooldown)
        ).fetchone()
        
        if recent_action:
            conn.close()
            return True
        
        # 記錄新操作
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
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')
CHAPTER_RICH_MENU_ID = os.environ.get('CHAPTER_RICH_MENU_ID')

required_env_vars = [CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID, CHAPTER_RICH_MENU_ID]
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

# --- 圖文選單處理（純 HTTP API）---
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

@app.route("/check-richmenu/<user_id>", methods=['GET'])
def check_user_richmenu(user_id):
    """檢查特定使用者的圖文選單"""
    try:
        headers = {
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        }
        
        # 獲取使用者當前的圖文選單
        response = requests.get(f'https://api.line.me/v2/bot/user/{user_id}/richmenu', headers=headers)
        
        if response.status_code == 200:
            current_menu = response.json()
            return {"status": "success", "current_richmenu": current_menu}
        elif response.status_code == 404:
            return {"status": "no_richmenu", "message": "使用者沒有設定圖文選單"}
        else:
            return {"status": "error", "code": response.status_code, "message": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.route("/debug-richmenu", methods=['GET'])
def debug_richmenu():
    """調試圖文選單設定"""
    try:
        headers = {
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        }
        response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=headers)
        
        if response.status_code == 200:
            rich_menus = response.json().get('richmenus', [])
            debug_info = []
            
            for menu in rich_menus:
                menu_info = {
                    'id': menu['richMenuId'],
                    'name': menu.get('name', '未命名'),
                    'areas': []
                }
                
                for i, area in enumerate(menu.get('areas', [])):
                    action = area.get('action', {})
                    menu_info['areas'].append({
                        'index': i+1,
                        'type': action.get('type'),
                        'data': action.get('data', action.get('text', 'no data')),
                        'bounds': area.get('bounds')
                    })
                
                debug_info.append(menu_info)
            
            return {"status": "success", "richmenus": debug_info}
        else:
            return {"status": "error", "code": response.status_code, "message": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

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
        # 取得使用者資訊
        try:
            profile = line_api.get_profile(user_id)
            display_name = profile.display_name
        except:
            display_name = f"User_{user_id[-6:]}"
        
        print(f">>> 新使用者: {display_name}")
        
        # 儲存使用者
        conn = get_db_connection()
        conn.execute(
            "INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", 
            (user_id, display_name)
        )
        conn.commit()
        conn.close()
        
        # 設定圖文選單 - 使用 HTTP API
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        
        # 發送歡迎訊息
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="歡迎使用英文文法攻略！\n\n點擊下方選單開始學習。\n\n小提示：\n• 輸入「進度」查看學習進度\n• 輸入「幫助」查看使用說明")]
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
        if '目錄' in text or 'menu' in text.lower():
            switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="已切換至主選單")]
                )
            )
        elif '進度' in text or 'progress' in text.lower():
            handle_progress_inquiry(user_id, event.reply_token, line_api)
        elif '幫助' in text or 'help' in text.lower():
            help_text = "使用說明：\n\n📚 閱讀內容：從頭開始閱讀\n⏯️ 上次進度：跳至上次閱讀處\n📝 本章測驗：練習測驗題目\n🔖 我的書籤：查看收藏內容\n📊 錯誤分析：檢視答錯題目\n\n小技巧：\n• 輸入「進度」查看學習進度\n• 閱讀時可標記重要段落\n• 完成測驗後可查看錯誤分析"
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=help_text)]
                )
            )
        elif '測試切換' in text:
            # 新增：手動測試圖文選單切換
            print(f">>> 手動測試圖文選單切換來自: {user_id}")
            
            # 強制切換到章節選擇選單
            success = switch_rich_menu(user_id, CHAPTER_RICH_MENU_ID)
            
            if success:
                response_text = "✅ 手動切換到章節選擇選單成功！\n\n現在請測試點擊數字按鈕 1-7"
            else:
                response_text = "❌ 圖文選單切換失敗\n\n請檢查環境變數設定"
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response_text)]
                )
            )
        elif '測試章節' in text:
            # 新增：測試章節功能
            print(f">>> 收到測試章節指令來自: {user_id}")
            handle_test_chapter_menu(user_id, event.reply_token, line_api)
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="請使用下方選單操作\n\n或輸入：\n• 「進度」查看學習進度\n• 「幫助」查看使用說明\n• 「測試切換」測試圖文選單切換\n• 「測試章節」測試章節選單")]
                )
            )
    except Exception as e:
        print(f">>> 處理文字訊息錯誤: {e}")

def handle_test_chapter_menu(user_id, reply_token, line_api):
    """處理測試章節選單功能"""
    try:
        print(f">>> 開始切換章節選單 for {user_id}")
        
        # 強制切換到章節圖文選單
        success = switch_rich_menu(user_id, CHAPTER_RICH_MENU_ID)
        
        if success:
            response_text = "✅ 章節圖文選單切換成功！\n\n現在您可以使用：\n📚 閱讀內容\n⏯️ 上次進度\n📝 本章測驗\n🔖 我的書籤\n📊 錯誤分析\n🏠 主選單\n\n請先選擇一個章節開始學習"
        else:
            response_text = "❌ 圖文選單切換失敗\n\n請檢查環境設定"
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=response_text)]
            )
        )
        
    except Exception as e:
        print(f">>> 測試章節選單錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="測試失敗，請檢查系統設定")]
            )
        )

def handle_progress_inquiry(user_id, reply_token, line_api):
    """處理進度查詢"""
    try:
        conn = get_db_connection()
        
        # 計算總進度
        total_sections = sum(len(ch['sections']) for ch in book_data['chapters'])
        
        # 計算已完成的內容段落數
        completed_content = conn.execute(
            """SELECT COUNT(DISTINCT chapter_id || '-' || section_id) 
               FROM users u 
               WHERE u.line_user_id = ? AND u.current_section_id IS NOT NULL""",
            (user_id,)
        ).fetchone()[0]
        
        # 計算測驗完成數
        quiz_attempts = conn.execute(
            "SELECT COUNT(DISTINCT chapter_id || '-' || section_id) FROM quiz_attempts WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()[0]
        
        # 計算正確率
        if quiz_attempts > 0:
            correct_answers = conn.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 1",
                (user_id,)
            ).fetchone()[0]
            accuracy = (correct_answers / quiz_attempts) * 100
        else:
            accuracy = 0
        
        # 取得當前進度
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()
        
        conn.close()
        
        progress_text = f"學習進度報告\n\n"
        if user and user['current_chapter_id']:
            progress_text += f"目前位置：第 {user['current_chapter_id']} 章第 {user['current_section_id'] or 1} 段\n"
        else:
            progress_text += "目前位置：尚未開始\n"
            
        progress_text += f"完成段落：{completed_content}/{total_sections}\n"
        progress_text += f"測驗次數：{quiz_attempts}\n"
        progress_text += f"答題正確率：{accuracy:.1f}%"
        
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
    
    # 檢查重複點擊
    if is_duplicate_action(user_id, data):
        print(f">>> 重複操作已忽略: {data}")
        return
    
    try:
        # 先檢查是否為純數字（直接章節選擇）
        if data.isdigit():
            chapter_number = int(data)
            print(f">>> 偵測到純數字章節選擇: 第 {chapter_number} 章")
            handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api)
            return
        
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        print(f">>> 解析的動作: {action}")
        
        if action == 'switch_to_main_menu':
            switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="已切換至主選單\n\n可開始選擇章節學習")]
                )
            )
            
        elif action == 'switch_to_chapter_menu' or action == 'show_chapter_menu':
            # 顯示章節選擇
            handle_show_chapter_menu(user_id, reply_token, line_api)
            
        elif action == 'select_chapter':
            chapter_id = int(params.get('chapter_id', [1])[0])
            print(f">>> 收到章節選擇: 第 {chapter_id} 章")
            handle_direct_chapter_selection(user_id, chapter_id, reply_token, line_api)
            
        # 新增：對應圖文選單的功能
        elif action == 'read_content':
            # 對應「閱讀內容」按鈕
            handle_chapter_action('read_chapter', user_id, reply_token, line_api)
            
        elif action == 'continue_reading':
            # 對應「上次進度」按鈕  
            handle_resume_reading(user_id, reply_token, line_api)
            
        elif action == 'chapter_quiz':
            # 對應「本章測驗題」按鈕
            handle_chapter_action('do_quiz', user_id, reply_token, line_api)
            
        elif action == 'test_chapter_menu':
            # 新增：測試切換章節選單功能
            force_switch_chapter_menu(user_id, reply_token, line_api)
            
        elif action in ['read_chapter', 'resume_chapter', 'do_quiz']:
            handle_chapter_action(action, user_id, reply_token, line_api)
            
        elif action == 'view_analytics':
            handle_analytics(user_id, reply_token, line_api)
            
        elif action == 'view_bookmarks':
            handle_bookmarks(user_id, reply_token, line_api)
            
        elif action == 'navigate':
            chapter_id = int(params.get('chapter_id', [1])[0])
            section_id = int(params.get('section_id', [1])[0])
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
            
        elif action == 'add_bookmark':
            handle_add_bookmark(params, user_id, reply_token, line_api)
            
        elif action == 'submit_answer':
            handle_answer(params, user_id, reply_token, line_api)
            
        elif action == 'resume_reading':
            handle_resume_reading(user_id, reply_token, line_api)
            
        # 新增：處理數字章節選擇（1-7）
        elif action == 'select_chapter_number':
            chapter_number = int(params.get('chapter', [1])[0])
            print(f">>> 收到數字章節選擇: 第 {chapter_number} 章")
            handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api)
            
    except Exception as e:
        print(f">>> Postback 處理錯誤: {e}")
        # 發送友善的錯誤訊息
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="操作發生錯誤，請稍後再試\n\n或輸入「幫助」查看使用說明")]
                )
            )
        except:
            pass

# 新增：章節選擇功能
def handle_show_chapter_menu(user_id, reply_token, line_api):
    """顯示章節選擇選單"""
    try:
        columns = []
        
        for chapter in book_data['chapters'][:6]:  # 只顯示前6章，避免選單過長
            chapter_id = chapter['chapter_id']
            title = chapter['title']
            
            # 截斷標題避免過長
            if len(title) > 30:
                title = title[:27] + "..."
            
            columns.append(
                CarouselColumn(
                    thumbnail_image_url=chapter.get('image_url', 'https://via.placeholder.com/400x200'),
                    title=f"第 {chapter_id} 章",
                    text=title,
                    actions=[
                        PostbackAction(
                            label="選擇此章節",
                            data=f"action=select_chapter&chapter_id={chapter_id}"
                        )
                    ]
                )
            )
        
        # 如果有第7章，額外添加
        if len(book_data['chapters']) > 6:
            chapter = book_data['chapters'][6]
            columns.append(
                CarouselColumn(
                    thumbnail_image_url=chapter.get('image_url', 'https://via.placeholder.com/400x200'),
                    title=f"第 {chapter['chapter_id']} 章",
                    text=chapter['title'][:30],
                    actions=[
                        PostbackAction(
                            label="選擇此章節",
                            data=f"action=select_chapter&chapter_id={chapter['chapter_id']}"
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
        print(f">>> 章節選單錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="章節選單載入失敗")]
            )
        )

def handle_select_chapter(user_id, chapter_id, reply_token, line_api):
    """選擇章節並切換到章節功能選單"""
    try:
        # 更新使用者當前章節
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", 
            (chapter_id, user_id)
        )
        conn.commit()
        conn.close()
        
        # 找章節資料
        chapter = next((ch for ch in book_data['chapters'] if ch['chapter_id'] == chapter_id), None)
        if chapter:
            content_count = len([s for s in chapter['sections'] if s['type'] == 'content'])
            quiz_count = len([s for s in chapter['sections'] if s['type'] == 'quiz'])
            
            chapter_info = f"已選擇：{chapter['title']}\n\n📝 內容段落：{content_count} 段\n❓ 測驗題目：{quiz_count} 題\n\n現在可以使用下方圖文選單的功能：\n• 閱讀內容：從頭開始\n• 上次進度：跳到上次位置\n• 本章測驗題：開始練習"
        else:
            chapter_info = f"已選擇第 {chapter_id} 章"
        
        # 先發送訊息
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=chapter_info)]
            )
        )
        
        # 切換到章節功能圖文選單（延遲一秒避免衝突）
        import threading
        def delayed_switch():
            time.sleep(1)
            switch_rich_menu(user_id, CHAPTER_RICH_MENU_ID)
        
        threading.Thread(target=delayed_switch).start()
        
    except Exception as e:
        print(f">>> 選擇章節錯誤: {e}")

def handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api):
    """處理直接數字章節選擇"""
    try:
        # 檢查章節是否存在
        chapter = next((ch for ch in book_data['chapters'] if ch['chapter_id'] == chapter_number), None)
        
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=f"第 {chapter_number} 章尚未開放")]
                )
            )
            return
        
        # 更新使用者當前章節
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", 
            (chapter_number, user_id)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 使用者 {user_id} 選擇第 {chapter_number} 章")
        
        # 計算章節資訊
        content_count = len([s for s in chapter['sections'] if s['type'] == 'content'])
        quiz_count = len([s for s in chapter['sections'] if s['type'] == 'quiz'])
        
        chapter_info = f"✅ 已選擇第 {chapter_number} 章\n{chapter['title']}\n\n📝 內容段落：{content_count} 段\n❓ 測驗題目：{quiz_count} 題\n\n使用下方功能開始學習：\n• 閱讀內容：從頭開始\n• 上次進度：跳到上次位置\n• 本章測驗題：開始練習"
        
        # 先發送選擇確認
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=chapter_info)]
            )
        )
        
        # 立即切換到章節功能選單，不使用延遲
        switch_success = switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        if switch_success:
            print(f">>> 成功為使用者 {user_id} 切換到章節功能選單")
        else:
            print(f">>> 為使用者 {user_id} 切換章節選單失敗")
        
    except Exception as e:
        print(f">>> 直接章節選擇錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="選擇章節失敗，請稍後再試")]
            )
        )

def handle_resume_reading(user_id, reply_token, line_api):
    """處理繼續閱讀功能"""
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
            
            print(f">>> 已更新使用者 {user_id} 的進度至 CH {chapter_id}, SEC {section_id}")
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚未開始任何章節\n\n請先選擇章節開始學習")]
                )
            )
    except Exception as e:
        print(f">>> 繼續閱讀錯誤: {e}")

def handle_chapter_action(action, user_id, reply_token, line_api):
    """處理章節動作"""
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
                    messages=[TextMessage(text="請先從主選單選擇章節")]
                )
            )
            return
            
        chapter_id = user['current_chapter_id']
        
        if action == 'read_chapter':
            handle_navigation(user_id, chapter_id, 1, reply_token, line_api)
        elif action == 'resume_chapter':
            section_id = user['current_section_id'] or 1
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
        elif action == 'do_quiz':
            # 找第一個測驗
            chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
            if chapter:
                quiz = next((s for s in chapter['sections'] if s['type'] == 'quiz'), None)
                if quiz:
                    handle_navigation(user_id, chapter_id, quiz['section_id'], reply_token, line_api)
                else:
                    line_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text=f"第 {chapter_id} 章沒有測驗題目")]
                        )
                    )
                    
    except Exception as e:
        print(f">>> 章節動作錯誤: {e}")

def handle_analytics(user_id, reply_token, line_api):
    """處理學習分析 - 修正文字長度"""
    try:
        conn = get_db_connection()
        total = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", (user_id,)
        ).fetchone()[0]
        
        if total == 0:
            text = "尚未有測驗記錄\n\n完成測驗後可查看詳細分析"
        else:
            correct = conn.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 1", 
                (user_id,)
            ).fetchone()[0]
            wrong = total - correct
            error_rate = (wrong / total) * 100
            
            # 找出錯誤最多的章節
            error_chapter = conn.execute(
                """SELECT chapter_id, COUNT(*) as errors 
                   FROM quiz_attempts 
                   WHERE line_user_id = ? AND is_correct = 0 
                   GROUP BY chapter_id 
                   ORDER BY errors DESC 
                   LIMIT 1""",
                (user_id,)
            ).fetchone()
            
            text = f"答對：{correct} 題\n答錯：{wrong} 題\n錯誤率：{error_rate:.1f}%"
            
            if error_chapter:
                text += f"\n\n需要加強：第 {error_chapter['chapter_id']} 章"
        
        conn.close()
        
        template = ButtonsTemplate(
            title="學習分析",
            text=text,
            actions=[PostbackAction(label="回主選單", data="action=switch_to_main_menu")]
        )
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TemplateMessage(alt_text="學習分析", template=template)]
            )
        )
        
    except Exception as e:
        print(f">>> 分析錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="分析載入失敗，請稍後再試")]
            )
        )

def handle_bookmarks(user_id, reply_token, line_api):
    """處理書籤查看"""
    try:
        conn = get_db_connection()
        bookmarks = conn.execute(
            "SELECT chapter_id, section_id FROM bookmarks WHERE line_user_id = ? ORDER BY chapter_id, section_id", 
            (user_id,)
        ).fetchall()
        conn.close()
        
        print(f">>> 收到來自 {user_id} 的 Postback: action=view_bookmarks")
        
        if not bookmarks:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚無書籤\n\n閱讀時可點擊「標記」按鈕收藏重要段落")]
                )
            )
        else:
            quick_reply_items = []
            for bm in bookmarks[:10]:  # 限制顯示10個
                ch_id, sec_id = bm['chapter_id'], bm['section_id']
                quick_reply_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=f"CH{ch_id}-{sec_id}",
                            display_text=f"跳至 CH{ch_id}-{sec_id}",
                            data=f"action=navigate&chapter_id={ch_id}&section_id={sec_id}"
                        )
                    )
                )
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(
                        text=f"您有 {len(bookmarks)} 個書籤\n\n點擊下方快速跳轉",
                        quick_reply=QuickReply(items=quick_reply_items)
                    )]
                )
            )
            
    except Exception as e:
        print(f">>> 書籤錯誤: {e}")

def handle_navigation(user_id, chapter_id, section_id, reply_token, line_api):
    """處理內容導覽 - 增強版"""
    try:
        # 更新進度
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",
            (chapter_id, section_id, user_id)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 收到來自 {user_id} 的 Postback: action=navigate")
        
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
        
        # 章節圖片（第一段時）
        if section_id == 1 and chapter.get('image_url'):
            messages.append(ImageMessage(
                original_content_url=chapter['image_url'],
                preview_image_url=chapter['image_url']
            ))
        
        if not section:
            # 章節結束
            template = ButtonsTemplate(
                title="章節完成",
                text=f"完成 {chapter['title'][:30]}\n\n恭喜！您已完成本章節",
                actions=[
                    PostbackAction(label="回主選單", data="action=switch_to_main_menu"),
                    PostbackAction(label="查看分析", data="action=view_analytics")
                ]
            )
            messages.append(TemplateMessage(alt_text="章節完成", template=template))
            
        elif section['type'] == 'content':
            # 內容段落 - 使用 QuickReply 取代 ButtonTemplate，避免遮擋內容
            content = section['content']
            if len(content) > 1000:
                content = content[:1000] + "\n\n...(內容較長，請點擊下一段繼續)"
                
            messages.append(TextMessage(text=content))
            
            # 使用 QuickReply 取代 ButtonTemplate，避免遮擋內容
            quick_items = []
            
            if section_id > 1:
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="⬅️ 上一段",
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id-1}"
                        )
                    )
                )
            
            if any(s['section_id'] == section_id + 1 for s in chapter['sections']):
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="➡️ 下一段",
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id+1}"
                        )
                    )
                )
                
            quick_items.extend([
                QuickReplyItem(
                    action=PostbackAction(
                        label="🔖 標記",
                        data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label="🏠 主選單",
                        data="action=switch_to_main_menu"
                    )
                )
            ])
            
            # 顯示進度資訊
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            current_pos = next((i+1 for i, s in enumerate(content_sections) if s['section_id'] == section_id), 1)
            progress_text = f"📖 第 {current_pos}/{len(content_sections)} 段"
            
            # 使用簡潔的文字訊息 + QuickReply
            messages.append(TextMessage(
                text=progress_text,
                quick_reply=QuickReply(items=quick_items)
            ))
            
        elif section['type'] == 'quiz':
            # 測驗題
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
            
            # 顯示測驗進度
            quiz_sections = [s for s in chapter['sections'] if s['type'] == 'quiz']
            current_quiz = next((i+1 for i, s in enumerate(quiz_sections) if s['section_id'] == section_id), 1)
            
            quiz_text = f"測驗 {current_quiz}/{len(quiz_sections)}\n\n{quiz['question']}"
            
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
            text = "此段已在書籤中\n\n可輸入「書籤」查看所有收藏"
        else:
            conn.execute(
                "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                (user_id, chapter_id, section_id)
            )
            conn.commit()
            text = f"已加入書籤\n\n第 {chapter_id} 章第 {section_id} 段"
            
        conn.close()
        line_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )
        
    except Exception as e:
        print(f">>> 書籤錯誤: {e}")

def handle_answer(params, user_id, reply_token, line_api):
    """處理答題 - 增強版"""
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        user_answer = params.get('answer', [None])[0]
        
        # 找正確答案
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
            
            actions = []
            
            # 檢查下一題
            next_section_id = section_id + 1
            next_section = next((s for s in chapter['sections'] if s['section_id'] == next_section_id), None)
            
            if next_section:
                if next_section['type'] == 'quiz':
                    actions.append(PostbackAction(
                        label="下一題",
                        data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                    ))
                else:
                    actions.append(PostbackAction(
                        label="繼續閱讀",
                        data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                    ))
            
            actions.extend([
                PostbackAction(label="查看分析", data="action=view_analytics"),
                PostbackAction(label="回主選單", data="action=switch_to_main_menu")
            ])
            
            template = ButtonsTemplate(
                title=f"作答結果 {emoji}",
                text=result_text,
                actions=actions[:4]  # 最多4個按鈕
            )
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TemplateMessage(alt_text="結果", template=template)]
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
    print(">>> 用戶體驗優化版本 v2.1 - 包含診斷功能")
    app.run(host='0.0.0.0', port=8080, debug=False)