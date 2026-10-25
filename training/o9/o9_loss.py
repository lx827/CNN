# o9 损失函数族
#
# 全部继承 _LossBase，alpha 在 __init__ 中唯一确定：
#   O9ReconstructionLoss      — 波形L1 + 对数FFT + 包络谱L2
#   O9OrthogonalLoss          — 子空间间/子空间内正交投影
#   O9DomainAdversarialLoss   — 工况判别（有标签CE + 无标签GRL熵最大）
#   ~~O9FaultAdversarialLoss~~  — 已移除（D_f 已移除，-entropy 塌缩无效）
#   O9FaultPrototypeLoss      — z_f 与 FaultBank 原型对比
#   ~~O9SparseCombinationLoss~~ — 已移除（未使用）
#   O9KLDivergenceLoss        — z_d VAE 的 KL 散度约束
#   ~~O7ZeroInputLoss~~        — 已移除（未使用）
#
# forward 统一返回 tuple[torch.Tensor, dict[str, torch.Tensor]]
#   total: 加权后的总损失（已乘 alpha）
#   info : 各子项的字典，键通过 _tag 自动加 name 前缀

from __future__ import annotations

import torch
import torch.nn as nn

from .o9_tools import DISABLE_TORCH_COMPILING, pearson_correlation_loss
import torch.nn.functional as F


# =============================================================================
# 基类（与 o6 一致）
# =============================================================================
class _LossBase(nn.Module):
    """
    损失函数基类。

    alpha: 损失权重，在 __init__ 中唯一确定，forward 不再接收额外缩放。
    name : 可选前缀，解决多实例键冲突。
    """

    def __init__(self, alpha: float = 1.0, name: str | None = None):
        super().__init__()
        self.alpha = alpha
        self.name = name

    def _tag(self, key: str) -> str:
        return f"{self.name}_{key}" if self.name else key


# =============================================================================
# 重构损失（波形 + 对数FFT + 包络谱）
# =============================================================================

class O9ReconstructionLoss(_LossBase):
    """
    重构损失（线性幅度谱版）。

    组成:
        - 波形 MSE: F.mse_loss(x_hat, x)
        - FFT 幅度谱 MSE: |||FFT(x_hat)| - |FFT(x)|||_2^2
        - 包络谱 MSE: ||EnvSpec(x_hat) - EnvSpec(x)||_2^2
        - 多尺度 STFT 幅度谱 MSE（256/512/1024/2048）

    输入: x_hat [B, 1, L], x [B, 1, L]
    返回: (总损失, 子项字典)
    """

    def __init__(
        self,
        alpha: float = 5.0,
        n_fft: int = 4096,
        stft_scales: list[int] | None = None,
        stft_alpha: float = 1.0,
        name: str | None = None,
    ):
        super().__init__(alpha, name)
        from .o9_tools import EnvelopeSpectrum, MultiScaleSTFT
        self.envelope = EnvelopeSpectrum(n_fft = n_fft)
        self.ms_stft = MultiScaleSTFT(
            scales = stft_scales or [256, 512, 1024, 2048],
            log_scale = False,
            return_db = False,
        )
        self.stft_alpha = stft_alpha
        self.mse = nn.MSELoss()
        self.n_fft = n_fft

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, x_hat: torch.Tensor, x: torch.Tensor) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        # 波形 MSE
        loss_wave = self.mse(x_hat, x) * 0.1

        # 展平为 [B, L] 以匹配频域工具输入
        x_hat_s = x_hat.squeeze(1)
        x_s = x.squeeze(1)

        # 时域皮尔逊相似性
        loss_wave_like = pearson_correlation_loss(x_hat_s, x_s)

        # FFT 幅度谱 MSE（线性幅度，加窗）
        window = torch.hann_window(x_s.shape[-1], device = x_s.device)
        fft_hat = torch.fft.rfft(x_hat_s * window, n = self.n_fft, dim = -1).abs() / self.n_fft
        fft_x = torch.fft.rfft(x_s * window, n = self.n_fft, dim = -1).abs() / self.n_fft
        loss_fft = self.mse(fft_hat, fft_x) * 100

        # 频域皮尔逊相似性
        loss_fft_like = pearson_correlation_loss(fft_hat, fft_x)

        # 包络谱 MSE
        env_hat = self.envelope(x_hat_s)
        env_x = self.envelope(x_s)
        loss_env = self.mse(env_hat, env_x) * 100

        # 包络谱皮尔逊相似性
        loss_env_like = pearson_correlation_loss(env_hat, env_x)

        # 多尺度 STFT 幅度谱 MSE + 皮尔逊相似性
        stft_hat = self.ms_stft(x_hat_s)
        stft_x = self.ms_stft(x_s)
        loss_stft = sum(
            self.mse(h, r)
            for h, r in zip(stft_hat, stft_x)
        )

        loss_stft_like = sum(
            pearson_correlation_loss(
                h.reshape(h.size(0), -1),
                r.reshape(r.size(0), -1),
            )
            for h, r in zip(stft_hat, stft_x)
        ) * 0.1

        # 先乘 alpha，再相加，避免重复计算
        loss_wave = loss_wave * self.alpha
        loss_wave_like = loss_wave_like * self.alpha
        loss_fft = loss_fft * self.alpha
        loss_fft_like = loss_fft_like * self.alpha
        loss_env = loss_env * self.alpha
        loss_env_like = loss_env_like * self.alpha
        loss_stft = loss_stft * self.alpha * self.stft_alpha
        loss_stft_like = loss_stft_like * self.alpha * self.stft_alpha

        total = (
                loss_wave + loss_wave_like
                + loss_fft + loss_fft_like
                + loss_env + loss_env_like
                + loss_stft + loss_stft_like
        )
        return total, {
            self._tag('recon')          : total,
            self._tag('recon_wave')     : loss_wave,
            self._tag('recon_wave_like'): loss_wave_like,
            self._tag('recon_fft')      : loss_fft,
            self._tag('recon_fft_like') : loss_fft_like,
            self._tag('recon_env')      : loss_env,
            self._tag('recon_env_like') : loss_env_like,
            self._tag('recon_stft')     : loss_stft,
            self._tag('recon_stft_like'): loss_stft_like,
        }


# =============================================================================
# KL 散度损失（z_d VAE）
# =============================================================================

class O9KLDivergenceLoss(_LossBase):
    """
    z_d 分支的 KL 散度损失。

    约束 z_d 的隐空间接近标准正态分布 N(0, I)，
    使设备/工况表示具有结构化先验，提升 unseen 设备泛化。

    公式: KL(q(z|x) || p(z)) = -0.5 * Σ(1 + logvar - mu² - exp(logvar))

    输入: mu [B, T, D], logvar [B, T, D]
    返回: (总损失, 子项字典)

    注意: z_f 保持确定性，不加 KL。
    """

    def __init__(self, alpha: float = 0.001, name: str | None = None):
        super().__init__(alpha, name)

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, mu: torch.Tensor, logvar: torch.Tensor) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        # mu, logvar: [B, T, D]
        kl = -0.5 * torch.sum(
            1 + logvar - mu.pow(2) - logvar.exp(),
            dim = -1,
        )  # [B, T]
        loss = self.alpha * kl.mean()
        return loss, {self._tag('kl'): loss}


# =============================================================================
# 正交投影损失
# =============================================================================

class O9OrthogonalLoss(_LossBase):
    """
    正交投影损失。

    约束双分支投影矩阵的子空间互相正交、各自内部行向量正交归一化，
    防止 z_d / z_f 共线泄露。

    输入: W_list = [W_d, W_f, W_c, ...]，每个 W_i 形状 [out_dim, in_dim]
    返回: (总损失, 子项字典)
    """

    def __init__(self, alpha: float = 1.0, name: str | None = None):
        super().__init__(alpha, name)

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, W_list: list[torch.Tensor]) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        from .o9_tools import orthogonal_projection_loss
        loss = self.alpha * orthogonal_projection_loss(W_list)
        return loss, {self._tag('orth'): loss}


# =============================================================================
# 域对抗损失
# =============================================================================

class O9DomainAdversarialLoss(_LossBase):
    """
    域对抗损失。

    双模式（由 domain_ids 参数控制）：
      - 有标签（domain_ids 不为 None）：训练判别器，CE(domain_logits, domain_ids)
      - 无标签（domain_ids 为 None）：GRL + MSE→均匀分布（LSGAN 风格）

    class_weights: [n_domains] 每域权重，自动均衡样本量差异。
                   传入 None 则等权。

    输入:
        domain_logits: [B, n_domains]
        domain_ids:    [B]（int64）或 None
    返回: (总损失, 子项字典)
    """

    def __init__(self, alpha: float = 1.5, class_weights: torch.Tensor | None = None, name: str | None = None):
        super().__init__(alpha, name)
        self.ce = nn.CrossEntropyLoss(weight = class_weights)

    def set_class_weights(self, class_weights: torch.Tensor) -> None:
        """动态更新类别权重（如从数据集统计计算）。"""
        self.ce.weight = class_weights

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(
        self,
        domain_logits: torch.Tensor,
        domain_ids: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        if domain_ids is not None:
            loss = self.alpha * self.ce(domain_logits, domain_ids)
            return loss, {self._tag('sup'): loss}
        else:
            from .o9_tools import grl_entropy_maximization
            loss = self.alpha * grl_entropy_maximization(domain_logits)
            return loss, {self._tag('adv'): loss}


# =============================================================================
# 故障原型损失
# =============================================================================

class O9FaultPrototypeLoss(_LossBase):
    """
    故障原型对比损失（L2 归一化原型 + z_f 归一化 + temperature BCE + softmax CE contrastive）。

    - 训练/评估度量统一：对 z_f 和 prototypes 均做 L2 归一化，使 logits = cosine / temperature，
      训练目标直接优化热图上的 cosine 相似度，而不是模长与 cosine 的耦合项。
    - temperature 放大 logits 范围（默认 0.1），保证 BCE 在高 cosine 区仍有充足梯度。
    - BCE 逐位拉近/推远各原型。
    - softmax CE 额外提供全局推斥力：z_f 不仅靠近目标原型，还被推向远离非目标原型。

    输入:
        z_f:            [B, T, F]
        fault_ids:      [B, K] 多标签
        prototypes:     nn.Parameter [K, F]（未归一化）
        sample_weights: [B] 可选，每样本权重。None=等权
    返回: (总损失, 子项字典)
    """

    def __init__(self, alpha: float = 1.0, contrastive_alpha: float = 0.5, temperature: float = 0.1, name: str | None = None):
        super().__init__(alpha, name)
        self.contrastive_alpha = contrastive_alpha
        self.temperature = temperature
        self.bce = nn.BCEWithLogitsLoss(reduction = 'none')

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(
        self,
        z_f: torch.Tensor,
        fault_ids: torch.Tensor,
        prototypes: torch.Tensor,
        sample_weights: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        # L2 归一化原型到单位球面
        proto_norm = F.normalize(prototypes, dim = 1, eps = 1e-8)  # [K, F]

        # 对 z_f 帧平均后归一化，使训练目标直接对齐纯 cosine 相似度
        z_f_mean = z_f.mean(dim = 1)  # [B, F]
        z_f_norm = F.normalize(z_f_mean, dim = 1, eps = 1e-8)  # [B, F]

        # 纯 cosine 相似度，用 temperature 放大 logits 范围以增强梯度
        # temperature=0.1 时，cosine=0.8 对应 logit=8.0，BCE 仍有强梯度继续拉近
        logits = (z_f_norm @ proto_norm.T) / self.temperature  # [B, K]

        per_sample_loss = self.bce(logits, fault_ids).mean(dim = 1)  # [B]

        # Contrastive（softmax CE，仅对单标签样本生效）
        # 对于多标签/混合故障，不做 softmax CE（避免强行推斥）
        row_sums = fault_ids.sum(dim = 1)  # [B]
        is_single_label = (row_sums == 1.0)  # 单标签（含健康）
        loss_ce = 0.0
        if is_single_label.any():
            targets = fault_ids[is_single_label].argmax(dim = 1)  # [B']
            logits_ce = logits[is_single_label]  # [B', K]
            loss_ce = F.cross_entropy(logits_ce, targets, reduction = 'mean')

        if sample_weights is not None:
            per_sample_loss = per_sample_loss * sample_weights

        loss = self.alpha * (per_sample_loss.mean() + self.contrastive_alpha * loss_ce)
        return loss, {self._tag('proto'): loss}


# =============================================================================
# 时序平滑损失（z_d 强 L2 平滑）
# =============================================================================

class O9TemporalSmoothnessLoss(_LossBase):
    """
    时序平滑损失。

    约束 Token 序列在时间上连续渐变，防止相邻帧输出剧烈跳变。
    主要用于 z_d（设备底纹），因为工况（转速、负载）是慢变的，
    相邻 Token 的 z_d 不应该在 7.8ms（1/128s）内剧烈抖动。

    输入: z [B, T, C]
    返回: (总损失, 子项字典)
    """

    def __init__(self, alpha: float = 0.1, name: str | None = None):
        super().__init__(alpha, name)

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, z: torch.Tensor) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        # z: [B, T, C]
        diff = z[:, 1:, :] - z[:, :-1, :]  # [B, T-1, C]
        loss = self.alpha * (diff ** 2).mean()
        return loss, {self._tag('smooth_d'): loss}


# =============================================================================
# 故障帧间一致性损失（z_f 段均值惩罚）
# =============================================================================

class O9FaultConsistencyLoss(_LossBase):
    """
    故障指纹帧间一致性损失。

    约束 z_f 在整段信号内保持恒定（或极慢变）。
    物理意义：故障类型是信号的全局属性（"这段有外圈故障，严重程度 0.8"），
    不应该帧级跳变。冲击的时域位置应由解码器定位。

    实现：惩罚每帧 z_f 偏离段均值的程度。

    输入: z_f [B, T, F]
    返回: (总损失, 子项字典)
    """

    def __init__(self, alpha: float = 0.1, name: str | None = None):
        super().__init__(alpha, name)

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, z_f: torch.Tensor) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        # z_f: [B, T, F]
        z_mean = z_f.mean(dim = 1, keepdim = True)  # [B, 1, F]，段均值
        loss = self.alpha * ((z_f - z_mean) ** 2).mean()
        return loss, {self._tag('f_consist'): loss}


# =============================================================================
# 特征方差正则（防坍缩）
# =============================================================================

class O9FeatureVarianceLoss(_LossBase):
    """
    特征方差正则损失（防坍缩）。

    防止编码器输出整体坍缩到零或彼此相似。
    通过 hinge 损失约束各通道标准差不低于阈值，
    只在坍缩时惩罚，不限制大方差。

    输入: 任意数量的 z 张量，每个 [B, T, C]
    返回: (总损失, 子项字典)
    """

    def __init__(self, alpha: float = 0.01, threshold: float = 0.1, name: str | None = None):
        super().__init__(alpha, name)
        self.threshold = threshold

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, *zs: torch.Tensor) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        loss = torch.tensor(0.0, device = zs[0].device, dtype = zs[0].dtype)
        for z in zs:
            # z: [B, T, C]
            std = z.std(dim = (0, 1))  # [C]，每通道标准差
            loss = loss + torch.relu(self.threshold - std).mean()
        loss = self.alpha * loss
        return loss, {self._tag('z_var'): loss}
