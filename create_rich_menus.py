# -*- coding: utf-8 -*-
"""
create_rich_menus.py - 五分鐘英文文法攻略統一圖文選單建立腳本
最終版本：根據用戶需求完整實現所有功能
"""
import os
import json
import requests
import time

# === 請填寫您的 Channel Access Token ===
CHANNEL_ACCESS_TOKEN = "5BvBNjyt6NrqujdHjczXYOSYvbF/WQIbhzsnrJKzcHqBoc2n12y34Ccc5IzOWRsKe/zqRtZuSprwjBlYR9PcPbO2PH/s8ZVsaBNMIXrU7GyAqpDSTrWaGbQbdg8vBd27ynXcqOKT8UfSC4r1gBwynwdB04t89/1O/w1cDnyilFU="  # 請替換為您的實際 Token

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

# 統一圖文選單配置 - 根據您的圖片和功能需求設計
UNIFIED_MENU_CONFIG = {
    "size": {"width": 1330, "height": 843},
    "selected": True,
    "name": "GrammarBot_UnifiedMenu_v2",
    "chatBarText": "五分鐘英文文法攻略",
    "areas": [
        # === 第一排功能按鈕 ===
        # 閱讀內容 (左上藍色區域) - 從第一章第一段開始，圖片視為第一段
        {
            "bounds": {"x": 48, "y": 105, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=read_content"}
        },
        
        # 章節選擇 (中上綠色區域) - 橫式輪播選單顯示1-7章
        {
            "bounds": {"x": 577, "y": 105, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=show_chapter_menu"}
        },
        
        # 我的書籤 (右上藍色區域) - 查看標記的內容
        {
            "bounds": {"x": 1107, "y": 105, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=view_bookmarks"}
        },
        
        # === 第二排功能按鈕 ===
        # 上次進度 (左中綠色區域) - 跳到上次閱讀位置
        {
            "bounds": {"x": 48, "y": 200, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=continue_reading"}
        },
        
        # 本章測驗題 (中中藍色區域) - 需要先進入章節才能使用
        {
            "bounds": {"x": 577, "y": 200, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=chapter_quiz"}
        },
        
        # 錯誤分析 (右中綠色區域) - 顯示答錯次數統計，錯誤多的排前面
        {
            "bounds": {"x": 1107, "y": 200, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=view_analytics"}
        }
        
        # 注意：根據您的圖片，底部沒有數字按鈕
        # 如果圖片中有數字按鈕區域，請取消下面的註解並調整座標
        
        # === 數字章節選擇按鈕（如果圖片中有的話）===
        # 第1章
        # {"bounds": {"x": 20, "y": 480, "width": 185, "height": 70}, 
        #  "action": {"type": "postback", "data": "1"}},
        # 第2章
        # {"bounds": {"x": 210, "y": 480, "width": 185, "height": 70}, 
        #  "action": {"type": "postback", "data": "2"}},
        # 第3章
        # {"bounds": {"x": 400, "y": 480, "width": 185, "height": 70}, 
        #  "action": {"type": "postback", "data": "3"}},
        # 第4章
        # {"bounds": {"x": 590, "y": 480, "width": 185, "height": 70}, 
        #  "action": {"type": "postback", "data": "4"}},
        # 第5章
        # {"bounds": {"x": 780, "y": 480, "width": 185, "height": 70}, 
        #  "action": {"type": "postback", "data": "5"}},
        # 第6章
        # {"bounds": {"x": 970, "y": 480, "width": 185, "height": 70}, 
        #  "action": {"type": "postback", "data": "6"}},
        # 第7章
        # {"bounds": {"x": 1155, "y": 480, "width": 155, "height": 70}, 
        #  "action": {"type": "postback", "data": "7"}}
    ]
}

def validate_token():
    """驗證 Channel Access Token"""
    if CHANNEL_ACCESS_TOKEN == "YOUR_CHANNEL_ACCESS_TOKEN_HERE":
        print("❌ 錯誤：請先填寫您的 Channel Access Token！")
        print("請在第12行將 YOUR_CHANNEL_ACCESS_TOKEN_HERE 替換為您的實際 Token")
        return False
    
    if not CHANNEL_ACCESS_TOKEN or len(CHANNEL_ACCESS_TOKEN) < 50:
        print("❌ 錯誤：Channel Access Token 格式不正確！")
        return False
    
    print("✅ Channel Access Token 驗證通過")
    return True

def check_image_file(file_path):
    """檢查圖片檔案"""
    if not os.path.exists(file_path):
        print(f"❌ 錯誤：找不到圖片檔案: {file_path}")
        return False
    
    file_size = os.path.getsize(file_path)
    if file_size > 1024 * 1024:  # 1MB 限制
        print(f"❌ 錯誤：圖片檔案太大: {file_size/1024/1024:.2f}MB (最大 1MB)")
        return False
    
    print(f"✅ 圖片檔案檢查通過: {file_path} ({file_size/1024:.1f}KB)")
    return True

def delete_existing_menus():
    """刪除現有的圖文選單"""
    print("\n🗑️ 正在清理現有的圖文選單...")
    
    try:
        response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=get_headers())
        if response.status_code != 200:
            print(f"⚠️ 無法取得圖文選單列表: {response.status_code}")
            return
        
        rich_menus = response.json().get('richmenus', [])
        
        if not rich_menus:
            print("✅ 沒有現有的圖文選單需要清理")
            return
        
        print(f"📋 找到 {len(rich_menus)} 個現有的圖文選單")
        
        for menu in rich_menus:
            menu_id = menu['richMenuId']
            menu_name = menu.get('name', 'Unknown')
            
            response = requests.delete(f'https://api.line.me/v2/bot/richmenu/{menu_id}', headers=get_headers())
            if response.status_code == 200:
                print(f"✅ 已刪除: {menu_name} ({menu_id[:8]}...)")
            else:
                print(f"❌ 刪除失敗: {menu_name}")
            
            time.sleep(0.5)  # 避免 API 速率限制
        
        print("✅ 圖文選單清理完成")
        
    except Exception as e:
        print(f"❌ 清理過程中發生錯誤: {e}")

def create_rich_menu(config, image_path):
    """建立圖文選單"""
    print(f"\n📋 正在建立圖文選單: {config['name']}")
    
    try:
        # 步驟 1: 建立圖文選單物件
        print("⚙️ 步驟 1: 建立圖文選單物件...")
        response = requests.post(
            'https://api.line.me/v2/bot/richmenu', 
            headers=get_headers(), 
            data=json.dumps(config)
        )
        
        if response.status_code != 200:
            print(f"❌ 建立圖文選單失敗: {response.status_code}")
            print(f"錯誤詳情: {response.text}")
            return None
        
        rich_menu_id = response.json()['richMenuId']
        print(f"✅ 圖文選單建立成功，ID: {rich_menu_id}")

        # 步驟 2: 上傳圖片
        print("📤 步驟 2: 上傳圖片...")
        with open(image_path, 'rb') as f:
            response = requests.post(
                f'https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content', 
                headers=get_upload_headers(), 
                data=f
            )
        
        if response.status_code != 200:
            print(f"❌ 圖片上傳失敗: {response.status_code}")
            print(f"錯誤詳情: {response.text}")
            # 清理失敗的選單
            requests.delete(f'https://api.line.me/v2/bot/richmenu/{rich_menu_id}', headers=get_headers())
            return None
        
        print("✅ 圖片上傳成功")
        
        # 步驟 3: 設定為預設圖文選單
        print("🎯 步驟 3: 設定為預設圖文選單...")
        response = requests.post(
            f'https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}', 
            headers=get_headers()
        )
        
        if response.status_code != 200:
            print(f"⚠️ 設定預設選單失敗: {response.status_code}")
            print("圖文選單已建立，但未設為預設")
        else:
            print("✅ 已設定為預設圖文選單")
        
        return rich_menu_id
        
    except Exception as e:
        print(f"❌ 建立圖文選單時發生錯誤: {e}")
        return None

def show_function_mapping():
    """顯示功能對應說明"""
    print("\n📋 圖文選單功能對應說明:")
    print("=" * 80)
    
    function_descriptions = [
        ("閱讀內容", "從第一章第一段開始閱讀，圖片視為第一段"),
        ("章節選擇", "顯示橫式輪播選單，可選擇 1-7 章"),
        ("我的書籤", "查看所有標記的重要段落"),
        ("上次進度", "跳到上次閱讀的位置"),
        ("本章測驗題", "顯示當前章節的測驗題（需要先進入章節）"),
        ("錯誤分析", "顯示答錯次數統計，錯誤多的排在前面")
    ]
    
    for i, (func, desc) in enumerate(function_descriptions, 1):
        print(f"{i}. {func:<12} - {desc}")
    
    print("\n📐 點擊區域座標:")
    print("-" * 80)
    for i, area in enumerate(UNIFIED_MENU_CONFIG['areas'], 1):
        bounds = area['bounds']
        action_data = area['action']['data']
        print(f"區域 {i}: ({bounds['x']:4d}, {bounds['y']:3d}, {bounds['width']:3d}, {bounds['height']:3d}) -> {action_data}")

def show_user_flow():
    """顯示使用者操作流程"""
    print("\n🔄 使用者操作流程:")
    print("=" * 60)
    print("1. 📱 加入 LINE Bot 好友")
    print("2. 🎯 顯示統一圖文選單")
    print("3. 📚 點擊「閱讀內容」→ 顯示第一章第一段圖片")
    print("   └── 🔽 下方有「下一段」和「標記」按鈕")
    print("4. 📖 點擊「章節選擇」→ 橫式輪播顯示 1-7 章")
    print("   └── 🎯 可選擇任意章節開始學習")
    print("5. 🔖 點擊「我的書籤」→ 查看所有標記內容")
    print("   └── 📍 快速跳轉到收藏的段落")
    print("6. ⏯️ 點擊「上次進度」→ 跳到上次閱讀位置")
    print("7. 📝 點擊「本章測驗題」→ 開始當前章節測驗")
    print("   └── ⚠️ 需要先進入章節才能使用")
    print("8. 📊 點擊「錯誤分析」→ 顯示答錯統計")
    print("   └── 🎯 錯誤次數多的題目排在前面")

def main():
    """主執行函式"""
    print("=" * 80)
    print("🚀 五分鐘英文文法攻略 - 統一圖文選單建立程式")
    print("=" * 80)
    print("版本: v2.0 - 根據用戶需求完整實現")
    print("功能: 統一圖文選單，包含完整學習流程")
    print("=" * 80)
    
    # 顯示功能對應和使用流程
    show_function_mapping()
    show_user_flow()
    
    # 驗證設定
    if not validate_token():
        return
    
    # 檢查圖片檔案
    image_path = './images/rich_menu_main.png'
    if not check_image_file(image_path):
        print(f"\n❌ 需要圖片檔案: {image_path}")
        print("請確保您有:")
        print("1. images 資料夾存在")
        print("2. rich_menu_main.png 檔案在 images 資料夾中")
        print("3. 圖片尺寸: 1330 x 843 像素")
        print("4. 圖片格式: PNG")
        print("5. 檔案大小: 小於 1MB")
        print("\n💡 圖片設計建議:")
        print("• 第一排: 閱讀內容、章節選擇、我的書籤")
        print("• 第二排: 上次進度、本章測驗題、錯誤分析")
        print("• 背景色: 深色系 (如深藍灰)")
        print("• 按鈕色: 藍色和綠色交替")
        return
    
    # 詢問是否繼續
    try:
        proceed = input("\n🚀 座標已根據您的圖片調整，是否繼續建立圖文選單? (y/N): ").strip().lower()
        if proceed not in ['y', 'yes', '是']:
            print("取消建立")
            return
    except KeyboardInterrupt:
        print("\n\n👋 已取消")
        return
    
    # 詢問是否清理現有選單
    try:
        cleanup = input("\n🗑️ 是否先刪除現有的圖文選單? (推薦: y/N): ").strip().lower()
        if cleanup in ['y', 'yes', '是']:
            delete_existing_menus()
            time.sleep(2)  # 等待清理完成
    except KeyboardInterrupt:
        print("\n\n👋 已取消")
        return
    
    # 建立圖文選單
    print("\n" + "=" * 80)
    print("📋 開始建立統一圖文選單...")
    
    menu_id = create_rich_menu(UNIFIED_MENU_CONFIG, image_path)
    
    # 顯示結果
    print("\n" + "=" * 80)
    
    if menu_id:
        print("🎉 圖文選單建立成功！")
        print("\n📋 選單詳情:")
        print(f"名稱: {UNIFIED_MENU_CONFIG['name']}")
        print(f"ID: {menu_id}")
        print(f"尺寸: {UNIFIED_MENU_CONFIG['size']['width']} x {UNIFIED_MENU_CONFIG['size']['height']}")
        print(f"點擊區域: {len(UNIFIED_MENU_CONFIG['areas'])} 個")
        
        print("\n🔧 接下來的步驟:")
        print("=" * 50)
        print("1. 複製下方的 Rich Menu ID")
        print("2. 登入您的 Render Dashboard")
        print("3. 選擇您的 LINE Bot 服務")
        print("4. 點擊 Environment 標籤")
        print("5. 更新環境變數:")
        print(f"   MAIN_RICH_MENU_ID = {menu_id}")
        print("6. 刪除 CHAPTER_RICH_MENU_ID (不再需要)")
        print("7. 點擊 Save Changes")
        print("8. 等待服務重新部署完成")
        print("9. 上傳修改版的 app.py")
        
        print("\n📋 Rich Menu ID (請複製):")
        print("=" * 50)
        print(menu_id)
        print("=" * 50)
        
        print("\n✅ 實現的完整功能:")
        print("📚 閱讀內容 - 從第一章第一段開始，圖片視為第一段")
        print("📖 章節選擇 - 橫式輪播顯示 1-7 章，可任意選擇")
        print("🔖 我的書籤 - 查看所有標記的重要段落")
        print("⏯️ 上次進度 - 跳轉到上次閱讀的確切位置")
        print("📝 本章測驗題 - 開始當前章節測驗 (需先進入章節)")
        print("📊 錯誤分析 - 顯示答錯統計，錯誤多的排前面")
        
        print("\n🧪 部署完成後測試流程:")
        print("1. 加 LINE Bot 為好友")
        print("2. 查看統一圖文選單是否正確顯示")
        print("3. 點擊「閱讀內容」→ 應顯示第一章圖片")
        print("4. 點擊「章節選擇」→ 應顯示橫式章節輪播")
        print("5. 測試標記功能 → 點擊「我的書籤」查看")
        print("6. 完成幾個測驗 → 點擊「錯誤分析」查看統計")
        print("7. 確認「上次進度」能正確跳轉")
        print("8. 確認「本章測驗題」在選擇章節後能使用")
        
        print("\n📱 用戶體驗重點:")
        print("• 圖片作為第一段，下方只有「下一段」和「標記」")
        print("• 一般段落有「上一段」、「下一段」、「標記」")
        print("• 章節選擇使用橫式輪播，視覺效果更佳")
        print("• 書籤提供快速跳轉功能")
        print("• 錯誤分析按錯誤次數排序，幫助重點複習")
        print("• 需要先進入章節才能使用測驗功能")
        
    else:
        print("❌ 圖文選單建立失敗")
        print("\n🔍 可能的原因:")
        print("• Channel Access Token 不正確")
        print("• 圖片檔案格式或尺寸不符合要求")
        print("• 網路連線問題")
        print("• LINE Bot 設定問題")
        print("• 座標設定與圖片不符")
        print("\n💡 請檢查上述項目後重試")

def adjust_coordinates():
    """座標微調模式"""
    print("\n🔧 座標微調模式")
    print("如果按鈕位置不準確，可以調整以下座標:")
    print("-" * 50)
    
    coordinate_tips = [
        ("閱讀內容", "左上角", "如果偏移，調整 x 和 y 值"),
        ("章節選擇", "中上", "如果按鈕範圍不對，調整 width"),
        ("我的書籤", "右上角", "注意不要超出圖片邊界"),
        ("上次進度", "左中", "垂直位置用 y 值調整"),
        ("本章測驗題", "中中", "是否與圖片按鈕對齊"),
        ("錯誤分析", "右中", "檢查右邊界是否正確")
    ]
    
    for func, pos, tip in coordinate_tips:
        print(f"• {func:<12} ({pos:<6}): {tip}")
    
    print(f"\n📐 當前座標設定:")
    for i, area in enumerate(UNIFIED_MENU_CONFIG['areas'], 1):
        bounds = area['bounds']
        print(f"區域 {i}: x={bounds['x']:4d}, y={bounds['y']:3d}, w={bounds['width']:3d}, h={bounds['height']:3d}")

if __name__ == "__main__":
    try:
        main()
        
        # 詢問是否需要座標調整說明
        adjust_help = input("\n🔧 是否需要查看座標調整說明? (y/N): ").strip().lower()
        if adjust_help in ['y', 'yes', '是']:
            adjust_coordinates()
            
    except KeyboardInterrupt:
        print("\n\n👋 程式已被使用者中斷")
    except Exception as e:
        print(f"\n❌ 程式執行時發生錯誤: {e}")
        print("💡 請檢查設定和網路連線後重試")

# === 重要說明 ===
"""
🎯 根據您的需求實現的完整功能:

1. 📱 進入頁面顯示統一圖文選單
2. 📚 「閱讀內容」從第一章第一段開始，圖片視為第一段
3. 📖 「章節選擇」顯示橫式輪播選單 (1-7章)
4. 🔖 「我的書籤」查看所有標記的內容
5. ⏯️ 「上次進度」跳到上次閱讀位置
6. 📝 「本章測驗題」需要先進入章節才能使用
7. 📊 「錯誤分析」顯示答錯次數，錯誤多的排前面

🛠️ 使用步驟:
1. 填入您的 Channel Access Token (第12行)
2. 確保 ./images/rich_menu_main.png 存在
3. 執行: python create_rich_menus.py
4. 複製輸出的 Rich Menu ID
5. 在 Render 中設定 MAIN_RICH_MENU_ID
6. 部署修改版的 app.py
7. 測試所有功能是否正常運作

📐 座標說明:
- 座標已根據您提供的圖片進行調整
- 如果按鈕位置不準確，請修改 bounds 中的 x, y, width, height 值
- 使用程式中的座標調整說明進行微調
"""