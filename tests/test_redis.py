#!/usr/bin/env python3
"""
Test Redis connection and basic operations
"""

import redis
import json
from datetime import datetime
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.utils import get_env_value

def test_redis_connection():
    """Test basic Redis connectivity and operations"""
    
    print("🔗 Testing Redis Connection")
    print("=" * 40)
    
    try:
        # Get Redis URL from environment
        redis_url = get_env_value("REDIS_URL")
        
        if not redis_url:
            print("❌ REDIS_URL not found in environment")
            return False
        
        print(f"📡 Connecting to Redis...")
        print(f"   URL: {redis_url[:30]}..." if len(redis_url) > 30 else f"   URL: {redis_url}")
        
        # Create Redis connection
        r = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=10,
            socket_timeout=10
        )
        
        # Test basic connection
        print("🔍 Testing connection...")
        pong = r.ping()
        print(f"   Ping response: {pong}")
        
        if not pong:
            print("❌ Redis ping failed")
            return False
        
        # Test basic operations
        print("🧪 Testing basic operations...")
        
        # Set a test key
        test_key = "pharmacy_finder_test"
        test_data = {
            "message": "Hello from Pharmacy Finder!",
            "timestamp": datetime.now().isoformat(),
            "test": True
        }
        
        print("   Setting test key...")
        r.set(test_key, json.dumps(test_data), ex=60)  # Expire in 60 seconds
        
        print("   Getting test key...")
        retrieved = r.get(test_key)
        
        if retrieved:
            parsed_data = json.loads(retrieved)
            print(f"   ✅ Retrieved: {parsed_data['message']}")
        else:
            print("   ❌ Failed to retrieve test data")
            return False
        
        # Test hash operations (used in our cache)
        print("   Testing hash operations...")
        hash_key = "pharmacy_finder_hash_test"
        hash_data = {
            "data": json.dumps({"pharmacies": ["test1", "test2"]}),
            "timestamp": datetime.now().isoformat(),
            "ttl": "300"
        }
        
        r.hset(hash_key, mapping=hash_data)
        retrieved_hash = r.hgetall(hash_key)
        
        if retrieved_hash:
            print(f"   ✅ Hash operations working")
        else:
            print("   ❌ Hash operations failed")
            return False
        
        # Get Redis info
        print("📊 Redis Server Info:")
        info = r.info()
        print(f"   Redis version: {info.get('redis_version', 'unknown')}")
        print(f"   Used memory: {info.get('used_memory_human', 'unknown')}")
        print(f"   Connected clients: {info.get('connected_clients', 'unknown')}")
        print(f"   Total commands processed: {info.get('total_commands_processed', 'unknown')}")
        
        # Clean up test keys
        print("🧹 Cleaning up test keys...")
        r.delete(test_key, hash_key)
        
        print("✅ Redis connection test PASSED!")
        return True
        
    except redis.ConnectionError as e:
        print(f"❌ Redis connection error: {e}")
        return False
    except redis.TimeoutError as e:
        print(f"❌ Redis timeout error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_cache_key_generation():
    """Test cache key generation logic"""
    print("\n🔑 Testing Cache Key Generation")
    print("=" * 40)
    
    from app.cache.redis_client import RedisClient
    
    client = RedisClient()
    
    # Test various endpoints and parameters
    test_cases = [
        ("/api/search", {"comuna": "SANTIAGO"}),
        ("/api/search", {"comuna": "LAS CONDES", "abierto": "true"}),
        ("/api/open-now", {"comuna": "PROVIDENCIA"}),
        ("/api/nearby", {"lat": "-33.4489", "lng": "-70.6693", "radius": "5"}),
        ("/api/stats", {}),
        ("/api/communes", None)
    ]
    
    for endpoint, params in test_cases:
        cache_key = client.generate_cache_key(endpoint, params)
        print(f"   {endpoint} + {params}")
        print(f"   → {cache_key}")
        
        # Check TTL assignment
        ttl = client.get_ttl_for_endpoint(endpoint)
        print(f"   → TTL: {ttl}s ({ttl//60}min)")
        print()
    
    print("✅ Cache key generation test completed!")

if __name__ == "__main__":
    success = test_redis_connection()
    
    if success:
        test_cache_key_generation()
        print("\n🎉 All Redis tests passed!")
        print("🚀 Ready to implement Redis caching!")
    else:
        print("\n❌ Redis tests failed!")
        print("🔧 Please check your Redis configuration and connection.")
