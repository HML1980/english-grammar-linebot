# -*- coding: utf-8 -*-
import os
import json
import sqlite3
from urllib.parse import parse_qs
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, MessagingApiBlob,
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
# (這部分保持不變)
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')
CHAPTER_RICH_MENU_ID = os.environ.get('CHAPTER_RICH_MENU_ID')
if not all([CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID, CHAPTER_RICH_MENU_ID]):
    print("錯誤：請檢查所有環境變數是否都已設定")
    exit()
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# --- 【核心修正】在全域範圍內建立 API 物件 ---
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
messaging_api_blob = MessagingApiBlob(api_client)

# 載入書籍資料
try:
    with open('book.json', 'r', encoding='utf-8') as f:
        book_data = json.load(f)
    print(">>> book.json 載入成功")
except Exception as e:
    print(f">>> book.json 載入失敗: {e}")
    book_data = {"chapters": []}

# ... (Webhook 路由 callback 函式不變) ...
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

# ... (create_carousel_menu 函式不變) ...
def create_carousel_menu(user_id):
    # ...
    pass

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    try:
        profile = messaging_api_blob.get_profile(user_id) # 使用全域物件
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", (user_id, profile.display_name))
        conn.commit()
        conn.close()
        print(f">>> 新使用者已儲存: {profile.display_name}")
        # 【核心修正】使用正確的全域物件和函式名稱
        messaging_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)
    except Exception as e:
        print(f">>> 處理 FollowEvent 時發生錯誤: {e}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id
    reply_token = event.reply_token
    if '目錄' in text or '目录' in text:
        try:
            # 【核心修正】使用正確的全域物件和函式名稱
            messaging_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="已為您開啟主選單。")]
                )
            )
        except Exception as e:
            print(f">>> 處理 '目錄' 指令時發生錯誤: {e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    params = parse_qs(data)
    action = params.get('action', [None])[0]

    if action == 'switch_to_main_menu':
        # 【核心修正】使用正確的全域物件和函式名稱
        messaging_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)
        messaging_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="已切換回主選單。")]))
    
    elif action == 'switch_to_chapter_menu':
        chapter_id = int(params.get('chapter_id', [1])[0])
        conn = get_db_connection()
        conn.execute("UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", (chapter_id, user_id))
        conn.commit()
        conn.close()
        
        # 【核心修正】使用正確的全域物件和函式名稱
        messaging_api_blob.link_rich_menu_id_to_user(user_id, CHAPTER_RICH_MENU_ID)
        chapter_title = next((c['title'] for c in book_data['chapters'] if c['chapter_id'] == chapter_id), "")
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=f"您已選擇：{chapter_title}\n\n請點擊下方選單開始操作。")]
            )
        )
    # ... (其他 action 的處理邏輯與上一版相同) ...

# ... (所有其他函式都保持不變) ...

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)