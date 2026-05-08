# 模型存放目录

把训练好的神经网络模型文件放在这里。

支持的格式（根据你在 `nn_predictor.py` 中实现的加载代码）：
- `.onnx` — ONNX Runtime（推荐，跨框架）
- `.pt` / `.pth` — PyTorch TorchScript
- `.pb` / `.h5` — TensorFlow SavedModel / HDF5

> 模型文件通常很大，已通过 `.gitignore` 设置为不提交到 Git。
