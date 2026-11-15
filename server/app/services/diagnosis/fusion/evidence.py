"""对象级二元 D-S 支持量与依赖去重；故障部位命题可共存，不互相排斥。"""

from __future__ import annotations

from app.services.diagnosis.domain import (
    DependencyGroup,
    DiagnosisConclusion,
    EvaluationStatus,
    Evidence,
    FusionResult,
)


def dependency_groups(
    evidence: tuple[Evidence, ...],
) -> tuple[tuple[Evidence, ...], ...]:
    """共享任何原始观测/处理依赖的证据形成连通分组，不按算法数量增票。

    与去噪方法无关；A 依赖 x、B 依赖 x/y、C 依赖 y 时三者也是一组。
    调用方要声明真正独立的来源，不能把方法名当成独立性证明。
    """
    identifiers = [value.evidence_id for value in evidence]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate_evidence_identity")
    if len({(value.key.record_id, value.object_id) for value in evidence}) > 1:
        raise ValueError("fusion_requires_same_record_channel_and_object")
    pending = sorted(evidence, key=lambda value: value.evidence_id)
    groups = []
    while pending:
        group = [pending.pop(0)]
        dependencies = set(group[0].dependencies)
        changed = True
        while changed:
            changed = False
            retained = []
            for value in pending:
                if dependencies & value.dependencies:
                    group.append(value)
                    dependencies.update(value.dependencies)
                    changed = True
                else:
                    retained.append(value)
            pending = retained
        groups.append(tuple(sorted(group, key=lambda value: value.evidence_id)))
    return tuple(groups)


def _group_mass(group: tuple[Evidence, ...]) -> DependencyGroup:
    normal = max(
        (
            value.confidence
            for value in group
            if value.diagnosis_conclusion == DiagnosisConclusion.NORMAL
        ),
        default=0.0,
    )
    anomaly = max(
        (
            value.confidence
            for value in group
            if value.diagnosis_conclusion
            in {DiagnosisConclusion.WARNING, DiagnosisConclusion.FAULT}
        ),
        default=0.0,
    )
    # 同源方法正反结论不做 Dempster 独立组合；保留内部冲突，不用重复支持放大。
    internal_conflict = normal * anomaly
    scale = max(1.0, normal + anomaly)
    return DependencyGroup(
        tuple(value.evidence_id for value in group),
        tuple(sorted(set().union(*(value.dependencies for value in group)))),
        normal / scale,
        anomaly / scale,
        max(0.0, 1.0 - (normal + anomaly) / scale),
        internal_conflict,
    )


def fuse_evidence(evidence: tuple[Evidence, ...]) -> FusionResult:
    """只融合已评估证据，无输入返回全集无知，不从时域数值猜测正常。

    框架是同一对象的 {normal, anomaly}。BPFO/BPFI/gear 等故障命题不构成
    互斥全集，仅由原对象证据保留。整体冲突使用未归一化合取质量累积，
    不用最后一步 K 覆盖先前冲突；不以 Murphy 自我组合伪造独立证据。
    """
    observed = tuple(
        value
        for value in evidence
        if value.evaluation_status == EvaluationStatus.EVALUATED
    )
    if not observed:
        return FusionResult(reason="no_evaluated_evidence")
    groups = tuple(_group_mass(group) for group in dependency_groups(observed))
    normal, anomaly, ignorance = 0.0, 0.0, 1.0
    for group in groups:
        normal, anomaly, ignorance = (
            normal * group.normal_mass
            + normal * group.ignorance_mass
            + ignorance * group.normal_mass,
            anomaly * group.anomaly_mass
            + anomaly * group.ignorance_mass
            + ignorance * group.anomaly_mass,
            ignorance * group.ignorance_mass,
        )
    surviving_mass = normal + anomaly + ignorance
    independent_conflict = max(0.0, min(1.0, 1.0 - surviving_mass))
    conflict = max(
        independent_conflict, max(group.internal_conflict for group in groups)
    )
    if surviving_mass <= 1e-15:
        return FusionResult(groups, conflict=1.0, reason="complete_evidence_conflict")
    return FusionResult(
        groups,
        normal / surviving_mass,
        anomaly / surviving_mass,
        ignorance / surviving_mass,
        conflict,
    )
