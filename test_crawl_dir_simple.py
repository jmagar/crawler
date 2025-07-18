#!/usr/bin/env python3
"""
Simple test for crawl_dir core logic without external dependencies.
"""
import os
import tempfile
import sys
from pathlib import Path

# Test the file detection and exclusion logic without imports
def is_text_file_simple(file_path: str) -> bool:
    """Simple version of text file detection."""
    text_extensions = {
        '.txt', '.md', '.markdown', '.rst', '.py', '.js', '.html', '.htm', 
        '.css', '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg',
        '.sh', '.bash', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.php', 
        '.rb', '.go', '.rs', '.swift', '.kt', '.ts', '.tsx', '.jsx'
    }
    
    file_ext = Path(file_path).suffix.lower()
    return file_ext in text_extensions

def should_exclude_path_simple(path: Path, exclude_patterns: list) -> bool:
    """Simple version of path exclusion."""
    path_str = str(path)
    path_name = path.name
    
    default_excludes = {
        '.git', '.svn', '__pycache__', 'node_modules', '.next', 
        'dist', 'build', '.venv', 'venv', '.DS_Store'
    }
    
    if path_name in default_excludes:
        return True
    
    for pattern in exclude_patterns:
        if pattern in path_str or pattern in path_name:
            return True
    
    return False

def test_file_detection():
    """Test file detection logic."""
    print("🧪 Testing file detection...")
    
    test_cases = [
        ("test.py", True),
        ("test.md", True), 
        ("test.txt", True),
        ("test.json", True),
        ("image.jpg", False),
        ("binary.exe", False),
        ("script.sh", True),
        ("config.yaml", True),
    ]
    
    for filename, expected in test_cases:
        result = is_text_file_simple(filename)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {filename}: {result}")

def test_exclusion_logic():
    """Test exclusion logic."""
    print("🧪 Testing exclusion logic...")
    
    test_cases = [
        (Path("/test/.git/config"), [".git"], True),
        (Path("/test/node_modules/pkg"), ["node_modules"], True),
        (Path("/test/src/main.py"), [".git"], False),
        (Path("/test/__pycache__/cache.pyc"), [], True),
        (Path("/test/regular.py"), ["custom"], False),
    ]
    
    for path, patterns, expected in test_cases:
        result = should_exclude_path_simple(path, patterns)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {path.name}: {result}")

def test_directory_scanning():
    """Test directory scanning without full crawling."""
    print("🧪 Testing directory scanning...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test files
        (temp_path / "test.py").write_text("print('hello')")
        (temp_path / "readme.md").write_text("# Test")
        (temp_path / "data.txt").write_text("some data")
        (temp_path / "image.jpg").write_bytes(b"fake image")
        
        # Create subdirectory
        subdir = temp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.json").write_text('{"test": true}')
        
        # Scan directory
        text_files = []
        excluded_files = []
        
        for file_path in temp_path.rglob('*'):
            if not file_path.is_file():
                continue
                
            if should_exclude_path_simple(file_path, []):
                excluded_files.append(file_path.name)
            elif is_text_file_simple(str(file_path)):
                text_files.append(file_path.name)
        
        print(f"  📄 Text files found: {text_files}")
        print(f"  🚫 Excluded files: {excluded_files}")
        
        # Verify we found the expected files
        expected_text = {"test.py", "readme.md", "data.txt", "nested.json"}
        found_text = set(text_files)
        
        if expected_text == found_text:
            print("  ✅ Directory scanning works correctly")
        else:
            print(f"  ❌ Expected {expected_text}, found {found_text}")

def main():
    """Run simple tests."""
    print("🚀 Running simple crawl_dir tests...\n")
    
    test_file_detection()
    print()
    test_exclusion_logic()
    print()
    test_directory_scanning()
    
    print("\n✅ Simple tests completed!")

if __name__ == "__main__":
    main()