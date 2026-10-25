"""只读训练日志监视器：终端逐轮结果与无需服务器的本地曲线页面。"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from .catalog import REPO_ROOT


CLASS_NAMES = ("正常", "内圈", "外圈", "滚动体", "保持架", "不平衡")


def read_epochs(path: Path) -> list[dict]:
    """容忍正在写入的末行，其他损坏明确报错，不伪造或补零。"""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    epochs = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1 and not line.endswith("\n"):
                break
            raise ValueError(f"日志损坏：{path.name}第{index + 1}行") from None
        losses = dict(item.get("train_mean_losses", {}))
        batches = item.get("batches", [])
        count = sum(b["windows"] for b in batches)
        if count:
            for key in ("proto", "d_adv", "domain_supervised_loss", "diversity", "z_var", "smooth_d", "f_consist"):
                if all(key in b for b in batches):
                    losses[key] = sum(b[key] * b["windows"] for b in batches) / count
        epochs.append({"stage": item["stage"], "epoch": item["epoch"], "losses": losses,
                       "windows": item.get("train_windows_used", count),
                       "available": item.get("train_windows_available"),
                       "batches": item.get("train_batches", len(batches)),
                       "val_ce": item.get("validation_six_class_cross_entropy"),
                       "val_balanced_accuracy": item["validation_record_balanced_accuracy"],
                       "false_alarms": item.get("validation_normal_false_alarms"),
                       "misses": item.get("validation_fault_misses"),
                       "smoke_only": item["smoke_only"]})
    return epochs


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_progress(runs: Path) -> dict:
    """只读取指定目录的JSON，不导入PyTorch、不读取权重、不启动训练。"""
    runs = Path(runs).resolve()
    if not runs.is_dir():
        raise ValueError("训练目录不存在")
    task = runs.parent
    plan_path = task / "expanded_plan.json"
    if not plan_path.exists():
        plan_path = task / "plan.json"
    plan = _json(plan_path) if plan_path.exists() else {}
    context_path = task / "monitor_context.json"
    context = _json(context_path) if context_path.exists() else {}
    stop_path = task / "stop_status.json"
    status = context.get("status_text")
    if not status:
        status = "已停止" if stop_path.exists() else "只读监视；运行状态未确认"
    items = []
    for folder in sorted(runs.iterdir()):
        manifest_path = folder / "run.json"
        if not folder.is_dir() or not manifest_path.exists():
            continue
        manifest = _json(manifest_path)
        config = manifest["config"]
        epochs = read_epochs(folder / "metrics.jsonl")
        summary = _json(folder / "summary.json") if (folder / "summary.json").exists() else None
        s2 = [e for e in epochs if e["stage"] == 2]
        best_epoch = summary.get("best_stage2_epoch") if summary else None
        if best_epoch is None and s2:
            best_epoch = max(s2, key=lambda e: (e["val_balanced_accuracy"],
                                                -e["val_ce"] if e["val_ce"] is not None else float("-inf")))["epoch"]
        best = next((e for e in s2 if e["epoch"] == best_epoch), None)
        predictions = []
        if best:
            path = folder / f"validation_s2_epoch{best_epoch:03d}.json"
            if path.exists():
                for record in _json(path)["records"]:
                    predictions.append({"rpm": record["nominal_motor_rpm"],
                                        "actual": CLASS_NAMES[record["class_id"]],
                                        "predicted": CLASS_NAMES[record["class_prediction"]],
                                        "fault_score": record["binary_fault_score"],
                                        "binary_prediction": "故障" if record["binary_prediction"] else "正常"})
        metrics_path = folder / "metrics.jsonl"
        modified = metrics_path.stat().st_mtime if metrics_path.exists() else manifest_path.stat().st_mtime
        items.append({"name": folder.name, "experiment": config["experiment"], "fold": config["fold"],
                      "initialization": config["initialization"], "complete": bool(summary and summary["complete"]),
                      "stage1_target": config["stage1_epochs"] if config["initialization"] == "scratch" else 0,
                      "stage2_target": config["stage2_epochs"], "smoke_only": manifest["smoke_only"],
                      "epochs": epochs, "best": best, "predictions": predictions,
                      "last_updated": datetime.fromtimestamp(modified, ZoneInfo("Asia/Shanghai")).isoformat(),
                      "modified": modified})
    completed = sum(item["complete"] for item in items)
    return {"runs": items, "planned": len(plan.get("runs", [])) or len(items), "completed": completed,
            "partial": len(items) - completed, "status_text": status, "context": context,
            "latest_run": max(items, key=lambda r: r["modified"])["name"] if items else None,
            "data_latest": max((r["last_updated"] for r in items), default="尚无日志")}


def write_page(output: Path, progress: dict) -> None:
    """在忽略目录原子更新独立HTML；读训练目录，只有指定页面会被写入。"""
    output = Path(output).resolve()
    allowed = (REPO_ROOT / "tmp/cqu").resolve()
    if not output.is_relative_to(allowed) or output.suffix.lower() != ".html":
        raise ValueError("页面输出必须位于本仓库tmp/cqu内，扩展名为.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(progress, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("monitor.html").read_text(encoding="utf-8")
    temporary = output.with_suffix(".html.next")
    temporary.write_text(template.replace("__TRAINING_DATA__", payload), encoding="utf-8")
    temporary.replace(output)


def format_epoch(run: dict, epoch: dict) -> str:
    """终端每轮一行，未知值保留为--，不把缺失误报计数冒充零。"""
    def number(value, fmt=".4f"):
        return "--" if value is None else format(value, fmt)
    losses = epoch["losses"]
    target = run["stage1_target"] if epoch["stage"] == 1 else run["stage2_target"]
    return (f"[{run['experiment']} 折{run['fold']} {run['initialization']}] "
            f"S{epoch['stage']} {epoch['epoch']:02d}/{target:02d} | 批次{epoch['batches']} 窗口{epoch['windows']} | "
            f"总损失{number(losses.get('main_loss'))} 重构{number(losses.get('recon'))} 原型{number(losses.get('proto'))} | "
            f"验证CE {number(epoch['val_ce'])} 平衡准确率{number(epoch['val_balanced_accuracy'], '.1%')} | "
            f"正常误报{number(epoch['false_alarms'], 'd')} 故障漏报{number(epoch['misses'], 'd')}")


def monitor(runs: Path, output: Path, watch: bool = False, history: bool = False, interval: float = 2.) -> None:
    """终端+页面只读监视；Ctrl+C只关闭监视，不触发或终止模型训练。"""
    if not 1 <= interval <= 60:
        raise ValueError("刷新间隔须为1～60秒")
    seen, previous, first = set(), None, True
    try:
        while True:
            try:
                progress = collect_progress(runs)
                fingerprint = json.dumps(progress, sort_keys=True)
                if fingerprint != previous:
                    write_page(output, progress)
                    print(f"\nO9训练监视 | {progress['status_text']} | 完成{progress['completed']}/{progress['planned']} "
                          f"未完成目录{progress['partial']} | 日志最近更新{progress['data_latest']}", flush=True)
                    print(f"曲线页面：{Path(output).resolve()}\n只读日志，不启动训练；Ctrl+C关闭监视。", flush=True)
                    for run in progress["runs"]:
                        visible = run["epochs"] if history or not first else run["epochs"][-1:]
                        for epoch in visible:
                            key = (run["name"], epoch["stage"], epoch["epoch"])
                            if key not in seen:
                                print(format_epoch(run, epoch), flush=True)
                        seen.update((run["name"], e["stage"], e["epoch"]) for e in run["epochs"])
                    previous = fingerprint
                first = False
            except (OSError, ValueError, KeyError) as error:
                print(f"读取失败，未覆盖上一次页面：{error}", flush=True)
                if not watch:
                    raise
            if not watch:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n监视已关闭；没有启动或停止任何训练进程。", flush=True)


def main() -> None:
    """命令行默认生成一次快照，--watch才持续只读刷新。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--interval", type=float, default=2.)
    args = parser.parse_args()
    monitor(args.runs, args.output, args.watch, args.history, args.interval)


if __name__ == "__main__":
    main()
