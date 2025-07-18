#!/usr/bin/env python3
"""
Test script for the new crawl_dir functionality.
Tests directory crawling, chunking, and validation components.
"""
import asyncio
import os
import tempfile
import shutil
import sys
from pathlib import Path

# Add src to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.crawling import crawl_directory, convert_directory_content_to_crawl_results, is_text_file, should_exclude_path
from src.core.validation import validate_directory_path, validate_crawl_dir_params
from src.core.processing import smart_chunk_markdown

async def test_directory_crawling():
    """Test the basic directory crawling functionality."""
    print("🧪 Testing directory crawling functionality...")
    
    # Create a temporary directory with test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test files
        (temp_path / "test1.py").write_text("""
def hello_world():
    '''A simple function that greets the world.'''
    return "Hello, World!"

class TestClass:
    def __init__(self):
        self.message = "Test message"
        
    def get_message(self):
        return self.message
""")
        
        (temp_path / "test2.md").write_text("""
# Test Document

This is a test markdown document for testing directory crawling.

## Features

- Directory scanning
- File content extraction
- Metadata generation

## Code Example

```python
def example():
    return "This is an example"
```

## Conclusion

This test should work properly.
""")
        
        (temp_path / "test3.txt").write_text("This is a simple text file for testing.")
        
        # Create a subdirectory
        subdir = temp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.json").write_text('{"name": "test", "value": 42}')
        
        # Create files that should be excluded
        (temp_path / "binary.exe").write_bytes(b'\x00\x01\x02\x03')
        (temp_path / ".DS_Store").write_text("system file")
        
        print(f"📁 Created test directory: {temp_dir}")
        
        # Test directory crawling
        try:
            results = await crawl_directory(
                directory_path=temp_dir,
                max_files=100,
                max_file_size=1024*1024,
                exclude_patterns=['.DS_Store']
            )
            
            print(f"✅ Successfully crawled {len(results)} files")
            
            for file_path, content, metadata in results:
                rel_path = Path(file_path).relative_to(temp_path)
                print(f"  📄 {rel_path}: {metadata['word_count']} words, {metadata['char_count']} chars")
            
            # Test conversion to crawl results
            crawl_results = await convert_directory_content_to_crawl_results(results)
            print(f"✅ Converted to {len(crawl_results)} crawl results")
            
            # Test chunking
            for result in crawl_results[:2]:  # Test first 2 files
                chunks = smart_chunk_markdown(result.markdown, chunk_size=500, strategy="smart")
                print(f"  🧩 {result.url}: {len(chunks)} chunks")
            
            return True
            
        except Exception as e:
            print(f"❌ Directory crawling test failed: {e}")
            return False

def test_text_file_detection():
    """Test the text file detection logic."""
    print("🧪 Testing text file detection...")
    
    test_cases = [
        ("test.py", True),
        ("test.md", True),
        ("test.txt", True),
        ("test.json", True),
        ("test.html", True),
        ("test.css", True),
        ("script.sh", True),
        ("config.yaml", True),
        ("image.jpg", False),
        ("binary.exe", False),
        ("data.bin", False),
        ("archive.zip", False),
    ]
    
    for filename, expected in test_cases:
        result = is_text_file(filename)
        if result == expected:
            print(f"  ✅ {filename}: {result}")
        else:
            print(f"  ❌ {filename}: expected {expected}, got {result}")
            return False
    
    return True

def test_exclude_patterns():
    """Test the path exclusion logic."""
    print("🧪 Testing exclude patterns...")
    
    test_cases = [
        (Path("/test/.git/config"), [".git"], True),
        (Path("/test/node_modules/package"), ["node_modules"], True),
        (Path("/test/src/main.py"), [".git", "node_modules"], False),
        (Path("/test/__pycache__/cache.pyc"), [], True),  # Default exclude
        (Path("/test/dist/build.js"), ["dist"], True),
        (Path("/test/regular_file.py"), ["test_pattern"], False),
    ]
    
    for path, patterns, expected in test_cases:
        result = should_exclude_path(path, patterns)
        if result == expected:
            print(f"  ✅ {path.name}: {result}")
        else:
            print(f"  ❌ {path.name}: expected {expected}, got {result}")
            return False
    
    return True

def test_validation():
    """Test the validation functions."""
    print("🧪 Testing validation functions...")
    
    # Test directory validation
    current_dir = os.getcwd()
    validation = validate_directory_path(current_dir)
    if validation["valid"]:
        print(f"  ✅ Valid directory: {current_dir}")
    else:
        print(f"  ❌ Invalid directory: {validation['error']}")
        return False
    
    # Test invalid directory
    invalid_validation = validate_directory_path("/nonexistent/path")
    if not invalid_validation["valid"]:
        print(f"  ✅ Correctly rejected invalid path")
    else:
        print(f"  ❌ Should have rejected invalid path")
        return False
    
    # Test parameter validation
    param_validation = validate_crawl_dir_params(
        directory_path=current_dir,
        max_files=100,
        max_file_size=1024*1024,
        chunk_size=5000
    )
    
    if param_validation["valid"]:
        print(f"  ✅ Valid parameters")
    else:
        print(f"  ❌ Invalid parameters: {param_validation['errors']}")
        return False
    
    # Test invalid parameters
    invalid_param_validation = validate_crawl_dir_params(
        directory_path=current_dir,
        max_files=-1,  # Invalid
        max_file_size=0,  # Invalid
        chunk_size=50   # Invalid (too small)
    )
    
    if not invalid_param_validation["valid"]:
        print(f"  ✅ Correctly rejected invalid parameters")
    else:
        print(f"  ❌ Should have rejected invalid parameters")
        return False
    
    return True

async def main():
    """Run all tests."""
    print("🚀 Starting crawl_dir functionality tests...\n")
    
    tests = [
        ("Text File Detection", test_text_file_detection),
        ("Exclude Patterns", test_exclude_patterns), 
        ("Validation Functions", test_validation),
        ("Directory Crawling", test_directory_crawling),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print('='*50)
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                print(f"✅ {test_name} PASSED")
                passed += 1
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"💥 {test_name} CRASHED: {e}")
    
    print(f"\n{'='*50}")
    print(f"Test Results: {passed}/{total} passed")
    print('='*50)
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("😞 Some tests failed.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)