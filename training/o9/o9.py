# o9 主网络封装 — O9MainNet
#
# 职责：组装 Encoder、Decoder、FaultBank、判别器。
# 约束：forward 中不出现 if self.training 分支切换。

from __future__ import annotations

import torch
import torch.nn as nn
from typing import Dict

from .o9_encoder import O9Encoder
from .o9_decoder import O9Decoder
from .fault_bank import FaultBank, FaultCombiner
from .classifier import DomainDiscriminator
from .o9_tools import (
    DISABLE_TORCH_COMPILING,
    GradientReversalLayer,
)


@torch.compile(disable = DISABLE_TORCH_COMPILING)
class O9MainNet(nn.Module):
    """
    o9 主网络：组装 Encoder、Decoder、FaultBank、判别器。

    forward 中不出现 if self.training，所有训练/推理差异由调度器外部控制。

    输入:  x [B, 1, 4096]
    输出:  dict {
        'x_hat'      : [B, 1, 4096]
        'z_d'        : [B, 128, 64]   (采样后或直接用 mu)
        'z_d_mu'     : [B, 128, 64]
        'z_d_logvar' : [B, 128, 64]
        'z_f_raw'    : [B, 128, 64]   (编码器原始输出)
        'z_f'        : [B, 128, 64]   (可能为 Combiner 输出)
        'weights'    : [B, K] or None (Combiner 权重)
    }
    """

    def __init__(
        self,
        n_domains: int,
        num_faults: int,
        z_d_dim: int = 64,
        z_f_dim: int = 64,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.z_d_dim = z_d_dim
        self.z_f_dim = z_f_dim
        self.num_faults = num_faults

        # 编码器 / 解码器
        self.encoder = O9Encoder(
            z_d_dim = z_d_dim, z_f_dim = z_f_dim, dropout = dropout
        )
        # decoder 首层通道数必须等于双分支拼接维度
        decoder_hc = (z_d_dim + z_f_dim, 128, 64, 32, 16, 16)
        self.decoder = O9Decoder(
            z_d_dim = z_d_dim, z_f_dim = z_f_dim,
            hidden_channels = decoder_hc, dropout = dropout
        )

        # 故障库 / 组合器
        self.fault_bank = FaultBank(num_faults, z_f_dim)
        self.fault_combiner = FaultCombiner(z_f_dim, num_faults)

        # 判别器（o9 仅保留 D_d，D_f/D_s/D_m 已移除）
        self.D_d = DomainDiscriminator(n_domains, z_d_dim, dropout)

        # GRL（仅 grl_domain 参与训练，其余定义保留但不产生实际梯度）
        self.grl_domain = GradientReversalLayer()

    def _reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """VAE 重参数化：z = mu + eps * exp(0.5 * logvar)"""
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def forward(
        self,
        x: torch.Tensor,
        sample_z_d: bool = True,
        use_combiner: bool = False,
        fault_mask: torch.Tensor | None = None,
    ) -> Dict[str, torch.Tensor | None]:
        """
        前向传播。

        参数:
            x:            [B, 1, 4096] 输入波形
            sample_z_d:   True=训练时重参数化采样；False=推理时用 mu
            use_combiner: True=用 FaultCombiner 生成 z_f；False=直接用 z_f_raw
            fault_mask:   [B, K] multi-hot 掩码，use_combiner=True 时必需
        """
        # ---- 编码 ----
        enc = self.encoder(x)
        z_d_mu = enc['z_d_mu']  # [B, T, D]
        z_d_logvar = enc['z_d_logvar']  # [B, T, D]
        z_f_raw = enc['z_f']  # [B, T, F]
        # VAE 采样（外部控制，forward 内无 training 分支）
        z_d = self._reparameterize(z_d_mu, z_d_logvar) if sample_z_d else z_d_mu

        # z_f 选择：原始输出 或 FaultCombiner 组合
        if use_combiner and fault_mask is not None:
            z_f, weights = self.fault_combiner(
                self.fault_bank, fault_mask, T = z_f_raw.size(1)
            )
        else:
            z_f = z_f_raw
            weights = None

        # ---- 解码 ----
        x_hat = self.decoder(z_d, z_f)

        return {
            'x_hat'     : x_hat,
            'z_d'       : z_d,
            'z_d_mu'    : z_d_mu,
            'z_d_logvar': z_d_logvar,
            'z_f_raw'   : z_f_raw,
            'z_f'       : z_f,
            'weights'   : weights,
        }

    def set_grl_lambda(self, lambda_: float) -> None:
        """设置 GRL 强度（由调度器控制 ramp）。仅 grl_domain 生效。"""
        self.grl_domain.set_lambda(lambda_)
