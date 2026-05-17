"""验证所有模块可正确导入"""
import sys
from pathlib import Path

# 确保路径正确
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "cloud"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "diagnosis"))

modules = [
    ("evaluation.config", "OUTPUT_DIR, SAMPLE_RATE, MAX_SAMPLES, HEALTH_THRESHOLD"),
    ("evaluation.utils", "compute_confusion_matrix, compute_cohen_kappa, compute_mcc, compute_macro_f1, compute_fdr_far_mdr_fia, compute_psnr, compute_monotonicity, compute_trendability"),
    ("evaluation.classification_metrics_eval", "evaluate_classification_performance, generate_classification_metrics_table"),
    ("evaluation.denoise_eval", "evaluate_denoise_methods"),
    ("evaluation.bearing_eval", "evaluate_bearing_methods"),
    ("evaluation.gear_eval", "evaluate_gear_methods"),
    ("evaluation.comprehensive_eval", "evaluate_comprehensive_diagnosis"),
    ("evaluation.robustness_eval", "evaluate_noise_robustness"),
    ("evaluation.ds_fusion_eval", "evaluate_ds_fusion"),
    ("evaluation.health_trend_eval", "evaluate_health_trend"),
    ("evaluation.channel_consensus_eval", "evaluate_channel_consensus"),
    ("evaluation.report_generator", "generate_final_report"),
    ("evaluation.main", "main"),
]

ok = []
fail = []
for mod_name, symbols in modules:
    try:
        mod = __import__(mod_name, fromlist=symbols.split(", "))
        for sym in symbols.split(", "):
            sym = sym.strip()
            if not hasattr(mod, sym):
                fail.append(f"{mod_name}.{sym}: symbol not found")
                break
        ok.append(mod_name)
    except Exception as e:
        fail.append(f"{mod_name}: {e}")

print(f"OK: {len(ok)}")
print(f"FAIL: {len(fail)}")
for x in fail:
    print(x)