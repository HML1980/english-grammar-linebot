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
    print(f">>> book.json 載入失敗: {e}")
    book_data = {"chapters": []}

# --- Webhook 路由 ---
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

# --- 訊息建立函式 ---
def create_carousel_menu(user_id):
    """建立主目錄，包含繼續閱讀和我的書籤"""
    try:
        columns = []
        conn = get_db_connection()
        user_progress = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        bookmark_count = conn.execute("SELECT COUNT(*) FROM bookmarks WHERE line_user_id = ?", (user_id,)).fetchone()[0]
        conn.close()

        if user_progress and user_progress['current_chapter_id'] is not None and user_progress['current_section_id'] is not None:
            chapter_id = user_progress['current_chapter_id']
            section_id = user_progress['current_section_id']
            columns.append(CarouselColumn(
                thumbnail_image_url="https://i.imgur.com/F0fT8w7.png",
                title="繼續閱讀",
                text=f"您上次看到第 {chapter_id} 章，第 {section_id} 段",
                actions=[PostbackAction(label="從上次進度開始", display_text="繼續上次的閱讀進度", data=f"action=resume_reading")]
            ))
        
        columns.append(CarouselColumn(
            thumbnail_image_url="https://i.imgur.com/NKYN3DE.png",
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
    line_api.link_rich_menu_to_user(user_id, MAIN_RICH_MENU_ID)

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id
    if '目錄' in text or '目录' in text:
        line_api = MessagingApi(ApiClient(configuration))
        line_api.link_rich_menu_to_user(user_id, MAIN_RICH_MENU_ID)

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
    
    elif action == 'switch_to_chapter_menu':
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
        line_api.link_rich_menu_to_user(user_id, CHAPTER_RICH_MENU_ID)
        print(f">>> 已為使用者 {user_id} 切換至章節選單 (CH {chapter_id})")

    elif action in ['read_chapter', 'resume_chapter', 'do_quiz']:
        conn = get_db_connection()
        user = conn.execute("SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", (user_id,)).fetchone()
        conn.close()
        if not user or user['current_chapter_id'] is None:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="請先從主選單選擇一個章節。")]))
            return
        
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
        if user and user['current_chapter_id'] and user['current_section_id']:
            handle_navigation(reply_token, line_api, user_id, user['current_chapter_id'], user['current_section_id'])
        else:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="您尚未有任何閱讀紀錄。")]))
            
    elif action == 'view_bookmarks':
        conn = get_db_connection()
        bookmarks = conn.execute("SELECT chapter_id, section_id FROM bookmarks WHERE line_user_id = ? ORDER BY chapter_id, section_id", (user_id,)).fetchall()
        conn.close()
        if not bookmarks:
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="您尚未標記任何書籤。")]))
        else:
            quick_reply_items = []
            for bm in bookmarks:
                chapter_id, section_id = bm['chapter_id'], bm['section_id']
                label_text = f"CH{chapter_id} - SEC{section_id}"
                quick_reply_items.append(QuickReplyItem(action=PostbackAction(label=label_text, display_text=f"跳至 {label_text}", data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id}")))
            line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text="請點擊下方按鈕，快速跳至您標記的段落：", quick_reply=QuickReply(items=quick_reply_items[:13]))]))

    elif action == 'view_analytics':
        conn = get_db_connection()
        total_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", (user_id,)).fetchone()[0]
        wrong_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 0", (user_id,)).fetchone()[0]
        
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
                actions.insert(0, PostbackAction(label=f"複習 Chapter {ch_id}", data=f"action=read_chapter&chapter_id={ch_id}"))

        conn.close()
        template = ButtonsTemplate(title="學習分析報告", text=reply_text, actions=actions)
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TemplateMessage(alt_text="學習分析報告", template=template)]))

    elif action == 'submit_answer':
        chapter_id, section_id, user_answer = int(params.get('chapter_id', [1])[0]), int(params.get('section_id', [1])[0]), params.get('answer', [None])[0]
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        quiz_section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
        correct_answer = quiz_section['content']['answer']
        is_correct = user_answer == correct_answer
        feedback_text = "✅ 答對了！" if is_correct else f"❌ 答錯了，正確答案是 {correct_answer}"
        
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)",(user_id, chapter_id, section_id, user_answer, is_correct))
            conn.commit()
            conn.close()
        except Exception as e: print(f">>> 儲存答題紀錄時發生錯誤: {e}")
        
        next_section_id = section_id + 1
        actions = []
        if any(s['section_id'] == next_section_id for s in chapter['sections']):
            actions.append(PostbackAction(label="下一題 ➡️", data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"))
        actions.append(PostbackAction(label="回目錄", data="action=show_toc"))
        template = ButtonsTemplate(title="作答結果", text=feedback_text, actions=actions)
        line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=[TemplateMessage(alt_text="作答結果", template=template)]))

def handle_navigation(reply_token, line_api, user_id, chapter_id, section_id):
    """處理導覽與測驗顯示，並更新進度"""
    try:
        conn = get_db_connection()
        conn.execute("UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",(chapter_id, section_id, user_id))
        conn.commit()
        conn.close()
        print(f">>> 已更新使用者 {user_id} 的進度至 CH {chapter_id}, SEC {section_id}")
    except Exception as e:
        print(f">>> 更新使用者進度時發生錯誤: {e}")

    chapter = next((chap for chap in book_data['chapters'] if chap['chapter_id'] == chapter_id), None)
    current_section = next((sec for sec in chapter['sections'] if sec['section_id'] == section_id), None)
    messages_to_reply = []

    if section_id == 1:
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
        actions.append(PostbackAction(label="⭐ 標記此段", data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"))
        actions.append(PostbackAction(label="回主選單", data="action=switch_to_main_menu"))
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
        messages_to_reply.append(TextMessage(text=quiz['question'], quick_reply=QuickReply(items=quick_reply_items[:13])))
    
    line_api.reply_message(ReplyMessageRequest(reply_token=reply_token, messages=messages_to_reply[:5]))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)