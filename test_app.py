#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試 app.py 是否可以正常導入和運行
"""
import os
import sys

def test_app_syntax():
    """測試 app.py 語法"""
    print("1. 檢查 app.py 語法...")
    try:
        import py_compile
        py_compile.compile('app.py', doraise=True)
        print("✅ 語法檢查通過")
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ 語法錯誤: {e}")
        return False

def test_app_import():
    """測試 app.py 是否可以導入"""
    print("\n2. 測試模組導入...")
    
    # 設置測試用環境變數
    os.environ['CHANNEL_SECRET'] = 'test_secret_12345678901234567890123456789012'
    os.environ['CHANNEL_ACCESS_TOKEN'] = 'test_token_12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234'
    os.environ['MAIN_RICH_MENU_ID'] = 'richmenu-test123456789012345'
    
    try:
        # 暫時重定向 stdout 來避免 app.py 的 print 輸出
        from io import StringIO
        import contextlib
        
        f = StringIO()
        with contextlib.redirect_stdout(f):
            import app
        
        print("✅ 模組導入成功")
        return True
    except ImportError as e:
        print(f"❌ 導入錯誤: {e}")
        return False
    except Exception as e:
        print(f"❌ 其他錯誤: {e}")
        return False

def test_dependencies():
    """測試依賴套件"""
    print("\n3. 檢查依賴套件...")
    
    dependencies = [
        ('flask', 'Flask'),
        ('linebot.v3', 'WebhookHandler'),
        ('requests', None),
        ('sqlite3', None)
    ]
    
    all_ok = True
    for module, item in dependencies:
        try:
            if item:
                exec(f"from {module} import {item}")
            else:
                exec(f"import {module}")
            print(f"✅ {module} 可用")
        except ImportError as e:
            print(f"❌ {module} 缺失: {e}")
            all_ok = False
    
    return all_ok

def test_book_json():
    """測試 book.json 是否存在且格式正確"""
    print("\n4. 檢查 book.json...")
    
    if not os.path.exists('book.json'):
        print("❌ book.json 不存在")
        return False
    
    try:
        import json
        with open('book.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 'chapters' not in data:
            print("❌ book.json 格式錯誤：缺少 chapters")
            return False
        
        chapters = data['chapters']
        print(f"✅ book.json 格式正確，包含 {len(chapters)} 個章節")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ book.json JSON 格式錯誤: {e}")
        return False
    except Exception as e:
        print(f"❌ 讀取 book.json 錯誤: {e}")
        return False

def test_database():
    """測試資料庫功能"""
    print("\n5. 測試資料庫功能...")
    
    try:
        import sqlite3
        conn = sqlite3.connect(':memory:')  # 使用記憶體資料庫測試
        cursor = conn.cursor()
        
        # 測試建立表格
        cursor.execute('''
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        ''')
        
        # 測試插入資料
        cursor.execute("INSERT INTO test_table (name) VALUES (?)", ("test",))
        
        # 測試查詢資料
        cursor.execute("SELECT * FROM test_table")
        result = cursor.fetchone()
        
        conn.close()
        
        if result and result[1] == "test":
            print("✅ 資料庫功能正常")
            return True
        else:
            print("❌ 資料庫測試失敗")
            return False
            
    except Exception as e:
        print(f"❌ 資料庫測試錯誤: {e}")
        return False

def main():
    print("🔧 LINE Bot App 整合測試")
    print("=" * 50)
    
    tests = [
        test_app_syntax,
        test_dependencies, 
        test_book_json,
        test_database,
        test_app_import,
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        if test_func():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 測試結果: {passed}/{total} 通過")
    
    if passed == total:
        print("🎉 所有測試通過！app.py 準備就緒")
        return True
    else:
        print("⚠️  部分測試失敗，請檢查上述錯誤")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)