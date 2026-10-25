# o9 解码器 — 标准转置卷积解码器
#
# 架构：
#   输入:  z_d [B, 128, 64], z_f [B, 128, 64]
#   拼接:  [B, 128, 176] → 转置为 [B, 176, 128]（Conv1d格式）
#   上采样: 5层 ConvTranspose1d(k=3, s=2, p=1, op=1)，累乘32倍（128→4096）
#   输出:  [B, 1, 4096]
#
# 约束:
#   - 上采样使用标准 ConvTranspose1d + 对称padding
#   - 每层后接平滑卷积(k=3, s=1, p=1)抑制混叠
#   - 禁止插值上采样
#   - 输出长度 = L * 2^5 精确匹配

from __future__ import annotations

import torch
import torch.nn as nn
from typing import Tuple

from .o9_tools import (
    ChannelLayerNorm,
    DISABLE_TORCH_COMPILING,
)


@torch.compile(disable = DISABLE_TORCH_COMPILING)
class DecoderBlock(nn.Module):
    """
    解码器上采样块。

    结构: ConvTranspose1d(上采样, k=3, s=2, p=1, op=1)
          → Conv1d(平滑, k=3, s=1, p=1) → ChannelLayerNorm → GELU → Dropout

    输入:  [B, in_channels, L]
    输出:  [B, out_channels, L * 2]
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 3,
        stride: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()
        # 标准转置卷积上采样（L → L*2 精确）
        self.up = nn.ConvTranspose1d(
            in_channels, out_channels,
            kernel_size = kernel_size, stride = stride,
            padding = kernel_size // 2, output_padding = stride - 1,
            bias = False,
        )
        # 平滑卷积：k=3, s=1, 对称padding，抑制上采样镜像频率
        self.smooth = nn.Conv1d(
            out_channels, out_channels, kernel_size = 3, stride = 1, padding = 1,
            bias = False,
        )
        self.norm = ChannelLayerNorm(out_channels)
        self.activation = nn.GELU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.up(x)  # [B, out, L*2]
        x = self.smooth(x)  # [B, out, L*2]
        x = self.norm(x)
        x = self.activation(x)
        x = self.dropout(x)
        return x


@torch.compile(disable = DISABLE_TORCH_COMPILING)
class O9Decoder(nn.Module):
    """
    o9 标准转置卷积解码器。

    将三分支拼接后的隐变量上采样还原为原始波形。

    设计要点:
        - 5层 ConvTranspose1d(k=3, s=2, p=1, op=1)，累乘32倍 (128 → 4096)
        - 每层后接平滑卷积(k=3, s=1, p=1)抑制混叠
        - 最终 1×1 Conv 投影到单通道
        - 输出长度精确匹配 (128 * 2^5 = 4096)
        - 输出不加 tanh（由重构损失约束）

    输入:
        z_d: [B, 128, 64]  设备/工况底纹（VAE采样后）
        z_f: [B, 128, 64]  故障模式指纹
    输出:
        x_hat: [B, 1, 4096]
    """

    def __init__(
        self,
        z_d_dim: int = 64,
        z_f_dim: int = 64,
        hidden_channels: Tuple[int, ...] = (128, 128, 64, 32, 16, 16),
        dropout: float = 0.1,
    ):
        super().__init__()

        assert len(hidden_channels) == 6
        assert hidden_channels[0] == z_d_dim + z_f_dim

        # ── 5个上采样块 ──
        # up1: 176→128, up2: 128→64, up3: 64→32, up4: 32→16, up5: 16→16
        self.blocks = nn.ModuleList()
        for i in range(5):
            self.blocks.append(
                DecoderBlock(
                    in_channels = hidden_channels[i],
                    out_channels = hidden_channels[i + 1],
                    kernel_size = 3,
                    stride = 2,
                    dropout = dropout,
                )
            )

        # ── 最终输出层: 16 → 1 ──
        self.out_conv = nn.Conv1d(
            hidden_channels[-1], 1, kernel_size = 1,
            bias = False,
        )

    def forward(
        self,
        z_d: torch.Tensor,
        z_f: torch.Tensor,
    ) -> torch.Tensor:
        """
        前向传播。

        输入:
            z_d: [B, 128, 64]
            z_f: [B, 128, 64]
        输出:
            x_hat: [B, 1, 4096]
        """
        # 在时序维度拼接: [B, T, C_d+F] = [B, 128, 128]
        x = torch.cat([z_d, z_f], dim = -1)

        # 转置为 Conv1d 格式: [B, C=128, T=128]
        x = x.transpose(1, 2)

        # 5个上采样块: 128 → 256 → 512 → 1024 → 2048 → 4096
        for block in self.blocks:
            x = block(x)

        # 最终投影到单通道
        x = self.out_conv(x)  # [B, 1, 4096]

        return x
