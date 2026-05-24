# 算法-文献对应总表

| 分类 | 序号 | 算法名称 | 原理 | 适用场景 | 核心参考文献 |
|------|------|---------|------|---------|-------------|
| 轴承 | 1 | 标准包络 | Hilbert变换解调+带通滤波 | 恒速工况，故障频率清晰 | Randall & Antoni (2011). *Rolling element bearing diagnostics—a tutorial*, MSSP 25(2): 485-520. |
| 轴承 | 2 | Fast Kurtogram | 谱峭度图自适应选共振频带 | 未知共振频带，变速工况 | Antoni (2007). *Fast computation of the kurtogram for the detection of transient faults*, MSSP 21(1): 108-124. |
| 轴承 | 3 | CPW预白化 | 倒频谱编辑去除确定性分量 | 齿轮箱中轴承诊断 | Borghesani et al. (2013). *Application of cepstrum pre-whitening for the diagnosis of bearing faults under variable speed*, MSSP 36(2): 370-384. |
| 轴承 | 4 | MED增强 | 最小熵解卷积锐化冲击 | 低信噪比工况 | Sawalhi et al. (2007). *Enhancement of fault detection using minimum entropy deconvolution combined with spectral kurtosis*, MSSP 21(6): 2616-2633. |
| 轴承 | 5 | MCKD | 最大相关峭度解卷积（引入故障周期约束） | 已知故障周期，降低漏检率 | McDonald et al. (2012). *Maximum correlated kurtosis deconvolution and application on gear tooth chip and cracked roller identification*, MSSP 33: 237-255. |
| 轴承 | 6 | Teager | Teager能量算子+包络 | 瞬态冲击增强 | Kaiser (1990). *On a simple algorithm to calculate the "energy" of a signal*, Proc. IEEE ICASSP. |
| 轴承 | 7 | 谱峭度重加权 | 自适应谱峭度重加权包络 | 强噪声背景 | Antoni (2006). *The spectral kurtosis: a useful tool for characterising non-stationary signals*, MSSP 20(2): 282-307. |
| 轴承 | 8 | SC-SCoh | 谱相关/谱相干循环平稳分析 | 变速工况，高级诊断 | Randall et al. (2001). *The relationship between spectral correlation and envelope analysis in the diagnostics of bearing faults*, MSSP 15(5): 945-962. |
| 轴承 | 9 | 小波包 | 小波包敏感节点+包络 | 频带能量重分布检测 | Lei et al. (2013). *An improved kurtogram method for fault diagnosis using wavelet packet transform*, MSSP 35(1-2): 176-199. |
| 轴承 | 10 | DWT | 离散小波变换敏感层+包络 | 多分辨率分析 | Mallat (1989). *A theory for multiresolution signal decomposition: the wavelet representation*, IEEE Trans. PAMI 11(7): 674-693. |
| 轴承 | 11 | EMD | 经验模态分解敏感IMF+包络 | 非线性非平稳信号 | Huang et al. (1998). *The empirical mode decomposition and the Hilbert spectrum for nonlinear and non-stationary time series analysis*, Proc. R. Soc. Lond. A 454: 903-995. |
| 轴承 | 12 | CEEMDAN | 完备集成EMD敏感IMF+包络 | 抑制模态混叠 | Torres et al. (2011). *A complete ensemble empirical mode decomposition with adaptive noise*, IEEE ICASSP. |
| 轴承 | 13 | VMD | 变分模态分解敏感模态+包络 | 频带分离清晰 | Dragomiretskiy & Zosso (2014). *Variational mode decomposition*, IEEE Trans. Signal Process. 62(3): 531-544. |
| 齿轮 | 14 | 标准边频分析 | SER+边频带检测 | 定轴齿轮箱 | Hanna et al. (GE). *Sideband Energy Ratio*, ADAPT.wind. |
| 齿轮 | 15 | 高级综合 | FM0/FM4/M6A/M8A+SER+CAR+小波包能量熵 | 行星齿轮箱 | Zakrajsek et al. (1993). *An analysis of gear fault detection methods as applied to pitting fatigue failure data*, Proc. MFPT. |
| 齿轮 | 16 | FM0 | 峰值差/啮合谐波幅值比 | 粗大故障（断齿、严重磨损） | Zakrajsek et al. (1993) / NASA CR-2009-00039501. *Gear Fault Detection Effectiveness*. |
| 齿轮 | 17 | FM4 | 差分信号归一化峭度 | 局部故障（点蚀、裂纹） | Zakrajsek et al. (1993) / Stewart (1977). *Some useful data analysis techniques for gearbox diagnostics*, Proc. MFPT. |
| 齿轮 | 18 | M6A | 差分信号6阶归一化矩 | 齿面损伤敏感 | Zakrajsek et al. (1993). |
| 齿轮 | 19 | M8A | 差分信号8阶归一化矩 | 更高灵敏度 | Zakrajsek et al. (1993). |
| 齿轮 | 20 | NA4 | 准归一化峭度（历史基线） | 趋势监测 | NASA CR-2009-00039501. *Gear Fault Detection Effectiveness*. |
| 齿轮 | 21 | NB4 | 包络域NA4 | 局部齿损伤 | NASA CR-2009-00039501. |
| 齿轮 | 22 | CAR | 倒频谱幅值比 | 啮合频率异常指示 | Randall (2017). *A history of cepstrum analysis and its application to mechanical problems*, MSSP 97: 3-19. |
| 齿轮 | 23 | ER | 差分信号RMS/啮合能量比 | 多齿磨损 | Zakrajsek et al. (1993). |
| 齿轮 | 24 | TSA残差峭度 | 时域同步平均+残差峭度 | 齿轮局部故障 | McFadden (1987). *Examination of a technique for the early detection of failure in gears by signal processing of the time domain average*, MSSP 1(2): 173-183. / Braun (1975). *The extraction of periodic waveforms by time domain averaging*, Acustica 23(2): 69-77. |
| 齿轮 | 25 | 窄带包络阶次 | 带通滤波+包络+阶次谱 | 行星排太阳轮/行星轮故障 | Feng & Zuo (2012). *Vibration signal models for fault diagnosis of planetary gearboxes*, JSV 331(22): 4919-4939. |
| 齿轮 | 26 | 全频带包络阶次 | 全频带包络+阶次分析 | 行星排通用 | Feng & Zuo (2012). |
| 齿轮 | 27 | VMD联合解调 | VMD分解+幅频解调谱 | 行星排多故障分离 | Feng, Zhang & Zuo (2017). *Planetary Gearbox Fault diagnosis via Joint Amplitude and Frequency Demodulation Analysis Based on VMD*, Appl. Sci. 7(8): 775. |
| 齿轮 | 28 | TSA包络分析 | 行星排TSA残差包络 | 行星排局部故障 | McFadden (1987). *TSA early detection*; Randall & Antoni (2011). *Envelope analysis tutorial*; Feng & Zuo (2012). *Planetary gearbox vibration models*, JSV 331(22): 4919-4939. |
| 齿轮 | 29 | SC/SCoh循环平稳 | 谱相关/谱相干分析 | 变速行星排 | Dong, Liu & Feng (2025). *Spectral Correlation Demodulation Analysis for Fault Diagnosis of Planetary Gearboxes*, Sensors 25(9): 2694. |
| 齿轮 | 30 | MSB调制双谱 | 调制信号双谱+残差边频 | 行星排多调制源 | Xu et al. / Feng & Zuo. *MSB-based methods for planetary gearbox fault diagnosis* (系列论文). |
| 齿轮 | 31 | CVS+MED | 连续振动分离+MED增强 | 行星排多通道 | Tong et al. *Vibration Separation Methodology Compensated by Time-Varying Transfer Function for Fault Diagnosis of Non-Hunting Tooth Planetary Gearbox*, Mech. Syst. Signal Process. |
| 齿轮 | 32 | 小波包能量熵 | 小波包分解+能量熵 | 齿轮频带能量重分布 | Yen & Lin (2000). *Wavelet packet feature extraction for vibration monitoring*, IEEE Trans. Industrial Electronics 47(3): 650-667; Coifman & Wickerhauser (1992). *Entropy-based algorithms for best basis selection*, IEEE Trans. IT 38(2): 713-718. |
| 去噪 | 33 | 无去噪 | — | 信噪比>10dB | — |
| 去噪 | 34 | 小波去噪 | 小波阈值收缩 | 高斯白噪声 | Donoho & Johnstone (1994). *Ideal spatial adaptation by wavelet shrinkage*, Biometrika 81(3): 425-455. |
| 去噪 | 35 | VMD去噪 | 变分模态分解+IMF筛选 | 非平稳信号 | Dragomiretskiy & Zosso (2014). *Variational mode decomposition*, IEEE Trans. Signal Process. 62(3): 531-544. |
| 去噪 | 36 | 小波+VMD级联 | 两阶段级联去噪 | 强噪声（<0dB） | Donoho & Johnstone (1994). *Wavelet shrinkage*; Dragomiretskiy & Zosso (2014). *VMD*. 级联组合策略见 ALGORITHMS.md §4.2.5. |
| 去噪 | 37 | 小波+LMS | 小波去噪+LMS自适应滤波 | 周期性干扰 | Widrow & Hoff (1960). *Adaptive switching circuits*, IRE WESCON Convention Record; Donoho & Johnstone (1994). *Wavelet shrinkage*. 小波域自适应滤波组合策略. |
| 去噪 | 38 | EMD | 经验模态分解+IMF筛选 | 非线性信号 | Huang et al. (1998). *The empirical mode decomposition...*, Proc. R. Soc. Lond. A 454: 903-995. |
| 去噪 | 39 | CEEMDAN | 完备集成EMD+自适应噪声 | 模态混叠严重 | Torres et al. (2011). *A complete ensemble empirical mode decomposition with adaptive noise*, IEEE ICASSP. |
| 去噪 | 40 | Savitzky-Golay | 多项式最小二乘平滑 | 多项式平滑 | Savitzky & Golay (1964). *Smoothing and differentiation of data by simplified least squares procedures*, Anal. Chem. 36(8): 1627-1639. |
| 去噪 | 41 | 小波包能量阈值 | 小波包能量熵+阈值筛选 | 高频噪声 | Coifman & Wickerhauser (1992). *Entropy-based algorithms for best basis selection*, IEEE Trans. IT 38(2): 713-718. |
| 去噪 | 42 | CEEMDAN+小波包 | CEEMDAN+小波包级联 | 复合故障 | Torres et al. (2011). *CEEMDAN*; Coifman & Wickerhauser (1992). *Best basis selection*. 级联联合降噪策略. |
| 去噪 | 43 | EEMD | 集成EMD+噪声辅助 | 集成EMD | Wu & Huang (2009). *Ensemble empirical mode decomposition: a noise-assisted data analysis method*, Advances in Adaptive Data Analysis 1(1): 1-41. |
| 阶次 | 44 | 单帧阶次跟踪 | 恒定转速下等角度插值重采样+FFT | 恒速工况 | Potter & Gahleitner (1995). *Signal processing for improved order tracking*, SAE Technical Paper 952146. |
| 阶次 | 45 | 多帧平均阶次跟踪 | 分帧+MAD离群值剔除+公共阶次轴谱平均 | 转速缓变工况 | Fyfe & Munck (1997). *Analysis of computed order tracking*, MSSP 11(2): 187-205（分帧平均扩展）; Vold & Leuridan (1985). *High resolution order tracking at extreme slew rates*, SAE Paper 851286（短时处理基础）. |
| 阶次 | 46 | 变速阶次跟踪 | STFT瞬时频率追踪+Savitzky-Golay平滑+数值积分等相位重采样 | 启停机、扫频等剧烈变速 | Urbanek et al. (2013). *Computation of instantaneous frequency and amplitude of non-stationary signals using STFT peak tracking*, IEEE T-IM 62(10): 2754-2763. |
