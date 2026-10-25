"""O9故障分支的现场二分类适配；不修改固定版本的上游模型。"""

from pathlib import Path

import torch
from torch import nn

from training.o9 import O9Encoder, O9MainNet, init_weights
from .catalog import sha256_file


INITIALIZATIONS = {"scratch": None, "epoch55": 55, "stage2": 60, "stage3": 100}
MODEL_PROTOCOL = {
    "version": "o9_fault_mean_pool_binary_v1",
    "input_shape": [1, 4096],
    "feature": "encoder.z_f",
    "pooling": "mean_over_time",
    "head": "Linear(64,2)",
    "loss": "unweighted_cross_entropy",
    "legacy_reconstruction_and_adversarial_losses": False,
    "dropout": 0.1,
}


class O9BinaryClassifier(nn.Module):
    """单个设备/通道任务的独立模型，输出[B,2]未归一化分类分数。"""

    def __init__(self):
        super().__init__()
        self.encoder = O9Encoder(dropout=MODEL_PROTOCOL["dropout"])
        self.head = nn.Linear(64, 2)
        # 编码器完整保留以便严格加载；设备分支没有本轮监督目标。
        for name in ("proj_d_mu", "proj_d_logvar", "norm_d_mu"):
            getattr(self.encoder, name).requires_grad_(False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3 or tuple(x.shape[1:]) != (1, 4096):
            raise ValueError("本轮只接受[B,1,4096]的已预处理单通道窗口")
        features = self.encoder(x)["z_f"].mean(dim=1)
        return self.head(features)


def build_classifier(initialization: str, checkpoint: Path | None = None,
                     parameters: str = "ema", seed: int = 42) -> tuple[O9BinaryClassifier, dict]:
    """新建任务模型；旧参数先完整严格校验，再提取编码器，不恢复旧优化器。"""
    if initialization not in INITIALIZATIONS or parameters not in ("ema", "model"):
        raise ValueError("未知初始化候选或检查点参数组")
    if (initialization == "scratch") != (checkpoint is None):
        raise ValueError("从零初始化不接受旧检查点；微调必须显式提供检查点")
    # 初始化来源不影响新分类头，且构建函数不消耗调用方的CPU随机状态。
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        classifier = O9BinaryClassifier().apply(init_weights)
        metadata = {"initialization": initialization, "checkpoint_parameters": None,
                    "source_epoch": None, "source_sha256": None,
                    "legacy_optimizer_restored": False, "head_seed": seed}
        if checkpoint is not None:
            checkpoint = Path(checkpoint)
            before = sha256_file(checkpoint)
            source = torch.load(checkpoint, map_location="cpu", weights_only=True)
            if source["epoch"] != INITIALIZATIONS[initialization]:
                raise ValueError("检查点轮次与指定候选不符，拒绝错误标记实验")
            if source["n_domains"] != 63 or source["num_faults"] != 5:
                raise ValueError("旧检查点的域数/类别数与已核对来源不符")
            legacy = O9MainNet(n_domains=source["n_domains"], num_faults=source["num_faults"])
            legacy.load_state_dict(source[parameters], strict=True)
            if not all(torch.isfinite(t).all() for t in legacy.state_dict().values()):
                raise ValueError("旧检查点包含非有限参数")
            classifier.encoder.load_state_dict(legacy.encoder.state_dict(), strict=True)
            if sha256_file(checkpoint) != before:
                raise ValueError("旧检查点在读取过程中发生变化")
            metadata.update(checkpoint_parameters=parameters, source_epoch=int(source["epoch"]),
                            source_sha256=before, source_file=checkpoint.name,
                            strict_full_model_tensors=len(source[parameters]),
                            strict_encoder_tensors=len(classifier.encoder.state_dict()))
    return classifier, metadata
