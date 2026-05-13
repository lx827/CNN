import requests, json

EDGE_KEY = 'turbine-edge-secret'
headers = {'X-Edge-Key': EDGE_KEY}

r = requests.get('http://127.0.0.1:8000/api/dashboard/', headers=headers)
print(f'Dashboard status: {r.status_code}')
data = r.json()

devices_data = data.get('data', {}).get('devices', [])
if not devices_data:
    devices_data = data.get('data', data.get('devices', []))
n = len(devices_data) if isinstance(devices_data, list) else 'N/A'
print(f'Devices found: {n}')

test_devices = ['TEST-001']
if isinstance(devices_data, list):
    for d in devices_data:
        if isinstance(d, dict):
            test_devices.append(d.get('device_id', ''))
        else:
            test_devices.append(d)

for did in test_devices:
    if not did:
        continue
    url = f'http://127.0.0.1:8000/api/data/{did}/1/reanalyze'
    print(f'\nPOST {url}')
    try:
        r = requests.post(url, headers=headers, timeout=120)
        print(f'  Status: {r.status_code}')
        if r.status_code == 200:
            print(f'  Success: {json.dumps(r.json(), ensure_ascii=False)[:300]}')
        else:
            print(f'  Error: {r.text[:500]}')
        if r.status_code != 404:
            break
    except Exception as e:
        print(f'  Exception: {e}')
