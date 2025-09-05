# -*- coding: utf-8 -*-
"""
更新原有的圖文選單建立腳本
根據你提供的圖片調整精確座標
"""
import os
import json
import requests
import time

# --- 請填寫您的 Channel Access Token ---
# 確保引號內只有您的金鑰，沒有其他多餘的字元
CHANNEL_ACCESS_TOKEN = "5BvBNjyt6NrqujdHjczXYOSYvbF/WQIbhzsnrJKzcHqBoc2n12y34Ccc5IzOWRsKe/zqRtZuSprwjBlYR9PcPbO2PH/s8ZVsaBNMIXrU7GyAqpDSTrWaGbQbdg8vBd27ynXcqOKT8UfSC4r1gBwynwdB04t89/1O/w1cDnyilFU="  # 請填入你的 Token
# ------------------------------------

# --- 建立請求標頭 ---
def get_headers():
    """取得 API 請求標頭"""
    return {
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }

def get_upload_headers():
    """取得上傳圖片的請求標頭"""
    return {
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'image/png'
    }

# --- 更新後的主選單設定 ---
main_menu_config = {
    "size": {"width": 1330, "height": 843},  # 根據你的圖片調整
    "selected": True,
    "name": "MainMenu_Updated_v3",
    "chatBarText": "查看主選單",
    "areas": [
        # 閱讀內容（左上藍色區域）
        {
            "bounds": {"x": 22, "y": 158, "width": 436, "height": 530}, 
            "action": {"type": "postback", "data": "action=read_content"}
        },
        
        # 上次進度（中間藍色區域）
        {
            "bounds": {"x": 458, "y": 158, "width": 436, "height": 530}, 
            "action": {"type": "postback", "data": "action=continue_reading"}
        },
        
        # 本章測驗題（右上藍色區域）
        {
            "bounds": {"x": 894, "y": 158, "width": 436, "height": 530}, 
            "action": {"type": "postback", "data": "action=chapter_quiz"}
        },
        
        # 主選單按鈕（左下灰色區域）
        {
            "bounds": {"x": 318, "y": 714, "width": 324, "height": 107}, 
            "action": {"type": "postback", "data": "action=switch_to_main_menu"}
        },
        
        # 章節選單按鈕（右下綠色區域）
        {
            "bounds": {"x": 700, "y": 714, "width": 324, "height": 107}, 
            "action": {"type": "postback", "data": "action=show_chapter_menu"}
        }
    ]
}

# --- 更新後的章節選單設定 ---
chapter_menu_config = {
    "size": {"width": 1330, "height": 843},
    "selected": False,
    "name": "ChapterMenu_Updated_v3",
    "chatBarText": "查看章節功能",
    "areas": [
        # 第一排章節按鈕
        # 第1章（左上灰色）
        {"bounds": {"x": 42, "y": 182, "width": 218, "height": 148}, 
         "action": {"type": "postback", "data": "action=select_chapter&chapter_id=1"}},
        
        # 第2章（中上灰色）
        {"bounds": {"x": 318, "y": 182, "width": 218, "height": 148}, 
         "action": {"type": "postback", "data": "action=select_chapter&chapter_id=2"}},
        
        # 第3章（右上灰色）
        {"bounds": {"x": 594, "y": 182, "width": 218, "height": 148}, 
         "action": {"type": "postback", "data": "action=select_chapter&chapter_id=3"}},
        
        # 第二排章節按鈕
        # 第4章（左中灰色）
        {"bounds": {"x": 42, "y": 352, "width": 218, "height": 148}, 
         "action": {"type": "postback", "data": "action=select_chapter&chapter_id=4"}},
        
        # 第5章（中中灰色）
        {"bounds": {"x": 318, "y": 352, "width": 218, "height": 148}, 
         "action": {"type": "postback", "data": "action=select_chapter&chapter_id=5"}},
        
        # 第6章（右中灰色）
        {"bounds": {"x": 594, "y": 352, "width": 218, "height": 148}, 
         "action": {"type": "postback", "data": "action=select_chapter&chapter_id=6"}},
        
        # 第7章（大的灰色區域）
        {"bounds": {"x": 42, "y": 522, "width": 770, "height": 148}, 
         "action": {"type": "postback", "data": "action=select_chapter&chapter_id=7"}},
        
        # 右側功能區域
        # 繼續閱讀（右上藍色）
        {"bounds": {"x": 820, "y": 182, "width": 488, "height": 148}, 
         "action": {"type": "postback", "data": "action=continue_reading"}},
        
        # 我的書籤（右中藍色）
        {"bounds": {"x": 820, "y": 352, "width": 488, "height": 148}, 
         "action": {"type": "postback", "data": "action=view_bookmarks"}},
        
        # 錯誤分析（右下藍色）
        {"bounds": {"x": 820, "y": 522, "width": 488, "height": 148}, 
         "action": {"type": "postback", "data": "action=view_analytics"}},
        
        # 底部按鈕
        # 主選單按鈕（左下綠色）
        {"bounds": {"x": 318, "y": 714, "width": 324, "height": 107}, 
         "action": {"type": "postback", "data": "action=switch_to_main_menu"}},
        
        # 章節選單按鈕（右下灰色）
        {"bounds": {"x": 700, "y": 714, "width": 324, "height": 107}, 
         "action": {"type": "postback", "data": "action=show_chapter_menu"}}
    ]
}

def validate_token():
    """驗證 Channel Access Token 是否有效"""
    if "你的_CHANNEL_ACCESS_TOKEN" in CHANNEL_ACCESS_TOKEN:
        print("❌ 錯誤：請先在程式碼中填寫您的 Channel Access Token！")
        return False
    
    if not CHANNEL_ACCESS_TOKEN or len(CHANNEL_ACCESS_TOKEN) < 50:
        print("❌ 錯誤：Channel Access Token 格式不正確！")
        return False
    
    return True

def check_file_exists(file_path):
    """檢查圖片檔案是否存在"""
    if not os.path.exists(file_path):
        print(f"❌ 錯誤：找不到圖片檔案 {file_path}")
        return False
    
    # 檢查檔案大小（LINE 限制 1MB）
    file_size = os.path.getsize(file_path)
    if file_size > 1024 * 1024:  # 1MB
        print(f"❌ 錯誤：圖片檔案 {file_path} 太大（{file_size/1024/1024:.2f}MB），請壓縮至 1MB 以下")
        return False
    
    print(f"✅ 圖片檔案檢查通過：{file_path} ({file_size/1024:.1f}KB)")
    return True

def delete_all_rich_menus():
    """刪除所有現有的圖文選單"""
    try:
        print("🧹 正在清理舊的圖文選單...")
        
        # 取得所有圖文選單
        response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=get_headers())
        if response.status_code != 200:
            print(f"⚠️ 無法取得圖文選單列表: {response.status_code}")
            return
        
        rich_menus = response.json().get('richmenus', [])
        
        if not rich_menus:
            print("✅ 沒有需要清理的圖文選單")
            return
        
        print(f"📋 找到 {len(rich_menus)} 個現有的圖文選單")
        
        # 刪除每個圖文選單
        for menu in rich_menus:
            menu_id = menu['richMenuId']
            menu_name = menu.get('name', 'Unknown')
            
            response = requests.delete(f'https://api.line.me/v2/bot/richmenu/{menu_id}', headers=get_headers())
            if response.status_code == 200:
                print(f"🗑️ 已刪除圖文選單：{menu_name} ({menu_id[:8]}...)")
            else:
                print(f"⚠️ 刪除圖文選單失敗：{menu_name} - {response.status_code}")
            
            time.sleep(0.5)  # 避免 API 限制
        
        print("✅ 圖文選單清理完成")
        
    except Exception as e:
        print(f"❌ 清理圖文選單時發生錯誤: {e}")

def create_rich_menu(config, image_path, set_as_default=False):
    """一個通用的函式，用來建立、上傳並設定圖文選單"""
    print(f"\n📋 開始處理 {config['name']}...")
    
    try:
        # 檢查圖片檔案
        if not check_file_exists(image_path):
            return None
        
        # 1. 建立圖文選單物件
        print("⚙️ 步驟 1: 正在建立圖文選單物件...")
        response = requests.post(
            'https://api.line.me/v2/bot/richmenu', 
            headers=get_headers(), 
            data=json.dumps(config)
        )
        
        if response.status_code != 200:
            print(f"❌ [錯誤] 建立失敗: {response.status_code} - {response.text}")
            return None
        
        rich_menu_id = response.json()['richMenuId']
        print(f"✅ [成功] 取得 ID: {rich_menu_id}")

        # 2. 上傳圖片
        print("📤 步驟 2: 正在上傳圖片...")
        try:
            with open(image_path, 'rb') as f:
                response = requests.post(
                    f'https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content', 
                    headers=get_upload_headers(), 
                    data=f
                )
            
            if response.status_code != 200:
                print(f"❌ [錯誤] 圖片上傳失敗: {response.status_code} - {response.text}")
                # 清理失敗的選單
                requests.delete(f'https://api.line.me/v2/bot/richmenu/{rich_menu_id}', headers=get_headers())
                return None
            
            print("✅ [成功] 圖片已上傳")
            
        except Exception as e:
            print(f"❌ [錯誤] 上傳圖片時發生例外: {e}")
            return None
        
        # 3. 設為預設（如果需要）
        if set_as_default:
            print("🎯 步驟 3: 正在設為預設選單...")
            response = requests.post(
                f'https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}', 
                headers=get_headers()
            )
            
            if response.status_code != 200:
                print(f"⚠️ [警告] 設定預設選單失敗: {response.status_code} - {response.text}")
                print("🔍 圖文選單已建立，但未設為預設。您可以手動設定。")
            else:
                print("✅ [成功] 已設為預設選單")
        
        print(f"🎉 {config['name']} 建立完成！")
        return rich_menu_id
        
    except Exception as e:
        print(f"❌ [嚴重錯誤] 建立 {config['name']} 時發生未知錯誤: {e}")
        return None

def main():
    """主程式"""
    print("🚀 LINE Bot 圖文選單更新程式啟動")
    print("=" * 50)
    
    # 驗證 Token
    if not validate_token():
        return
    
    print("✅ Channel Access Token 格式檢查通過")
    
    # 定義圖片路徑（你可能需要調整這些路徑）
    main_image_path = './images/rich_menu_main.png'
    chapter_image_path = './images/rich_menu_chapter.png'
    
    # 檢查圖片檔案
    if not all([
        check_file_exists(main_image_path),
        check_file_exists(chapter_image_path)
    ]):
        print("\n❌ 請確保以下圖片檔案存在：")
        print("  - ./images/rich_menu_main.png")
        print("  - ./images/rich_menu_chapter.png")
        return
    
    # 詢問是否要清理舊選單
    try:
        user_input = input("\n🗑️ 是否要先清理所有現有的圖文選單？(y/N): ").strip().lower()
        if user_input in ['y', 'yes', '是']:
            delete_all_rich_menus()
            time.sleep(2)  # 等待清理完成
    except KeyboardInterrupt:
        print("\n\n👋 程式已取消")
        return
    
    print("\n" + "=" * 50)
    print("📋 開始建立新的圖文選單...")
    
    # 建立主選單（更新版）
    main_id = create_rich_menu(
        config=main_menu_config, 
        image_path=main_image_path, 
        set_as_default=True
    )
    
    # 建立章節選單（更新版）
    chapter_id = create_rich_menu(
        config=chapter_menu_config, 
        image_path=chapter_image_path, 
        set_as_default=False
    )
    
    # 總結結果
    print("\n" + "=" * 50)
    
    if main_id and chapter_id:
        print("🎉 圖文選單更新完成！")
        print("\n📋 請將這兩個新的 ID 複製起來，更新到 Render 的環境變數中:")
        print(f"MAIN_RICH_MENU_ID: {main_id}")
        print(f"CHAPTER_RICH_MENU_ID: {chapter_id}")
        
        print("\n💡 環境變數設定步驟：")
        print("1. 登入 Render Dashboard")
        print("2. 選擇您的服務")
        print("3. 點擊 Environment 標籤")
        print("4. 更新上述兩個環境變數")
        print("5. 點擊 Save Changes")
        
        print("\n✅ 設定完成後，您的 LINE Bot 就可以使用新的圖文選單了！")
        print("\n🔧 如果座標有偏移，請調整 main_menu_config 和 chapter_menu_config 中的 bounds 設定")
        
    elif main_id or chapter_id:
        print("⚠️ 部分圖文選單建立成功")
        if main_id:
            print(f"✅ 主選單 ID: {main_id}")
        if chapter_id:
            print(f"✅ 章節選單 ID: {chapter_id}")
        print("❌ 請檢查錯誤訊息並重新執行")
        
    else:
        print("❌ 圖文選單建立失敗")
        print("💡 請檢查：")
        print("  - Channel Access Token 是否正確")
        print("  - 圖片檔案是否存在且格式正確")
        print("  - 網路連線是否正常")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程式已被使用者中斷")
    except Exception as e:
        print(f"\n❌ 程式執行時發生未知錯誤: {e}")
        print("💡 請檢查程式碼和環境設定")

# 座標調整說明：
"""
如果圖文選單按鈕位置有偏移，請調整以下座標：

主選單 (main_menu_config):
- 閱讀內容: {"x": 22, "y": 158, "width": 436, "height": 530}
- 上次進度: {"x": 458, "y": 158, "width": 436, "height": 530}
- 本章測驗題: {"x": 894, "y": 158, "width": 436, "height": 530}
- 主選單按鈕: {"x": 318, "y": 714, "width": 324, "height": 107}
- 章節選單按鈕: {"x": 700, "y": 714, "width": 324, "height": 107}

章節選單 (chapter_menu_config):
- 1-6章: 分別對應不同的小方格
- 第7章: 橫跨較大的區域
- 右側功能按鈕: 繼續閱讀、我的書籤、錯誤分析

如需精確調整，請使用圖片編輯軟體測量座標。
"""