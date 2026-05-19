import sys, json
sys.path.insert(0, '/opt/CNN/cloud')
sys.path.insert(0, '/opt/CNN')
from app.database import SessionLocal
from app.models import Diagnosis
db = SessionLocal()
d = db.query(Diagnosis).filter(Diagnosis.device_id=='WTG-008', Diagnosis.batch_index==4, Diagnosis.channel==0).first()
if d:
    print('hs={} status={}'.format(d.health_score, d.status))
    print('engine_result is None: {}'.format(d.engine_result is None))
    print('full_analysis is None: {}'.format(d.full_analysis is None))
    er = d.engine_result
    if er:
        er = json.loads(er) if isinstance(er, str) else er
        tf = er.get('time_features', {})
        ens = er.get('ensemble', {})
        print('kurt={} crest={} rms_mad_z={}'.format(tf.get('kurtosis'), tf.get('crest_factor'), tf.get('rms_mad_z')))
        print('bearing_conf={} gear_conf={} time_conf={}'.format(ens.get('bearing_confidence'), ens.get('gear_confidence'), ens.get('time_confidence')))
        print('skip_bearing={} skip_gear={} has_bearing={} has_gear={}'.format(ens.get('skip_bearing'), ens.get('skip_gear'), ens.get('has_bearing_params'), ens.get('has_gear_params')))
        gear = er.get('gear', {})
        inds = gear.get('fault_indicators', {})
        for k, v in inds.items():
            if isinstance(v, dict):
                print('  {}: val={} w={} c={}'.format(k, v.get('value'), v.get('warning'), v.get('critical')))
    else:
        print('no engine_result in DB')
else:
    print('no WTG-008 batch=4 diagnosis')
db.close()
