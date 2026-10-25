# o9 FaultBank — 故障原型库 + 无参原型组合 + 贪心稀疏分解
#
# 组件：
#   FaultBank      — 可学习原型参数 [num_faults, F=64]，健康原型(索引0)趋近零
#   FaultCombiner  — 小数据无参简化版：L2 归一化原型 + active_mask 归一化加权
#   MatchingPursuit— 贪心匹配追踪（分析用，不参与训练梯度）
#
# 单故障: 硬查表取原型 → 广播到时序
# 混合故障: FaultCombiner 按 active_mask 归一化加权 → 广播到时序

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Tuple

from .o9_tools import DISABLE_TORCH_COMPILING


# =============================================================================
# FaultBank — 可学习故障原型表
# =============================================================================

@torch.compile(disable = DISABLE_TORCH_COMPILING)
class FaultBank(nn.Module):
    """
    故障原型库（可训练参数，无 EMA）。

    存储 K 个可学习的 F 维原型向量，对应 K 种故障类型（含健康态）。
    原型由 O9FaultPrototypeLoss 的梯度直接更新，配合 AdamW weight decay 做 L2 正则。

    参数:
        num_faults: 故障类型总数（含健康，索引0）
        feature_dim: 原型维度，与 z_f 分支一致（默认 64）

    原型: nn.Parameter [num_faults, feature_dim]
    """

    def __init__(self, num_faults: int, feature_dim: int = 64):
        super().__init__()
        self.num_faults = num_faults
        self.feature_dim = feature_dim

        self.prototypes = nn.Parameter(
            torch.empty(num_faults, feature_dim)
        )

    def forward(self, query: torch.Tensor) -> torch.Tensor:
        """
        计算 query 与各原型的相似度（内积，未归一化）。

        输入: query [B, F] 或 [B, T, F]
        输出: logits [B, K] 或 [B, T, K]
        """
        if query.dim() == 2:
            return query @ self.prototypes.T
        elif query.dim() == 3:
            return query @ self.prototypes.T
        else:
            raise ValueError(f"query 维度应为 2 或 3，got {query.dim()}")


# =============================================================================
# FaultCombiner — 故障原型组合器（小数据简化版）
# =============================================================================
@torch.compile(disable = DISABLE_TORCH_COMPILING)
class FaultCombiner(nn.Module):
    """
    混合故障原型组合器（小数据无参简化版）。

    设计动机:
        原始 MLP+Transformer 版在数据量 < 20 小时时容易过拟合，
        学会给训练集设备"特调"组合比例，unseen 设备失效。
        简化版退化为**无参归一化加权**：直接按 active_mask 硬约束
        做 L2 归一化后加权平均，保留"多故障向量方向叠加"的物理意义，
        但去除所有可学习参数，彻底避免过拟合。

    角色:
        FaultBank 是"颜料盘"（静态原型库），FaultCombiner 是"调色手"。
        Bank 存放每种故障的标准原型，Combiner 按 active_mask 硬约束
        归一化调配各原型比例，广播回时序维度。

    输入:
        fault_bank: FaultBank 实例，提供原型 [K, F]
        active_mask: [B, K] 多标签 0/1 掩码，硬约束只激活已标注故障
        T: 时序长度（默认 128），用于广播回时序 Token 格式

    输出:
        z_f:     [B, T, F]  组合后的故障特征
        weights: [B, K]     归一化后的组合权重（和为 1，用于可解释性）
    """

    def __init__(
        self,
        z_f_dim: int = 64,
        num_faults: int = 8,
    ):
        super().__init__()
        self.z_f_dim = z_f_dim
        self.num_faults = num_faults
        # 无参版本：无 learnable parameters，避免小数据过拟合

    def forward(
        self,
        fault_bank: FaultBank,
        active_mask: torch.Tensor,
        T: int = 128,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        前向传播（无参归一化加权）。

        参数:
            fault_bank:  FaultBank 实例，提供原型 [K, F]
            active_mask: [B, K] 多标签 0/1 掩码。
                         1=允许参与组合，0=强制屏蔽（硬门控）。
                         单故障时仅一个 1，退化为直接查表。
            T:           时序长度，用于广播回 [B, T, F]

        返回:
            z_f:      [B, T, F]  组合后的故障特征
            weights:  [B, K]     归一化权重（和为 1）
        """
        # 1. L2 归一化原型到单位球面，避免数值爆炸/抵消
        prototypes = F.normalize(fault_bank.prototypes, dim = 1)  # [K, F]

        # 2. active_mask 归一化到和为 1（避免简单相加的数值爆炸）
        sum_mask = active_mask.sum(dim = 1, keepdim = True).clamp(min = 1e-8)  # [B, 1]
        weights = active_mask / sum_mask  # [B, K]，每样本和为 1

        # 3. 加权组合: [B, K] @ [K, F] → [B, F]
        z_f_combined = weights @ prototypes  # [B, F]

        # 4. 广播回时序维度（同一段信号各帧共享故障指纹）
        z_f_combined = z_f_combined.unsqueeze(1).expand(-1, T, -1)  # [B, T, F]

        return z_f_combined, weights
