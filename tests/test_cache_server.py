#!/usr/bin/env python3
"""
Test the updated server with Redis caching
"""

import requests
import time
import json
from datetime import datetime

def test_server_with_redis():
    """Test the server with Redis caching enabled"""
    
    base_url = "http://127.0.0.1:8000"
    
    print("🧪 Testing Pharmacy Finder with Redis Cache")
    print("=" * 50)
    
    # Test health endpoint
    print("1. 🏥 Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ Health: {response.json()}")
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Health check error: {e}")
        return False
    
    # Test cache health
    print("\n2. 🔍 Testing cache health...")
    try:
        response = requests.get(f"{base_url}/api/cache/health", timeout=10)
        if response.status_code == 200:
            cache_health = response.json()
            print(f"   ✅ Cache health: {cache_health['status']}")
            print(f"   📊 Redis status: {cache_health['cache_system'].get('redis_available', 'unknown')}")
        else:
            print(f"   ⚠️  Cache health check status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Cache health error: {e}")
    
    # Test cache statistics
    print("\n3. 📊 Testing cache statistics...")
    try:
        response = requests.get(f"{base_url}/api/cache/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()
            redis_stats = stats.get('redis_stats', {})
            print(f"   ✅ Redis connected: {redis_stats.get('status', 'unknown')}")
            print(f"   💾 Memory used: {redis_stats.get('used_memory_human', 'unknown')}")
            print(f"   🎯 Cache hits: {redis_stats.get('keyspace_hits', 0)}")
            print(f"   ❌ Cache misses: {redis_stats.get('keyspace_misses', 0)}")
        else:
            print(f"   ⚠️  Cache stats status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Cache stats error: {e}")
    
    # Test API endpoints with cache timing
    print("\n4. ⚡ Testing API performance (cache effectiveness)...")
    
    endpoints_to_test = [
        ("/api/stats", "Statistics"),
        ("/api/search?comuna=SANTIAGO", "Santiago search"),
        ("/api/open-now", "Open pharmacies"),
        ("/api/communes", "Commune list")
    ]
    
    for endpoint, description in endpoints_to_test:
        print(f"\n   🎯 Testing {description}...")
        
        # First request (should be cache MISS)
        start_time = time.time()
        try:
            response1 = requests.get(f"{base_url}{endpoint}", timeout=10)
            time1 = (time.time() - start_time) * 1000
            
            if response1.status_code == 200:
                cache_header1 = response1.headers.get('X-Cache', 'UNKNOWN')
                print(f"     First request: {time1:.1f}ms - Cache: {cache_header1}")
                
                # Second request (should be cache HIT)
                start_time = time.time()
                response2 = requests.get(f"{base_url}{endpoint}", timeout=10)
                time2 = (time.time() - start_time) * 1000
                
                cache_header2 = response2.headers.get('X-Cache', 'UNKNOWN')
                cache_age = response2.headers.get('X-Cache-Age', 'unknown')
                
                print(f"     Second request: {time2:.1f}ms - Cache: {cache_header2} (Age: {cache_age}s)")
                
                # Calculate performance improvement
                if time1 > 0 and time2 > 0:
                    improvement = ((time1 - time2) / time1) * 100
                    print(f"     ⚡ Performance improvement: {improvement:.1f}%")
                
                # Check response consistency
                if response1.status_code == response2.status_code:
                    print(f"     ✅ Response consistency: OK")
                else:
                    print(f"     ⚠️  Response consistency: DIFFER")
            else:
                print(f"     ❌ Request failed: {response1.status_code}")
        except Exception as e:
            print(f"     ❌ Request error: {e}")
    
    # Test cache invalidation
    print(f"\n5. 🔄 Testing manual cache invalidation...")
    try:
        response = requests.post(f"{base_url}/api/cache/invalidate", timeout=10)
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Invalidation: {result['status']}")
            print(f"   🗑️  Entries cleared: {result.get('invalidated_count', 0)}")
        else:
            print(f"   ⚠️  Invalidation status: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Invalidation error: {e}")
    
    print(f"\n🎉 Redis cache testing completed!")
    print(f"📅 Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return True

if __name__ == "__main__":
    print("⏳ Please make sure the server is running with:")
    print("   uvicorn app.main:app --host 127.0.0.1 --port 8000")
    print("\nPress Enter to start testing...")
    input()
    
    test_server_with_redis()
