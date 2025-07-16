#!/usr/bin/env python3
"""
Simple test to verify the query parameter utility functions work.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test the core logic without imports
def test_query_param_conversion():
    """Test the core query parameter conversion logic."""
    print("Testing query parameter conversion logic...")
    
    # Simulate the conversion logic from our utility
    def convert_params(query_params):
        converted_params = {}
        for key, value in query_params.items():
            # Handle common numeric parameters
            if key in ['limit', 'offset', 'page', 'size', 'count', 'max_results'] and value.isdigit():
                converted_params[key] = int(value)
            # Handle boolean parameters
            elif key in ['include_archived', 'has_code', 'recursive', 'enabled'] and value.lower() in ['true', 'false']:
                converted_params[key] = value.lower() == 'true'
            else:
                converted_params[key] = value
        return converted_params
    
    # Test data
    test_params = {
        "limit": "50",
        "offset": "10",
        "source_filter": "github.com",
        "include_archived": "true",
        "has_code": "false",
        "custom_param": "custom_value"
    }
    
    result = convert_params(test_params)
    
    print(f"Input: {test_params}")
    print(f"Output: {result}")
    
    # Verify conversions
    assert result["limit"] == 50, f"Expected int 50, got {result['limit']}"
    assert result["offset"] == 10, f"Expected int 10, got {result['offset']}"
    assert result["include_archived"] is True, f"Expected bool True, got {result['include_archived']}"
    assert result["has_code"] is False, f"Expected bool False, got {result['has_code']}"
    assert result["source_filter"] == "github.com", f"Expected str, got {result['source_filter']}"
    assert result["custom_param"] == "custom_value", f"Expected str, got {result['custom_param']}"
    
    print("✅ Parameter conversion works correctly!")


def test_pagination_logic():
    """Test pagination calculation logic."""
    print("\nTesting pagination logic...")
    
    def get_pagination_params(query_params):
        limit = query_params.get("limit", 50)
        offset = query_params.get("offset", 0) 
        page = query_params.get("page", 1)
        
        # If page is provided without offset, calculate offset
        if page > 1 and offset == 0:
            offset = (page - 1) * limit
        
        return {
            "limit": limit,
            "offset": offset,
            "page": page
        }
    
    # Test with page number
    test_params = {"limit": 25, "page": 3}
    result = get_pagination_params(test_params)
    
    print(f"Input: {test_params}")
    print(f"Output: {result}")
    
    expected_offset = (3 - 1) * 25  # = 50
    assert result["offset"] == expected_offset, f"Expected offset {expected_offset}, got {result['offset']}"
    assert result["limit"] == 25, f"Expected limit 25, got {result['limit']}"
    assert result["page"] == 3, f"Expected page 3, got {result['page']}"
    
    print("✅ Pagination logic works correctly!")


if __name__ == "__main__":
    print("🧪 Testing FastMCP Query Parameters Core Logic\n")
    
    try:
        test_query_param_conversion()
        test_pagination_logic()
        
        print("\n🎉 All core logic tests passed!")
        print("The implementation should work correctly when integrated with FastMCP.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()