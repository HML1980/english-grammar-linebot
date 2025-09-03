# -*- coding: utf-8 -*-
import os
import json
import requests

# --- 請填寫您的 Channel Access Token ---
CHANNEL_ACCESS_TOKEN = "5BvBNjyt6NrqujdHjczXYOSYvbF/WQIbhzsnrJKzcHqBoc2n12y34Ccc5IzOWRsKe/zqRtZuSprwjBlYR9PcPbO2PH/s8ZVsaBNMIXrU7GyAqpDSTrWaGbQbdg8vBd27ynXcqOKT8UfSC4r1gBwynwdB04t89/1O/w1cDnyilFU="
# ------------------------------------

# 【核心修正】確保 headers 字典中的值都是標準的字串型別，避免編碼錯誤
headers = {
    "Authorization": str(f"Bearer {CHANNEL_ACCESS_TOKEN}"),
    "Content-Type": str("application/json")
}

# --- 主選單 (Main Menu) 的設定 ---
main_menu_config = {
  "size": {"width": 2500, "height": 1686},
  "selected": True,
  "name": "MainMenu_v1", # 加上版本號，方便日後更新
  "chatBarText": "查看主選單",
  "areas": [
    # 數字按鈕 1-7
    {"bounds": {"x": 145, "y": 450, "width": 400, "height": 400}, "action": {"type": "postback", "data": "action=switch_to_chapter_menu&chapter_id=1"}},
    {"bounds": {"x": 585, "y": 450, "width": 400, "height": 400}, "action": {"type": "postback", "data": "action=switch_to_chapter_menu&chapter_id=2"}},
    {"bounds": {"x": 1025, "y": 450, "width": 400, "height": 400}, "action": {"type": "postback", "data": "action=switch_to_chapter_menu&chapter_id=3"}},
    {"bounds": {"x": 145, "y": 890, "width": 400, "height": 400}, "action": {"type": "postback", "data": "action=switch_to_chapter_menu&chapter_id=4"}},
    {"bounds": {"x": 585, "y": 890, "width": 400, "height": 400}, "action": {"type": "postback", "data": "action=switch_to_chapter_menu&chapter_id=5"}},
    {"bounds": {"x": 1025, "y": 890, "width": 400, "height": 400}, "action": {"type": "postback", "data": "action=switch_to_chapter_menu&chapter_id=6"}},
    {"bounds": {"x": 145, "y": 1330, "width": 1280, "height": 280}, "action": {"type": "postback", "data": "action=switch_to_chapter_menu&chapter_id=7"}},
    # 功能按鈕
    {"bounds": {"x": 1580, "y": 450, "width": 775, "height": 336}, "action": {"type": "postback", "data": "action=resume_reading"}},
    {"bounds": {"x": 1580, "y": 820, "width": 775, "height": 336}, "action": {"type": "postback", "data": "action=view_bookmarks"}},
    {"bounds": {"x": 1580, "y": 1190, "width": 775, "height": 336}, "action": {"type": "postback", "data": "action=view_analytics"}}
  ]
}

# --- 章節選單 (Chapter Menu) 的設定 ---
chapter_menu_config = {
  "size": {"width": 2500, "height": 1686},
  "selected": False,
  "name": "ChapterMenu_v1", # 加上版本號
  "chatBarText": "查看章節功能",
  "areas": [
    # 功能按鈕
    {"bounds": {"x": 100, "y": 400, "width": 733, "height": 900}, "action": {"type": "postback", "data": "action=read_chapter"}},
    {"bounds": {"x": 883, "y": 400, "width": 734, "height": 900}, "action": {"type": "postback", "data": "action=resume_chapter"}},
    {"bounds": {"x": 1667, "y": 400, "width": 733, "height": 900}, "action": {"type": "postback", "data": "action=do_quiz"}},
    # 底部頁籤
    {"bounds": {"x": 420, "y": 1450, "width": 800, "height": 236}, "action": {"type": "postback", "data": "action=switch_to_main_menu"}},
    # 回主選單按鈕 (左上角)
    {"bounds": {"x": 60, "y": 180, "width": 400, "height": 150}, "action": {"type": "postback", "data": "action=switch_to_main_menu"}}
  ]
}

def create_and_set_rich_menu(config, image_path, set_as_default=False):
    """一個通用的函式，用來建立、上傳並設定圖文選單"""
    
    # 1. 建立物件
    print(f">>> 1. 正在建立 {config['name']} 物件...")
    req = requests.post('https://api.line.me/v2/bot/richmenu', headers=headers, data=json.dumps(config))
    if req.status_code != 200:
        print(f"    [錯誤] 建立物件失敗: {req.status_code}\n{req.text}")
        return None
    rich_menu_id = req.json()['richMenuId']
    print(f"    [成功] 取得 ID: {rich_menu_id}")

    # 2. 上傳圖片
    print(f">>> 2. 正在為 {rich_menu_id} 上傳圖片...")
    with open(image_path, 'rb') as f:
        # 圖片上傳的 header 只需要 Authorization 和 Content-Type
        upload_headers = {
            "Authorization": str(f"Bearer {CHANNEL_ACCESS_TOKEN}"),
            "Content-Type": "image/png" # 假設您的圖片是 png 格式
        }
        req = requests.post(f'https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content', headers=upload_headers, data=f)
    if req.status_code != 200:
        print(f"    [錯誤] 上傳圖片失敗: {req.status_code}\n{req.text}")
        return None
    print("    [成功] 圖片已上傳")
    
    # 3. 設為預設 (如果需要)
    if set_as_default:
        print(f">>> 3. 正在將 {rich_menu_id} 設為預設...")
        req = requests.post(f'https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}', headers=headers)
        if req.status_code != 200:
            print(f"    [錯誤] 設定預設失敗: {req.status_code}\n{req.text}")
            return None
        print("    [成功] 已設為預設")
        
    return rich_menu_id

if __name__ == "__main__":
    if CHANNEL_ACCESS_TOKEN == "【5BvBNjyt6NrqujdHjczXYOSYvbF/WQIbhzsnrJKzcHqBoc2n12y34Ccc5IzOWRsKe/zqRtZuSprwjBlYR9PcPbO2PH/s8ZVsaBNMIXrU7GyAqpDSTrWaGbQbdg8vBd27ynXcqOKT8UfSC4r1gBwynwdB04t89/1O/w1cDnyilFU=":
        print("!!! 錯誤：請先在程式碼中填寫您的 Channel Access Token！")
    else:
        # 建立主選單並設為預設
        main_menu_id = create_and_set_rich_menu(main_menu_config, './images/rich_menu_main.png', set_as_default=True)
        if main_menu_id:
            print(f"\n主選單建立成功！ ID: {main_menu_id}")
        
        # 建立章節選單 (但不設為預設)
        chapter_menu_id = create_and_set_rich_menu(chapter_menu_config, './images/rich_menu_chapter.png')
        if chapter_menu_id:
            print(f"章節選單建立成功！ ID: {chapter_menu_id}")

        print("\n>>> 圖文選單設定完成！請將這兩個 ID 複製起來，我們稍後會在 app.py 中用到。")