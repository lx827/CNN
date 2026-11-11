"""业务已知反例；不执行算法或声称验证真实故障效果。"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.services.diagnosis.assessment import AssessmentPolicy, assess_evidence, reassess_diagnosis
from app.services.diagnosis.domain import DiagnosisConclusion as C, EvaluationStatus as S, DiagnosisKey, Evidence, PenaltyRequest
from app.services.diagnosis.fusion.evidence import fuse_evidence


def known(identity="a", object_id="bearing", dependency="raw", conclusion=C.FAULT, reliability=.9):
    return Evidence(identity, DiagnosisKey("D", 1, 2, "none"), object_id, "ENVELOPE", frozenset({dependency}), S.EVALUATED, conclusion, reliability, 1., ("BPFO",) if conclusion != C.NORMAL else (), (PenaltyRequest("bearing_outer", 20.),) if conclusion != C.NORMAL else ())


class DiagnosisDomainTests(unittest.TestCase):
    def test_related_variants_do_not_add_votes_or_deductions(self):
        original = known()
        variant = replace(original, evidence_id="wavelet:med", method="med", key=replace(original.key, denoise_method="wavelet"))
        single = assess_evidence({"bearing": (original,)})
        repeated = assess_evidence({"bearing": (original, variant)})
        self.assertEqual(single.health_score, repeated.health_score)
        self.assertEqual(len(repeated.deductions), 1)
        self.assertEqual(len(repeated.evaluations[0].fusion.groups), 1)

    def test_independent_sources_increase_support_but_physical_faults_can_coexist(self):
        outer = known()
        inner = replace(known("b", dependency="other_sensor"), propositions=("BPFI",))
        result = assess_evidence({"bearing": (outer, inner)})
        self.assertAlmostEqual(result.evaluations[0].fusion.anomaly_mass, .99)
        self.assertEqual({value.value for value in result.fault_propositions}, {"bearing_outer", "bearing_inner"})
        self.assertAlmostEqual(result.evaluations[0].fusion.conflict, 0.)

    def test_unavailable_object_does_not_erase_valid_negative_and_is_not_hidden(self):
        normal = known(conclusion=C.NORMAL)
        missing = Evidence("missing", normal.key, "gear", "planetary_gear", frozenset({"raw"}), S.NOT_EVALUABLE, C.UNKNOWN, None, None, reason="missing_baseline")
        result = assess_evidence({"bearing": (normal,), "gear": (missing,)})
        self.assertEqual(result.diagnosis_conclusion, C.NORMAL)
        self.assertEqual(result.coverage, "partial")
        self.assertIn("不覆盖", result.recommendation)
        self.assertEqual(result.evaluations[1].diagnosis_conclusion, C.UNKNOWN)

    def test_no_evidence_zero_energy_and_unknown_method_cannot_create_normal(self):
        result = assess_evidence({})
        self.assertEqual(result.evaluation_status, S.NOT_EVALUABLE)
        self.assertIsNone(result.health_score)
        for kwargs in ({"signal_rms": 0.}, {"method": "unknown_new_method"}, {"propositions": ("arbitrary_tooth_break",)}):
            with self.assertRaises(ValueError):
                replace(known(), **kwargs)

    def test_full_and_internal_conflict_remain_unknown(self):
        for dependency in ("independent", "raw"):
            fault = known(reliability=1.)
            normal = known("b", dependency=dependency, conclusion=C.NORMAL, reliability=1.)
            result = assess_evidence({"bearing": (fault, normal)})
            self.assertEqual(result.evaluation_status, S.INDETERMINATE)
            self.assertEqual(result.diagnosis_conclusion, C.UNKNOWN)
            self.assertIsNone(result.health_score)

    def test_conflict_weight_is_applied_exactly_once(self):
        fault = known(reliability=.5)
        normal = known("b", dependency="independent", conclusion=C.NORMAL, reliability=.5)
        result = assess_evidence({"bearing": (fault, normal)}, AssessmentPolicy(weights={"bpfo": 2., "ds_conflict": 8.}))
        self.assertEqual(result.deductions[0].weighted_amount, 40.)
        conflict = next(value for value in result.deductions if value.code == "evidence_conflict")
        self.assertAlmostEqual(conflict.amount, .25)
        self.assertAlmostEqual(conflict.weighted_amount, 2.)
        self.assertAlmostEqual(result.health_score, 58.)
        with self.assertRaises(ValueError):
            assess_evidence({"bearing": (replace(fault, penalties=(PenaltyRequest("misspelled_name", 5.),)),)})

    def test_serialized_evidence_reassesses_without_algorithm_and_without_status_alias(self):
        result = assess_evidence({"bearing": (known(),)})
        payload = result.to_dict()
        self.assertNotIn("status", payload)
        self.assertEqual(payload["diagnosis_conclusion"], "fault")
        self.assertEqual(reassess_diagnosis(payload).to_dict(), payload)
        with self.assertRaises(ValueError):
            reassess_diagnosis({"status": "normal", "health_score": 100})

    def test_transitive_dependency_and_real_channel_identity(self):
        a = known()
        b = replace(known("b"), dependencies=frozenset({"raw", "other"}))
        c = known("c", dependency="other")
        self.assertEqual(len(fuse_evidence((a, b, c)).groups), 1)
        with self.assertRaises(ValueError):
            fuse_evidence((a, replace(b, key=replace(b.key, channel=3))))


if __name__ == "__main__":
    unittest.main()
