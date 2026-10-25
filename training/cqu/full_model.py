"""完整O9的CQU适配：六类原型、三个转速域及分阶段原损失。"""

from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from training.o9 import O9MainNet, init_weights
from training.o9.o9_loss import (
    O9ReconstructionLoss, O9KLDivergenceLoss, O9OrthogonalLoss,
    O9DomainAdversarialLoss, O9FaultPrototypeLoss, O9TemporalSmoothnessLoss,
    O9FaultConsistencyLoss, O9FeatureVarianceLoss,
)
from training.o9.o9_tools import EMATracker, MultiScaleSTFT
from .binary import INITIALIZATIONS
from .catalog import EXPERIMENTS, RPM_LEVELS, sha256_file


CLASS_NAMES = ("normal", "inner_race", "outer_race", "ball", "cage", "imbalance")
FULL_PROTOCOL = {
    "version": "o9_full_cqu_six_classes_v1",
    "classes": list(CLASS_NAMES), "domains_motor_rpm": list(RPM_LEVELS),
    "independent_experiments": True, "temperature": 0.1,
    "domain_objective": "minimize_negative_normalized_entropy_without_grl",
    "discriminator_main_step": "eval_and_frozen",
    "s1": "training_normal_only_no_vae_sampling_bank_and_domain_frozen",
    "s2": "all_training_labels_vae_sampling_alternating_raw_and_bank",
    "augmentation": "none", "ema_decay": 0.999,
    "domain_weighting": "inverse_training_window_counts_normalized_to_mean_one",
    "domain_updates": "two_of_each_three_main_updates",
    "adversarial_ramp": "linear_0_to_3_over_stage2_epochs_once",
    "validation": "six_way_mean_softmax_per_record_binary_fault_score_1_minus_normal",
    "stft_reflect_padding": "equivalent_slice_flip_concat_for_deterministic_cuda_backward",
}


class DeterministicMultiScaleSTFT(MultiScaleSTFT):
    """等价显式反射补边，绕过PyTorch CUDA反射补边的非确定性反向。"""

    def forward(self, signal: torch.Tensor) -> list[torch.Tensor]:
        if signal.ndim == 3:
            signal = signal.squeeze(1)
        results = []
        for n_fft in self.scales:
            padding = n_fft // 2
            if signal.shape[-1] <= padding:
                raise ValueError("反射补边要求输入长于补边长度")
            padded = torch.cat((signal[:, 1:padding + 1].flip(-1), signal,
                                signal[:, -padding - 1:-1].flip(-1)), dim=-1)
            spectrum = torch.stft(padded, n_fft=n_fft, hop_length=self.hop_length or n_fft // 4,
                                  win_length=n_fft, window=self._get_window(n_fft, signal.device, signal.dtype),
                                  center=False, normalized=True, onesided=True, return_complex=True)
            magnitude = spectrum.abs()
            if self.log_scale:
                magnitude = 20. * torch.log10(magnitude + 1e-8) if self.return_db else torch.log(magnitude + 1e-8)
            results.append(magnitude)
        return results


def class_ids(binary_labels: torch.Tensor, experiment: str) -> torch.Tensor:
    """保留旧五类顺序；两台的故障分别映射到不平衡5和外圈2。"""
    if experiment not in EXPERIMENTS or not torch.all((binary_labels == 0) | (binary_labels == 1)):
        raise ValueError("未知实验或非二值现场标签")
    return binary_labels * (5 if EXPERIMENTS[experiment]["device"] == 1 else 2)


def build_full_model(initialization: str, checkpoint: Path | None = None,
                     parameters: str = "ema", seed: int = 42) -> tuple[O9MainNet, dict]:
    """严格验证全部旧参数；迁入编码器/解码器/五原型，新增一原型和三域判别器。"""
    if initialization not in INITIALIZATIONS or parameters not in ("ema", "model"):
        raise ValueError("未知初始化或旧参数组")
    if (initialization == "scratch") != (checkpoint is None):
        raise ValueError("从零不接受旧权重；微调必须提供旧权重")
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        model = O9MainNet(n_domains=3, num_faults=6).apply(init_weights)
        metadata = {"initialization": initialization, "checkpoint_parameters": None,
                    "legacy_optimizer_restored": False, "seed": seed,
                    "new_parameters": ["fault_bank.prototypes[5]", "D_d.*"]}
        if checkpoint is not None:
            checkpoint = Path(checkpoint)
            before = sha256_file(checkpoint)
            source = torch.load(checkpoint, map_location="cpu", weights_only=True)
            if (source["epoch"] != INITIALIZATIONS[initialization]
                    or source["n_domains"] != 63 or source["num_faults"] != 5):
                raise ValueError("旧检查点候选轮次/域数/类别不匹配")
            legacy = O9MainNet(n_domains=63, num_faults=5)
            legacy.load_state_dict(source[parameters], strict=True)
            if not all(torch.isfinite(t).all() for t in legacy.state_dict().values()):
                raise ValueError("旧模型包含非有限参数")
            model.encoder.load_state_dict(legacy.encoder.state_dict(), strict=True)
            model.decoder.load_state_dict(legacy.decoder.state_dict(), strict=True)
            with torch.no_grad():
                model.fault_bank.prototypes[:5].copy_(legacy.fault_bank.prototypes)
            if before != sha256_file(checkpoint):
                raise ValueError("源权重读取过程中发生变化")
            metadata.update(checkpoint_parameters=parameters, source_file=checkpoint.name,
                            source_sha256=before, source_epoch=int(source["epoch"]),
                            strict_full_model_tensors=len(source[parameters]),
                            transferred=["encoder.*", "decoder.*", "fault_bank.prototypes[:5]"])
    return model, metadata


def prototype_logits(model: O9MainNet, x: torch.Tensor) -> torch.Tensor:
    """预测只使用信号本身；不传真实标签，不走标签条件原型组合路径。"""
    feature = F.normalize(model.encoder(x)["z_f"].mean(dim=1), dim=1, eps=1e-8)
    prototypes = F.normalize(model.fault_bank.prototypes, dim=1, eps=1e-8)
    return feature @ prototypes.T / FULL_PROTOCOL["temperature"]


class FullObjective(nn.Module):
    """采用固定版本S1/S2的损失及权重；域对抗去掉多余梯度反转。"""

    def __init__(self, stage: int, domain_weights: torch.Tensor):
        super().__init__()
        if stage not in (1, 2):
            raise ValueError("阶段必须为1或2")
        self.stage = stage
        self.recon = O9ReconstructionLoss(alpha=1.)
        self.recon.ms_stft = DeterministicMultiScaleSTFT(
            scales=[256, 512, 1024, 2048], log_scale=False, return_db=False)
        self.kl = O9KLDivergenceLoss(alpha=1e-5)
        self.orth = O9OrthogonalLoss(alpha=.5 if stage == 1 else .1)
        self.smooth_d = O9TemporalSmoothnessLoss(alpha=1e-5 if stage == 1 else 2e-5)
        self.f_consist = O9FaultConsistencyLoss(alpha=1e-4 if stage == 1 else 4e-4)
        self.z_var = O9FeatureVarianceLoss(alpha=1e-2 if stage == 1 else 1e-4,
                                         threshold=.01 if stage == 1 else .1)
        self.domain = O9DomainAdversarialLoss(alpha=3., class_weights=domain_weights, name="d")
        self.proto = O9FaultPrototypeLoss(alpha=2., contrastive_alpha=2., temperature=.1)

    def forward(self, model: O9MainNet, out: dict, x: torch.Tensor,
                labels: torch.Tensor, adversarial_weight: float) -> tuple[torch.Tensor, dict]:
        terms = {}
        calls = (
            (self.recon, (out["x_hat"], x)),
            (self.kl, (out["z_d_mu"], out["z_d_logvar"])),
            (self.orth, ([model.encoder.proj_d_mu[-1].weight,
                           model.encoder.proj_f[-1].weight],)),
            (self.smooth_d, (out["z_d"],)),
            (self.f_consist, (out["z_f_raw"],)),
            (self.z_var, (out["z_f_raw"],)),
        )
        total = x.new_zeros(())
        for criterion, args in calls:
            value, info = criterion(*args)
            total = total + value
            terms.update(info)
        if self.stage == 2:
            value, info = self.proto(out["z_f_raw"], F.one_hot(labels, 6).float(),
                                     model.fault_bank.prototypes)
            total = total + value
            terms.update(info)
            distances = torch.pdist(model.fault_bank.prototypes)
            terms["diversity"] = .3 * torch.relu(1. - distances).mean()
            # 直接最小化负熵，让编码器提高域预测的不确定性；D固定但允许梯度通过输入。
            value, info = self.domain(model.D_d(out["z_f_raw"]), None)
            terms.update(info)
            total = total + terms["diversity"] + adversarial_weight * value
        if not torch.isfinite(total) or not all(torch.isfinite(v).all() for v in terms.values()):
            raise ValueError("完整O9损失出现非有限值")
        terms["main_loss"] = total
        return total, terms


class FullStageTrainer:
    """单阶段优化状态；阶段切换新建优化器，模型和EMA延续。"""

    def __init__(self, model: O9MainNet, stage: int, domain_weights: torch.Tensor,
                 ema: EMATracker, lr_main: float = 1e-4, lr_disc: float = 5e-5):
        self.model, self.stage, self.ema = model, stage, ema
        model.requires_grad_(True)
        model.fault_bank.requires_grad_(stage == 2)
        model.D_d.requires_grad_(stage == 2)
        self.main_parameters = list(model.encoder.parameters()) + list(model.decoder.parameters())
        if stage == 2:
            self.main_parameters += list(model.fault_bank.parameters())
        self.main = torch.optim.AdamW(self.main_parameters, lr=lr_main, weight_decay=1e-4)
        self.discriminator = torch.optim.AdamW(model.D_d.parameters(), lr=lr_disc, weight_decay=1e-4)
        self.objective = FullObjective(stage, domain_weights).to(next(model.parameters()).device)
        self.steps = self.discriminator_steps = 0

    def step(self, x: torch.Tensor, labels: torch.Tensor, domains: torch.Tensor,
             adversarial_weight: float) -> dict:
        """判别器只收detach特征；主更新固定D，重算前向，交替原始/原型重构。"""
        model = self.model
        model.train()
        model.zero_grad(set_to_none=True)
        disc_loss, disc_norm = x.new_zeros(()), x.new_zeros(())
        update_disc = self.stage == 2 and self.steps % 3 < 2
        if update_disc:
            model.D_d.requires_grad_(True)
            with torch.no_grad():
                detached = model.encoder(x)["z_f"]
            disc_loss, _ = self.objective.domain(model.D_d(detached), domains)
            if not torch.isfinite(disc_loss):
                raise ValueError("域监督损失出现非有限值")
            disc_loss.backward()
            disc_norm = nn.utils.clip_grad_norm_(model.D_d.parameters(), 10., error_if_nonfinite=True)
            self.discriminator.step()
            self.discriminator_steps += 1
            model.zero_grad(set_to_none=True)
        model.D_d.eval().requires_grad_(False)
        bank_path = self.stage == 2 and self.steps % 2 == 0
        out = model(x, sample_z_d=self.stage == 2, use_combiner=bank_path,
                    fault_mask=F.one_hot(labels, 6).float() if bank_path else None)
        loss, terms = self.objective(model, out, x, labels, adversarial_weight)
        loss.backward()
        main_norm = nn.utils.clip_grad_norm_(self.main_parameters, 20., error_if_nonfinite=True)
        self.main.step()
        model.zero_grad(set_to_none=True)
        self.ema.update(model)
        self.steps += 1
        # 便于下一个判别器更新；不改变主更新阶段实际冻结行为。
        model.D_d.requires_grad_(self.stage == 2)
        return {**{k: float(v.detach()) for k, v in terms.items()},
                "domain_supervised_loss": float(disc_loss.detach()),
                "main_grad_norm_before_clip": float(main_norm),
                "disc_grad_norm_before_clip": float(disc_norm),
                "bank_reconstruction_path": bank_path, "discriminator_updated": update_disc,
                "adversarial_weight": adversarial_weight}
