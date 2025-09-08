# -*- coding: utf-8 -*-
"""
單一圖文選單建立腳本
根據您的圖片設計建立包含所有功能的統一選單
"""
import os
import json
import requests
import time

# --- 請填寫您的 Channel Access Token ---
CHANNEL_ACCESS_TOKEN = "請填入您的_CHANNEL_ACCESS_TOKEN"  # 請填入你的 Token
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

# --- 統一圖文選單設定 ---
# 根據您提供的圖片設計，包含所有功能區域
unified_menu_config = {
    "size": {"width": 1330, "height": 843},
    "selected": True,
    "name": "UnifiedGrammarMenu_v1",
    "chatBarText": "五分鐘英文文法攻略",
    "areas": [
        # === 第一排功能按鈕 ===
        # 閱讀內容（左上藍色區域）
        {
            "bounds": {"x": 20, "y": 105, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=read_content"}
        },
        
        # 章節選擇（中上綠色區域）
        {
            "bounds": {"x": 449, "y": 105, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=show_chapter_menu"}
        },
        
        # 我的書籤（右上藍色區域）
        {
            "bounds": {"x": 878, "y": 105, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=view_bookmarks"}
        },
        
        # === 第二排功能按鈕 ===
        # 上次進度（左中綠色區域）
        {
            "bounds": {"x": 20, "y": 200, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=continue_reading"}
        },
        
        # 本章測驗題（中中藍色區域）
        {
            "bounds": {"x": 449, "y": 200, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=chapter_quiz"}
        },
        
        # 錯誤分析（右中綠色區域）
        {
            "bounds": {"x": 878, "y": 200, "width": 432, "height": 170}, 
            "action": {"type": "postback", "data": "action=view_analytics"}
        },
        
        # === 數字章節選擇區域（第三排）===
        # 根據圖片設計，數字按鈕位於底部，排成一列
        
        # 第1章（最左）
        {"bounds": {"x": 20, "y": 390, "width": 185, "height": 70}, 
         "action": {"type": "postback", "data": "1"}},
        
        # 第2章
        {"bounds": {"x": 210, "y": 390, "width": 185, "height": 70}, 
         "action": {"type": "postback", "data": "2"}},
        
        # 第3章
        {"bounds": {"x": 400, "y": 390, "width": 185, "height": 70}, 
         "action": {"type": "postback", "data": "3"}},
        
        # 第4章
        {"bounds": {"x": 590, "y": 390, "width": 185, "height": 70}, 
         "action": {"type": "postback", "data": "4"}},
        
        # 第5章
        {"bounds": {"x": 780, "y": 390, "width": 185, "height": 70}, 
         "action": {"type": "postback", "data": "5"}},
        
        # 第6章
        {"bounds": {"x": 970, "y": 390, "width": 160, "height": 70}, 
         "action": {"type": "postback", "data": "6"}},
        
        # 第7章
        {"bounds": {"x": 1135, "y": 390, "width": 160, "height": 70}, 
         "action": {"type": "postback", "data": "7"}}
    ]
}

def validate_token():
    """驗證 Channel Access Token 是否有效"""
    if "請填入您的_CHANNEL_ACCESS_TOKEN" in CHANNEL_ACCESS_TOKEN:
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

def create_rich_menu(config, image_path, set_as_default=True):
    """建立、上傳並設定圖文選單"""
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
        
        # 3. 設為預設
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

def create_sample_coordinates_guide():
    """建立座標調整指南"""
    guide = """
📐 座標調整指南

如果圖文選單按鈕位置不正確，請調整 bounds 中的座標：

格式：{"x": 左邊距離, "y": 上邊距離, "width": 寬度, "height": 高度}

根據您的圖片設計：
- 圖片總尺寸：1330 x 843
- 第一排功能按鈕：y=105, height=170
- 第二排功能按鈕：y=200, height=170  
- 數字章節按鈕：y=390, height=70

調整方式：
- 如果按鈕太靠左，增加 x 值
- 如果按鈕太靠右，減少 x 值
- 如果按鈕太靠上，增加 y 值
- 如果按鈕太靠下，減少 y 值
- 如果按鈕太小，增加 width 和 height
- 如果按鈕太大，減少 width 和 height

建議：先測試中間的按鈕是否對準，再調整其他按鈕。
"""
    return guide

def main():
    """主程式"""
    print("🚀 統一圖文選單建立程式啟動")
    print("=" * 60)
    print("📝 功能說明：")
    print("   • 閱讀內容：從頭開始閱讀當前章節")
    print("   • 章節選擇：顯示章節輪播選單")
    print("   • 我的書籤：查看收藏的重要段落")
    print("   • 上次進度：跳到上次閱讀位置")
    print("   • 本章測驗題：開始當前章節測驗")
    print("   • 錯誤分析：檢視答錯的題目統計")
    print("   • 數字 1-7：直接選擇對應章節")
    print("=" * 60)
    
    # 驗證 Token
    if not validate_token():
        return
    
    print("✅ Channel Access Token 格式檢查通過")
    
    # 定義圖片路徑
    image_path = './images/unified_rich_menu.png'
    
    # 檢查圖片檔案
    if not check_file_exists(image_path):
        print("\n❌ 請確保圖片檔案存在：")
        print("  - ./images/unified_rich_menu.png    (統一圖文選單圖片)")
        print("\n💡 圖片設計要求：")
        print("  - 尺寸：1330 x 843 像素")
        print("  - 格式：PNG")
        print("  - 大小：小於 1MB")
        print("  - 包含所有功能區域的設計")
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
    
    print("\n" + "=" * 60)
    print("📋 開始建立統一圖文選單...")
    
    # 建立統一圖文選單
    menu_id = create_rich_menu(
        config=unified_menu_config, 
        image_path=image_path, 
        set_as_default=True
    )
    
    # 總結結果
    print("\n" + "=" * 60)
    
    if menu_id:
        print("🎉 統一圖文選單建立完成！")
        
        print("\n🔧 請將此 ID 更新到 Render 的環境變數：")
        print(f"MAIN_RICH_MENU_ID: {menu_id}")
        
        print("\n💡 Render 環境變數更新步驟：")
        print("1. 登入 Render Dashboard")
        print("2. 選擇您的服