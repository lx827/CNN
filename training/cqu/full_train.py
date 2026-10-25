"""完整O9分阶段训练；默认遍历全部训练窗，显式批次上限才标记短程检查。"""

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import platform
import subprocess
from zoneinfo import ZoneInfo

import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.data import DataLoader, Subset

from training.o9.o9_tools import EMATracker
from .binary import INITIALIZATIONS
from .catalog import EXPERIMENTS, PACKAGE, REPO_ROOT, RPM_LEVELS, sha256_file
from .full_model import CLASS_NAMES, FULL_PROTOCOL, FullStageTrainer, build_full_model, class_ids
from .prepare import write_json
from .preprocessing import PROTOCOL
from .train import WindowDataset, seed_training


@dataclass(frozen=True)
class FullTrainConfig:
    """单任务完整训练预算，旧权重跳过S1，从零依次通过S1和S2。"""

    experiment: str
    fold: int
    initialization: str
    stage1_epochs: int = 5
    stage2_epochs: int = 20
    max_train_batches: int | None = None
    batch_size: int = 8
    seed: int = 42
    parameters: str = "ema"
    device: str = "cpu"


@dataclass(frozen=True)
class FullSmokeConfig(FullTrainConfig):
    """保留先前短程调用接口，不能误当成完整训练。"""

    stage1_epochs: int = 1
    stage2_epochs: int = 2
    max_train_batches: int | None = 2


def evaluate_full(trainer: FullStageTrainer, dataset: WindowDataset, experiment: str,
                  batch_size: int, adversarial_weight: float) -> dict:
    """用EMA完整验证6份记录；六类预测不输入标签，另报正常/任意故障汇总。"""
    model, ema = trainer.model, trainer.ema
    device = next(model.parameters()).device
    grouped, sums = {}, {}
    model.eval()
    ema.apply_shadow(model)
    try:
        with torch.inference_mode():
            for x, binary, indices in DataLoader(dataset, batch_size=batch_size, shuffle=False,
                                               num_workers=0, drop_last=False):
                x, binary = x.to(device), binary.to(device)
                labels = class_ids(binary, experiment)
                out = model(x, sample_z_d=False, use_combiner=False)
                _, terms = trainer.objective(model, out, x, labels, adversarial_weight)
                feature = F.normalize(out["z_f_raw"].mean(dim=1), dim=1, eps=1e-8)
                prototypes = F.normalize(model.fault_bank.prototypes, dim=1, eps=1e-8)
                logits = feature @ prototypes.T / FULL_PROTOCOL["temperature"]
                if not torch.isfinite(logits).all():
                    raise ValueError("验证六类输出包含非有限值")
                terms["six_class_cross_entropy"] = F.cross_entropy(logits, labels)
                for name, value in terms.items():
                    sums[name] = sums.get(name, 0.) + float(value) * len(x)
                for index, label, scores in zip(indices.tolist(), labels.tolist(), logits.softmax(1).tolist()):
                    row = dataset.rows[index]
                    item = grouped.setdefault(row["record_id"], {
                        "record_id": row["record_id"], "binary_label": row["label"], "class_id": label,
                        "nominal_motor_rpm": row["nominal_motor_rpm"],
                        "sequence_group": row["sequence_group"], "window_class_scores": []})
                    item["window_class_scores"].append(scores)
        confusion, binary_confusion, records = [[0] * 6 for _ in range(6)], [[0, 0], [0, 0]], []
        for item in grouped.values():
            if len(item["window_class_scores"]) != 60:
                raise ValueError("验证没有完整覆盖60窗")
            mean_scores = np.mean(item["window_class_scores"], axis=0).tolist()
            predicted = int(np.argmax(mean_scores))
            fault_score = 1. - mean_scores[0]
            binary_prediction = int(fault_score >= .5)
            confusion[item["class_id"]][predicted] += 1
            binary_confusion[item["binary_label"]][binary_prediction] += 1
            records.append(dict(item, mean_class_scores=mean_scores, class_prediction=predicted,
                                binary_fault_score=fault_score, binary_prediction=binary_prediction))
        if len(records) != 6:
            raise ValueError("验证记录数量不符")
        return {"records": records, "mean_losses": {k: v / len(dataset) for k, v in sums.items()},
                "six_class_confusion_true_rows_pred_columns": confusion,
                "binary_confusion_true_rows_pred_columns": binary_confusion,
                "record_balanced_accuracy": sum(binary_confusion[i][i] / sum(binary_confusion[i])
                                                 for i in (0, 1)) / 2,
                "normal_false_alarms": binary_confusion[0][1], "fault_misses": binary_confusion[1][0],
                "score_is_calibrated_probability": False, "parameters": "new_cqu_ema"}
    finally:
        ema.restore_online(model)


def run_training(prepared: Path, output: Path, config: FullTrainConfig,
                 checkpoint: Path | None = None) -> dict:
    """执行完整或显式限批预算，保存完整模型/双优化器/EMA/调度器及阶段状态。"""
    if config.experiment not in EXPERIMENTS or config.fold not in (0, 1, 2):
        raise ValueError("未知实验/折")
    if config.initialization not in INITIALIZATIONS or config.parameters not in ("ema", "model"):
        raise ValueError("未知初始化")
    if min(config.stage1_epochs, config.stage2_epochs, config.batch_size) < 1:
        raise ValueError("轮数和批量必须为正数")
    if config.max_train_batches is not None and config.max_train_batches < 1:
        raise ValueError("显式批次上限必须为正数")
    smoke_only = config.max_train_batches is not None
    if config.device not in ("cpu", "cuda") or (config.device == "cuda" and not torch.cuda.is_available()):
        raise ValueError("设备必须为可用的cpu/cuda，不自动降级")
    prepared, output = Path(prepared).resolve(), Path(output).resolve()
    allowed = (REPO_ROOT / "tmp/cqu").resolve()
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        raise ValueError("输出必须为tmp/cqu下不存在的新目录")
    seed_training(config.seed)
    dataset = WindowDataset(prepared, config.experiment, config.fold, "train")
    validation = WindowDataset(prepared, config.experiment, config.fold, "validation")
    if set(dataset.record_ids) & set(validation.record_ids):
        raise ValueError("训练与验证同源")
    normal_indices = torch.where(dataset.y == 0)[0].tolist()
    domains = torch.tensor([RPM_LEVELS.index(r["nominal_motor_rpm"]) for r in dataset.rows])
    counts = torch.bincount(domains, minlength=3)
    if (counts == 0).any() or not normal_indices:
        raise ValueError("训练来源域或正常样本缺失")
    weights = counts.float().reciprocal()
    weights /= weights.mean()
    model, initialization = build_full_model(config.initialization, checkpoint, config.parameters, config.seed)
    device = torch.device(config.device)
    model.to(device)
    # 在阶段冻结前跟踪全部参数，保证S2解冻后原型/D仍在EMA中。
    ema = EMATracker(model, decay=FULL_PROTOCOL["ema_decay"])
    shuffle = torch.Generator().manual_seed(config.seed)
    stages = [(1, config.stage1_epochs), (2, config.stage2_epochs)] if config.initialization == "scratch" else [(2, config.stage2_epochs)]
    output.mkdir(parents=True, exist_ok=False)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    sources = [PACKAGE / n for n in ("full_model.py", "full_train.py", "train.py", "binary.py",
                                    "catalog.py", "prepare.py", "preprocessing.py")]
    sources += [PACKAGE.parent / "o9" / n for n in ("o9_loss.py", "o9.py", "o9_encoder.py",
                                                    "o9_decoder.py", "o9_tools.py", "fault_bank.py", "classifier.py")]
    run = {
        "started_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "config": asdict(config), "full_protocol": FULL_PROTOCOL, "input_protocol": PROTOCOL,
        "initialization": initialization, "stages": stages, "smoke_only": smoke_only,
        "prepared_sha256": sha256_file(prepared / "prepared.json"),
        "source_sha256": {p.relative_to(REPO_ROOT).as_posix(): sha256_file(p) for p in sources},
        "upstream": json.loads((PACKAGE.parent / "o9/UPSTREAM.json").read_text(encoding="utf-8")),
        "git_head_before_run": git.stdout.strip() if git.returncode == 0 else None,
        "environment": {"python": platform.python_version(), "torch": str(torch.__version__),
                        "numpy": np.__version__, "cuda_build": torch.version.cuda,
                        "device": config.device,
                        "device_name": torch.cuda.get_device_name(0) if config.device == "cuda" else "cpu"},
        "train_record_ids": dataset.record_ids, "validation_record_ids": validation.record_ids,
        "s1_train_record_ids": sorted({dataset.rows[i]["record_id"] for i in normal_indices}) if config.initialization == "scratch" else [],
        "training_domain_window_counts": counts.tolist(), "training_domain_weights": weights.tolist(),
        "held_out_or_historical_evaluated": False,
        "legacy_unobserved_classes_preservation_verified": False,
        "selection": "stage2_only_max_binary_record_balanced_accuracy_then_min_six_class_window_ce",
    }
    write_json(output / "run.json", run)
    best_score, best_loss, best_epoch = -1., math.inf, None
    main_updates = disc_updates = 0
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    for stage, epochs in stages:
        trainer = FullStageTrainer(model, stage, weights.to(device), ema)
        sched_main = torch.optim.lr_scheduler.CosineAnnealingLR(trainer.main, T_max=epochs, eta_min=1e-5)
        sched_disc = torch.optim.lr_scheduler.CosineAnnealingLR(trainer.discriminator, T_max=epochs, eta_min=5e-6)
        selected = Subset(dataset, normal_indices) if stage == 1 else dataset
        loader = DataLoader(selected, batch_size=config.batch_size, shuffle=True, generator=shuffle,
                            num_workers=0, drop_last=False)
        for epoch in range(1, epochs + 1):
            adversarial_weight = 0. if stage == 1 else 3. * (epoch - 1) / max(1, epochs - 1)
            batch_logs = []
            for batch_index, (x, binary, indices) in enumerate(loader):
                labels = class_ids(binary, config.experiment)
                if stage == 1 and labels.any():
                    raise ValueError("S1混入故障记录")
                log = trainer.step(x.to(device), labels.to(device), domains[indices].to(device), adversarial_weight)
                log.update(batch_index=batch_index, windows=len(x))
                batch_logs.append(log)
                main_updates += 1
                disc_updates += int(log["discriminator_updated"])
                if config.max_train_batches is not None and len(batch_logs) >= config.max_train_batches:
                    break
            windows_seen = sum(b["windows"] for b in batch_logs)
            if not smoke_only and (len(batch_logs) != len(loader) or windows_seen != len(selected)):
                raise ValueError("完整轮次没有覆盖全部训练窗口")
            evaluation = evaluate_full(trainer, validation, config.experiment, config.batch_size, adversarial_weight)
            write_json(output / f"validation_s{stage}_epoch{epoch:03d}.json", evaluation)
            score = evaluation["record_balanced_accuracy"]
            loss = evaluation["mean_losses"]["six_class_cross_entropy"]
            improved = stage == 2 and (score > best_score or (score == best_score and loss < best_loss))
            if improved:
                best_score, best_loss, best_epoch = score, loss, epoch
            sched_main.step()
            if any(b["discriminator_updated"] for b in batch_logs):
                sched_disc.step()
            metrics = {"stage": stage, "epoch": epoch, "batches": batch_logs,
                       "main_updates_total": main_updates, "discriminator_updates_total": disc_updates,
                       "train_windows_used": windows_seen, "train_windows_available": len(selected),
                       "train_batches": len(batch_logs),
                       "train_mean_losses": {name: sum(b[name] * b["windows"] for b in batch_logs) / windows_seen
                                             for name in ("main_loss", "recon", "kl", "orth")},
                       "validation_six_class_cross_entropy": loss,
                       "validation_normal_false_alarms": evaluation["normal_false_alarms"],
                       "validation_fault_misses": evaluation["fault_misses"],
                       "validation_record_balanced_accuracy": score, "smoke_only": smoke_only}
            with (output / "metrics.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(metrics, ensure_ascii=False, allow_nan=False) + "\n")
            state = {
                "format": "cqu_o9_full_smoke_v1" if smoke_only else "cqu_o9_full_train_v1",
                "config": asdict(config), "smoke_only": smoke_only,
                "full_protocol": FULL_PROTOCOL, "input_protocol": PROTOCOL,
                "prepared_sha256": run["prepared_sha256"], "initialization": initialization,
                "stage": stage, "epoch_in_stage": epoch, "steps_in_stage": trainer.steps,
                "main_updates_total": main_updates, "discriminator_updates_total": disc_updates,
                "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                "ema": {k: v.cpu() for k, v in ema.state_dict().items()},
                "main_optimizer": trainer.main.state_dict(), "disc_optimizer": trainer.discriminator.state_dict(),
                "main_scheduler": sched_main.state_dict(), "disc_scheduler": sched_disc.state_dict(),
                "torch_rng_state": torch.get_rng_state(), "shuffle_rng_state": shuffle.get_state(),
                "cuda_rng_state_all": torch.cuda.get_rng_state_all() if device.type == "cuda" else [],
                "best_stage2_epoch": best_epoch, "best_score": best_score if best_epoch is not None else None,
                "best_loss": best_loss if best_epoch is not None else None,
            }
            torch.save(state, output / "last.pt")
            if stage == 1 and epoch == epochs:
                torch.save(state, output / "stage1_last.pt")
            if improved:
                torch.save(state, output / "best.pt")
            print(json.dumps({k: v for k, v in metrics.items() if k != "batches"}), flush=True)
    summary = {"complete": True, "smoke_only": smoke_only, "experiment": config.experiment,
               "fold": config.fold, "initialization": config.initialization,
               "main_updates_total": main_updates, "discriminator_updates_total": disc_updates,
               "best_stage2_epoch": best_epoch, "best_checkpoint": str(output / "best.pt"),
               "held_out_or_historical_evaluated": False,
               "full_training_budget_completed": not smoke_only,
               "formal_accuracy_experiment_completed": False,
               "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else None}
    write_json(output / "summary.json", summary)
    return summary


def run_smoke(prepared: Path, output: Path, config: FullSmokeConfig,
              checkpoint: Path | None = None) -> dict:
    """兼容原短程接口，要求显式限批，拒绝伪装成完整训练。"""
    if config.max_train_batches is None:
        raise ValueError("run_smoke必须配置短程批次上限；完整训练使用run_training")
    return run_training(prepared, output, config, checkpoint)


def main() -> None:
    """显式指定单个任务；默认完整轮次，传批次上限时自动标记短程。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment", choices=EXPERIMENTS, required=True)
    parser.add_argument("--fold", type=int, choices=(0, 1, 2), required=True)
    parser.add_argument("--init", dest="initialization", choices=INITIALIZATIONS, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--parameters", choices=("ema", "model"), default="ema")
    parser.add_argument("--stage1-epochs", type=int, default=5)
    parser.add_argument("--stage2-epochs", type=int, default=20)
    parser.add_argument("--max-train-batches", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = vars(parser.parse_args())
    prepared, output, checkpoint = (args.pop(k) for k in ("prepared", "output", "checkpoint"))
    run_training(prepared, output, FullTrainConfig(**args), checkpoint)


if __name__ == "__main__":
    main()
