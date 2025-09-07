"""
Simple test script for the pharmacy web interface
"""
import requests
import webbrowser
import time

def test_web_interface():
    """Test the pharmacy finder web interface"""
    print("🧪 Testing Pharmacy Finder Web Interface")
    print("=" * 50)

    # Test the main page
    try:
        print("📄 Testing main page...")
        response = requests.get("http://localhost:8000/")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            print("✅ Main page loaded successfully")
        else:
            print(f"❌ Main page failed: {response.text[:100]}")

    except Exception as e:
        print(f"❌ Main page error: {e}")

    # Test API stats
    try:
        print("\n📊 Testing API stats...")
        response = requests.get("http://localhost:8000/api/stats")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            stats = response.json()
            print(f"✅ Stats loaded: {stats}")
        else:
            print(f"❌ Stats failed: {response.text}")

    except Exception as e:
        print(f"❌ Stats error: {e}")

    # Test pharmacy search
    try:
        print("\n🏥 Testing pharmacy search...")
        response = requests.get("http://localhost:8000/farmacias?comuna=villa%20alemana&abierto=true")
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            pharmacies = data.get('items', [])
            print(f"✅ Found {len(pharmacies)} pharmacies in Villa Alemana")
            if pharmacies:
                pharmacy = pharmacies[0]
                print(f"   📍 {pharmacy['nombre']} - {pharmacy['direccion']}")
        else:
            print(f"❌ Search failed: {response.text}")

    except Exception as e:
        print(f"❌ Search error: {e}")

    print("\n" + "=" * 50)
    print("🌐 Opening web interface in browser...")
    print("   Visit: http://localhost:8000")
    print("💡 Try searching for 'santiago' or 'valparaiso'")

    # Open browser
    try:
        webbrowser.open("http://localhost:8000")
    except Exception as e:
        print(f"Could not open browser: {e}")

if __name__ == "__main__":
    test_web_interface()
