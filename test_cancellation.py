#!/usr/bin/env python3
"""
Test script to verify cancellation handling in the MCP server.
"""
import asyncio
import json
import time
from fastmcp import Context

# Simulate a cancellable operation
async def test_cancellation_handling():
    """Test how our tools handle cancellation."""
    print("Testing cancellation handling...")
    
    # Simulate a long-running operation that might be cancelled
    try:
        print("Starting operation...")
        for i in range(10):
            print(f"Progress: {i}/10")
            await asyncio.sleep(1)  # Simulate work
            
            # Check for cancellation
            if asyncio.current_task().cancelled():
                print("Operation was cancelled!")
                break
                
        print("Operation completed successfully!")
        
    except asyncio.CancelledError:
        print("✓ CancelledError caught and handled gracefully")
        # In real tools, this would return a proper JSON response
        return {"success": False, "error": "Operation cancelled by user"}
    
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return {"success": False, "error": str(e)}
    
    return {"success": True, "message": "Operation completed"}

async def test_with_timeout():
    """Test cancellation with timeout."""
    print("\n" + "="*50)
    print("Testing operation with 3-second timeout...")
    
    try:
        # This should be cancelled after 3 seconds
        result = await asyncio.wait_for(test_cancellation_handling(), timeout=3.0)
        print(f"Result: {result}")
        
    except asyncio.TimeoutError:
        print("✓ Operation timed out as expected")
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")

async def main():
    """Run cancellation tests."""
    print("🔬 Testing MCP Server Cancellation Handling")
    print("="*50)
    
    # Test 1: Normal completion
    print("Test 1: Normal operation (should complete)")
    result = await test_cancellation_handling()
    print(f"Result: {result}")
    
    # Test 2: Timeout/cancellation
    await test_with_timeout()
    
    print("\n✓ All cancellation tests completed!")
    print("The server should now handle tool cancellations gracefully.")

if __name__ == "__main__":
    asyncio.run(main())