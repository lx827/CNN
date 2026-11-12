"""独立原生趋势/统计序列核；输入同步借用，结果由NumPy独立持有。"""
from ._native import sequence as _native
from .emd import _signal


def holt(values, steps, alpha, beta, gamma, period, initial_trend):
    """Holt/加法Holt-Winters递推；返回level/trend/season/fitted/forecast。"""
    return _native.holt(_signal(values), steps, alpha, beta, gamma, period, initial_trend)


def kalman(values, process_noise=1.0, measurement_noise=5.0):
    """常速度二状态Kalman，Joseph协方差更新；返回score/rate/final_variance。"""
    return _native.kalman(_signal(values), process_noise, measurement_noise)


def cusum(values, allowance=0.5, alpha=0.2):
    """返回双侧CUSUM最大值/最终值/EWMA；不判断告警。"""
    return _native.cusum(_signal(values), allowance, alpha)


def mann_whitney_z(values, reference, window):
    """参考窗与步进滑窗的Mann-Whitney min(U1,U2) z统计量。"""
    return _native.mann_whitney_z(_signal(values), _signal(reference), window)


def regression(x, y):
    """最小二乘直线 slope/intercept；零自变量方差返回常数均值。"""
    return _native.regression(_signal(x), _signal(y))


def central_moment(values, degree, *, scaled=False):
    """返回中心degree阶矩/方差；scaled先除最大中心绝对幅值。"""
    return _native.central_moment(_signal(values), degree, scaled)


def window_moments(values, window):
    """完整不重叠窗口的RMS/Pearson峰度；常数窗峰度NaN。"""
    return _native.window_moments(_signal(values), window)
