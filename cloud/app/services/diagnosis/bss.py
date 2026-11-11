"""BSS研究服务边界；失败不回退原始信号伪成功。"""
from app.algorithms.composite.ica import FastICAParameters, compute_fast_ica
from .composite import analyze_composite_research


def fast_ica(X, n_components=None, max_iter=200, tol=1e-6, whiten=True):
    if not whiten:
        raise ValueError("explicit_SVD_whitening_is_required")
    result = compute_fast_ica(X, FastICAParameters(n_components, max_iter, tol))
    if result.components is None or not result.converged:
        raise ValueError(result.reason)
    return result.components, {"method": "FastICA", "mixing": result.mixing,
                               "unmixing": result.unmixing, "mean": result.mean,
                               "converged": result.converged, "iterations": result.iterations}


def vmd_ica_separation(signal, fs, K=5, alpha=2000, max_ica_iter=200, ica_tol=1e-6):
    result = analyze_composite_research(
        "vmd_ica", signal, fs, options={"modes": K, "alpha": alpha,
            "ica_iterations": max_ica_iter, "ica_tolerance": ica_tol})
    selection = result.analysis.data.get("selection")
    return {"status": result.analysis.status, "reason": result.analysis.reason,
            "denoised_signal": selection.representation if selection else None,
            "analysis": result.analysis, "evaluation": result.evaluation,
            "research_only": True, "production_eligible": False}
