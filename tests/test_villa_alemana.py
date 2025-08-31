import requests
import json

# Test Villa Alemana pharmacies
print('Testing Villa Alemana pharmacies...')
try:
    resp = requests.get('http://localhost:8000/farmacias?comuna=villa%20alemana&abierto=true&limit=10', timeout=10)
    print(f'Status: {resp.status_code}')

    if resp.status_code == 200:
        data = resp.json()
        print(f'Found {len(data["items"])} pharmacies:')

        for i, pharmacy in enumerate(data['items'][:5]):  # Show first 5
            print(f'{i+1}. {pharmacy["nombre_local"]}')
            print(f'   📍 {pharmacy["direccion"]}, {pharmacy["comuna"]}')
            print(f'   📞 {pharmacy.get("telefono", "No phone")}')
            print(f'   🕐 {pharmacy.get("horario_apertura", "N/A")} - {pharmacy.get("horario_cierre", "N/A")}')
            if pharmacy.get("lat") and pharmacy.get("lng"):
                print(f'   📌 Coordinates: {pharmacy["lat"]}, {pharmacy["lng"]}')
            print()
    else:
        print(f'Error: {resp.text}')

except Exception as e:
    print(f'Error: {e}')
