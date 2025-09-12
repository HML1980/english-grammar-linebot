#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import re
from urllib.parse import urlparse

class BookValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        
    def validate_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def validate_chapter(self, chapter, chapter_index):
        chapter_errors = []
        
        if not isinstance(chapter, dict):
            chapter_errors.append(f"Chapter {chapter_index + 1} must be a dictionary")
            return chapter_errors
        
        required_fields = ['chapter_id', 'title', 'sections']
        for field in required_fields:
            if field not in chapter:
                chapter_errors.append(f"Chapter {chapter_index + 1}: Missing required field '{field}'")
        
        if 'chapter_id' in chapter:
            if not isinstance(chapter['chapter_id'], int):
                chapter_errors.append(f"Chapter {chapter_index + 1}: chapter_id must be integer")
            elif chapter['chapter_id'] != chapter_index + 1:
                chapter_errors.append(f"Chapter {chapter_index + 1}: chapter_id should be {chapter_index + 1}, got {chapter['chapter_id']}")
        
        if 'title' in chapter:
            if not isinstance(chapter['title'], str) or not chapter['title'].strip():
                chapter_errors.append(f"Chapter {chapter_index + 1}: title must be non-empty string")
        
        if 'image_url' in chapter:
            if not self.validate_url(chapter['image_url']):
                chapter_errors.append(f"Chapter {chapter_index + 1}: Invalid image_url format")
        
        if 'sections' in chapter:
            if not isinstance(chapter['sections'], list):
                chapter_errors.append(f"Chapter {chapter_index + 1}: sections must be a list")
            else:
                chapter_errors.extend(self.validate_sections(chapter['sections'], chapter_index + 1))
        
        return chapter_errors
    
    def validate_sections(self, sections, chapter_id):
        section_errors = []
        section_ids = set()
        content_count = 0
        quiz_count = 0
        
        for section_index, section in enumerate(sections):
            if not isinstance(section, dict):
                section_errors.append(f"Chapter {chapter_id}, Section {section_index + 1}: Must be a dictionary")
                continue
            
            required_fields = ['section_id', 'type', 'content']
            for field in required_fields:
                if field not in section:
                    section_errors.append(f"Chapter {chapter_id}, Section {section_index + 1}: Missing required field '{field}'")
            
            if 'section_id' in section:
                if not isinstance(section['section_id'], int):
                    section_errors.append(f"Chapter {chapter_id}, Section {section_index + 1}: section_id must be integer")
                elif section['section_id'] in section_ids:
                    section_errors.append(f"Chapter {chapter_id}: Duplicate section_id {section['section_id']}")
                else:
                    section_ids.add(section['section_id'])
            
            if 'type' in section:
                if section['type'] not in ['content', 'quiz']:
                    section_errors.append(f"Chapter {chapter_id}, Section {section['section_id']}: type must be 'content' or 'quiz'")
                elif section['type'] == 'content':
                    content_count += 1
                    section_errors.extend(self.validate_content_section(section, chapter_id))
                elif section['type'] == 'quiz':
                    quiz_count += 1
                    section_errors.extend(self.validate_quiz_section(section, chapter_id))
        
        if content_count == 0:
            self.warnings.append(f"Chapter {chapter_id}: No content sections found")
        
        if quiz_count == 0:
            self.warnings.append(f"Chapter {chapter_id}: No quiz sections found")
        
        return section_errors
    
    def validate_content_section(self, section, chapter_id):
        errors = []
        section_id = section.get('section_id', 'Unknown')
        
        if 'content' not in section:
            return errors
        
        content = section['content']
        if not isinstance(content, str) or not content.strip():
            errors.append(f"Chapter {chapter_id}, Section {section_id}: Content must be non-empty string")
        elif len(content) < 10:
            self.warnings.append(f"Chapter {chapter_id}, Section {section_id}: Content is very short ({len(content)} chars)")
        elif len(content) > 5000:
            self.warnings.append(f"Chapter {chapter_id}, Section {section_id}: Content is very long ({len(content)} chars)")
        
        return errors
    
    def validate_quiz_section(self, section, chapter_id):
        errors = []
        section_id = section.get('section_id', 'Unknown')
        
        if 'content' not in section:
            return errors
        
        content = section['content']
        if not isinstance(content, dict):
            errors.append(f"Chapter {chapter_id}, Section {section_id}: Quiz content must be a dictionary")
            return errors
        
        required_quiz_fields = ['question', 'options', 'answer']
        for field in required_quiz_fields:
            if field not in content:
                errors.append(f"Chapter {chapter_id}, Section {section_id}: Missing quiz field '{field}'")
        
        if 'question' in content:
            if not isinstance(content['question'], str) or not content['question'].strip():
                errors.append(f"Chapter {chapter_id}, Section {section_id}: Question must be non-empty string")
        
        if 'options' in content:
            if not isinstance(content['options'], dict):
                errors.append(f"Chapter {chapter_id}, Section {section_id}: Options must be a dictionary")
            else:
                if len(content['options']) < 2:
                    errors.append(f"Chapter {chapter_id}, Section {section_id}: Must have at least 2 options")
                
                for key, value in content['options'].items():
                    if not isinstance(key, str) or not isinstance(value, str):
                        errors.append(f"Chapter {chapter_id}, Section {section_id}: Option keys and values must be strings")
                    elif not value.strip():
                        errors.append(f"Chapter {chapter_id}, Section {section_id}: Option '{key}' is empty")
        
        if 'answer' in content and 'options' in content:
            if content['answer'] not in content['options']:
                errors.append(f"Chapter {chapter_id}, Section {section_id}: Answer '{content['answer']}' not found in options")
        
        return errors
    
    def validate_book_structure(self, data):
        if not isinstance(data, dict):
            self.errors.append("Root element must be a dictionary")
            return False
        
        if 'chapters' not in data:
            self.errors.append("Missing 'chapters' field in root")
            return False
        
        if not isinstance(data['chapters'], list):
            self.errors.append("'chapters' must be a list")
            return False
        
        if len(data['chapters']) == 0:
            self.errors.append("No chapters found")
            return False
        
        return True
    
    def validate(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.errors.append(f"File not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON format: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error reading file: {e}")
            return False
        
        if not self.validate_book_structure(data):
            return False
        
        chapters = data['chapters']
        for chapter_index, chapter in enumerate(chapters):
            chapter_errors = self.validate_chapter(chapter, chapter_index)
            self.errors.extend(chapter_errors)
        
        return len(self.errors) == 0
    
    def print_results(self):
        if self.errors:
            print("❌ VALIDATION FAILED")
            print(f"\nFound {len(self.errors)} error(s):")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        else:
            print("✅ VALIDATION PASSED")
        
        if self.warnings:
            print(f"\n⚠️  Found {len(self.warnings)} warning(s):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        print(f"\nValidation Summary:")
        print(f"  Errors: {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")
        
        return len(self.errors) == 0

def main():
    if len(sys.argv) != 2:
        print("Usage: python validate_book.py <book.json>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    validator = BookValidator()
    
    print(f"Validating {file_path}...")
    print("=" * 50)
    
    is_valid = validator.validate(file_path)
    validator.print_results()
    
    sys.exit(0 if is_valid else 1)

if __name__ == "__main__":
    main()