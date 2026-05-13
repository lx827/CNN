import requests

EDGE_KEY = 'turbine-edge-secret'
headers = {'X-Edge-Key': EDGE_KEY}

# Test direct device lookup via API
r = requests.get('http://127.0.0.1:8000/api/data/TEST-001/', headers=headers)
print(f'Device info: {r.status_code} | {r.text[:300]}')

# Try batch lookup
r = requests.get('http://127.0.0.1:8000/api/data/TEST-001/batches/', headers=headers)
print(f'Batches: {r.status_code} | {r.text[:300]}')

# Try with different URL encoding
import urllib.parse
encoded = urllib.parse.quote('TEST-001')
r = requests.post(f'http://127.0.0.1:8000/api/data/{encoded}/1/reanalyze', headers=headers, timeout=30)
print(f'Encoded reanalyze: {r.status_code} | {r.text[:300]}')

# Try with Invoke-WebRequest equivalent: check if server is even seeing the right device_id
# Let's also check the route registration
print('\n--- Checking routes ---')
r = requests.get('http://127.0.0.1:8000/docs', headers=headers)
print(f'Docs: {r.status_code}')

# Try the reanalyze with trailing slash variants
for url in [
    'http://127.0.0.1:8000/api/data/TEST-001/1/reanalyze',
    'http://127.0.0.1:8000/api/data/TEST-001/1/reanalyze/',
]:
    r = requests.post(url, headers=headers, timeout=30)
    print(f'{url} -> {r.status_code}: {r.text[:200]}')
