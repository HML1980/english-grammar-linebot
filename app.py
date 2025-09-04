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

def init_database():
    """初始化資料庫表格"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # 建立使用者表
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
    
    # 建立書籤表
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
    
    # 建立測驗記錄表
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

# --- 金鑰與 LINE Bot 初始化 ---
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')
CHAPTER_RICH_MENU_ID = os.environ.get('CHAPTER_RICH_MENU_ID')

# 驗證環境變數
required_env_vars = {
    'CHANNEL_SECRET': CHANNEL_SECRET,
    'CHANNEL_ACCESS_TOKEN': CHANNEL_ACCESS_TOKEN,
    'MAIN_RICH_MENU_ID': MAIN_RICH_MENU_ID,
    'CHAPTER_RICH_MENU_ID': CHAPTER_RICH_MENU_ID
}

missing_vars = [var for var, value in required_env_vars.items() if not value]
if missing_vars:
    print(f"錯誤：缺少環境變數: {', '.join(missing_vars)}")
    exit(1)

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 載入書籍資料
def load_book_data():
    """載入書籍資料，加入錯誤處理"""
    try:
        with open('book.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(">>> book.json 載入成功")
        return data
    except FileNotFoundError:
        print(">>> 警告：book.json 檔案不存在，使用預設空資料")
        return {"chapters": []}
    except json.JSONDecodeError as e:
        print(f">>> 錯誤：book.json 格式錯誤 - {e}")
        return {"chapters": []}
    except Exception as e:
        print(f">>> 錯誤：載入 book.json 時發生未知錯誤 - {e}")
        return {"chapters": []}

book_data = load_book_data()

# 初始化資料庫
init_database()

# --- Webhook 路由 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print(">>> 錯誤：Invalid signature")
        abort(400)
    except Exception as e:
        print(f">>> [嚴重錯誤] handle 發生未知錯誤: {e}")
        abort(500)
    
    return 'OK'

@app.route("/health", methods=['GET'])
def health_check():
    """健康檢查端點"""
    return {"status": "healthy", "chapters_loaded": len(book_data.get('chapters', []))}

# --- 訊息建立函式 ---
def create_carousel_menu(user_id):
    """建立主目錄，包含繼續閱讀和我的書籤"""
    try:
        columns = []
        conn = get_db_connection()
        
        # 查詢使用者進度
        user_progress = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        
        # 查詢書籤數量
        bookmark_count = conn.execute(
            "SELECT COUNT(*) FROM bookmarks WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()[0]
        
        conn.close()

        # 如果有閱讀進度，顯示繼續閱讀選項
        if (user_progress and 
            user_progress['current_chapter_id'] is not None and 
            user_progress['current_section_id'] is not None):
            
            chapter_id = user_progress['current_chapter_id']
            section_id = user_progress['current_section_id']
            columns.append(CarouselColumn(
                thumbnail_image_url="https://i.imgur.com/F0fT8w7.png",
                title="繼續閱讀",
                text=f"您上次看到第 {chapter_id} 章，第 {section_id} 段",
                actions=[PostbackAction(
                    label="從上次進度開始", 
                    display_text="繼續上次的閱讀進度", 
                    data="action=resume_reading"
                )]
            ))
        
        # 書籤選項
        columns.append(CarouselColumn(
            thumbnail_image_url="https://i.imgur.com/NKYN3DE.png",
            title="我的書籤",
            text=f"您已標記 {bookmark_count} 個段落",
            actions=[PostbackAction(
                label="查看書籤", 
                display_text="查看我的書籤", 
                data="action=view_bookmarks"
            )]
        ))

        # 章節選項
        for chapter in book_data['chapters'][:8]:  # 限制最多8個章節
            short_title = chapter['title'][5:] if len(chapter['title']) > 5 else chapter['title']
            columns.append(CarouselColumn(
                thumbnail_image_url=chapter.get('image_url', 'https://i.imgur.com/default.png'),
                title=f"Chapter {chapter['chapter_id']}",
                text=short_title[:60], 
                actions=[PostbackAction(
                    label="開始閱讀", 
                    display_text=f"開始閱讀 {short_title}", 
                    data=f"action=view_chapter&chapter_id={chapter['chapter_id']}"
                )]
            ))
        
        # 限制 carousel 最多10個欄位
        return TemplateMessage(
            alt_text='英文文法攻略 目錄', 
            template=CarouselTemplate(columns=columns[:10])
        )
        
    except Exception as e:
        print(f">>> 建立主目錄時發生錯誤: {e}")
        return TextMessage(text="抱歉，建立主目錄時發生錯誤。請稍後再試。")

def safe_get_user_info(line_api, user_id):
    """安全地取得使用者資訊"""
    try:
        profile = line_api.get_profile(user_id)
        return profile.display_name
    except Exception as e:
        print(f">>> 無法取得使用者 {user_id} 的資訊: {e}")
        return f"User_{user_id[-6:]}"  # 使用 user_id 後6位作為暫時名稱

# --- 事件處理 ---
@handler.add(FollowEvent)
def handle_follow(event):
    """處理新使用者關注事件"""
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        # 取得使用者資訊
        display_name = safe_get_user_info(line_api, user_id)
        
        # 儲存使用者資料
        conn = get_db_connection()
        conn.execute(
            "INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", 
            (user_id, display_name)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 新使用者已儲存: {display_name}")
        
        # 設定主選單
        line_api.link_rich_menu_to_user(user_id, MAIN_RICH_MENU_ID)
        
        # 傳送歡迎訊息
        welcome_message = TextMessage(
            text="歡迎使用五分鐘英文文法攻略！📚\n\n點擊下方選單開始您的學習之旅。"
        )
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[welcome_message]
            )
        )
        
    except Exception as e:
        print(f">>> 處理新關注事件時發生錯誤: {e}")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """處理文字訊息"""
    text = event.message.text.strip()
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        # 處理特定關鍵字
        if '目錄' in text or '目录' in text or 'menu' in text.lower():
            line_api.link_rich_menu_to_user(user_id, MAIN_RICH_MENU_ID)
            reply_message = TextMessage(text="已為您切換至主選單 📋")
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply_message]
                )
            )
        elif 'help' in text.lower() or '幫助' in text or '說明' in text:
            help_text = """📖 使用說明：

• 點擊下方選單按鈕進行操作
• 選擇章節開始閱讀
• 可隨時標記重要段落
• 完成章節後進行測驗
• 查看學習分析了解進度

輸入「目錄」可回到主選單"""
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=help_text)]
                )
            )
        else:
            # 預設回應
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="請使用下方選單進行操作，或輸入「help」查看說明。")]
                )
            )
            
    except Exception as e:
        print(f">>> 處理文字訊息時發生錯誤: {e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    """處理 Postback 事件"""
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        
        print(f">>> 收到來自 {user_id} 的 Postback: action={action}")
        
        if action == 'switch_to_main_menu':
            line_api.link_rich_menu_to_user(user_id, MAIN_RICH_MENU_ID)
            
        elif action == 'switch_to_chapter_menu':
            handle_chapter_menu_switch(params, user_id, reply_token, line_api)
            
        elif action in ['read_chapter', 'resume_chapter', 'do_quiz']:
            handle_chapter_actions(action, user_id, reply_token, line_api)
            
        elif action == 'resume_reading':
            handle_resume_reading(user_id, reply_token, line_api)
            
        elif action == 'view_bookmarks':
            handle_view_bookmarks(user_id, reply_token, line_api)
            
        elif action == 'view_analytics':
            handle_view_analytics(user_id, reply_token, line_api)
            
        elif action == 'navigate':
            chapter_id = int(params.get('chapter_id', [1])[0])
            section_id = int(params.get('section_id', [1])[0])
            handle_navigation(reply_token, line_api, user_id, chapter_id, section_id)
            
        elif action == 'add_bookmark':
            handle_add_bookmark(params, user_id, reply_token, line_api)
            
        elif action == 'submit_answer':
            handle_submit_answer(params, user_id, reply_token, line_api)
            
        else:
            print(f">>> 未知的 action: {action}")
            
    except Exception as e:
        print(f">>> 處理 Postback 時發生錯誤: {e}")
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="處理請求時發生錯誤，請稍後再試。")]
                )
            )
        except:
            pass

def handle_chapter_menu_switch(params, user_id, reply_token, line_api):
    """處理切換章節選單"""
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        
        # 更新使用者當前章節
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ? WHERE line_user_id = ?", 
            (chapter_id, user_id)
        )
        conn.commit()
        conn.close()
        
        # 找到章節標題
        chapter_title = "未知章節"
        for chapter in book_data.get('chapters', []):
            if chapter['chapter_id'] == chapter_id:
                chapter_title = chapter['title']
                break
        
        # 回覆訊息並切換選單
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=f"您已選擇：{chapter_title}\n\n請點擊下方選單開始操作。")]
            )
        )
        line_api.link_rich_menu_to_user(user_id, CHAPTER_RICH_MENU_ID)
        
        print(f">>> 已為使用者 {user_id} 切換至章節選單 (CH {chapter_id})")
        
    except Exception as e:
        print(f">>> 處理章節選單切換時發生錯誤: {e}")

def handle_chapter_actions(action, user_id, reply_token, line_api):
    """處理章節相關動作"""
    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        conn.close()
        
        if not user or user['current_chapter_id'] is None:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token, 
                    messages=[TextMessage(text="請先從主選單選擇一個章節。")]
                )
            )
            return
        
        chapter_id = user['current_chapter_id']
        
        if action == 'read_chapter':
            handle_navigation(reply_token, line_api, user_id, chapter_id, 1)
        elif action == 'resume_chapter':
            section_id = user['current_section_id'] if user['current_section_id'] else 1
            handle_navigation(reply_token, line_api, user_id, chapter_id, section_id)
        elif action == 'do_quiz':
            # 找到第一個測驗題
            chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
            if chapter:
                first_quiz = next((s for s in chapter['sections'] if s['type'] == 'quiz'), None)
                if first_quiz:
                    handle_navigation(reply_token, line_api, user_id, chapter_id, first_quiz['section_id'])
                else:
                    line_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token, 
                            messages=[TextMessage(text=f"Chapter {chapter_id} 沒有測驗題。")]
                        )
                    )
            
    except Exception as e:
        print(f">>> 處理章節動作時發生錯誤: {e}")

def handle_resume_reading(user_id, reply_token, line_api):
    """處理繼續閱讀"""
    try:
        conn = get_db_connection()
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        conn.close()
        
        if user and user['current_chapter_id'] and user['current_section_id']:
            handle_navigation(reply_token, line_api, user_id, user['current_chapter_id'], user['current_section_id'])
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token, 
                    messages=[TextMessage(text="您尚未有任何閱讀紀錄。請從主選單選擇章節開始學習。")]
                )
            )
            
    except Exception as e:
        print(f">>> 處理繼續閱讀時發生錯誤: {e}")

def handle_view_bookmarks(user_id, reply_token, line_api):
    """處理查看書籤"""
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
                    messages=[TextMessage(text="您尚未標記任何書籤。\n\n閱讀時點擊「⭐ 標記此段」即可新增書籤。")]
                )
            )
        else:
            quick_reply_items = []
            for bm in bookmarks[:13]:  # 限制最多13個按鈕
                chapter_id, section_id = bm['chapter_id'], bm['section_id']
                label_text = f"CH{chapter_id}-SEC{section_id}"
                quick_reply_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=label_text, 
                            display_text=f"跳至 {label_text}", 
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id}"
                        )
                    )
                )
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token, 
                    messages=[TextMessage(
                        text=f"您有 {len(bookmarks)} 個書籤：", 
                        quick_reply=QuickReply(items=quick_reply_items)
                    )]
                )
            )
            
    except Exception as e:
        print(f">>> 處理查看書籤時發生錯誤: {e}")

def handle_view_analytics(user_id, reply_token, line_api):
    """處理查看學習分析"""
    try:
        conn = get_db_connection()
        
        total_attempts = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()[0]
        
        wrong_attempts = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ? AND is_correct = 0", 
            (user_id,)
        ).fetchone()[0]
        
        actions = [PostbackAction(label="回主選單", data="action=switch_to_main_menu")]
        
        if total_attempts == 0:
            reply_text = "您尚未做過任何測驗，沒有分析資料。\n\n開始學習後就能看到您的進度分析！"
        else:
            error_rate = (wrong_attempts / total_attempts) * 100
            reply_text = f"📊 您的學習分析報告\n\n整體錯誤率: {error_rate:.1f}%\n(答錯 {wrong_attempts} 題 / 共 {total_attempts} 題)"
            
            # 找出錯誤率最高的章節
            cursor = conn.execute("""
                SELECT chapter_id, 
                       CAST(SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS error_rate,
                       COUNT(*) as attempt_count
                FROM quiz_attempts 
                WHERE line_user_id = ? 
                GROUP BY chapter_id 
                HAVING attempt_count >= 3
                ORDER BY error_rate DESC, chapter_id ASC 
                LIMIT 1
            """, (user_id,))
            
            top_error_chapter = cursor.fetchone()
            
            if top_error_chapter and top_error_chapter['error_rate'] > 0:
                ch_id = top_error_chapter['chapter_id']
                reply_text += f"\n\n📍 建議加強：Chapter {ch_id}"
                actions.insert(0, PostbackAction(
                    label=f"重做 Ch{ch_id} 測驗", 
                    data=f"action=switch_to_chapter_menu&chapter_id={ch_id}"
                ))
        
        conn.close()
        
        template = ButtonsTemplate(
            title="學習分析報告", 
            text=reply_text, 
            actions=actions[:4]  # 限制最多4個按鈕
        )
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token, 
                messages=[TemplateMessage(alt_text="學習分析報告", template=template)]
            )
        )
        
    except Exception as e:
        print(f">>> 處理學習分析時發生錯誤: {e}")

def handle_add_bookmark(params, user_id, reply_token, line_api):
    """處理新增書籤"""
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        
        conn = get_db_connection()
        
        # 檢查是否已存在
        existing = conn.execute(
            "SELECT id FROM bookmarks WHERE line_user_id = ? AND chapter_id = ? AND section_id = ?",
            (user_id, chapter_id, section_id)
        ).fetchone()
        
        if existing:
            reply_text = f"第 {chapter_id} 章第 {section_id} 段已在您的書籤中！"
        else:
            conn.execute(
                "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                (user_id, chapter_id, section_id)
            )
            conn.commit()
            reply_text = f"✅ 已將第 {chapter_id} 章第 {section_id} 段加入書籤！"
        
        conn.close()
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token, 
                messages=[TextMessage(text=reply_text)]
            )
        )
        
    except Exception as e:
        print(f">>> 處理新增書籤時發生錯誤: {e}")

def handle_submit_answer(params, user_id, reply_token, line_api):
    """處理提交答案"""
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        user_answer = params.get('answer', [None])[0]
        
        if not user_answer:
            return
        
        # 找到題目和正確答案
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if not chapter:
            return
            
        quiz_section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
        if not quiz_section or quiz_section['type'] != 'quiz':
            return
            
        correct_answer = quiz_section['content']['answer']
        is_correct = user_answer == correct_answer
        
        feedback_text = "✅ 答對了！很棒！" if is_correct else f"❌ 答錯了，正確答案是 {correct_answer}"
        
        # 儲存答題記錄
        try:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)",
                (user_id, chapter_id, section_id, user_answer, is_correct)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f">>> 儲存答題記錄時發生錯誤: {e}")
        
        # 建立回覆按鈕
        actions = []
        next_section_id = section_id + 1
        
        # 檢查是否有下一題
        if any(s['section_id'] == next_section_id for s in chapter['sections']):
            actions.append(PostbackAction(
                label="下一題 ➡️", 
                data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
            ))
        
        actions.append(PostbackAction(label="回主選單", data="action=switch_to_main_menu"))
        
        template = ButtonsTemplate(
            title="作答結果", 
            text=feedback_text, 
            actions=actions[:4]
        )
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token, 
                messages=[TemplateMessage(alt_text="作答結果", template=template)]
            )
        )
        
    except Exception as e:
        print(f">>> 處理提交答案時發生錯誤: {e}")

def handle_navigation(reply_token, line_api, user_id, chapter_id, section_id):
    """處理導覽與測驗顯示，並更新進度"""
    try:
        # 更新使用者進度
        conn = get_db_connection()
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",
            (chapter_id, section_id, user_id)
        )
        conn.commit()
        conn.close()
        
        print(f">>> 已更新使用者 {user_id} 的進度至 CH {chapter_id}, SEC {section_id}")
        
        # 找到對應的章節和段落
        chapter = next((chap for chap in book_data['chapters'] if chap['chapter_id'] == chapter_id), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token, 
                    messages=[TextMessage(text=f"找不到第 {chapter_id} 章的內容。")]
                )
            )
            return
        
        current_section = next((sec for sec in chapter['sections'] if sec['section_id'] == section_id), None)
        messages_to_reply = []

        # 如果是第一段，顯示章節封面圖片
        if section_id == 1 and chapter.get('image_url'):
            messages_to_reply.append(ImageMessage(
                original_content_url=chapter['image_url'], 
                preview_image_url=chapter['image_url']
            ))

        # 處理不同類型的內容
        if not current_section:
            # 章節結束
            actions = [
                PostbackAction(label="回主選單", data="action=switch_to_main_menu"),
                PostbackAction(label="選擇其他章節", data="action=switch_to_main_menu")
            ]
            template = ButtonsTemplate(
                title="章節完成！", 
                text=f"🎉 恭喜您完成了 {chapter['title']}！\n\n您可以選擇其他章節繼續學習。", 
                actions=actions
            )
            messages_to_reply.append(TemplateMessage(alt_text="章節結束", template=template))
            
        elif current_section['type'] == 'content':
            # 一般內容
            messages_to_reply.append(TextMessage(text=current_section['content']))
            
            # 建立導覽按鈕
            actions = []
            
            # 上一段按鈕
            if section_id > 1:
                actions.append(PostbackAction(
                    label="⬅️ 上一段", 
                    data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id-1}"
                ))
            
            # 下一段按鈕
            if any(sec['section_id'] == section_id + 1 for sec in chapter['sections']):
                actions.append(PostbackAction(
                    label="下一段 ➡️", 
                    data=f"action=navigate&chapter_id={chapter_id}&section_id={section_id+1}"
                ))
            
            # 標記書籤按鈕
            actions.append(PostbackAction(
                label="⭐ 標記書籤", 
                data=f"action=add_bookmark&chapter_id={chapter_id}&section_id={section_id}"
            ))
            
            # 回主選單按鈕
            actions.append(PostbackAction(label="回主選單", data="action=switch_to_main_menu"))
            
            template = ButtonsTemplate(
                title=f"導覽選單 (第 {section_id} 段)", 
                text="請選擇下一步操作：", 
                actions=actions[:4]  # 限制最多4個按鈕
            )
            messages_to_reply.append(TemplateMessage(alt_text="導覽選單", template=template))
            
        elif current_section['type'] == 'quiz':
            # 測驗題目
            quiz = current_section['content']
            quick_reply_items = []
            
            for option_key, option_text in quiz['options'].items():
                # 限制選項文字長度
                label_text = f"{option_key}. {option_text}"
                if len(label_text) > 20:
                    label_text = label_text[:17] + "..."
                
                quick_reply_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=label_text, 
                            display_text=f"我選 {option_key}", 
                            data=f"action=submit_answer&chapter_id={chapter_id}&section_id={section_id}&answer={option_key}"
                        )
                    )
                )
            
            quiz_text = f"📝 測驗時間！\n\n{quiz['question']}"
            messages_to_reply.append(TextMessage(
                text=quiz_text, 
                quick_reply=QuickReply(items=quick_reply_items[:13])  # 限制最多13個選項
            ))
        
        # 發送訊息（限制最多5則）
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token, 
                messages=messages_to_reply[:5]
            )
        )
        
    except Exception as e:
        print(f">>> 處理導覽時發生錯誤: {e}")
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token, 
                    messages=[TextMessage(text="處理內容時發生錯誤，請稍後再試。")]
                )
            )
        except:
            pass

# --- 錯誤處理 ---
@app.errorhandler(404)
def not_found(error):
    return {"error": "Not found"}, 404

@app.errorhandler(500)
def internal_error(error):
    return {"error": "Internal server error"}, 500

if __name__ == "__main__":
    print(">>> LINE Bot 伺服器啟動中...")
    print(f">>> 已載入 {len(book_data.get('chapters', []))} 個章節")
    app.run(host='0.0.0.0', port=8080, debug=False)