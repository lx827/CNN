import sys; sys.path.insert(0, 'd:/code/CNN/cloud')
from app.services.diagnosis.hyperparams import HyperParams

hp_cw = HyperParams(dataset='cw')
print(f'significant_snr: {hp_cw.get_float("diagnosis.bearing.significant_snr", 4.5)}')
print(f'dominant_ratio: {hp_cw.get_float("diagnosis.bearing.dominant_ratio", 1.5)}')

hp_def = HyperParams()
print(f'default significant_snr: {hp_def.get_float("diagnosis.bearing.significant_snr", 4.5)}')
print(f'default dominant_ratio: {hp_def.get_float("diagnosis.bearing.dominant_ratio", 1.5)}')
