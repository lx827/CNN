"""业务测试只构造已经过对象评估的证据，不用原始数值猜诊断状态。"""
import numpy as np

from app.services.diagnosis.adapters import adapt_method_result, unavailable_result
from app.services.diagnosis.domain import DiagnosisKey


def snapshot(device="BUSINESS", batch=1, channel=1, denoise="none", conclusion="warning"):
    key = DiagnosisKey(device, batch, channel, denoise)
    if conclusion == "unknown":
        return unavailable_result("missing_physical_parameters", key=key, object_id="gear", method="advanced")
    indicators = {"ser": {"evaluable": True, "warning": conclusion in {"warning", "fault"}, "critical": conclusion == "fault"}}
    return adapt_method_result({"evaluation": {"status": "evaluated", "indicators": indicators}},
        key=key, object_id="gear", method="advanced", signal=np.array([1., -1.]), physical_parameters=True)


def batch_snapshot(device="BUSINESS", batch=1, denoise="none"):
    from dataclasses import replace
    from app.services.diagnosis.domain import Evidence
    from app.services.diagnosis.assessment import assess_evidence
    channels = {"ch1": snapshot(device, batch, 1, denoise), "ch3": snapshot(device, batch, 3, denoise, "unknown")}
    grouped = {f"{name}/gear": tuple(replace(Evidence.from_dict(item), object_id=f"{name}/gear") for item in value["evaluations"][0]["evidence"])
               for name, value in channels.items()}
    return {**assess_evidence(grouped).to_dict(), "channels": channels, "rot_freq": 16.}
