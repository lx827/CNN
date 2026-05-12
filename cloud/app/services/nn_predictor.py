"""
神经网络故障预测接口（预留模块）

用途：
  当你训练好深度学习模型（PyTorch / TensorFlow / ONNX）后，
  把模型文件放到指定路径，修改 .env 中 NN_ENABLED=true，
  本模块就会自动加载模型并替代默认的简化分析算法。

当前状态：
  默认返回 None，云端会自动回退到 analyzer.py 中的简化规则算法。
  这样你可以先让系统完整跑起来，后续再无缝接入真实模型。

接入步骤：
  1. 训练模型（输入：振动信号时域数组，输出：故障类型概率向量）
  2. 导出为 ONNX / TorchScript / SavedModel 格式
  3. 放到 cloud/models/ 目录下
  4. 修改 cloud/.env：NN_ENABLED=true，NN_MODEL_PATH=./models/your_model.onnx
  5. 在 predict() 函数中补充模型加载和推理代码
"""
import logging
import os
import numpy as np
from typing import Dict, Optional
from app.core.config import NN_ENABLED, NN_MODEL_PATH

logger = logging.getLogger(__name__)

# 全局模型句柄（延迟加载，第一次调用时才初始化）
_model = None


def _load_model():
    """加载神经网络模型"""
    global _model
    if _model is not None:
        return _model
    if not os.path.exists(NN_MODEL_PATH):
        logger.warning(f"[NN] 模型文件不存在: {NN_MODEL_PATH}，跳过加载")
        return None
    logger.warning("[NN] 模型路径存在但未配置加载代码，请修改 nn_predictor.py")
    return None


def _preprocess(signal: np.ndarray, sample_rate: int = 1000) -> np.ndarray:
    """数据预处理：把原始振动信号转换成模型输入格式"""
    fixed_len = 5000
    if len(signal) > fixed_len:
        signal = signal[:fixed_len]
    else:
        signal = np.pad(signal, (0, fixed_len - len(signal)), mode='constant')
    mean = np.mean(signal)
    std = np.std(signal)
    if std > 0:
        signal = (signal - mean) / std
    return signal.astype(np.float32)


def predict(channels_data: Dict[str, list], sample_rate: int = 1000) -> Optional[Dict]:
    """
    神经网络预测主函数
    如果模型未启用或加载失败，返回 None（云端自动回退到简化算法）
    """
    if not NN_ENABLED:
        return None
    model = _load_model()
    if model is None:
        return None
    try:
        ch1_data = np.array(channels_data.get("ch1", []))
        if len(ch1_data) == 0:
            return None
        input_tensor = _preprocess(ch1_data, sample_rate)
        # TODO: 在此补充模型推理代码
        logger.warning("[NN] 模型已加载，但推理代码尚未实现，请修改 nn_predictor.py")
        return None
    except Exception as e:
        logger.error(f"[NN] 推理异常: {e}")
        return None
