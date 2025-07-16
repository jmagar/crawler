#!/usr/bin/env python3
"""
Quick test script to verify query parameter functionality works.
"""

import asyncio
import json
from unittest.mock import Mock, patch
from src.utils.fastmcp_utils import get_query_parameters, get_pagination_params


def test_query_parameters():
    """Test query parameter parsing."""
    print("Testing query parameter parsing...")
    
    # Mock HTTP request with query parameters
    mock_request = Mock()
    mock_request.query_params = {
        "limit": "50",
        "offset": "10", 
        "source_filter": "github.com",
        "include_archived": "true",
        "has_code": "false"
    }
    
    # Test with mock request
    with patch('src.utils.fastmcp_utils.get_http_request', return_value=mock_request):
        params = get_query_parameters()
        
        print(f"Parsed parameters: {json.dumps(params, indent=2)}")
        
        # Verify type conversions
        assert params["limit"] == 50, f"Expected limit=50, got {params['limit']}"
        assert params["offset"] == 10, f"Expected offset=10, got {params['offset']}"
        assert params["source_filter"] == "github.com", f"Expected source_filter='github.com', got {params['source_filter']}"
        assert params["include_archived"] is True, f"Expected include_archived=True, got {params['include_archived']}"
        assert params["has_code"] is False, f"Expected has_code=False, got {params['has_code']}"
        
        print("✅ Query parameter parsing works correctly!")


def test_pagination_params():
    """Test pagination parameter helper."""
    print("\nTesting pagination parameter helper...")
    
    # Test with limit and offset
    params1 = {"limit": 20, "offset": 40}
    pagination1 = get_pagination_params(params1)
    print(f"Test 1 - Limit/Offset: {json.dumps(pagination1, indent=2)}")
    
    # Test with page number
    params2 = {"limit": 25, "page": 3}
    pagination2 = get_pagination_params(params2)
    print(f"Test 2 - Page number: {json.dumps(pagination2, indent=2)}")
    
    # Verify page calculation
    expected_offset = (3 - 1) * 25  # (page - 1) * limit
    assert pagination2["offset"] == expected_offset, f"Expected offset={expected_offset}, got {pagination2['offset']}"
    
    print("✅ Pagination parameter helper works correctly!")


def test_no_request_context():
    """Test behavior when no HTTP request context is available."""
    print("\nTesting no request context...")
    
    # Test with no request context
    with patch('src.utils.fastmcp_utils.get_http_request', return_value=None):
        params = get_query_parameters()
        
        print(f"No request context parameters: {json.dumps(params, indent=2)}")
        assert params == {}, f"Expected empty dict, got {params}"
        
        print("✅ No request context handling works correctly!")


if __name__ == "__main__":
    print("🧪 Testing FastMCP Query Parameters Implementation\n")
    
    try:
        test_query_parameters()
        test_pagination_params()
        test_no_request_context()
        
        print("\n🎉 All tests passed! The implementation is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()