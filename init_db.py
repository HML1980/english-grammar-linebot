# -*- coding: utf-8 -*-
import sqlite3

# 資料庫檔案的名稱
DATABASE_NAME = 'linebot.db'

# 連接到資料庫 (如果檔案不存在，它會自動被建立)
connection = sqlite3.connect(DATABASE_NAME)

# 建立一個 cursor 物件，用來執行 SQL 指令
cursor = connection.cursor()

# --- 建立 users 資料表 ---
# 用來儲存使用者的基本資料和閱讀進度
# IF NOT EXISTS 可以確保如果資料表已存在，就不會重複建立而出錯
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    line_user_id TEXT PRIMARY KEY,
    display_name TEXT,
    current_chapter_id INTEGER,
    current_section_id INTEGER,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')
print("資料表 'users' 建立成功或已存在。")

# --- 建立 quiz_attempts 資料表 ---
# 用來記錄每一次的答題結果
cursor.execute('''
CREATE TABLE IF NOT EXISTS quiz_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_user_id TEXT NOT NULL,
    chapter_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    user_answer TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (line_user_id) REFERENCES users (line_user_id)
)
''')
print("資料表 'quiz_attempts' 建立成功或已存在。")

# --- 建立 bookmarks 資料表 ---
# 用來儲存使用者標記的段落
cursor.execute('''
CREATE TABLE IF NOT EXISTS bookmarks (
    bookmark_id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_user_id TEXT NOT NULL,
    chapter_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (line_user_id) REFERENCES users (line_user_id)
)
''')
print("資料表 'bookmarks' 建立成功或已存在。")


# 提交變更到資料庫
connection.commit()

# 關閉資料庫連線
connection.close()

print(f"資料庫 '{DATABASE_NAME}' 初始化完成！")