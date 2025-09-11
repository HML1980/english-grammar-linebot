# -*- coding: utf-8 -*-
import os
import json
import sqlite3
import requests
import time
import re
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
    except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
    print(">>> 資料庫初始化完成")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn
# --- 防重複點擊機制 ---
def is_duplicate_action(user_id, action_data, cooldown=2):
    """簡化版本 - 避免資料庫問題"""
    return False
        
    except Exception as e:
        print(f">>> 檢查重複操作錯誤: {e}")
        return False

# --- 新手引導檢查 ---
def check_new_user_guidance(user_id):
    """檢查是否為新用戶，返回引導文字"""
    try:
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        action_count = conn.execute(
            "SELECT COUNT(*) FROM user_actions WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()[0]
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        if action_count < 5:  # 新用戶或操作較少的用戶
            return "\n\n🌟 小提示：輸入「1」快速開始第一章，「幫助」查看所有指令"
        return ""
    except:
        return ""

# --- 環境變數設定 ---
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')

# 調試：顯示環境變數狀態
print(">>> 環境變數檢查:")
print(f"CHANNEL_SECRET: {'已設定' if CHANNEL_SECRET else '未設定'}")
print(f"CHANNEL_ACCESS_TOKEN: {'已設定' if CHANNEL_ACCESS_TOKEN else '未設定'}")
print(f"MAIN_RICH_MENU_ID: {'已設定' if MAIN_RICH_MENU_ID else '未設定'}")

required_env_vars = [CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID]
if not all(required_env_vars):
    print("錯誤：缺少必要的環境變數")
    print("請在 Render 中設定以下環境變數:")
    if not CHANNEL_SECRET:
        print("- CHANNEL_SECRET")
    if not CHANNEL_ACCESS_TOKEN:
        print("- CHANNEL_ACCESS_TOKEN")
    if not MAIN_RICH_MENU_ID:
        print("- MAIN_RICH_MENU_ID")
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

# --- 增強版文字訊息處理 ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        # 正規化文字輸入（移除空格，轉小寫比對）
        normalized_text = text.replace(' ', '').lower()
        
        # 閱讀內容相關指令
        if any(keyword in normalized_text for keyword in ['閱讀內容', '開始閱讀', '閱讀', 'read', 'start']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 開始閱讀")
            handle_start_reading(user_id, event.reply_token, line_api)
            
        # 章節選擇相關指令  
        elif any(keyword in normalized_text for keyword in ['章節選擇', '選擇章節', 'chapter', 'chapters']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 章節選擇")
            handle_show_chapter_carousel(user_id, event.reply_token, line_api)
            
        # 書籤相關指令
        elif any(keyword in normalized_text for keyword in ['我的書籤', '書籤', 'bookmark', 'bookmarks']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 我的書籤")
            handle_bookmarks(user_id, event.reply_token, line_api)
            
        # 上次進度相關指令
        elif any(keyword in normalized_text for keyword in ['上次進度', '繼續閱讀', '進度', 'continue', 'resume']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 上次進度")
            handle_resume_reading(user_id, event.reply_token, line_api)
            
        # 測驗相關指令
        elif any(keyword in normalized_text for keyword in ['本章測驗', '測驗題', '測驗', 'quiz', 'test']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 本章測驗")
            handle_chapter_quiz(user_id, event.reply_token, line_api)
            
        # 錯誤分析相關指令
        elif any(keyword in normalized_text for keyword in ['錯誤分析', '分析', 'analytics', 'analysis']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 錯誤分析")
            handle_error_analytics(user_id, event.reply_token, line_api)
            
        # 直接章節跳轉（數字1-7）
        elif text.isdigit() and 1 <= int(text) <= 7:
            chapter_number = int(text)
            print(f">>> 用戶 {user_id} 輸入: {text} -> 選擇第{chapter_number}章")
            handle_direct_chapter_selection(user_id, chapter_number, event.reply_token, line_api)
            
        # 快速導航指令
        elif text.lower() in ['n', 'next', '下', '下一段', '下一']:
            print(f">>> 用戶 {user_id} 輸入: {text} -> 快速下一段")
            handle_quick_navigation(user_id, 'next', event.reply_token, line_api)
            
        elif text.lower() in ['b', 'back', 'prev', '上', '上一段', '上一']:
            print(f">>> 用戶 {user_id} 輸入: {text} -> 快速上一段")
            handle_quick_navigation(user_id, 'prev', event.reply_token, line_api)
            
        # 第X章格式
        elif text.startswith('第') and text.endswith('章') and len(text) == 3:
            try:
                chapter_num = int(text[1])
                if 1 <= chapter_num <= 7:
                    print(f">>> 用戶 {user_id} 輸入: {text} -> 選擇第{chapter_num}章")
                    handle_direct_chapter_selection(user_id, chapter_num, event.reply_token, line_api)
                else:
                    raise ValueError("章節號碼超出範圍")
            except:
                handle_unknown_command(user_id, event.reply_token, line_api, text)
                
        # 跳轉指令 (跳到第X章第Y段)
        elif '跳到' in normalized_text or '跳轉' in normalized_text:
            match = re.search(r'第?(\d+)章.*?第?(\d+)段', text)
            if match:
                ch, sec = int(match.group(1)), int(match.group(2))
                print(f">>> 用戶 {user_id} 輸入: {text} -> 跳轉到第{ch}章第{sec}段")
                handle_navigation(user_id, ch, sec, event.reply_token, line_api)
            else:
                handle_unknown_command(user_id, event.reply_token, line_api, text)
                
        # 進度查詢
        elif any(keyword in normalized_text for keyword in ['學習進度', '我的進度', 'progress']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 進度查詢")
            handle_progress_inquiry(user_id, event.reply_token, line_api)
            
        # 狀態查詢
        elif any(keyword in normalized_text for keyword in ['狀態', '資訊', 'status', 'info']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 狀態查詢")
            handle_status_inquiry(user_id, event.reply_token, line_api)
            
        # 幫助說明
        elif any(keyword in normalized_text for keyword in ['幫助', '說明', '指令', 'help', 'command']):
            print(f">>> 用戶 {user_id} 輸入: {text} -> 幫助說明")
            handle_help_message(user_id, event.reply_token, line_api)
            
        # 未知指令
        else:
            handle_unknown_command(user_id, event.reply_token, line_api, text)
            
    except Exception as e:
        print(f">>> 處理文字訊息錯誤: {e}")
        try:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="指令處理發生錯誤，請稍後再試\n\n輸入「幫助」查看可用指令" + check_new_user_guidance(user_id))]
                )
            )
        except:
            pass
# --- 新增的輔助處理函數 ---
def handle_help_message(user_id, reply_token, line_api):
    """處理幫助訊息"""
    help_text = """📖 指令說明：

📱 **快速指令**
• 閱讀內容 / 開始閱讀 → 從第一章開始
• 章節選擇 → 選擇 1-7 章節
• 我的書籤 → 查看收藏內容
• 上次進度 / 繼續閱讀 → 跳到上次位置
• 本章測驗 → 練習當前章節測驗
• 錯誤分析 → 查看答錯統計

🔢 **數字快捷**
• 直接輸入 1-7 → 快速跳到該章節
• 第1章、第2章... → 另一種章節選擇方式

⚡ **快速導航**
• n / next / 下 / 下一段 → 下一段內容
• b / back / 上 / 上一段 → 上一段內容
• 跳到第2章第3段 → 直接跳轉

📊 **學習追蹤**
• 學習進度 → 詳細進度報告
• 狀態 → 顯示當前學習狀態

💡 **操作技巧**
✓ 可使用中文或英文指令
✓ 閱讀時點擊「標記」收藏重要段落
✓ 完成測驗自動記錄學習進度
✓ 支援上下段落快速切換"""
    
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=help_text)]
        )
    )

def handle_status_inquiry(user_id, reply_token, line_api):
    """處理狀態查詢"""
    try:
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id, display_name FROM users WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()
        
        bookmark_count = conn.execute(
            "SELECT COUNT(*) FROM bookmarks WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()[0]
        
        quiz_count = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?",
            (user_id,)
        ).fetchone()[0]
        
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        if user:
            status_text = f"👤 {user['display_name'] or '學習者'}\n\n"
            if user['current_chapter_id']:
                status_text += f"📍 目前位置：第 {user['current_chapter_id']} 章第 {user['current_section_id'] or 1} 段\n"
            else:
                status_text += "📍 目前位置：尚未開始\n"
            status_text += f"🔖 書籤數量：{bookmark_count} 個\n"
            status_text += f"📝 測驗記錄：{quiz_count} 次\n\n"
            status_text += "輸入「幫助」查看所有可用指令"
        else:
            status_text = "使用者資料讀取失敗，請稍後再試"
            
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=status_text)]
            )
        )
    except Exception as e:
        print(f">>> 狀態查詢錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="狀態查詢失敗，請稍後再試")]
            )
        )

def handle_unknown_command(user_id, reply_token, line_api, original_text):
    """處理未知指令"""
    suggestions = [
        "📚 閱讀內容 - 開始學習",
        "📖 章節選擇 - 選擇章節", 
        "🔖 我的書籤 - 查看收藏",
        "⏯️ 上次進度 - 繼續學習",
        "📝 本章測驗 - 練習測驗",
        "📊 錯誤分析 - 學習分析",
        "💡 幫助 - 查看說明"
    ]
    
    suggestion_text = "請嘗試以下指令：\n\n" + "\n".join(suggestions)
    suggestion_text += "\n\n或直接輸入數字 1-7 選擇章節"
    suggestion_text += check_new_user_guidance(user_id)
    
    line_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=suggestion_text)]
        )
    )

def handle_quick_navigation(user_id, direction, reply_token, line_api):
    """處理快速導航 (上一段/下一段)"""
    try:
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        if not user or not user['current_chapter_id']:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請先選擇章節開始學習\n\n輸入「1」快速開始第一章，或「章節選擇」選擇其他章節")]
                )
            )
            return
            
        current_chapter = user['current_chapter_id']
        current_section = user['current_section_id'] or 0
        
        # 找到當前章節
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == current_chapter), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="章節資料錯誤，請重新選擇章節")]
                )
            )
            return
        
        # 取得所有段落（包含圖片段落0）
        has_image = bool(chapter.get('image_url'))
        content_sections = sorted([s for s in chapter['sections'] if s['type'] == 'content'], 
                                key=lambda x: x['section_id'])
        
        # 建立完整的段落順序列表
        all_sections = []
        if has_image:
            all_sections.append(0)  # 圖片段落
        all_sections.extend([s['section_id'] for s in content_sections])
        
        # 找到當前位置
        try:
            current_index = all_sections.index(current_section)
        except ValueError:
            current_index = 0
            
        # 計算目標段落
        if direction == 'next':
            target_index = current_index + 1
            if target_index >= len(all_sections):
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="已經是最後一段了\n\n輸入「本章測驗」開始測驗，或「章節選擇」選擇其他章節")]
                    )
                )
                return
        else:  # prev
            target_index = current_index - 1
            if target_index < 0:
                line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text="已經是第一段了\n\n輸入「章節選擇」選擇其他章節")]
                    )
                )
                return
        
        target_section = all_sections[target_index]
        handle_navigation(user_id, current_chapter, target_section, reply_token, line_api)
        
    except Exception as e:
        print(f">>> 快速導航錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="導航失敗，請稍後再試")]
            )
        )

# --- 關注事件處理 ---
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
        
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (line_user_id, display_name) VALUES (?, ?)", 
            (user_id, display_name)
        )
        conn.commit()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        # 設定統一圖文選單
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        
        welcome_text = """歡迎使用五分鐘英文文法攻略！

📱 **手機用戶**：使用下方圖文選單操作
💻 **電腦用戶**：可直接輸入指令

🚀 **快速開始**
• 輸入「1」→ 立即開始第一章
• 輸入「幫助」→ 查看所有指令

📚 **主要功能**
• 閱讀內容：從第一章開始
• 章節選擇：選擇想學的章節  
• 我的書籤：查看收藏內容
• 上次進度：繼續上次學習
• 本章測驗：練習測驗題目
• 錯誤分析：檢視學習狀況"""
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=welcome_text)]
            )
        )
        
    except Exception as e:
        print(f">>> 處理關注事件錯誤: {e}")

# --- Postback 事件處理 ---
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    reply_token = event.reply_token
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    print(f">>> 收到來自 {user_id} 的 Postback: {data}")
    
    # 重複檢查已停用
    
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
            handle_start_reading(user_id, reply_token, line_api)
        elif action == 'show_chapter_menu':
            handle_show_chapter_carousel(user_id, reply_token, line_api)
        elif action == 'view_bookmarks':
            handle_bookmarks(user_id, reply_token, line_api)
        elif action == 'continue_reading':
            handle_resume_reading(user_id, reply_token, line_api)
        elif action == 'chapter_quiz':
            handle_chapter_quiz(user_id, reply_token, line_api)
        elif action == 'view_analytics':
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
# --- 主要功能處理函數 ---

def handle_start_reading(user_id, reply_token, line_api):
    """閱讀內容：從第一章開始（如果有圖片先顯示圖片）"""
    try:
        chapter = next((ch for ch in book_data['chapters'] if ch['chapter_id'] == 1), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="第一章尚未開放")]
                )
            )
            return
        
        # 如果第一章有圖片，從圖片開始（虛擬section_id = 0）
        if chapter.get('image_url'):
            start_section_id = 0  # 圖片段落
        else:
            # 否則從第一個內容段落開始
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            start_section_id = content_sections[0]['section_id'] if content_sections else 1
        
        # 更新使用者進度
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        conn.execute(
            "UPDATE users SET current_chapter_id = 1, current_section_id = ? WHERE line_user_id = ?", 
            (start_section_id, user_id)
        )
        conn.commit()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        print(f">>> 使用者 {user_id} 開始閱讀第一章，起始段落: {start_section_id}")
        
        # 導航到起始位置
        handle_navigation(user_id, 1, start_section_id, reply_token, line_api)
        
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
        
        # 決定起始段落：如果有圖片從圖片開始，否則從第一個內容段落
        if chapter.get('image_url'):
            start_section_id = 0  # 圖片段落
        else:
            content_sections = [s for s in chapter['sections'] if s['type'] == 'content']
            start_section_id = content_sections[0]['section_id'] if content_sections else 1
        
        # 更新使用者當前章節和段落
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?", 
            (chapter_number, start_section_id, user_id)
        )
        conn.commit()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        print(f">>> 使用者 {user_id} 選擇第 {chapter_number} 章，起始段落: {start_section_id}")
        
        # 導航到起始位置
        handle_navigation(user_id, chapter_number, start_section_id, reply_token, line_api)
        
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
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        user = conn.execute(
            "SELECT current_chapter_id, current_section_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        if user and user['current_chapter_id']:
            chapter_id = user['current_chapter_id']
            section_id = user['current_section_id'] or 0
            
            print(f">>> 繼續閱讀: CH {chapter_id}, SEC {section_id}")
            handle_navigation(user_id, chapter_id, section_id, reply_token, line_api)
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚未開始任何章節\n\n請輸入「閱讀內容」開始學習，或「章節選擇」選擇想要的章節" + check_new_user_guidance(user_id))]
                )
            )
    except Exception as e:
        print(f">>> 繼續閱讀錯誤: {e}")

def handle_chapter_quiz(user_id, reply_token, line_api):
    """本章測驗題：需要先進入章節才能使用"""
    try:
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        user = conn.execute(
            "SELECT current_chapter_id FROM users WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        if not user or not user['current_chapter_id']:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="請先選擇章節才能進行測驗\n\n輸入「章節選擇」選擇要測驗的章節，或輸入「1」快速開始第一章")]
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

def handle_progress_inquiry(user_id, reply_token, line_api):
    """處理進度查詢"""
    try:
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
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
        
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
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
def handle_error_analytics(user_id, reply_token, line_api):
    """錯誤分析：顯示答錯統計，錯誤多的排前面"""
    try:
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        # 計算總體統計
        total_attempts = conn.execute(
            "SELECT COUNT(*) FROM quiz_attempts WHERE line_user_id = ?", 
            (user_id,)
        ).fetchone()[0]
        
        if total_attempts == 0:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚未有測驗記錄\n\n完成測驗後可以查看詳細的錯誤分析" + check_new_user_guidance(user_id))]
                )
            )
            except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
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
        
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
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
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        bookmarks = conn.execute(
            """SELECT chapter_id, section_id
               FROM bookmarks
               WHERE line_user_id = ?
               ORDER BY chapter_id, section_id""", 
            (user_id,)
        ).fetchall()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        if not bookmarks:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="尚無書籤內容\n\n閱讀時可以點擊「標記」按鈕收藏重要段落" + check_new_user_guidance(user_id))]
                )
            )
        else:
            # 顯示書籤列表並提供快速跳轉
            bookmark_text = f"📚 我的書籤 ({len(bookmarks)} 個)\n\n"
            
            quick_reply_items = []
            for i, bm in enumerate(bookmarks[:10], 1):  # 最多顯示10個
                ch_id, sec_id = bm['chapter_id'], bm['section_id']
                if sec_id == 0:
                    bookmark_text += f"{i}. 第{ch_id}章圖片\n"
                    label = f"第{ch_id}章圖片"
                else:
                    bookmark_text += f"{i}. 第{ch_id}章第{sec_id}段\n"
                    label = f"第{ch_id}章第{sec_id}段"
                
                quick_reply_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=label if len(label) <= 20 else label[:17] + "...",
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

def handle_add_bookmark(params, user_id, reply_token, line_api):
    """新增書籤"""
    try:
        chapter_id = int(params.get('chapter_id', [1])[0])
        section_id = int(params.get('section_id', [1])[0])
        
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        existing = conn.execute(
            "SELECT id FROM bookmarks WHERE line_user_id = ? AND chapter_id = ? AND section_id = ?",
            (user_id, chapter_id, section_id)
        ).fetchone()
        
        if existing:
            if section_id == 0:
                text = "📌 章節圖片已在書籤中\n\n輸入「我的書籤」查看所有收藏"
            else:
                text = "📌 此段已在書籤中\n\n輸入「我的書籤」查看所有收藏"
        else:
            conn.execute(
                "INSERT INTO bookmarks (line_user_id, chapter_id, section_id) VALUES (?, ?, ?)",
                (user_id, chapter_id, section_id)
            )
            conn.commit()
            if section_id == 0:
                text = f"✅ 已加入書籤\n\n第 {chapter_id} 章圖片"
            else:
                text = f"✅ 已加入書籤\n\n第 {chapter_id} 章第 {section_id} 段"
            
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
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
            try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
            conn.execute(
                "INSERT INTO quiz_attempts (line_user_id, chapter_id, section_id, user_answer, is_correct) VALUES (?, ?, ?, ?, ?)",
                (user_id, chapter_id, section_id, user_answer, is_correct)
            )
            conn.commit()
            except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
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

def handle_navigation(user_id, chapter_id, section_id, reply_token, line_api):
    """處理內容導覽 - 修正圖片段落邏輯"""
    try:
        # 更新使用者進度
        try:
        conn = get_db_connection()
    except Exception as e:
        print(f">>> 資料庫連接失敗: {e}")
        return
    
    try:
        conn.execute(
            "UPDATE users SET current_chapter_id = ?, current_section_id = ? WHERE line_user_id = ?",
            (chapter_id, section_id, user_id)
        )
        conn.commit()
        except Exception as e:
        print(f">>> 資料庫操作錯誤: {e}")
    finally:
        if conn:
            conn.close()
        
        # 找章節
        chapter = next((c for c in book_data['chapters'] if c['chapter_id'] == chapter_id), None)
        if not chapter:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=f"找不到第 {chapter_id} 章")]
                )
            )
            return
        
        # 獲取章節的所有內容段落（排序）
        content_sections = sorted([s for s in chapter['sections'] if s['type'] == 'content'], 
                                key=lambda x: x['section_id'])
        has_chapter_image = bool(chapter.get('image_url'))
        
        messages = []
        
        # section_id = 0 表示顯示章節圖片
        if section_id == 0 and has_chapter_image:
            messages.append(ImageMessage(
                original_content_url=chapter['image_url'],
                preview_image_url=chapter['image_url']
            ))
            
            # 建立導航按鈕
            quick_items = []
            
            # 下一段按鈕：跳到第一個文字內容段落
            if content_sections:
                next_section_id = content_sections[0]['section_id']
                quick_items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label="➡️ 下一段",
                            data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                        )
                    )
                )
            
            # 標記按鈕（標記圖片段落為 section_id=0）
            quick_items.append(
                QuickReplyItem(
                    action=PostbackAction(
                        label="🔖 標記",
                        data=f"action=add_bookmark&chapter_id={chapter_id}&section_id=0"
                    )
                )
            )
            
            # 顯示章節標題和進度
            total_content = len(content_sections) + 1  # +1 for image
            progress_text = f"📖 {chapter['title']}\n\n第 1/{total_content} 段 (章節圖片)\n\n💡 輸入 n=下一段"
            
            messages.append(TextMessage(
                text=progress_text,
                quick_reply=QuickReply(items=quick_items)
            ))
        
        else:
            # 查找當前段落
            section = next((s for s in chapter['sections'] if s['section_id'] == section_id), None)
            
            if not section:
                # 章節結束
                total_content = len(content_sections) + (1 if has_chapter_image else 0)
                
                template = ButtonsTemplate(
                    title="🎉 章節完成",
                    text=f"完成 {chapter['title']}\n\n已閱讀 {total_content} 段內容\n恭喜完成本章節！",
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
                
                # 找到當前段落在內容段落中的位置
                current_index = next((i for i, s in enumerate(content_sections) if s['section_id'] == section_id), -1)
                
                # 上一段按鈕
                if current_index > 0:
                    # 有前一個文字段落
                    prev_section_id = content_sections[current_index - 1]['section_id']
                    quick_items.append(
                        QuickReplyItem(
                            action=PostbackAction(
                                label="⬅️ 上一段",
                                data=f"action=navigate&chapter_id={chapter_id}&section_id={prev_section_id}"
                            )
                        )
                    )
                elif has_chapter_image:
                    # 回到章節圖片（section_id=0）
                    quick_items.append(
                        QuickReplyItem(
                            action=PostbackAction(
                                label="⬅️ 上一段",
                                data=f"action=navigate&chapter_id={chapter_id}&section_id=0"
                            )
                        )
                    )
                
                # 下一段按鈕
                if current_index < len(content_sections) - 1:
                    # 有下一個文字段落
                    next_section_id = content_sections[current_index + 1]['section_id']
                    quick_items.append(
                        QuickReplyItem(
                            action=PostbackAction(
                                label="➡️ 下一段",
                                data=f"action=navigate&chapter_id={chapter_id}&section_id={next_section_id}"
                            )
                        )
                    )
                else:
                    # 檢查是否有測驗題
                    quiz_sections = [s for s in chapter['sections'] if s['type'] == 'quiz']
                    if quiz_sections:
                        first_quiz_id = min(quiz_sections, key=lambda x: x['section_id'])['section_id']
                        quick_items.append(
                            QuickReplyItem(
                                action=PostbackAction(
                                    label="📝 開始測驗",
                                    data=f"action=navigate&chapter_id={chapter_id}&section_id={first_quiz_id}"
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
                
                # 計算進度（考慮圖片段落）
                content_position = current_index + 1  # 在內容段落中的位置
                if has_chapter_image:
                    display_position = content_position + 1  # 圖片算第一段
                    total_content = len(content_sections) + 1
                else:
                    display_position = content_position
                    total_content = len(content_sections)
                
                progress_text = f"📖 第 {display_position}/{total_content} 段\n\n💡 輸入 n=下一段 b=上一段"
                
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

# --- 主程式啟動 ---
if __name__ == "__main__":
    print(">>> LINE Bot 啟動")
    print(f">>> 載入 {len(book_data.get('chapters', []))} 章節")
    print(">>> 五分鐘英文文法攻略 - 增強版 v4.0 (支援通用LINE電腦版)")
    print(">>> 新功能：文字指令、快速導航、智能建議")
    app.run(host='0.0.0.0', port=8080, debug=False)