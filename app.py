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
    # --- 【核心修正】匯入新的 API 類別 ---
    MessagingApiBlob,
    ReplyMessageRequest, TextMessage, ImageMessage, PostbackAction,
    TemplateMessage, ButtonsTemplate, CarouselTemplate, CarouselColumn,
    QuickReply, QuickReplyItem
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent, FollowEvent

app = Flask(__name__)

# ... (資料庫設定、金鑰設定... 和之前一樣) ...
DATABASE_NAME = 'linebot.db'
def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')
CHAPTER_RICH_MENU_ID = os.environ.get('CHAPTER_RICH_MENU_ID')
if not all([CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID, CHAPTER_RICH_MENU_ID]):
    print("錯誤：請檢查所有環境變數是否都已設定")
    exit()
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ... (載入 book.json 和 callback 函式，和之前一樣) ...
try:
    with open('book.json', 'r', encoding='utf-8') as f:
        book_data = json.load(f)
    print(">>> book.json 載入成功")
except Exception as e:
    print(f">>> book.json 載入失敗: {e}")
    book_data = {"chapters": []}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f">>> [嚴重錯誤] handle 發生未知錯誤: {e}")
        abort(500)
    return 'OK'

def create_carousel_menu(user_id):
    # (此函式與上一版相同，不需要修改)
    # ...
    pass

@handler.add(FollowEvent)
def handle_follow(event):
    # (此函式大部分與上一版相同)
    user_id = event.source.user_id
    # --- 【核心修正】使用 MessagingApiBlob 來操作 Rich Menu ---
    line_api_blob = MessagingApiBlob(ApiClient(configuration))
    # ... (儲存使用者資料的邏輯) ...
    line_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # (此函式大部分與上一版相同)
    text = event.message.text
    user_id = event.source.user_id
    if '目錄' in text or '目录' in text:
        # --- 【核心修正】使用 MessagingApiBlob 來操作 Rich Menu ---
        line_api_blob = MessagingApiBlob(ApiClient(configuration))
        line_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    # --- 【核心修正】建立 MessagingApiBlob 物件 ---
    line_api_blob = MessagingApiBlob(ApiClient(configuration))
    params = parse_qs(data)
    action = params.get('action', [None])[0]

    print(f">>> 收到來自 {user_id} 的 Postback: action={action}")

    if action == 'switch_to_main_menu':
        line_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)
    
    elif action == 'switch_to_chapter_menu':
        # ... (儲存 chapter_id 的邏輯) ...
        chapter_id = int(params.get('chapter_id', [1])[0])
        conn = get_db_connection()
        conn.execute("UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", (chapter_id, user_id))
        conn.commit()
        conn.close()
        
        chapter_title = next((c['title'] for c in book_data['chapters'] if c['chapter_id'] == chapter_id), "")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=f"您已選擇：{chapter_title}\n\n請點擊下方選單開始操作。")]
            )
        )
        line_api_blob.link_rich_menu_id_to_user(user_id, CHAPTER_RICH_MENU_ID)
        print(f">>> 已為使用者 {user_id} 切換至章節選單 (CH {chapter_id})")

    elif action == 'view_analytics':
        # --- 【核心修正】將分析報告的文字和按鈕分開 ---
        conn = get_db_connection()
        total_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", (user_id,)).fetchone()[0]
        wrong_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 0", (user_id,)).fetchone()[0]
        
        messages_to_reply = []
        actions = [PostbackAction(label="回主選單", data="action=switch_to_main_menu")]

        if total_attempts == 0:
            reply_text = "您尚未做過任何測驗，沒有分析資料。"
        else:
            error_rate = (wrong_attempts / total_attempts) * 100
            reply_text = f"📊 您的學習分析報告\n\n整體錯誤率: {error_rate:.1f}%\n(答錯 {wrong_attempts} 題 / 共 {total_attempts} 題)"
            
            cursor = conn.execute("""
                SELECT chapter_id, CAST(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS error_rate
                FROM quiz_attempts WHERE line_user_id = ? GROUP BY chapter_id ORDER BY error_rate DESC, chapter_id ASC LIMIT 1
            """, (user_id,))
            top_error_chapter = cursor.fetchone()

            if top_error_chapter and top_error_chapter['error_rate'] > 0:
                ch_id = top_error_chapter['chapter_id']
                reply_text += f"\n\n您最需要加強的是： Chapter {ch_id}"
                actions.insert(0, PostbackAction(label=f"重做 Chapter {ch_id} 測驗", data=f"action=do_quiz&chapter_id={ch_id}"))
        
        conn.close()

        # 先傳送完整的文字報告
        messages_to_reply.append(TextMessage(text=reply_text))
        # 再傳送操作按鈕
        template = ButtonsTemplate(title="下一步", text="您可以選擇：", actions=actions)
        messages_to_reply.append(TemplateMessage(alt_text="學習分析報告操作選單", template=template))
        
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=messages_to_reply))

    # ... (其他 action 的處理邏輯與上一版相同) ...
    
# ... (其他函式與上一版相同) ...

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)