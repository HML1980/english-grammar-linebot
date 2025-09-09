# -*- coding: utf-8 -*-
"""
create_rich_menus.py - 五分鐘英文文法攻略統一圖文選單建立腳本
修正版：800 x 270 像素標準尺寸
"""
import os
import json
import requests
import time

# === 請填寫您的 Channel Access Token ===
CHANNEL_ACCESS_TOKEN = "5BvBNjyt6NrqujdHjczXYOSYvbF/WQIbhzsnrJKzcHqBoc2n12y34Ccc5IzOWRsKe/zqRtZuSprwjBlYR9PcPbO2PH/s8ZVsaBNMIXrU7GyAqpDSTrWaGbQbdg8vBd27ynXcqOKT8UfSC4r1gBwynwdB04t89/1O/w1cDnyilFU="

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

# 根據 LINE 標準尺寸的圖文選單配置 (800 x 270)
UNIFIED_MENU_CONFIG = {
    "size": {"width": 800, "height": 270},
    "selected": True,
    "name": "GrammarBot_UnifiedMenu_v4",
    "chatBarText": "五分鐘英文文法攻略",
    "areas": [
        # === 第一排 (上排) ===
        # 閱讀內容 (左上)
        {
            "bounds": {"x": 20, "y": 47, "width": 240, "height": 88}, 
            "action": {"type": "postback", "data": "action=read_content"}
        },
        
        # 章節選擇 (中上)
        {
            "bounds": {"x": 280, "y": 47, "width": 240, "height": 88}, 
            "action": {"type": "postback", "data": "action=show_chapter_menu"}
        },
        
        # 我的書籤 (右上)
        {
            "bounds": {"x": 540, "y": 47, "width": 240, "height": 88}, 
            "action": {"type": "postback", "data": "action=view_bookmarks"}
        },
        
        # === 第二排 (下排) ===
        # 上次進度 (左下)
        {
            "bounds": {"x": 20, "y": 153, "width": 240, "height": 88}, 
            "action": {"type": "postback", "data": "action=continue_reading"}
        },
        
        # 本章測驗題 (中下)
        {
            "bounds": {"x": 280, "y": 153, "width": 240, "height": 88}, 
            "action": {"type": "postback", "data": "action=chapter_quiz"}
        },
        
        # 錯誤分析 (右下)
        {
            "bounds": {"x": 540, "y": 153, "width": 240, "height": 88}, 
            "action": {"type": "postback", "data": "action=view_analytics"}
        }
    ]
}

def validate_token():
    """驗證 Channel Access Token"""
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
            
            time.sleep(0.5)
        
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

def show_coordinate_mapping():
    """顯示座標對應"""
    print("\n📐 LINE 標準尺寸座標對應 (800x270, 2排3列):")
    print("=" * 70)
    
    area_names = [
        "閱讀內容 (左上)",
        "章節選擇 (中上)", 
        "我的書籤 (右上)",
        "上次進度 (左下)",
        "本章測驗題 (中下)",
        "錯誤分析 (右下)"
    ]
    
    for i, (area, name) in enumerate(zip(UNIFIED_MENU_CONFIG['areas'], area_names)):
        bounds = area['bounds']
        action = area['action']['data']
        print(f"{i+1}. {name:<15} -> {action}")
        print(f"   座標: x={bounds['x']:3d}, y={bounds['y']:3d}, w={bounds['width']:3d}, h={bounds['height']:2d}")

def main():
    """主執行函式"""
    print("=" * 80)
    print("🚀 五分鐘英文文法攻略 - 圖文選單建立程式 (800x270版)")
    print("=" * 80)
    print("版本: v4.0 - 配合 800x270 標準尺寸")
    print("設計: 2排3列，共6個功能按鈕")
    print("=" * 80)
    
    # 顯示座標對應
    show_coordinate_mapping()
    
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
        print("3. 圖片尺寸: 800 x 270 像素")
        print("4. 圖片格式: PNG")
        print("5. 檔案大小: 小於 1MB")
        print("6. 圖片採用 2排3列設計")
        return
    
    # 詢問是否繼續
    try:
        proceed = input("\n🚀 座標已調整為 800x270 標準尺寸，是否繼續建立? (y/N): ").strip().lower()
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
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\n👋 已取消")
        return
    
    # 建立圖文選單
    print("\n" + "=" * 80)
    print("📋 開始建立圖文選單...")
    
    menu_id = create_rich_menu(UNIFIED_MENU_CONFIG, image_path)
    
    # 顯示結果
    print("\n" + "=" * 80)
    
    if menu_id:
        print("🎉 圖文選單建立成功！")
        print("\n📋 選單詳情:")
        print(f"名稱: {UNIFIED_MENU_CONFIG['name']}")
        print(f"ID: {menu_id}")
        print(f"設計: 2排3列 (6個按鈕)")
        print(f"尺寸: {UNIFIED_MENU_CONFIG['size']['width']} x {UNIFIED_MENU_CONFIG['size']['height']} (LINE標準)")
        
        print("\n🔧 接下來的步驟:")
        print("=" * 50)
        print("1. 複製下方的 Rich Menu ID")
        print("2. 登入您的 Render Dashboard")
        print("3. 選擇您的 LINE Bot 服務")
        print("4. 點擊 Environment 標籤")
        print("5. 更新環境變數:")
        print(f"   MAIN_RICH_MENU_ID = {menu_id}")
        print("6. 點擊 Save Changes")
        print("7. 等待服務重新部署完成")
        
        print("\n📋 Rich Menu ID (請複製):")
        print("=" * 50)
        print(menu_id)
        print("=" * 50)
        
        print("\n✅ 功能對應:")
        print("第一排: 閱讀內容 | 章節選擇 | 我的書籤")
        print("第二排: 上次進度 | 本章測驗題 | 錯誤分析")
        
        print("\n🧪 測試建議:")
        print("1. 加 LINE Bot 為好友")
        print("2. 確認圖文選單正確顯示")
        print("3. 測試每個按鈕是否對應正確功能")
        print("4. 如果按鈕位置不準確，可微調座標")
        
    else:
        print("❌ 圖文選單建立失敗")
        print("\n🔍 可能的原因:")
        print("• Channel Access Token 不正確")
        print("• 圖片檔案格式或尺寸不符合要求")
        print("• 網路連線問題")
        print("• 座標設定與圖片不符")

def debug_coordinates():
    """座標除錯模式"""
    print("\n🔧 座標除錯資訊 (800x270):")
    print("-" * 50)
    print("圖片總尺寸: 800 x 270")
    print("按鈕排列: 2排3列")
    print("每個按鈕大小: 240 x 88")
    print("按鈕間距: 約 20 像素")
    print("邊距: 20 像素")
    print("\n按鈕位置計算:")
    print("第一排 y=47, 第二排 y=153")
    print("第一列 x=20, 第二列 x=280, 第三列 x=540")
    print("\n如果按鈕對不準，請調整以下座標:")
    
    adjustment_tips = [
        "如果整體偏左，將所有 x 值增加 5-10",
        "如果整體偏右，將所有 x 值減少 5-10", 
        "如果整體偏上，將所有 y 值增加 5-10",
        "如果整體偏下，將所有 y 值減少 5-10",
        "如果按鈕太小，增加 width 和 height 值",
        "如果按鈕太大，減少 width 和 height 值",
        "如果按鈕重疊，增加間距或減少按鈕大小"
    ]
    
    for tip in adjustment_tips:
        print(f"• {tip}")

if __name__ == "__main__":
    try:
        main()
        
        # 詢問是否需要座標除錯資訊
        debug_help = input("\n🔧 是否需要查看座標除錯資訊? (y/N): ").strip().lower()
        if debug_help in ['y', 'yes', '是']:
            debug_coordinates()
            
    except KeyboardInterrupt:
        print("\n\n👋 程式已被使用者中斷")
    except Exception as e:
        print(f"\n❌ 程式執行時發生錯誤: {e}")
        print("💡 請檢查設定和網路連線後重試")

# 使用說明:
"""
🎯 800x270 像素版本說明:

圖片規格:
- 尺寸: 800 x 270 像素 (LINE 官方標準)
- 格式: PNG
- 大小: 小於 1MB
- 設計: 2排3列，共6個按鈕

座標配置:
- 第一排 y=47, 第二排 y=153
- 三列 x=20, 280, 540
- 按鈕大小: 240 x 88

功能對應:
第一排: 閱讀內容 | 章節選擇 | 我的書籤
第二排: 上次進度 | 本章測驗題 | 錯誤分析

使用步驟:
1. 確保圖片為 800x270 像素
2. 執行: python create_rich_menus.py
3. 複製輸出的 Rich Menu ID
4. 在 Render 中更新 MAIN_RICH_MENU_ID
"""