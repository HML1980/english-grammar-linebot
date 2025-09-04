# book.json 驗證和改進腳本

import json
import requests
from urllib.parse import urlparse

def validate_book_json(book_data):
    """驗證 book.json 的結構和內容"""
    issues = []
    suggestions = []
    
    # 1. 檢查基本結構
    if 'chapters' not in book_data:
        issues.append("缺少 'chapters' 根節點")
        return issues, suggestions
    
    chapters = book_data['chapters']
    print(f"📚 發現 {len(chapters)} 個章節")
    
    # 2. 檢查每個章節
    for i, chapter in enumerate(chapters):
        chapter_num = i + 1
        print(f"\n🔍 檢查第 {chapter_num} 章...")
        
        # 檢查必要字段
        required_fields = ['chapter_id', 'title', 'image_url', 'sections']
        for field in required_fields:
            if field not in chapter:
                issues.append(f"第 {chapter_num} 章缺少 '{field}' 字段")
        
        # 檢查 chapter_id 一致性
        if chapter.get('chapter_id') != chapter_num:
            issues.append(f"第 {chapter_num} 章的 chapter_id 不匹配")
        
        # 檢查段落結構
        sections = chapter.get('sections', [])
        content_count = 0
        quiz_count = 0
        
        for section in sections:
            if section.get('type') == 'content':
                content_count += 1
            elif section.get('type') == 'quiz':
                quiz_count += 1
                
                # 檢查測驗題結構
                content = section.get('content', {})
                if not all(key in content for key in ['question', 'options', 'answer']):
                    issues.append(f"第 {chapter_num} 章第 {section.get('section_id')} 段測驗結構不完整")
        
        print(f"   📝 內容段落: {content_count}")
        print(f"   ❓ 測驗題目: {quiz_count}")
        
        # 建議優化長內容
        for section in sections:
            if section.get('type') == 'content':
                content_length = len(section.get('content', ''))
                if content_length > 800:
                    suggestions.append(f"第 {chapter_num} 章第 {section.get('section_id')} 段內容較長 ({content_length} 字符)，建議分段")
    
    return issues, suggestions

def check_image_urls(book_data):
    """檢查圖片 URL 可訪問性"""
    print("\n🖼️ 檢查圖片 URL...")
    
    for chapter in book_data.get('chapters', []):
        image_url = chapter.get('image_url', '')
        if image_url:
            try:
                response = requests.head(image_url, timeout=5)
                if response.status_code == 200:
                    print(f"✅ 第 {chapter.get('chapter_id')} 章圖片正常")
                else:
                    print(f"❌ 第 {chapter.get('chapter_id')} 章圖片無法訪問 (HTTP {response.status_code})")
            except requests.RequestException as e:
                print(f"⚠️ 第 {chapter.get('chapter_id')} 章圖片檢查失敗: {str(e)[:50]}...")

def generate_content_statistics(book_data):
    """生成內容統計"""
    stats = {
        'total_chapters': len(book_data.get('chapters', [])),
        'total_sections': 0,
        'content_sections': 0,
        'quiz_sections': 0,
        'chapter_details': []
    }
    
    for chapter in book_data.get('chapters', []):
        sections = chapter.get('sections', [])
        content_count = sum(1 for s in sections if s.get('type') == 'content')
        quiz_count = sum(1 for s in sections if s.get('type') == 'quiz')
        
        stats['total_sections'] += len(sections)
        stats['content_sections'] += content_count
        stats['quiz_sections'] += quiz_count
        
        stats['chapter_details'].append({
            'chapter_id': chapter.get('chapter_id'),
            'title': chapter.get('title'),
            'total_sections': len(sections),
            'content_sections': content_count,
            'quiz_sections': quiz_count
        })
    
    return stats

def suggest_improvements(book_data):
    """提供改進建議"""
    suggestions = []
    
    # 1. 內容一致性建議
    for chapter in book_data.get('chapters', []):
        sections = chapter.get('sections', [])
        quiz_sections = [s for s in sections if s.get('type') == 'quiz']
        
        if len(quiz_sections) != 15:
            suggestions.append(f"建議第 {chapter.get('chapter_id')} 章保持 15 題測驗的一致性")
    
    # 2. 內容品質建議
    suggestions.extend([
        "建議在每個章節開始添加學習目標",
        "考慮在複雜文法點後添加更多範例",
        "建議添加章節總結或重點回顧",
        "可以考慮添加音頻發音功能",
        "建議添加難度標記 (初級/中級/高級)",
    ])
    
    return suggestions

# 示例用法
if __name__ == "__main__":
    # 假設已載入 book_data
    print("📖 book.json 驗證與改進建議")
    print("=" * 50)
    
    # 這裡應該載入您的 book.json 資料
    # with open('book.json', 'r', encoding='utf-8') as f:
    #     book_data = json.load(f)
    
    # issues, suggestions = validate_book_json(book_data)
    # stats = generate_content_statistics(book_data)
    # improvements = suggest_improvements(book_data)
    
    print("✅ 驗證完成！")