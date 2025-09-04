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
    print("錯誤：請檢查所有環境變數是否都已設定")
    exit()
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ... (載入 book.json 和 callback 函式，與之前相同) ...
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


# ... (create_carousel_menu 函式與上一版相同，不需要修改) ...
def create_carousel_menu(user_id):
    try:
        columns = []
        conn = get_db_connection()
        user_progress = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        bookmark_count = conn.execute("SELECT COUNT(*) FROM bookmarks WHERE line_user_id = ?", (user_id,)).fetchone()[0]
        conn.close()
        if user_progress and user_progress['current_chapter_id'] is not None and user_progress['current_section_id'] is not None:
            chapter_id, section_id = user_progress['current_chapter_id'], user_progress['current_section_id']
            columns.append(CarouselColumn(thumbnail_image_url="https://i.imgur.com/F0fT8w7.png",title="繼續閱讀",text=f"您上次看到第 {chapter_id} 章，第 {section_id} 段",actions=[PostbackAction(label="從上次進度開始", display_text="繼續上次的閱讀進度", data=f"action=resume_reading")]))
        columns.append(CarouselColumn(thumbnail_image_url="https://i.imgur.com/NKYN3DE.png",title="我的書籤",text=f"您已標記 {bookmark_count} 個段落",actions=[PostbackAction(label="查看書籤", display_text="查看我的書籤", data="action=view_bookmarks")]))
        for chapter in book_data['chapters']:
            short_title = chapter['title'][5:] if len(chapter['title']) > 5 else chapter['title']
            columns.append(CarouselColumn(thumbnail_image_url=chapter['image_url'],title=f"Chapter {chapter['chapter_id']}",text=short_title[:60], actions=[PostbackAction(label="開始閱讀", display_text=f"開始閱讀 {short_title}", data=f"action=view_chapter&chapter_id={chapter['chapter_id']}")]))
        return TemplateMessage(alt_text='英文文法攻略 目錄', template=CarouselTemplate(columns=columns[:10]))
    except Exception as e:
        print(f">>> 建立主目錄時發生錯誤: {e}")
        return TextMessage(text="抱歉，建立主目錄時發生錯誤。")


@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    line_api_blob = MessagingApiBlob(ApiClient(configuration)) # 使用修正後的 API
    try:
        profile = line_api_blob.get_profile(user_id) # 使用修正後的 API
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", (user_id, profile.display_name))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f">>> 儲存使用者資料時發生錯誤: {e}")
    line_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID) # 使用修正後的 API

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id
    reply_token = event.reply_token
    line_api = MessagingApi(ApiClient(configuration))
    line_api_blob = MessagingApiBlob(ApiClient(configuration))

    if '目錄' in text or '目录' in text:
        print(">>> 關鍵字 '目錄' 匹配成功，傳送確認訊息並切換選單...")
        # --- 【核心修正】先切換選單，再回覆訊息 ---
        line_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="已為您開啟主選單。")]
            )
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    line_api_blob = MessagingApiBlob(ApiClient(configuration))
    params = parse_qs(data)
    action = params.get('action', [None])[0]

    print(f">>> 收到來自 {user_id} 的 Postback: action={action}")

    if action == 'switch_to_main_menu':
        # --- 【核心修正】先切換，再回覆 ---
        line_api_blob.link_rich_menu_id_to_user(user_id, MAIN_RICH_MENU_ID)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="已為您切換回主選單。")]
            )
        )
    
    elif action == 'switch_to_chapter_menu':
        chapter_id = int(params.get('chapter_id', [1])[0])
        conn = get_db_connection()
        conn.execute("UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", (chapter_id, user_id))
        conn.commit()
        conn.close()
        
        # --- 【核心修正】先切換，再回覆 ---
        line_api_blob.link_rich_menu_id_to_user(user_id, CHAPTER_RICH_MENU_ID)
        chapter_title = next((c['title'] for c in book_data['chapters'] if c['chapter_id'] == chapter_id), "")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=f"您已選擇：{chapter_title}\n\n請點擊下方選單開始操作。")]
            )
        )
        print(f">>> 已為使用者 {user_id} 切換至章節選單 (CH {chapter_id})")
        
    # ... (其他 action 的處理邏輯保持不變，因為它們本來就有效) ...
    elif action in ['read_chapter', 'resume_chapter', 'do_quiz']:
        # ...
        pass
    elif action == 'resume_reading':
        # ...
        pass
    elif action == 'view_bookmarks':
        # ...
        pass
    elif action == 'view_analytics':
        # ...
        pass
    elif action == 'submit_answer':
        # ...
        pass

# ... (所有其他函式都保持不變) ...

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)