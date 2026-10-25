# o9 编码器 — 连续 Token 编码器（标准卷积版）
#
# 架构：
#   输入:  [B, 1, 4096]
#   输出:  z_d [B, 128, 64]  设备/工况底纹
#          z_f [B, 128, 64]  故障模式指纹
#
# 主干:
#   channel_up(1→8)
#   → EncoderBlock[0~4]: 卷积残差 + 下采样（对称padding，stride=2）
#       累乘32倍（4096→128），主干输出 [B, 256, 128]
# 投影: 三个无偏置 nn.Linear（proj_d_mu / proj_d_logvar / proj_f）拆分双分支
# 约束: 全网络GELU，LayerNorm仅通道维度

from __future__ import annotations

import torch
import torch.nn as nn
from typing import Tuple

from .o9_tools import (
    ChannelLayerNorm,
    DISABLE_TORCH_COMPILING,
)


class EncoderBlock(nn.Module):
    """
    编码器下采样块（标准卷积残差版）。

    结构:
        Conv1d(k=3, s=1, p=1) → ChannelLayerNorm → GELU → Dropout + 残差
        → Conv1d(下采样, k=3, stride=2, p=1)
        → ChannelLayerNorm → GELU → Dropout

    输入:  [B, in_channels, L]
    输出:  [B, out_channels, L // 2]
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        stride: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        kernel_size = 3
        # 卷积残差块（k=3, s=1，通道不变，对称padding）
        self.res_conv = nn.Sequential(
            nn.Conv1d(in_channels, in_channels, kernel_size = kernel_size, stride = 1, padding = kernel_size // 2),
            ChannelLayerNorm(in_channels),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        # 下采样（对称padding）
        self.down = nn.Sequential(
            nn.Conv1d(in_channels, out_channels, kernel_size = kernel_size, stride = stride, padding = kernel_size // 2),
            ChannelLayerNorm(out_channels),
            nn.GELU(),
            nn.Dropout(dropout),
        )

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.res_conv(x) + x
        x = self.down(x)
        return x


class O9Encoder(nn.Module):
    """
    o9 连续 Token 编码器（标准卷积版）。

    设计要点:
        - 全小核(k=3)，参数量低，计算高效
        - 对称padding标准卷积
        - 5层stride=2下采样，累乘32倍 (4096 → 128)

    将 [B, 1, 4096] 原始波形编码为三分支连续隐变量。

    输出:
        z_d: [B, 128, 64]  设备/工况底纹
        z_f: [B, 128, 64]  故障模式指纹
    """

    def __init__(
        self,
        in_channels: int = 1,
        hidden_channels: Tuple[int, ...] = (32, 64, 128, 192, 256),
        z_d_dim: int = 64,
        z_f_dim: int = 64,
        dropout: float = 0.1,
    ):
        super().__init__()

        assert len(hidden_channels) == 5

        # ── 通道扩展: 1 → 8 ──
        self.channel_up = nn.Conv1d(
            in_channels, 8, kernel_size = 1, stride = 1
        )

        # ── 5个标准卷积下采样块 ──
        # 8→32→64→128→192→256, 4096→2048→1024→512→256→128
        self.blocks = nn.Sequential(
            EncoderBlock(8, hidden_channels[0], stride = 2, dropout = dropout),
            EncoderBlock(hidden_channels[0], hidden_channels[1], stride = 2, dropout = dropout),
            EncoderBlock(hidden_channels[1], hidden_channels[2], stride = 2, dropout = dropout),
            EncoderBlock(hidden_channels[2], hidden_channels[3], stride = 2, dropout = dropout),
            EncoderBlock(hidden_channels[3], hidden_channels[4], stride = 2, dropout = dropout),
        )

        final_channels = hidden_channels[-1]

        # z_d: VAE（μ + logvar），概率化设备/工况表示
        # 2 层 MLP 增强解耦能力
        self.proj_d_mu = nn.Sequential(
            nn.Linear(final_channels, 128, bias = False),
            nn.GELU(),
            nn.Linear(128, z_d_dim, bias = False),
        )
        self.proj_d_logvar = nn.Sequential(
            nn.Linear(final_channels, 128, bias = False),
            nn.GELU(),
            nn.Linear(128, z_d_dim, bias = False),
        )

        # z_f: 确定性，FaultBank 锚定故障特征
        self.proj_f = nn.Sequential(
            nn.Linear(final_channels, 128, bias = False),
            nn.GELU(),
            nn.Linear(128, z_f_dim, bias = False),
        )

        # 投影后 LayerNorm（对 [B, T, C] 的最后一维归一化）
        # logvar 不过 LN（范围需自由），mu 过 LN 稳定分布
        self.norm_d_mu = nn.LayerNorm(z_d_dim)
        self.norm_f = nn.LayerNorm(z_f_dim)

    @torch.compile(disable = DISABLE_TORCH_COMPILING)
    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        前向传播。

        输入: x [B, 1, 4096]
        返回: dict {
            'z_d_mu':     [B, 128, 64],  # 设备/工况均值
            'z_d_logvar': [B, 128, 64],  # 设备/工况对数方差
            'z_f':        [B, 128, 64],  # 故障模式（确定性）
            'h':          [B, 128, 256], # 主干输出（时序Token格式 [B, T, C]）
        }

        注意:
            z_d 的概率采样（z_d = mu + eps * exp(0.5*logvar)）
            由调度器在外部控制，forward 只输出参数。
        """
        x = self.channel_up(x)  # [B, 8, 4096]
        x = self.blocks(x)  # [B, 256, 128]

        # 转置为时序Token格式: [B, T, C] = [B, 128, 256]
        h = x.transpose(1, 2)

        # 双分支投影（z_c 已在 o9 中移除）
        z_d_mu = self.proj_d_mu(h)  # [B, 128, 64]
        z_d_logvar = self.proj_d_logvar(h)  # [B, 128, 64]
        z_f = self.proj_f(h)  # [B, 128, 64]

        # 投影后归一化（logvar 不过 LN）
        z_d_mu = self.norm_d_mu(z_d_mu)
        z_f = self.norm_f(z_f)

        return {
            'z_d_mu'    : z_d_mu,
            'z_d_logvar': z_d_logvar,
            'z_f'       : z_f,
            'h'         : h,
        }
