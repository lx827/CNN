# o9 判别器 — 域判别器 D_d（唯一活跃）
#
# 设计目标：配合 GRL 实现对抗隔离
#   - D_d 从 z_d / GRL(z_f) 预测域，确保 z_f 不含域信息
#   - D_f/D_s/D_m 已在 o9 中移除（-entropy 梯度消失导致塌缩无效）
#
# 聚合方式：1×1 Conv 生成注意力权重，加权求和（禁止全局均值池化）

from __future__ import annotations

import torch
import torch.nn as nn

from .o9_tools import (
    TimeAttentionPool,
    DISABLE_TORCH_COMPILING,
)


class BaseDiscriminator(nn.Module):
    """
    判别器基类（轻量版，防止 GRL 梯度消失）。

    结构:
        1. 1x1 Conv 特征提取 + 通道收缩 (input_dim → hidden_dim)
        2. 时间注意力聚合 (TimeAttentionPool) → [B, hidden_dim]
        3. 单层 Linear 分类 (hidden_dim → num_classes)

    输入:  [B, T, input_dim]
    输出:  [B, num_classes]
    """

    def __init__(
        self,
        input_dim: int,
        num_classes: int,
        hidden_dim: int = 32,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim

        # 1. 1x1 Conv 特征提取 + 收缩通道
        self.feature_conv = nn.Sequential(
            nn.Conv1d(input_dim, hidden_dim, kernel_size = 1),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        # 2. 时间注意力聚合
        self.attn_pool = TimeAttentionPool(hidden_dim)

        # 3. 单层分类（取消深 MLP，防止过拟合 + GRL 梯度消失）
        self.classifier = nn.Linear(hidden_dim, num_classes)

    @torch.compile(disable = DISABLE_TORCH_COMPILING, dynamic = True)
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        前向传播。

        输入: x [B, T, input_dim]
        输出: logits [B, num_classes]
        """
        x = x.transpose(1, 2)  # [B, input_dim, T]
        x = self.feature_conv(x)  # [B, hidden_dim, T]
        x = self.attn_pool(x)  # [B, hidden_dim]
        x = self.classifier(x)  # [B, num_classes]
        return x


@torch.compile(disable = DISABLE_TORCH_COMPILING)
class DomainDiscriminator(BaseDiscriminator):
    """
    域判别器（D_d）—— o9 唯一活跃判别器。

    输入: z_d [B, 128, 64] 或经 GRL 后的 z_f [B, 128, 64]
    输出: domain_logits [B, n_domains]

    用途:
        - 有标签数据：最小化 CE(domain_logits, domain_ids)
        - 全部数据（经 GRL 的 z_f）：最大化输出熵，确保 z_f 不携带域信息
    """

    def __init__(self, n_domains: int, input_dim: int = 64, dropout: float = 0.1):
        super().__init__(input_dim, n_domains, dropout = dropout)
