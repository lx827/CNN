# o9 内部工具层
#
# 所有 o9 专用工具集中于此，不分散到各模块，不依赖外部非常用工具。
# 仅保留对 PyTorch/NumPy 标准库的必要引用。

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
import math
from typing import List, Literal, Tuple

# o9 全局编译开关（内部定义，不从外部模块导入）
# 本地迁移默认使用eager，CPU/CUDA均不依赖额外编译器。
DISABLE_TORCH_COMPILING = True


# =============================================================================
# 通道维度 LayerNorm
# =============================================================================

@torch.compile(disable = DISABLE_TORCH_COMPILING)
class ChannelLayerNorm(nn.Module):
    """
    仅对通道维度做 LayerNorm。

    输入:  [B, C, L] (Conv1d 格式)
    处理:  transpose → [B, L, C] → LayerNorm(C) → transpose回 [B, C, L]
    """

    def __init__(self, channels: int, bias: bool = True):
        super().__init__()
        self.norm = nn.LayerNorm(channels, elementwise_affine = True, bias = bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, C, L] → [B, L, C] → LayerNorm(C) → [B, C, L]
        x = x.transpose(1, 2)
        x = self.norm(x)
        x = x.transpose(1, 2)
        return x


# =============================================================================
# 频域工具（均为 nn.Module 子类，支持 torch.compile）
# =============================================================================

@torch.compile(disable = DISABLE_TORCH_COMPILING)
class HilbertTransform(nn.Module):
    """
    频域希尔伯特变换。

    输入: signal [B, T]
    输出: analytic_signal [B, T] (复数张量)

    h 向量按长度惰性缓存，训练时仅首次 forward 分配。
    """

    def __init__(self):
        super().__init__()
        self._h_cache: dict[int, torch.Tensor] = {}

    def _get_h(self, N: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        if N not in self._h_cache:
            h = torch.zeros(N, device = device, dtype = dtype)
            if N % 2 == 0:
                h[0] = h[N // 2] = 1.0
                h[1: N // 2] = 2.0
            else:
                h[0] = 1.0
                h[1: (N + 1) // 2] = 2.0
            self._h_cache[N] = h
        # 返回时确保设备 / dtype 匹配（缓存可能来自不同设备）
        return self._h_cache[N].to(device = device, dtype = dtype)

    def forward(self, signal: torch.Tensor) -> torch.Tensor:
        N = signal.shape[-1]
        h = self._get_h(N, signal.device, signal.dtype)
        fft_signal = torch.fft.fft(signal, dim = -1)
        fft_signal = fft_signal * h
        return torch.fft.ifft(fft_signal, dim = -1)


@torch.compile(disable = DISABLE_TORCH_COMPILING)
class EnvelopeSpectrum(nn.Module):
    """
    包络谱计算器（含加窗）。

    输入: signal [B, T]
    输出: envelope_magnitude [B, n_fft//2+1]
    流程: Hilbert变换 → 取模得包络 → 去均值 → Hann加窗 → rfft → 幅度谱
    """

    def __init__(self, n_fft: int):
        super().__init__()
        self.n_fft = n_fft
        self.hilbert = HilbertTransform()
        # 惰性缓存 Hann 窗（按长度索引，避免每次 forward 重建）
        self._windows: dict[int, torch.Tensor] = {}

    def _get_window(self, length: int, device: torch.device) -> torch.Tensor:
        key = (length, device)
        if key not in self._windows:
            self._windows[key] = torch.hann_window(length, device = device)
        return self._windows[key]

    def forward(self, signal: torch.Tensor) -> torch.Tensor:
        # 希尔伯特变换求解析信号
        analytic = self.hilbert(signal)
        # 包络 = |解析信号|
        envelope = torch.abs(analytic)
        # 去直流
        envelope = envelope - torch.mean(envelope, dim = -1, keepdim = True)
        # Hann 加窗（惰性缓存，训练时仅首次分配）
        window = self._get_window(envelope.shape[-1], envelope.device)
        # FFT + 幅度
        spec = torch.fft.rfft(envelope * window, n = self.n_fft, dim = -1)
        magnitude = torch.abs(spec) / self.n_fft
        return magnitude


# =============================================================================
# 多尺度 STFT
# =============================================================================

class MultiScaleSTFT(nn.Module):
    """
    多尺度短时傅里叶变换。

    对同一信号以不同窗口大小做 STFT，输出各尺度的幅度谱或对数幅度谱，
    用于多分辨率频域分析或感知损失。

    参数:
        scales:        窗口大小列表，如 [256, 512, 1024]
        hop_length:    帧移，默认 window // 4（75% 重叠）
        log_scale:     True 输出对数幅度，False 输出线性幅度
        return_db:     True 输出 dB 刻度 (20*log10)，仅 log_scale=True 时生效

    输入:  signal [B, T] 或 [B, 1, T]
    输出:  list of [B, F, N_frames]，每个 scale 一个，F = n_fft//2+1

    先验示例:
        signal = sin(2π·100t) + 0.5·sin(2π·400t)，win=256
        → 幅度谱在 100Hz 和 400Hz 处有谱峰，谱峰频率比 ≈ 4:1
    """

    def __init__(
        self,
        scales: List[int],
        hop_length: int | None = None,
        log_scale: bool = True,
        return_db: bool = False,
    ):
        super().__init__()
        self.scales = scales
        self.hop_length = hop_length
        self.log_scale = log_scale
        self.return_db = return_db
        # 惰性缓存 Hann 窗（按 n_fft+device 索引）
        self._windows: dict[tuple, torch.Tensor] = {}

    def _get_window(self, n_fft: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        key = (n_fft, device)
        if key not in self._windows:
            self._windows[key] = torch.hann_window(n_fft, device = device, dtype = dtype)
        return self._windows[key]

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, signal: torch.Tensor) -> List[torch.Tensor]:
        # 统一 shape: 确保 [B, T]
        if signal.dim() == 3:
            signal = signal.squeeze(1)  # [B, 1, T] → [B, T]

        results = []
        for n_fft in self.scales:
            hop = self.hop_length or n_fft // 4
            window = self._get_window(n_fft, signal.device, signal.dtype)

            # STFT: [B, T] → [B, n_fft//2+1, N_frames]
            # normalized=True 使幅度与信号能量成正比（除以 sqrt(sum(window²))）
            Z = torch.stft(
                signal,
                n_fft = n_fft,
                hop_length = hop,
                win_length = n_fft,
                window = window,
                center = True,
                pad_mode = 'reflect',
                normalized = True,
                onesided = True,
                return_complex = True,
            )
            mag = torch.abs(Z)  # [B, n_fft//2+1, N_frames]

            if self.log_scale:
                if self.return_db:
                    mag = 20.0 * torch.log10(mag + 1e-8)
                else:
                    mag = torch.log(mag + 1e-8)

            results.append(mag)

        return results


# =============================================================================
# 正交投影与对抗损失辅助
# =============================================================================

@torch.compile(disable = DISABLE_TORCH_COMPILING)
def orthogonal_projection_loss(W_list: List[torch.Tensor]) -> torch.Tensor:
    """
    正交投影损失（批量 matmul 版，消除 Python 循环）。

    输入: W_list = [W_d, W_f, W_c]，每个形状 [out_dim, in_dim]
    计算:
        1. 子空间间: sum_{i<j} ||W_i @ W_j.T||_F^2
        2. 子空间内: sum_i ||W_i @ W_i.T - I||_F^2
    返回: 标量损失

    注: 子空间内约束要求 out_dim <= in_dim（行满秩），o9 中投影矩阵
        为 64->64/64/48，满足条件。
    """
    device = W_list[0].device
    dtype = W_list[0].dtype
    n = len(W_list)
    in_dim = W_list[0].size(1)

    # 找出最大 out_dim，零填充对齐到 [n, max_out, in_dim]
    out_dims = [w.size(0) for w in W_list]
    max_out = max(out_dims)
    W_padded = torch.zeros(n, max_out, in_dim, device = device, dtype = dtype)
    for i, w in enumerate(W_list):
        W_padded[i, : out_dims[i]] = w

    # 批量 gram: [n, max_out, max_out]
    gram_all = W_padded @ W_padded.transpose(1, 2)

    # 子空间内损失: sum_i ||W_i @ W_i.T - I_i||²
    # 对每个子空间组装自己的单位阵（仅有效部分参与）
    intra_loss = torch.tensor(0.0, device = device, dtype = dtype)
    for i in range(n):
        d = out_dims[i]
        eye = torch.eye(d, device = device, dtype = dtype)
        diff = gram_all[i, :d, :d] - eye
        intra_loss = intra_loss + (diff * diff).sum()

    # 子空间间损失: sum_{i<j} ||W_i @ W_j.T||²
    # 批量: cross_all[a,b] = W_padded[a] @ W_padded[b].T → [n, n, max_out, max_out]
    cross_all = torch.einsum('aik,bjk->abij', W_padded, W_padded)
    # 上三角 (i<j) 的 Frobenius 平方和（padding 行/列零张量贡献为 0，自动排除无效维度）
    mask = torch.triu(torch.ones(n, n, device = device), diagonal = 1).view(n, n, 1, 1)
    inter_loss = (cross_all * mask).pow(2).sum()

    return intra_loss + inter_loss


# 保留旧实现，标记 deprecated
@torch.compile(disable = DISABLE_TORCH_COMPILING)
def grl_entropy_maximization(logits: torch.Tensor) -> torch.Tensor:
    """
    GRL 对抗熵最大化损失（归一化版，排除类别数偏见）。

    输入: logits [B, K]
    计算: p = softmax; norm_entropy = -sum(p*log(p)) / log(K)
    返回: -norm_entropy（minimize = maximize normalized entropy ∈ [0,1]）

    63 类和 10 类的理想值都是 -1.0，可跨判别器比较。
    """
    K = logits.size(-1)
    p = F.softmax(logits, dim = -1)
    log_p = torch.log(p + 1e-8)
    entropy = -(p * log_p).sum(dim = -1).mean()  # 原始熵
    norm_entropy = entropy / math.log(K)  # 归一化到 [0,1]
    return -norm_entropy


@torch.compile(disable = DISABLE_TORCH_COMPILING)
def pearson_correlation_loss(raw: torch.Tensor, pred: torch.Tensor) -> torch.Tensor:
    """
    皮尔逊相关系数损失函数。

    损失 = 1 - 皮尔逊相关系数（行维度计算，dim=1）
    输入: raw [B, D], pred [B, D]
    返回: 标量损失
    """
    raw_mean = torch.mean(raw, dim = 1, keepdim = True)
    pred_mean = torch.mean(pred, dim = 1, keepdim = True)
    raw_centered = raw - raw_mean
    pred_centered = pred - pred_mean
    dot_product = torch.sum(raw_centered * pred_centered, dim = 1)
    norm_raw = torch.norm(raw_centered, dim = 1)
    norm_pred = torch.norm(pred_centered, dim = 1)
    eps = 1e-8
    pearson_coef = (dot_product / (norm_raw * norm_pred + eps)).mean(dim = 0)
    return 1.0 - pearson_coef


# =============================================================================
# 梯度反转层（GRL）
# =============================================================================

class GradientReversalFunction(torch.autograd.Function):
    """
    梯度反转函数。

    前向: 恒等映射
    反向: grad * (-lambda_)
    """

    @staticmethod
    def forward(ctx, x: torch.Tensor, lambda_: float):
        ctx.lambda_ = lambda_
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad_output: torch.Tensor):
        return -ctx.lambda_ * grad_output, None


class GradientReversalLayer(nn.Module):
    """
    梯度反转层（Gradient Reversal Layer, GRL）。

    前向传播为恒等映射，反向传播时梯度乘以 -lambda_，
    用于对抗训练中"欺骗"判别器。

    lambda_ 由调度器通过 `set_lambda()` 动态控制，
    训练时通常从 0 线性 ramp 到 1。

    输入/输出: [B, ...]（任意形状）
    """

    def __init__(self):
        super().__init__()
        self.lambda_ = 0.0

    def set_lambda(self, lambda_: float):
        self.lambda_ = lambda_

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return GradientReversalFunction.apply(x, self.lambda_)


# =============================================================================
# 时间注意力聚合（替代全局均值池化）
# =============================================================================
@torch.compile(disable = DISABLE_TORCH_COMPILING)
class TimeAttentionPool(nn.Module):
    """
    时间维度注意力聚合。

    用 1x1 Conv 生成注意力权重，在时间维度 softmax 后加权求和，
    替代全局均值池化，保留关键冲击帧信息。

    输入: [B, C, T] (Conv1d 格式)
    输出: [B, C]
    """

    def __init__(self, channels: int):
        super().__init__()
        self.attn_conv = nn.Conv1d(channels, 1, kernel_size = 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, C, T]
        attn = self.attn_conv(x)  # [B, 1, T]
        attn = F.softmax(attn, dim = -1)  # 在时间维度 softmax
        # 加权求和: [B, 1, T] @ [B, T, C] → [B, 1, C]
        x_t = x.transpose(1, 2)  # [B, T, C]
        pooled = torch.bmm(attn, x_t)  # [B, 1, C]
        return pooled.squeeze(1)  # [B, C]


# =============================================================================
# EMA 权重跟踪器
# =============================================================================

class EMATracker:
    """
    EMA（指数移动平均）权重跟踪器。

    训练时维护两套权重：
      - 在线权重（online weights）：正常反向传播更新，响应快但噪声大
      - EMA 权重（shadow weights）：在线权重的指数滑动平均，平滑噪声、泛化更好

    衰减率默认 0.999（大数据集长训练）。

    使用规范（AGENTS.md §9.2）：
        # 推理前
        ema_tracker.apply_shadow()
        with torch.no_grad():
            output = model(x)
        # 推理后（如需继续训练）
        ema_tracker.restore_online()

    保存 checkpoint 时：
        state = {
            'model': model.state_dict(),
            'ema': ema_tracker.state_dict(),
            ...
        }
    """

    def __init__(self, model: nn.Module, decay: float = 0.999, param_filter: callable | None = None):
        """
        参数:
            model:        需要跟踪的模型
            decay:        EMA 衰减率，越大平滑度越高（默认 0.999）
            param_filter: 可选过滤函数，signature: (name: str, param: nn.Parameter) -> bool
                          返回 True 表示该参数需要 EMA。默认所有可学习参数。
        """
        super().__init__()
        self.decay = decay
        self.shadow: dict[str, torch.Tensor] = {}
        self._online_backup: dict[str, torch.Tensor] | None = None
        self._applied = False

        # 构建 shadow 参数字典（与模型参数同设备，避免搬运开销）
        for name, param in model.named_parameters():
            if param_filter is not None and not param_filter(name, param):
                continue
            if param.requires_grad:
                self.shadow[name] = param.data.clone().detach()

        if not self.shadow:
            raise ValueError("EMATracker: 没有可跟踪的参数，请检查模型和 param_filter")

    @torch.compile(disable = DISABLE_TORCH_COMPILING, dynamic = True)
    def update(self, model: nn.Module) -> None:
        """
        执行一次 EMA 更新。

        应在每个训练 step 的 optimizer.step() 之后调用：
            optimizer.step()
            ema_tracker.update(model)
        """
        if self._applied:
            raise RuntimeError("EMATracker.update() 被调用时 EMA shadow 正处于应用状态，"
                               "请先 restore_online()")

        decay = self.decay
        with torch.no_grad():
            for name, param in model.named_parameters():
                if name not in self.shadow:
                    continue
                # shadow 与 param 同设备，原地更新
                self.shadow[name].mul_(decay).add_(param.data, alpha = 1.0 - decay)

    @torch.compile(disable = DISABLE_TORCH_COMPILING, dynamic = True)
    def apply_shadow(self, model: nn.Module) -> None:
        """
        将 EMA shadow 权重应用到模型（推理前调用）。

        会自动备份当前在线权重，供 restore_online() 恢复。
        """
        if self._applied:
            return  # 已应用，幂等
        with torch.no_grad():
            self._online_backup = {}
            for name, param in model.named_parameters():
                if name not in self.shadow:
                    continue
                # 备份在线权重（与 param 同设备）
                self._online_backup[name] = param.data.clone()
                # 应用 shadow（同设备，无需搬运）
                param.copy_(self.shadow[name])

            self._applied = True

    @torch.compile(disable = DISABLE_TORCH_COMPILING, dynamic = True)
    def restore_online(self, model: nn.Module) -> None:
        """
        恢复在线权重（推理后调用，如需继续训练）。

        若未调用过 apply_shadow()，则不做任何事。
        """
        with torch.no_grad():
            if not self._applied or self._online_backup is None:
                return

            for name, param in model.named_parameters():
                if name not in self._online_backup:
                    continue
                param.copy_(self._online_backup[name])

            self._online_backup = None
            self._applied = False

    def state_dict(self) -> dict[str, torch.Tensor]:
        """
        返回 shadow 权重的 state_dict，用于保存 checkpoint。
        """
        return {k: v.clone() for k, v in self.shadow.items()}

    def load_state_dict(self, state_dict: dict[str, torch.Tensor], strict: bool = True) -> None:
        """
        从 state_dict 加载 shadow 权重。

        参数:
            state_dict: 保存的 shadow 权重
            strict:     若为 True，要求 keys 完全匹配；否则允许缺失/多余
        """
        if strict:
            missing = set(self.shadow.keys()) - set(state_dict.keys())
            extra = set(state_dict.keys()) - set(self.shadow.keys())
            if missing:
                raise KeyError(f"EMATracker 加载 state_dict 缺少 keys: {missing}")
            if extra:
                raise KeyError(f"EMATracker 加载 state_dict 有多余 keys: {extra}")

        for k, v in state_dict.items():
            if k in self.shadow:
                # 防御性设备对齐：确保加载的张量与已有 shadow 同设备
                target_device = self.shadow[k].device
                self.shadow[k] = v.clone().to(target_device, non_blocking = True)

    def __len__(self) -> int:
        return len(self.shadow)

    def __contains__(self, name: str) -> bool:
        return name in self.shadow


# =============================================================================
# 权重初始化
# =============================================================================

def init_weights(module: nn.Module) -> None:
    """
    o9 统一权重初始化（递归应用于 module 及其所有子模块）。

    策略:
      - Conv1d / ConvTranspose1d / Linear: kaiming_normal_(fan_in, nonlinearity='linear')
        （自编码器必须用 fan_in，保证每层输出方差 ≈ 输入方差；fan_out 会导致 out_conv
         等少数 fan_out 极小的层权重标准差暴涨，重构输出炸掉。）
      - LayerNorm / ChannelLayerNorm: weight=1.0, bias=0.0
      - Skip连接(1x1 Conv): weight=0, bias=0（初始时 skip 传递零信号）
      - FaultBank 原型向量: normal_(mean=0, std=0.5)
      - nn.Parameter（如原型矩阵）: normal_(mean=0, std=0.5)
    """
    classname = module.__class__.__name__

    # 1) Conv / Linear: Kaiming normal (fan_in, linear)
    #    自编码器必须用 fan_in，保证每层输出方差 ≈ 输入方差，防止信号爆炸/坍缩。
    #    fan_out 会导致 out_conv(16→1) 的权重标准差变为 1.0，重构输出直接炸掉。
    if isinstance(module, (nn.Conv1d, nn.ConvTranspose1d, nn.Linear)):
        nn.init.kaiming_normal_(module.weight, mode = 'fan_in', nonlinearity = 'linear')
        if module.bias is not None:
            nn.init.zeros_(module.bias)

    # 2) LayerNorm / ChannelLayerNorm: weight=1, bias=0
    elif isinstance(module, nn.LayerNorm):
        if module.weight is not None:
            nn.init.ones_(module.weight)
        if module.bias is not None:
            nn.init.zeros_(module.bias)
    elif isinstance(module, ChannelLayerNorm):
        if module.norm.weight is not None:
            nn.init.ones_(module.norm.weight)
        if module.norm.bias is not None:
            nn.init.zeros_(module.norm.bias)

    # 3) FaultBank 类（通过类名识别，因为 fault_bank.py 可能后导入）
    elif 'FaultBank' in classname and hasattr(module, 'prototypes'):
        if isinstance(module.prototypes, nn.Parameter):
            nn.init.normal_(module.prototypes, mean = 0.0, std = 0.5)

    # 4) 独立的 nn.Parameter（遍历所有 Parameter 做兜底）
    for name, param in module.named_parameters(recurse = False):
        if 'prototype' in name.lower() or 'bank' in name.lower() or 'codebook' in name.lower():
            if param.dim() >= 2:
                nn.init.normal_(param, mean = 0.0, std = 0.5)


# =============================================================================
# 一维旋转位置编码（RoPE）
# =============================================================================

@torch.compile(disable = DISABLE_TORCH_COMPILING)
class RoPE1d(nn.Module):
    """
    一维旋转位置编码（Rotary Position Embedding, RoPE）。

    预计算 cos/sin buffer，forward 时对 Q/K 做旋转变换。
    相对位置编码，外推性好，特别适合因果注意力。

    参考: manifold/autoencoder/tools.py WindowRoPE1d
    """

    def __init__(self, d_model: int, max_len: int = 128):
        super().__init__()
        assert d_model % 2 == 0, "d_model 必须为偶数"
        self.d_model = d_model

        # 频率：theta_i = 10000^(-2i/d_model)
        inv_freq = 1.0 / (10000 ** (torch.arange(0, d_model, 2).float() / d_model))
        # 位置 0 ~ max_len-1
        pos = torch.arange(max_len)
        # 外积: [max_len, d_model//2]
        freqs = torch.outer(pos, inv_freq)
        # 注册 buffer（不训练，预计算避免 forward 重复计算）
        self.register_buffer(
            "cos", freqs.cos().repeat(1, 2)[None, :, :]  # [1, max_len, d_model]
        )
        self.register_buffer(
            "sin", freqs.sin().repeat(1, 2)[None, :, :]  # [1, max_len, d_model]
        )

    @staticmethod
    def rotate_half(x: torch.Tensor) -> torch.Tensor:
        """将最后维度对半拆分并旋转: [-x2, x1]"""
        x1, x2 = x.chunk(2, dim = -1)
        return torch.cat((-x2, x1), dim = -1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        对输入 x 应用 RoPE。

        输入: x [B, T, d_model]
        输出: x_rotated [B, T, d_model]
        """
        T = x.size(1)
        return x * self.cos[:, :T, :] + self.rotate_half(x) * self.sin[:, :T, :]


# =============================================================================
# 极简因果 Transformer 块（当前未使用，保留备用）
# =============================================================================
