"""现场二分类训练入口；只用当前折训练/验证记录，外层与历史记录不参与选优。"""

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
from zoneinfo import ZoneInfo

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from .binary import INITIALIZATIONS, MODEL_PROTOCOL, O9BinaryClassifier, build_classifier
from .catalog import EXPERIMENTS, PACKAGE, REPO_ROOT, sha256_file
from .prepare import iter_partition, write_json
from .preprocessing import PROTOCOL


@dataclass(frozen=True)
class TrainConfig:
    """训练预算必须显式给定；短程批次上限非空时标记为链路试运行。"""

    experiment: str
    fold: int
    initialization: str
    epochs: int
    parameters: str = "ema"
    seed: int = 42
    batch_size: int = 8
    encoder_lr: float = 1e-4
    head_lr: float = 1e-3
    weight_decay: float = 1e-4
    max_train_batches: int | None = None
    device: str = "cpu"


class WindowDataset(Dataset):
    """一次载入一个任务分区，约480/360个窗口，保留每个窗口的记录身份。"""

    def __init__(self, prepared: Path, experiment: str, fold: int, split: str):
        if split not in ("train", "validation"):
            raise ValueError("训练入口只允许训练和验证分区")
        self.rows = list(iter_partition(prepared, experiment, fold, split))
        expected = 8 if split == "train" else 6
        records = {row["record_id"] for row in self.rows}
        if len(records) != expected or len(self.rows) != expected * 60:
            raise ValueError("输入记录或窗口覆盖不完整")
        for record in records:
            group = [r for r in self.rows if r["record_id"] == record]
            if {r["window_index"] for r in group} != set(range(60)):
                raise ValueError("同记录窗口重复或缺失")
            if len({r["label"] for r in group}) != 1:
                raise ValueError("同记录标签不一致")
        if {r["label"] for r in self.rows} != {0, 1}:
            raise ValueError("训练/验证分区必须同时覆盖正常和故障")
        self.x = torch.from_numpy(np.stack([row.pop("x") for row in self.rows]))
        self.y = torch.tensor([row["label"] for row in self.rows], dtype=torch.long)
        self.record_ids = sorted(records)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return self.x[index], self.y[index], index


def seed_training(seed: int) -> None:
    """固定本轮随机状态和线程数，不修改后端线程池或全局系统设置。"""
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(2)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)


def evaluate_validation(model: nn.Module, dataset: WindowDataset, batch_size: int,
                        device: torch.device) -> dict:
    """完整读取本折6份验证记录，以窗口故障分数均值汇总到记录级。"""
    model.eval()
    grouped = {}
    loss_sum = 0.0
    with torch.inference_mode():
        for x, y, indices in DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0, drop_last=False):
            logits = model(x.to(device))
            if not torch.isfinite(logits).all():
                raise ValueError("验证输出出现非有限值")
            loss_sum += float(nn.functional.cross_entropy(logits, y.to(device), reduction="sum"))
            probabilities = logits.softmax(dim=1)[:, 1].cpu().tolist()
            for index, probability in zip(indices.tolist(), probabilities):
                row = dataset.rows[index]
                item = grouped.setdefault(row["record_id"], {
                    "record_id": row["record_id"], "label": row["label"],
                    "nominal_motor_rpm": row["nominal_motor_rpm"],
                    "sequence_group": row["sequence_group"], "window_fault_scores": []})
                item["window_fault_scores"].append(float(probability))
    records = []
    confusion = [[0, 0], [0, 0]]
    for item in grouped.values():
        if len(item["window_fault_scores"]) != 60:
            raise ValueError("验证记录未完整覆盖60窗")
        score = sum(item["window_fault_scores"]) / 60
        predicted = int(score >= .5)
        confusion[item["label"]][predicted] += 1
        records.append(dict(item, mean_fault_score=score, prediction=predicted))
    recalls = [confusion[label][label] / sum(confusion[label]) for label in (0, 1)]
    return {"window_loss": loss_sum / len(dataset), "records": records,
            "record_confusion_true_rows_pred_columns": confusion,
            "record_balanced_accuracy": sum(recalls) / 2,
            "record_accuracy": (confusion[0][0] + confusion[1][1]) / len(records),
            "normal_false_alarms": confusion[0][1], "fault_misses": confusion[1][0],
            "score_is_calibrated_probability": False}


def _check_config(config: TrainConfig) -> None:
    if config.experiment not in EXPERIMENTS or config.fold not in (0, 1, 2):
        raise ValueError("未知实验或折编号")
    if config.initialization not in INITIALIZATIONS or config.parameters not in ("ema", "model"):
        raise ValueError("未知初始化来源")
    for number in (config.epochs, config.batch_size):
        if number < 1:
            raise ValueError("轮数和批量必须为正数")
    for number in (config.encoder_lr, config.head_lr, config.weight_decay):
        if not math.isfinite(number) or number < 0:
            raise ValueError("学习率和权重衰减必须有限且非负")
    if min(config.encoder_lr, config.head_lr) <= 0:
        raise ValueError("学习率必须大于零")
    if config.max_train_batches is not None and config.max_train_batches < 1:
        raise ValueError("短程批次上限必须为正数")
    if config.device not in ("cpu", "cuda"):
        raise ValueError("本轮只接受cpu或cuda，不静默替换硬件")
    if config.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("明确请求CUDA但当前不可用")


def train(prepared: Path, output: Path, config: TrainConfig, checkpoint: Path | None = None,
          resume: Path | None = None) -> dict:
    """执行显式预算，另建目录保存配置、日志、验证预测及best/last任务检查点。"""
    _check_config(config)
    prepared, output = Path(prepared).resolve(), Path(output).resolve()
    allowed = (REPO_ROOT / "tmp/cqu").resolve()
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        raise ValueError("训练输出必须是本仓库tmp/cqu下不存在的新子目录")
    if resume is not None and checkpoint is not None:
        raise ValueError("恢复新任务与初始化旧权重不能同时指定")
    seed_training(config.seed)
    prepared_hash = sha256_file(prepared / "prepared.json")
    train_data = WindowDataset(prepared, config.experiment, config.fold, "train")
    validation_data = WindowDataset(prepared, config.experiment, config.fold, "validation")
    if set(train_data.record_ids) & set(validation_data.record_ids):
        raise ValueError("训练与验证出现同源文件")
    model, initialization = build_classifier(config.initialization if resume is None else "scratch",
                                            checkpoint, config.parameters, config.seed)
    device = torch.device(config.device)
    model.to(device)
    optimizer = torch.optim.AdamW([
        {"params": [p for p in model.encoder.parameters() if p.requires_grad], "lr": config.encoder_lr},
        {"params": model.head.parameters(), "lr": config.head_lr},
    ], weight_decay=config.weight_decay)
    shuffle = torch.Generator().manual_seed(config.seed)
    start_epoch, updates, best_score, best_loss, best_epoch = 0, 0, -1., math.inf, 0
    parent = None
    best_checkpoint_path = None
    if resume is not None:
        resume = Path(resume)
        restored = torch.load(resume, map_location="cpu", weights_only=True)
        if restored["format_version"] != 1 or restored["model_protocol"] != MODEL_PROTOCOL:
            raise ValueError("不是兼容的CQU二分类任务检查点")
        previous_config = restored["config"]
        for name, value in asdict(config).items():
            if name not in ("epochs", "device") and value != previous_config[name]:
                raise ValueError(f"恢复时不允许更换训练协议：{name}")
        if restored["prepared_sha256"] != prepared_hash or restored["input_protocol"] != PROTOCOL:
            raise ValueError("恢复时数据缓存或输入协议已变化")
        model.load_state_dict(restored["model"], strict=True)
        optimizer.load_state_dict(restored["optimizer"])
        start_epoch, updates = restored["epoch"], restored["optimizer_updates"]
        best_score, best_loss, best_epoch = restored["best_score"], restored["best_loss"], restored["best_epoch"]
        best_checkpoint_path = restored["best_checkpoint_path"]
        if start_epoch >= config.epochs:
            raise ValueError("epochs表示总轮数，必须大于已完成轮数")
        initialization = restored["initialization"]
        torch.set_rng_state(restored["torch_rng_state"])
        shuffle.set_state(restored["shuffle_rng_state"])
        if config.device == "cuda" and restored["cuda_rng_state_all"]:
            torch.cuda.set_rng_state_all(restored["cuda_rng_state_all"])
        parent = {"checkpoint_file": resume.name, "sha256": sha256_file(resume), "epoch": start_epoch}
    output.mkdir(parents=True, exist_ok=False)
    model_sources = ("binary.py", "train.py", "prepare.py", "catalog.py", "preprocessing.py")
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    run = {
        "started_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "config": asdict(config), "model_protocol": MODEL_PROTOCOL, "input_protocol": PROTOCOL,
        "class_names": ["normal", "imbalance" if EXPERIMENTS[config.experiment]["device"] == 1 else "outer_race"],
        "initialization": initialization, "resume_parent": parent, "prepared_sha256": prepared_hash,
        "train_record_ids": train_data.record_ids, "validation_record_ids": validation_data.record_ids,
        "held_out_or_historical_evaluated": False,
        "source_sha256": {name: sha256_file(PACKAGE / name) for name in model_sources},
        "o9_upstream": json.loads((PACKAGE.parent / "o9/UPSTREAM.json").read_text(encoding="utf-8")),
        "git_head_before_run": git.stdout.strip() if git.returncode == 0 else None,
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "torch": str(torch.__version__), "cuda_build": torch.version.cuda,
                        "device": str(device), "device_name": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu"},
        "selection_rule": "max_validation_record_balanced_accuracy_then_min_validation_window_loss",
        "smoke_only": config.max_train_batches is not None,
    }
    write_json(output / "run.json", run)
    loader = DataLoader(train_data, batch_size=config.batch_size, shuffle=True, generator=shuffle,
                        num_workers=0, drop_last=False)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    for epoch in range(start_epoch + 1, config.epochs + 1):
        model.train()
        loss_sum, samples, batches = 0., 0, 0
        for x, y, _ in loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(x.to(device))
            loss = nn.functional.cross_entropy(logits, y.to(device))
            if not torch.isfinite(loss):
                raise ValueError("训练损失出现非有限值")
            loss.backward()
            nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1., error_if_nonfinite=True)
            optimizer.step()
            loss_sum += float(loss.detach()) * len(y)
            samples += len(y)
            batches += 1
            updates += 1
            if config.max_train_batches is not None and batches >= config.max_train_batches:
                break
        validation = evaluate_validation(model, validation_data, config.batch_size, device)
        score, val_loss = validation["record_balanced_accuracy"], validation["window_loss"]
        improved = score > best_score or (score == best_score and val_loss < best_loss)
        if improved:
            best_score, best_loss, best_epoch = score, val_loss, epoch
            best_checkpoint_path = str(output / "best.pt")
        write_json(output / f"validation_epoch{epoch:03d}.json", validation)
        metrics = {"epoch": epoch, "optimizer_updates": updates, "train_batches": batches,
                   "train_windows_used": samples, "train_window_loss": loss_sum / samples,
                   "validation_window_loss": val_loss, "validation_record_balanced_accuracy": score,
                   "best_epoch": best_epoch, "smoke_only": run["smoke_only"]}
        with (output / "metrics.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(metrics, ensure_ascii=False, allow_nan=False) + "\n")
        state = {
            "format_version": 1, "model_protocol": MODEL_PROTOCOL, "input_protocol": PROTOCOL,
            "config": asdict(config), "initialization": initialization, "prepared_sha256": prepared_hash,
            "epoch": epoch, "optimizer_updates": updates, "best_epoch": best_epoch,
            "best_score": best_score, "best_loss": best_loss,
            "best_checkpoint_path": best_checkpoint_path,
            "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "optimizer": optimizer.state_dict(), "torch_rng_state": torch.get_rng_state(),
            "shuffle_rng_state": shuffle.get_state(),
            "cuda_rng_state_all": torch.cuda.get_rng_state_all() if device.type == "cuda" else [],
        }
        # 仅覆盖本轮新建目录中的last/best，源权重及既有运行始终保持原样。
        torch.save(state, output / "last.pt")
        if improved:
            torch.save(state, output / "best.pt")
        print(json.dumps(metrics, ensure_ascii=False), flush=True)
    summary = {
        "complete": True, "experiment": config.experiment, "fold": config.fold,
        "epochs_completed_total": config.epochs, "optimizer_updates_total": updates,
        "best_epoch": best_epoch, "best_validation_record_balanced_accuracy": best_score,
        "best_checkpoint_in_this_run": (output / "best.pt").exists(),
        "best_checkpoint_path": best_checkpoint_path,
        "resume_parent": parent, "smoke_only": run["smoke_only"],
        "performance_interpretation": "training_chain_check_only" if run["smoke_only"] else "within_collection_development_validation_only",
        "held_out_or_historical_evaluated": False,
        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else None,
    }
    write_json(output / "summary.json", summary)
    return summary


def main() -> None:
    """命令行要求明确实验、折编号、初始化和总轮数，不自动跑多组实验。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment", choices=EXPERIMENTS, required=True)
    parser.add_argument("--fold", type=int, choices=(0, 1, 2), required=True)
    parser.add_argument("--init", dest="initialization", choices=INITIALIZATIONS, required=True)
    parser.add_argument("--parameters", choices=("ema", "model"), default="ema")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--encoder-lr", type=float, default=1e-4)
    parser.add_argument("--head-lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--max-train-batches", type=int)
    args = vars(parser.parse_args())
    prepared, output, checkpoint, resume = (args.pop(name) for name in ("prepared", "output", "checkpoint", "resume"))
    train(prepared, output, TrainConfig(**args), checkpoint, resume)


if __name__ == "__main__":
    main()
