# -*- coding: utf-8 -*-
import os
import json
import sqlite3
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
def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- 金鑰與 LINE Bot 初始化 ---
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')
CHAPTER_RICH_MENU_ID = os.environ.get('CHAPTER_RICH_MENU_ID')

if not all([CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID, CHAPTER_RICH_MENU_ID]):
    print("錯誤：請檢查 CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID, CHAPTER_RICH_MENU_ID 環境變數是否都已設定")
    exit()

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 載入書籍資料
try:
    with open('book.json', 'r', encoding='utf-8') as f:
        book_data = json.load(f)
    print(">>> book.json 載入成功")
except Exception as e:
    print(f">>> book.json 載入失敗: {e}", book_data = {"chapters": []})

# --- Webhook 路由 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError: abort(400)
    except Exception as e:
        print(f">>> [嚴重錯誤] handle 發生未知錯誤: {e}")
        abort(500)
    return 'OK'

# --- 事件處理 ---
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    try:
        profile = line_api.get_profile(user_id)
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", (user_id, profile.display_name))
        conn.commit()
        conn.close()
        print(f">>> 新使用者已儲存: {profile.display_name}")
    except Exception as e:
        print(f">>> 儲存使用者資料時發生錯誤: {e}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    if '目錄' in event.message.text:
        line_api = MessagingApi(ApiClient(configuration))
        line_api.link_rich_menu_to_user(event.source.user_id, MAIN_RICH_MENU_ID)
        print(f">>> 已為使用者 {event.source.user_id} 切換至主選單")

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    params = parse_qs(data)
    action = params.get('action', [None])[0]

    print(f">>> 收到來自 {user_id} 的 Postback: action={action}")

    if action == 'switch_to_main_menu':
        line_api.link_rich_menu_to_user(user_id, MAIN_RICH_MENU_ID)
        print(f">>> 已為使用者 {user_id} 切換至主選單")
    
    elif action == 'switch_to_chapter_menu':
        chapter_id = int(params.get('chapter_id', [1])[0])
        # 暫存當前選擇的章節ID，以便章節選單知道要操作哪一章
        conn = get_db_connection()
        conn.execute("UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", (chapter_id, user_id))
        conn.commit()
        conn.close()
        
        line_api.link_rich_menu_to_user(user_id, CHAPTER_RICH_MENU_ID)
        print(f">>> 已為使用者 {user_id} 切換至章節選單 (CH {chapter_id})")

    elif action in ['read_chapter', 'resume_chapter', 'do_quiz']:
        conn = get_db_connection()
        user = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        conn.close()
        chapter_id = user['current_chapter_id']
        
        if action == 'read_chapter':
            handle_navigation(reply_token, line_api, user_id, chapter_id, 1)
        elif action == 'resume_chapter':
            section_id = user['current_section_id'] if user['current_section_id'] else 1
            handle_navigation(reply_token, line_api, user_id, chapter_id, section_id)
        elif action == 'do_quiz':
            chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
            first_quiz = next((s for s in chapter['sections'] if s['type'] == 'quiz'), None)
            if first_quiz:
                handle_navigation(reply_token, line_api, user_id, chapter_id, first_quiz['section_id'])
            else:
                line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=f"Chapter {chapter_id} 沒有測驗題。")]))

    elif action == 'resume_reading':
        conn = get_db_connection()
        user = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        conn.close()
        if user and user['current_chapter_id']:
            handle_navigation(reply_token, line_api, user_id, user['current_chapter_id'], user['current_section_id'])
        else:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="您尚未有任何閱讀紀錄。")]))
            
    elif action == 'view_bookmarks':
        # ... (此邏輯與上一版相同) ...
        pass # 省略以保持簡潔

    elif action == 'view_analytics':
        # --- 【新功能】錯誤分析邏輯 ---
        conn = get_db_connection()
        # 計算整體錯誤率
        total_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", (user_id,)).fetchone()[0]
        wrong_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 0", (user_id,)).fetchone()[0]
        
        if total_attempts == 0:
            reply_text = "您尚未做過任何測驗，沒有分析資料。"
        else:
            error_rate = (wrong_attempts / total_attempts) * 100
            reply_text = f"📊 您的學習分析報告\n\n整體錯誤率: {error_rate:.1f}%\n(答錯 {wrong_attempts} 題 / 共 {total_attempts} 題)"
            
            # 找出錯誤率最高的章節
            cursor = conn.execute("""
                SELECT chapter_id, 
                       CAST(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS error_rate
                FROM quiz_attempts
                WHERE line_user_id = ?
                GROUP BY chapter_id
                ORDER BY error_rate DESC
                LIMIT 1
            """, (user_id,))
            top_error_chapter = cursor.fetchone()
            if top_error_chapter:
                reply_text += f"\n\n您最需要加強的是： Chapter {top_error_chapter['chapter_id']}"
        
        conn.close()
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=reply_text)]))

    # ... (其他 action 的處理邏輯，例如 submit_answer, navigate) ...
    # (此處省略，與上一版程式碼相同)

def handle_navigation(reply_token, line_api, user_id, chapter_id, section_id):
    # ... (此函式與上一版程式碼完全相同) ...
    pass # 省略以保持簡潔

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)