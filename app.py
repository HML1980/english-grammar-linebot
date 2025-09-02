# -*- coding: utf-8 -*-
import os
import json
import sqlite3
import datetime
from urllib.parse import parse_qs
from flask import Flask, request, abort
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    ImageMessage,
    PostbackAction,
    TemplateMessage,
    ButtonsTemplate,
    CarouselTemplate,
    CarouselColumn,
    QuickReply,
    QuickReplyItem
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent,
    FollowEvent,
)

app = Flask(__name__)

# --- 資料庫設定 ---
DATABASE_NAME = 'linebot.db'

def get_db_connection():
    """建立並回傳一個資料庫連線"""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# ... (金鑰與 LINE Bot 初始化，與之前相同) ...
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
if not CHANNEL_SECRET or not CHANNEL_ACCESS_TOKEN:
    print("錯誤：請設定 CHANNEL_SECRET 和 CHANNEL_ACCESS_TOKEN 環境變數")
    exit()
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 載入書籍資料
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

def create_main_menu(user_id):
    """建立主目錄，包含繼續閱讀和我的書籤"""
    try:
        columns = []
        conn = get_db_connection()
        user_progress = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        
        # --- 【新功能】查詢書籤數量 ---
        bookmark_count = conn.execute("SELECT COUNT(*) FROM bookmarks WHERE line_user_id = ?", (user_id,)).fetchone()[0]
        conn.close()

        if user_progress and user_progress['current_chapter_id'] is not None:
            chapter_id = user_progress['current_chapter_id']
            section_id = user_progress['current_section_id']
            columns.append(CarouselColumn(
                thumbnail_image_url="https://i.imgur.com/F0fT8w7.png",
                title="繼續閱讀",
                text=f"您上次看到第 {chapter_id} 章，第 {section_id} 段",
                actions=[PostbackAction(label="從上次進度開始", display_text="繼續上次的閱讀進度", data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id}")]
            ))
        
        # --- 【新功能】新增「我的書籤」卡片 ---
        columns.append(CarouselColumn(
            thumbnail_image_url="https://i.imgur.com/NKYN3DE.png", # 書籤圖示
            title="我的書籤",
            text=f"您已標記 {bookmark_count} 個段落",
            actions=[PostbackAction(label="查看書籤", display_text="查看我的書籤", data="action=view_bookmarks")]
        ))

        for chapter in book_data['chapters']:
            short_title = chapter['title'][5:] if len(chapter['title']) > 5 else chapter['title']
            columns.append(CarouselColumn(
                thumbnail_image_url=chapter['image_url'],
                title=f"Chapter {chapter['chapter_id']}",
                text=short_title[:60], 
                actions=[PostbackAction(label="開始閱讀", display_text=f"開始閱讀 {short_title}", data=f"action=view_chapter&chapter_id={chapter['chapter_id']}")]
            ))
        
        return TemplateMessage(alt_text='英文文法攻略 目錄', template=CarouselTemplate(columns=columns[:10]))
    except Exception as e:
        print(f">>> 建立主目錄時發生錯誤: {e}")
        return TextMessage(text="抱歉，建立主目錄時發生錯誤。")

# ... (handle_follow 和 handle_message 函式與上一版相同) ...
@handler.add(FollowEvent)
def handle_follow(event):
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    try:
        profile = line_api.get_profile(user_id)
        display_name = profile.display_name
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", (user_id, display_name))
        conn.commit()
        conn.close()
        print(f">>> 新使用者已儲存: {display_name} ({user_id})")
    except Exception as e:
        print(f">>> 取得或儲存使用者資料時發生錯誤: {e}")
    line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[create_main_menu(user_id)]))

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id
    if '目錄' in text or '目录' in text:
        reply_token = event.reply_token
        line_api = MessagingApi(ApiClient(configuration))
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[create_main_menu(user_id)]))

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    params = parse_qs(data)
    action = params.get('action', [None])[0]

    print(f">>> 收到來自 {user_id} 的 PostbackEvent: action={action}")

    if action == 'show_toc':
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[create_main_menu(user_id)]))
    elif action == 'view_chapter':
        chapter_id = int(params.get('chapter_id', [1])[0])
        handle_navigation(reply_token, line_api, user_id, chapter_id, 1)
    elif action == 'navigate':
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        handle_navigation(reply_token, line_api, user_id, chapter_id, section_id)
    elif action == 'submit_answer':
        # ... (作答邏輯與上一版相同) ...
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        user_answer = params.get('answer', [None])[0]
        chapter = next((chap for chap in book_data['chapters'] if chap['chapter_id'] == chapter_id), None)
        quiz_section = next((sec for sec in chapter['sections'] if sec['section_id'] == section_id), None)
        correct_answer = quiz_section['content']['answer']
        is_correct = (user_answer == correct_answer)
        if is_correct: feedback_text = "✅ 答對了！"
        else: feedback_text = f"❌ 答錯了，正確答案是 {correct_answer}"
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)",(user_id, chapter_id, section_id, user_answer, is_correct))
            conn.commit()
            conn.close()
            print(f">>> 已儲存使用者 {user_id} 的答題紀錄 (CH {chapter_id}, SEC {section_id})")
        except Exception as e:
            print(f">>> 儲存答題紀錄時發生錯誤: {e}")
        next_section_id = section_id + 1
        next_section_exists = any(sec['section_id'] == next_section_id for sec in chapter['sections'])
        actions = []
        if next_section_exists:
            actions.append(PostbackAction(label="下一題 ➡️", data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"))
        actions.append(PostbackAction(label="回目錄", data="action=show_toc"))
        template = ButtonsTemplate(title="作答結果", text=feedback_text, actions=actions)
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TemplateMessage(alt_text="作答結果", template=template)]))
    
    # --- 【新功能】處理書籤相關的 action ---
    elif action == 'add_bookmark':
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        conn = get_db_connection()
        # 檢查是否已存在，避免重複加入
        existing = conn.execute("SELECT * FROM bookmarks WHERE line_user_id = ? AND chapter_id = ? AND section_id = ?", (user_id, chapter_id, section_id)).fetchone()
        if not existing:
            conn.execute("INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)", (user_id, chapter_id, section_id))
            conn.commit()
            feedback_text = "✅ 已成功加入書籤！"
        else:
            feedback_text = "ℹ️ 您已標記過此段落。"
        conn.close()
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=feedback_text)]))

    elif action == 'view_bookmarks':
        conn = get_db_connection()
        bookmarks = conn.execute("SELECT chapter_id, section_id FROM bookmarks WHERE line_user_id = ? ORDER BY chapter_id, section_id", (user_id,)).fetchall()
        conn.close()
        if not bookmarks:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="您尚未標記任何書籤。")]))
        else:
            quick_reply_items = []
            for bm in bookmarks:
                chapter_id = bm['chapter_id']
                section_id = bm['section_id']
                label_text = f"CH{chapter_id} - SEC{section_id}"
                quick_reply_items.append(QuickReplyItem(action=PostbackAction(label=label_text, display_text=f"跳至 {label_text}", data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id}")))
            
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="請點擊下方按鈕，快速跳至您標記的段落：", quick_reply=QuickReply(items=quick_reply_items))]))


def handle_navigation(reply_token, line_api, user_id, chapter_id, section_id):
    # ... (更新使用者進度的邏輯與上一版相同) ...
    try:
        conn = get_db_connection()
        conn.execute("UPDATE users SET current_chapter_id = ?, current_section_id = ?, last_seen = CURRENT_TIMESTAMP WHERE line_user_id = ?",(chapter_id, section_id, user_id))
        conn.commit()
        conn.close()
        print(f">>> 已更新使用者 {user_id} 的進度至 CH {chapter_id}, SEC {section_id}")
    except Exception as e:
        print(f">>> 更新使用者進度時發生錯誤: {e}")

    chapter = next((chap for chap in book_data['chapters'] if chap['chapter_id'] == chapter_id), None)
    current_section = next((sec for sec in chapter['sections'] if sec['section_id'] == section_id), None)
    messages_to_reply = []

    if section_id == 1 and current_section:
        messages_to_reply.append(ImageMessage(original_content_url=chapter['image_url'], preview_image_url=chapter['image_url']))

    if not current_section:
        actions = [PostbackAction(label="回目錄", data="action=show_toc")]
        template = ButtonsTemplate(title=f"章節結束", text=f"您已讀完 {chapter['title']}！", actions=actions)
        messages_to_reply.append(TemplateMessage(alt_text="章節結束", template=template))
    elif current_section['type'] == 'content':
        messages_to_reply.append(TextMessage(text=current_section['content']))
        actions = []
        if section_id > 1:
            actions.append(PostbackAction(label="⬅️ 上一段", data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id-1}"))
        if any(sec['section_id'] == section_id + 1 for sec in chapter['sections']):
            actions.append(PostbackAction(label="下一段 ➡️", data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id+1}"))
        
        # --- 【新功能】新增「標記此段」按鈕 ---
        actions.append(PostbackAction(label="⭐ 標記此段", data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"))
        actions.append(PostbackAction(label="回目錄", data="action=show_toc"))
        
        template = ButtonsTemplate(title=f"導覽選單 (第 {section_id} 段)", text="請選擇下一步：", actions=actions[:4])
        messages_to_reply.append(TemplateMessage(alt_text=f"導覽選單", template=template))
    elif current_section['type'] == 'quiz':
        quiz = current_section['content']
        quick_reply_items = []
        for option_key, option_text in quiz['options'].items():
            label_text = f"{option_key}. {option_text}"
            if len(label_text) > 20:
                label_text = label_text[:17] + "..."
            quick_reply_items.append(QuickReplyItem(action=PostbackAction(label=label_text, display_text=f"我選 {option_key}", data=f"action=submit_answer&chapter_id={chapter_id}&section_id={section_id}&answer={option_key}")))
        messages_to_reply.append(TextMessage(text=quiz['question'], quick_reply=QuickReply(items=quick_reply_items)))
    
    line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=messages_to_reply[:5]))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)