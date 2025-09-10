#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ast
import os
import sys

def check_app():
    print("🔍 檢查 app.py 檔案...")
    
    if not os.path.exists('app.py'):
        print("❌ 找不到 app.py 檔案")
        return False
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 1. 語法檢查
        try:
            ast.parse(content)
            print("✅ Python 語法正確")
        except SyntaxError as e:
            print(f"❌ 語法錯誤 第{e.lineno}行: {e.msg}")
            return False
        
        # 2. 檢查關鍵函數
        required_functions = [
            'handle_message', 'handle_navigation', 'handle_start_reading',
            'handle_show_chapter_carousel', 'handle_bookmarks',
            'handle_resume_reading', 'handle_chapter_quiz',
            'handle_error_analytics', 'handle_quick_navigation'
        ]
        
        tree = ast.parse(content)
        defined_functions = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                defined_functions.add(node.name)
        
        missing_functions = []
        for func in required_functions:
            if func not in defined_functions:
                missing_functions.append(func)
        
        if missing_functions:
            print(f"❌ 缺少函數: {', '.join(missing_functions)}")
            return False
        else:
            print("✅ 所有必要函數都存在")
        
        # 3. 檢查導入
        required_imports = ['Flask', 'sqlite3', 'json', 'os', 'time']
        for imp in required_imports:
            if imp not in content:
                print(f"⚠️  可能缺少導入: {imp}")
        
        print("✅ 基本檢查完成")
        return True
        
    except Exception as e:
        print(f"❌ 檢查過程中出錯: {e}")
        return False

if __name__ == "__main__":
    check_app()
