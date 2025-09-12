#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import os
import sys
from datetime import datetime

DATABASE_NAME = 'linebot.db'

def create_database():
    """建立完整的資料庫結構"""
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        print(f"建立資料庫: {DATABASE_NAME}")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT UNIQUE NOT NULL,
                display_name TEXT,
                current_chapter_id INTEGER,
                current_section_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_date DATE DEFAULT CURRENT_DATE,
                total_users INTEGER DEFAULT 0,
                active_users INTEGER DEFAULT 0,
                total_interactions INTEGER DEFAULT 0,
                quiz_attempts INTEGER DEFAULT 0,
                bookmarks_added INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        print("建立索引...")
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_user_id ON user_actions(line_user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_actions_timestamp ON user_actions(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(line_user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookmarks_chapter ON bookmarks(chapter_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_id ON quiz_attempts(line_user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quiz_attempts_chapter ON quiz_attempts(chapter_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quiz_attempts_correct ON quiz_attempts(is_correct)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_system_stats_date ON system_stats(stat_date)')
        
        conn.commit()
        print("✅ 資料庫表格和索引建立完成")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ 資料庫建立失敗: {e}")
        return False
    finally:
        if conn:
            conn.close()

def drop_database():
    """刪除資料庫檔案"""
    if os.path.exists(DATABASE_NAME):
        try:
            os.remove(DATABASE_NAME)
            print(f"✅ 資料庫檔案 {DATABASE_NAME} 已刪除")
            return True
        except Exception as e:
            print(f"❌ 刪除資料庫檔案失敗: {e}")
            return False
    else:
        print(f"資料庫檔案 {DATABASE_NAME} 不存在")
        return True

def reset_database():
    """重設資料庫（刪除後重新建立）"""
    print("重設資料庫...")
    if drop_database():
        return create_database()
    return False

def show_database_info():
    """顯示資料庫資訊"""
    if not os.path.exists(DATABASE_NAME):
        print(f"❌ 資料庫檔案 {DATABASE_NAME} 不存在")
        return False
    
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        print(f"📊 資料庫資訊: {DATABASE_NAME}")
        print("=" * 50)
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        
        print(f"表格數量: {len(tables)}")
        print("表格列表:")
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  - {table_name}: {count} 筆記錄")
        
        print("\n📈 使用者統計:")
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        print(f"  總使用者數: {total_users}")
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE last_active >= date('now', '-7 days')")
        active_users = cursor.fetchone()[0]
        print(f"  週活躍使用者: {active_users}")
        
        cursor.execute("SELECT COUNT(*) FROM quiz_attempts")
        total_quizzes = cursor.fetchone()[0]
        print(f"  總測驗次數: {total_quizzes}")
        
        if total_quizzes > 0:
            cursor.execute("SELECT COUNT(*) FROM quiz_attempts WHERE is_correct = 1")
            correct_answers = cursor.fetchone()[0]
            accuracy = (correct_answers / total_quizzes) * 100
            print(f"  整體正確率: {accuracy:.1f}%")
        
        cursor.execute("SELECT COUNT(*) FROM bookmarks")
        total_bookmarks = cursor.fetchone()[0]
        print(f"  總書籤數: {total_bookmarks}")
        
        print(f"\n📁 檔案大小: {os.path.getsize(DATABASE_NAME)} bytes")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ 查詢資料庫資訊失敗: {e}")
        return False
    finally:
        if conn:
            conn.close()

def cleanup_old_data():
    """清理舊資料"""
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        print("🧹 清理舊資料...")
        
        cursor.execute("DELETE FROM user_actions WHERE timestamp < ?", (datetime.now().timestamp() - 86400,))
        old_actions = cursor.rowcount
        
        cursor.execute("DELETE FROM users WHERE last_active < date('now', '-90 days')")
        inactive_users = cursor.rowcount
        
        cursor.execute("VACUUM")
        
        conn.commit()
        
        print(f"✅ 清理完成:")
        print(f"  刪除舊操作記錄: {old_actions} 筆")
        print(f"  刪除非活躍使用者: {inactive_users} 筆")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ 清理資料失敗: {e}")
        return False
    finally:
        if conn:
            conn.close()

def test_database():
    """測試資料庫連接和基本操作"""
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        
        print("🔧 測試資料庫連接...")
        
        test_user_id = "test_user_123"
        
        cursor.execute(
            "INSERT OR REPLACE INTO users (line_user_id, display_name) VALUES (?, ?)",
            (test_user_id, "Test User")
        )
        
        cursor.execute("SELECT * FROM users WHERE line_user_id = ?", (test_user_id,))
        result = cursor.fetchone()
        
        if result:
            print("✅ 資料庫寫入測試成功")
            
            cursor.execute("DELETE FROM users WHERE line_user_id = ?", (test_user_id,))
            print("✅ 資料庫刪除測試成功")
            
            conn.commit()
            return True
        else:
            print("❌ 資料庫讀取測試失敗")
            return False
            
    except sqlite3.Error as e:
        print(f"❌ 資料庫測試失敗: {e}")
        return False
    finally:
        if conn:
            conn.close()

def backup_database(backup_path=None):
    """備份資料庫"""
    if not os.path.exists(DATABASE_NAME):
        print(f"❌ 資料庫檔案 {DATABASE_NAME} 不存在")
        return False
    
    if backup_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{DATABASE_NAME}.backup_{timestamp}"
    
    try:
        import shutil
        shutil.copy2(DATABASE_NAME, backup_path)
        print(f"✅ 資料庫備份完成: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ 備份失敗: {e}")
        return False

def main():
    """主程式"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python init_db.py create     - 建立資料庫")
        print("  python init_db.py reset      - 重設資料庫")
        print("  python init_db.py info       - 顯示資料庫資訊")
        print("  python init_db.py cleanup    - 清理舊資料")
        print("  python init_db.py test       - 測試資料庫")
        print("  python init_db.py backup     - 備份資料庫")
        print("  python init_db.py drop       - 刪除資料庫")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "create":
        if create_database():
            test_database()
    elif command == "reset":
        confirm = input("確定要重設資料庫嗎？所有資料將被刪除 (y/N): ")
        if confirm.lower() in ['y', 'yes']:
            reset_database()
    elif command == "info":
        show_database_info()
    elif command == "cleanup":
        cleanup_old_data()
    elif command == "test":
        test_database()
    elif command == "backup":
        backup_database()
    elif command == "drop":
        confirm = input("確定要刪除資料庫嗎？所有資料將被清除 (y/N): ")
        if confirm.lower() in ['y', 'yes']:
            drop_database()
    else:
        print(f"❌ 未知指令: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()