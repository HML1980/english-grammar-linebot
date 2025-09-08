# -*- coding: utf-8 -*-
"""
單一圖文選單修改版
將兩個圖文選單合併為一個，包含所有功能
"""

# app.py 主要修改部分

# === 1. 環境變數修改 ===
# 原本的環境變數設定
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.environ.get('5BvBNjyt6NrqujdHjczXYOSYvbF/WQIbhzsnrJKzcHqBoc2n12y34Ccc5IzOWRsKe/zqRtZuSprwjBlYR9PcPbO2PH/s8ZVsaBNMIXrU7GyAqpDSTrWaGbQbdg8vBd27ynXcqOKT8UfSC4r1gBwynwdB04t89/1O/w1cDnyilFU=')
# 修改：只需要一個圖文選單 ID
MAIN_RICH_MENU_ID = os.environ.get('MAIN_RICH_MENU_ID')  # 刪除 CHAPTER_RICH_MENU_ID

# 修改環境變數檢查
required_env_vars = [CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN, MAIN_RICH_MENU_ID]  # 移除 CHAPTER_RICH_MENU_ID
if not all(required_env_vars):
    print("錯誤：缺少必要的環境變數")
    exit(1)

# === 2. 關注事件處理修改 ===
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
        
        # 設定圖文選單 - 只設定主選單
        switch_rich_menu(user_id, MAIN_RICH_MENU_ID)
        
        # 發送歡迎訊息
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="歡迎使用英文文法攻略！\n\n點擊下方選單開始學習。\n\n小提示：\n• 點擊數字 1-7 選擇章節\n• 輸入「進度」查看學習進度\n• 輸入「幫助」查看使用說明")]
            )
        )
        
    except Exception as e:
        print(f">>> 處理關注事件錯誤: {e}")

# === 3. 文字訊息處理修改 ===
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    line_api = MessagingApi(ApiClient(configuration))
    
    try:
        if '目錄' in text or 'menu' in text.lower():
            # 不需要切換選單，因為只有一個
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="請使用下方圖文選單功能")]
                )
            )
        elif '進度' in text or 'progress' in text.lower():
            handle_progress_inquiry(user_id, event.reply_token, line_api)
        elif '幫助' in text or 'help' in text.lower():
            help_text = "使用說明：\n\n📚 閱讀內容：從頭開始閱讀\n⏯️ 上次進度：跳至上次閱讀處\n📝 本章測驗：練習測驗題目\n🔖 我的書籤：查看收藏內容\n📊 錯誤分析：檢視答錯題目\n📖 章節選擇：選擇其他章節\n\n小技巧：\n• 點擊數字 1-7 直接選擇章節\n• 閱讀時可標記重要段落\n• 完成測驗後可查看錯誤分析"
            
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=help_text)]
                )
            )
        else:
            line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="請使用下方選單操作\n\n或輸入：\n• 「進度」查看學習進度\n• 「幫助」查看使用說明\n• 數字 1-7 直接選擇章節")]
                )
            )
    except Exception as e:
        print(f">>> 處理文字訊息錯誤: {e}")

# === 4. Postback 事件處理修改 ===
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
        # 直接章節選擇（數字 1-7）
        if data.isdigit():
            chapter_number = int(data)
            print(f">>> 偵測到數字章節選擇: 第 {chapter_number} 章")
            handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api)
            return
        
        params = parse_qs(data)
        action = params.get('action', [None])[0]
        print(f">>> 解析的動作: {action}")
        
        # 各種功能處理（不再需要選單切換）
        if action == 'read_content':
            handle_chapter_action('read_chapter', user_id, reply_token, line_api)
            
        elif action == 'continue_reading':
            handle_resume_reading(user_id, reply_token, line_api)
            
        elif action == 'chapter_quiz':
            handle_chapter_action('do_quiz', user_id, reply_token, line_api)
            
        elif action == 'view_bookmarks':
            handle_bookmarks(user_id, reply_token, line_api)
            
        elif action == 'view_analytics':
            handle_analytics(user_id, reply_token, line_api)
            
        elif action == 'show_chapter_menu':
            handle_show_chapter_carousel(user_id, reply_token, line_api)
            
        # 其他現有功能保持不變
        elif action in ['read_chapter', 'resume_chapter', 'do_quiz']:
            handle_chapter_action(action, user_id, reply_token, line_api)
            
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

# === 5. 新增章節輪播展示功能 ===
def handle_show_chapter_carousel(user_id, reply_token, line_api):
    """顯示章節選擇輪播（用於章節選擇按鈕）"""
    try:
        columns = []
        
        for chapter in book_data['chapters']:
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
                messages=[TextMessage(text="章節選單載入失敗")]
            )
        )

# === 6. 章節選擇處理修改 ===
def handle_direct_chapter_selection(user_id, chapter_number, reply_token, line_api):
    """處理直接數字章節選擇（不需要切換選單）"""
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
        
        chapter_info = f"✅ 已選擇第 {chapter_number} 章\n{chapter['title']}\n\n📝 內容段落：{content_count} 段\n❓ 測驗題目：{quiz_count} 題\n\n使用下方功能開始學習：\n• 閱讀內容：從頭開始\n• 上次進度：跳到上次位置\n• 本章測驗：開始練習"
        
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=chapter_info)]
            )
        )
        
    except Exception as e:
        print(f">>> 直接章節選擇錯誤: {e}")
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text="選擇章節失敗，請稍後再試")]
            )
        )

# === 7. 移除不需要的函式 ===
# 刪除以下函式（因為不再需要選單切換）：
# - handle_show_chapter_menu (替換為 handle_show_chapter_carousel)
# - handle_select_chapter (合併到 handle_direct_chapter_selection)
# - 所有 switch_rich_menu 相關的選單切換邏輯可以簡化