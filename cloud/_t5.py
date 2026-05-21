import sys; sys.path.insert(0, 'd:/code/CNN/cloud')
import numpy as np
from app.services.diagnosis.ensemble import run_research_ensemble

sig = np.load(r'D:\code\CNN\CW\down8192_CW\I-A-1.npy').astype(np.float64)[:40960]
res = run_research_ensemble(sig, 8192,
    bearing_params={'n':9,'d':7.94,'D':38.52,'alpha':0},
    max_seconds=5.0, dataset='cw')

print(f"fault_label: {res.get('fault_label')}")
print(f"health_score: {res.get('health_score')}")
print(f"status: {res.get('status')}")

ens = res.get('ensemble', {})
print(f"best_bearing: {ens.get('best_bearing')}")
print(f"bearing_votes keys: {list(ens.get('bearing_votes',{}).keys())[:5]}")
print(f"bearing_confidence: {ens.get('bearing_confidence')}")
