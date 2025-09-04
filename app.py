# -*- coding: utf-8 -*-
import os
import json
import sqlite3
import requests
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
    
    conn.commit()
    conn.close()
    print(">>> 資料庫初始化完成")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

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

# --- 圖文選單處理（只使用 HTTP API）---
def switch_rich_menu(user_id, rich_menu_id):
    """使用 HTTP API 切換圖文選單"""
    try:
        headers = {
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
            'Content-Type': 'application/json'
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
        
        # 儲存使用者
        conn = get_db_connection()
        conn.execute(
            "INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", 
            (user_id, display_name)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 新使用者: {display_name}")
        
        # 設定圖文選單
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        
        # 發送歡迎訊息
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="歡迎使用英文文法攻略！\n\n點擊下方選單開始學習。")]
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
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="請使用下方選單操作")]
                )
            )
    except Exception as e:
        print(f">>> 處理文字訊息錯誤: {e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        
        print(f">>> Postback: {action}")
        
        if action == 'switch_to_main_menu':
            switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
            
        elif action == 'switch_to_chapter_menu':
            chapter_id = int(params.get('chapter_id', [1])[0])
            
            # 更新使用者章節
            conn = get_db_connection()
            conn.execute(
                "UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", 
                (chapter_id, user_id)
            )
            conn.commit()
            conn.close()
            
            # 找章節標題
            chapter_title = f"Chapter {chapter_id}"
            for ch in book_data.get('chapters', []):
                if ch['chapter_id'] == chapter_id:
                    chapter_title = ch['title'][:30]  # 限制長度
                    break
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=f"已選擇：{chapter_title}\n\n點擊下方選單操作")]
                )
            )
            switch_rich_menu(user_id, CHAPTER_RICH_MENU_ID)
            
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
            
    except Exception as e:
        print(f">>> Postback 處理錯誤: {e}")

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
                    messages=[TextMessage(text="請先選擇章節")]
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
                            messages=[TextMessage(text=f"第 {chapter_id} 章沒有測驗")]
                        )
                    )
                    
    except Exception as e:
        print(f">>> 章節動作錯誤: {e}")

def handle_analytics(user_id, reply_token, line_api):
    """處理學習分析 - 修正文字長度問題"""
    try:
        conn = get_db_connection()
        total = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", (user_id,)
        ).fetchone()[0]
        
        if total == 0:
            text = "尚未有測驗記錄"
        else:
            wrong = conn.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 0", 
                (user_id,)
            ).fetchone()[0]
            error_rate = (wrong / total) * 100
            text = f"錯誤率: {error_rate:.1f}%"  # 簡短文字
        
        conn.close()
        
        template = ButtonsTemplate(
            title="學習分析",
            text=text,  # 確保不超過60字元
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
                messages=[TextMessage(text="分析載入失敗")]
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
        
        if not bookmarks:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚無書籤\n\n閱讀時可標記重要段落")]
                )
            )
        else:
            quick_reply_items = []
            for bm in bookmarks[:10]:  # 限制數量
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
                        text=f"您有 {len(bookmarks)} 個書籤",
                        quick_reply=QuickReply(items=quick_reply_items)
                    )]
                )
            )
            
    except Exception as e:
        print(f">>> 書籤錯誤: {e}")

def handle_navigation(user_id, chapter_id, section_id, reply_token, line_api):
    """處理內容導覽"""
    try:
        # 更新進度
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",
            (chapter_id, section_id, user_id)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 更新進度: CH{chapter_id} SEC{section_id}")
        
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
                text=f"完成 {chapter['title'][:30]}",
                actions=[PostbackAction(label="回主選單", data="action=switch_to_main_menu")]
            )
            messages.append(TemplateMessage(alt_text="章節完成", template=template))
            
        elif section['type'] == 'content':
            # 內容段落
            messages.append(TextMessage(text=section['content']))
            
            # 導覽按鈕
            actions = []
            if section_id > 1:
                actions.append(PostbackAction(
                    label="上一段",
                    data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id-1}"
                ))
            
            if any(s['section_id'] == section_id + 1 for s in chapter['sections']):
                actions.append(PostbackAction(
                    label="下一段",
                    data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id+1}"
                ))
                
            actions.append(PostbackAction(
                label="標記",
                data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"
            ))
            
            actions.append(PostbackAction(label="主選單", data="action=switch_to_main_menu"))
            
            template = ButtonsTemplate(
                title=f"第 {section_id} 段",
                text="選擇操作",
                actions=actions[:4]
            )
            messages.append(TemplateMessage(alt_text="導覽", template=template))
            
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
            
            messages.append(TextMessage(
                text=f"測驗\n\n{quiz['question']}",
                quick_reply=QuickReply(items=quick_items)
            ))
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=messages[:5]
            )
        )
        
    except Exception as e:
        print(f">>> 導覽錯誤: {e}")

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
            text = "此段已在書籤中"
        else:
            conn.execute(
                "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                (user_id, chapter_id, section_id)
            )
            conn.commit()
            text = "已加入書籤"
            
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
            
            result_text = "答對了！" if is_correct else f"答錯，正確答案是 {correct}"
            
            actions = [PostbackAction(label="回主選單", data="action=switch_to_main_menu")]
            
            # 檢查下一題
            next_section_id = section_id + 1
            if any(s['section_id'] == next_section_id for s in chapter['sections']):
                actions.insert(0, PostbackAction(
                    label="下一題",
                    data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                ))
            
            template = ButtonsTemplate(
                title="作答結果",
                text=result_text,
                actions=actions
            )
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TemplateMessage(alt_text="結果", template=template)]
                )
            )
        
    except Exception as e:
        print(f">>> 答題錯誤: {e}")

if __name__ == "__main__":
    print(">>> LINE Bot 啟動")
    print(f">>> 載入 {len(book_data.get('chapters', []))} 章節")
    app.run(host='0.0.0.0', port=8080, debug=False)