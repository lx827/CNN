<template>
  <div class="data-view">
    <!-- 标题栏 -->
    <el-card class="header-card">
      <div class="header-bar">
        <span class="title">振动数据查看</span>
        <div class="actions">
          <el-button type="danger" size="small" @click="onDeleteAllSpecial" :loading="deleteLoading">
            <el-icon><Delete /></el-icon> 清空所有特殊数据
          </el-button>
          <el-button type="primary" size="small" @click="loadAllDevices" :loading="loading">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 设备批次表格 -->
    <DeviceTable
      :data="deviceTableData"
      :loading="loading"
      :selected-device-id="selectedDevice?.device_id"
      :selected-batch-index="selectedBatch?.batch_index"
      @select-batch="selectBatch"
      @refresh="loadAllDevices"
      @batch-deleted="onBatchDeleted"
    />

    <!-- 选中批次详情 -->
    <el-card v-if="selectedDevice && selectedBatch" class="detail-card">
      <template #header>
        <DetailHeader
          :device="selectedDevice"
          :batch="selectedBatch"
          v-model:channel="selectedChannel"
          :channel-options="channelOptions"
          v-model:maxFreq="maxFreq"
          v-model:denoiseMethod="denoiseMethod"
          v-model:enableDetrend="enableDetrend"
          :reanalyzing="reanalyzing"
          :reanalyzingAll="reanalyzingAll"
          @export-csv="onExportCSV"
          @reanalyze="onReanalyze"
          @reanalyze-all="onReanalyzeAll"
          @delete-batch="onDeleteBatch(selectedDevice.device_id, selectedBatch.batch_index)"
          @goto-research="gotoResearchDiagnosis"
        />
      </template>

      <DiagnosisAlert :status="selectedBatch.diagnosis_status" :description="diagnosisDesc" />

      <!-- 时域波形：始终自动加载 -->
      <TimeDomainPanel :chart-option="timeOption" />

      <!-- 统计指标 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :span="24">
          <div class="section-header">
            <span class="chart-title">统计特征指标</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <template v-if="!computedStats">
                <el-text type="info" size="small">窗口</el-text>
                <el-input-number
                  v-model="statsWindowSize"
                  :min="64"
                  :max="8192"
                  :step="64"
                  size="small"
                  style="width: 110px"
                  controls-position="right"
                />
                <el-text type="info" size="small">步长</el-text>
                <el-input-number
                  v-model="statsStep"
                  :min="1"
                  :max="4096"
                  :step="32"
                  size="small"
                  style="width: 100px"
                  controls-position="right"
                />
                <el-button
                  type="primary"
                  size="small"
                  :loading="loadingStats"
                  @click="computeStats"
                >
                  <el-icon><DataAnalysis /></el-icon> 计算
                </el-button>
              </template>
              <el-button v-else type="info" size="small" @click="clearStats">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <div v-if="computedStats && statsData" class="stats-grouped">
            <div v-for="group in statsGroups" :key="group.title" class="stats-group">
              <div class="stats-group-title">{{ group.icon }} {{ group.title }}</div>
              <el-descriptions :column="group.items.length > 4 ? 4 : group.items.length" border size="small">
                <el-descriptions-item v-for="item in group.items" :key="item.key" :label="item.label">
                  <span class="stat-value">
                    {{ statsData[item.key] !== null && statsData[item.key] !== undefined ? Number(statsData[item.key]).toFixed(item.precision) : '-' }}
                  </span>
                  <el-text v-if="item.normal" type="info" size="small" class="stat-normal">{{ item.normal }}</el-text>
                </el-descriptions-item>
              </el-descriptions>
            </div>
            <el-text type="info" size="small" style="display: block; margin-top: 8px;">
              加窗参数：窗口大小 {{ statsData.window_params.window_size }} 点，滑动步长 {{ statsData.window_params.step }} 点
            </el-text>
          </div>
          <div v-if="computedStats && statsData?.window_series" style="margin-top: 16px;">
            <div class="chart-title">加窗统计量时序图</div>
            <VibrationChart :option="windowedOption" height="280px" />
          </div>
          <div v-else-if="loadingStats" class="placeholder">
            <el-skeleton :rows="2" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="设置窗口参数后点击计算" :image-size="80" />
          </div>
        </el-col>
      </el-row>

      <!-- FFT 频谱 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :xs="24" :md="12">
          <div class="section-header">
            <span class="chart-title">FFT 频谱</span>
            <el-button
              v-if="!computedFFT"
              type="primary"
              size="small"
              :loading="loadingFFT"
              @click="computeFFT"
            >
              <el-icon><DataAnalysis /></el-icon> 计算 FFT
            </el-button>
            <el-button v-else type="info" size="small" @click="clearFFT">
              <el-icon><Close /></el-icon> 收起
            </el-button>
          </div>
          <VibrationChart v-if="computedFFT" :option="fftOption" />
          <div v-else-if="loadingFFT" class="placeholder">
            <el-skeleton :rows="3" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="点击按钮计算 FFT 频谱" :image-size="80" />
          </div>
        </el-col>

        <!-- 包络谱 -->
        <el-col :xs="24" :md="12">
          <div class="section-header">
            <span class="chart-title">包络谱（轴承诊断）</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <el-select
                v-if="!computedEnvelope"
                v-model="envelopeMethod"
                size="small"
                style="width: 150px"
              >
                <el-option label="标准包络" value="envelope" />
                <el-option label="快速峭度图" value="kurtogram" />
                <el-option label="CPW+包络" value="cpw" />
                <el-option label="TEO+包络" value="teager" />
                <el-option label="谱峭度包络" value="spectral_kurtosis" />
                <el-option label="MED+包络" value="med" />
                <el-option label="谱相关/谱相干" value="sc_scoh" />
              </el-select>
              <el-select
                v-if="!computedEnvelope"
                v-model="envelopeDenoise"
                size="small"
                style="width: 130px"
              >
                <el-option label="无预处理" value="none" />
                <el-option label="小波去噪" value="wavelet" />
                <el-option label="VMD降噪" value="vmd" />
                <el-option label="小波+VMD" value="wavelet_vmd" />
                <el-option label="小波+LMS" value="wavelet_lms" />
              </el-select>
              <el-tag v-else type="success" size="small" effect="plain">{{ envelopeMethodLabel }}</el-tag>
              <el-button
                v-if="!computedEnvelope"
                type="primary"
                size="small"
                :loading="loadingEnvelope"
                @click="computeEnvelope"
              >
                <el-icon><DataAnalysis /></el-icon> 计算
              </el-button>
              <el-button v-else type="info" size="small" @click="clearEnvelope">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <div v-if="computedEnvelope && envelopeData" class="envelope-info">
            <el-tag v-if="envelopeData.optimal_fc" type="info" size="small" effect="plain">
              最优频段 {{ envelopeData.optimal_fc }}±{{ (envelopeData.optimal_bw/2).toFixed(0) }} Hz
            </el-tag>
            <el-tag v-if="envelopeData.max_kurtosis != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
              峭度 {{ envelopeData.max_kurtosis.toFixed(2) }}
            </el-tag>
            <el-tag v-if="envelopeData.kurtosis_after != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
              MED后峭度 {{ envelopeData.kurtosis_after.toFixed(2) }}
            </el-tag>
            <el-tag v-if="envelopeData.teager_rms != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
              TEO RMS {{ envelopeData.teager_rms.toFixed(4) }}
            </el-tag>
            <el-tag v-if="envelopeData.reweighted_score != null" type="info" size="small" effect="plain" style="margin-left: 8px;">
              SK评分 {{ envelopeData.reweighted_score.toFixed(2) }}
            </el-tag>
          </div>
          <VibrationChart v-if="computedEnvelope" :option="envelopeOption" />
          <div v-else-if="loadingEnvelope" class="placeholder">
            <el-skeleton :rows="3" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="选择方法后计算包络谱" :image-size="80" />
          </div>
        </el-col>
      </el-row>

      <!-- 齿轮诊断 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :span="24">
          <div class="section-header">
            <span class="chart-title">齿轮诊断分析</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <el-select
                v-if="!computedGear"
                v-model="gearMethod"
                size="small"
                style="width: 140px"
              >
                <el-option label="标准边频带" value="standard" />
                <el-option label="高级指标" value="advanced" />
              </el-select>
              <el-tag v-else type="success" size="small" effect="plain">{{ gearMethodLabel }}</el-tag>
              <el-button
                v-if="!computedGear"
                type="primary"
                size="small"
                :loading="loadingGear"
                @click="computeGear"
              >
                <el-icon><DataAnalysis /></el-icon> 计算
              </el-button>
              <el-button v-else type="info" size="small" @click="clearGear">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <div v-if="computedGear && gearData" class="gear-info">
            <el-descriptions :column="4" size="small" border>
              <el-descriptions-item label="SER" v-if="gearData.ser != null">
                <el-tag :type="gearData.ser > 3 ? 'danger' : gearData.ser > 1.5 ? 'warning' : 'success'" size="small">
                  {{ gearData.ser.toFixed(3) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="FM0" v-if="gearData.fm0 != null">
                <el-tag :type="gearData.fm0 > 10 ? 'danger' : gearData.fm0 > 5 ? 'warning' : 'success'" size="small">
                  {{ gearData.fm0.toFixed(2) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="CAR" v-if="gearData.car != null">
                <el-tag :type="gearData.car > 2 ? 'danger' : gearData.car > 1.2 ? 'warning' : 'success'" size="small">
                  {{ gearData.car.toFixed(2) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="转频" v-if="gearData.rot_freq_hz">
                {{ gearData.rot_freq_hz }} Hz / {{ (gearData.rot_freq_hz * 60).toFixed(0) }} RPM
              </el-descriptions-item>
            </el-descriptions>
            <el-table v-if="gearData.sidebands && gearData.sidebands.length > 0" :data="gearData.sidebands" size="small" style="margin-top: 8px;" max-height="200">
              <el-table-column prop="order" label="阶次" width="60" />
              <el-table-column prop="order_low" label="下边频阶次" width="110" />
              <el-table-column prop="order_high" label="上边频阶次" width="110" />
              <el-table-column prop="amp_low" label="下幅值" width="90" />
              <el-table-column prop="amp_high" label="上幅值" width="90" />
              <el-table-column prop="asymmetry" label="不对称度" width="90" />
              <el-table-column label="显著">
                <template #default="{ row }">
                  <el-tag :type="row.significant ? 'warning' : 'info'" size="small">
                    {{ row.significant ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div v-else style="margin-top: 8px; color: #999; font-size: 13px;">
              未检测到啮合频率参数，无法计算边频带
            </div>
          </div>
          <div v-else-if="loadingGear" class="placeholder">
            <el-skeleton :rows="2" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="选择方法后计算齿轮诊断" :image-size="80" />
          </div>
        </el-col>
      </el-row>

      <!-- 综合故障诊断 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :span="24">
          <div class="section-header">
            <span class="chart-title">综合故障诊断</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <!-- 策略快速诊断 -->
              <template v-if="!computedStrategyAnalyze && !computedFullAnalysis">
                <el-select v-model="analyzeStrategy" size="small" style="width: 120px">
                  <el-option label="标准策略" value="standard" />
                  <el-option label="高级策略" value="advanced" />
                  <el-option label="专家策略" value="expert" />
                </el-select>
                <el-select v-model="analyzeDenoise" size="small" style="width: 130px">
                  <el-option label="无预处理" value="none" />
                  <el-option label="小波去噪" value="wavelet" />
                  <el-option label="VMD分解" value="vmd" />
                  <el-option label="小波+VMD级联" value="wavelet_vmd" />
                  <el-option label="小波+LMS级联" value="wavelet_lms" />
                </el-select>
                <el-button
                  type="success"
                  size="small"
                  :loading="loadingStrategyAnalyze"
                  @click="computeStrategyAnalyze"
                >
                  <el-icon><DataAnalysis /></el-icon> 策略诊断
                </el-button>
                <el-divider direction="vertical" />
              </template>
              <el-tag v-if="computedStrategyAnalyze && !computedFullAnalysis" type="success" size="small" effect="plain">
                {{ analyzeStrategyLabel }}
              </el-tag>
              <el-button v-if="computedStrategyAnalyze && !computedFullAnalysis" type="info" size="small" @click="clearStrategyAnalyze">
                <el-icon><Close /></el-icon> 收起策略
              </el-button>
              <!-- 全算法诊断 -->
              <template v-if="!computedFullAnalysis">
                <el-select v-model="fullAnalysisDenoise" size="small" style="width: 130px">
                  <el-option label="无预处理" value="none" />
                  <el-option label="小波去噪" value="wavelet" />
                  <el-option label="VMD分解" value="vmd" />
                  <el-option label="小波+VMD级联" value="wavelet_vmd" />
                  <el-option label="小波+LMS级联" value="wavelet_lms" />
                </el-select>
                <el-button
                  type="primary"
                  size="small"
                  :loading="loadingFullAnalysis"
                  @click="computeFullAnalysis"
                >
                  <el-icon><DataAnalysis /></el-icon> 全算法诊断
                </el-button>
              </template>
              <el-button v-else type="info" size="small" @click="clearFullAnalysis">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <div v-if="computedStrategyAnalyze && strategyAnalyzeData && !computedFullAnalysis">
            <!-- 策略诊断简洁结果 -->
            <el-alert
              v-if="strategyAnalyzeData.status !== 'normal'"
              :title="strategyAnalyzeData.status === 'critical' || strategyAnalyzeData.status === 'fault' ? '⚠️ 检出故障特征' : '⚡ 检出预警信号'"
              :type="strategyAnalyzeData.status === 'critical' || strategyAnalyzeData.status === 'fault' ? 'error' : 'warning'"
              :description="strategyAnalyzeData.recommendation"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
            <el-alert
              v-else
              title="✅ 未检出显著故障特征"
              type="success"
              :description="strategyAnalyzeData.recommendation || '策略诊断未检出显著故障特征，设备运行正常。'"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
            <el-descriptions :column="4" size="small" border>
              <el-descriptions-item label="健康度">{{ strategyAnalyzeData.health_score }}</el-descriptions-item>
              <el-descriptions-item label="状态">{{ strategyAnalyzeData.status }}</el-descriptions-item>
              <el-descriptions-item label="转频">{{ strategyAnalyzeData.rot_freq_hz }} Hz</el-descriptions-item>
              <el-descriptions-item label="策略">{{ analyzeStrategyLabel }}</el-descriptions-item>
              <el-descriptions-item label="峭度" v-if="strategyAnalyzeData.time_features">{{ strategyAnalyzeData.time_features.kurtosis?.toFixed(4) }}</el-descriptions-item>
              <el-descriptions-item label="RMS" v-if="strategyAnalyzeData.time_features">{{ strategyAnalyzeData.time_features.rms?.toFixed(4) }}</el-descriptions-item>
              <el-descriptions-item label="峰值因子" v-if="strategyAnalyzeData.time_features">{{ strategyAnalyzeData.time_features.crest_factor?.toFixed(4) }}</el-descriptions-item>
            </el-descriptions>
          </div>
          <div v-else-if="loadingStrategyAnalyze" class="placeholder">
            <el-icon class="is-loading"><Loading /></el-icon> 正在执行策略诊断...
          </div>
          <div v-if="computedFullAnalysis && fullAnalysisData">
            <!-- 综合结论 -->
            <el-alert
              v-if="fullAnalysisData.status !== 'normal'"
              :title="fullAnalysisData.status === 'fault' ? '⚠️ 检出故障特征' : '⚡ 检出预警信号'"
              :type="fullAnalysisData.status === 'fault' ? 'error' : 'warning'"
              :description="fullAnalysisData.recommendation"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />
            <el-alert
              v-else
              title="✅ 未检出显著故障特征"
              type="success"
              :description="fullAnalysisData.recommendation || '所有诊断方法均未检出显著故障特征，设备运行正常。'"
              show-icon
              :closable="false"
              style="margin-bottom: 12px"
            />

            <!-- 时域特征 -->
            <el-card size="small" style="margin-bottom: 12px">
              <template #header>
                <span style="font-weight: 600;">📊 时域特征参数</span>
                <el-text v-if="fullAnalysisData.rot_freq_hz" type="info" size="small" style="margin-left: 12px;">
                  估计转频: {{ fullAnalysisData.rot_freq_hz }} Hz / {{ (fullAnalysisData.rot_freq_hz * 60).toFixed(0) }} RPM
                </el-text>
              </template>
              <el-descriptions :column="4" size="small" border v-if="fullAnalysisData.time_features">
                <el-descriptions-item label="峰值">{{ fullAnalysisData.time_features.peak?.toFixed(4) }}</el-descriptions-item>
                <el-descriptions-item label="RMS">{{ fullAnalysisData.time_features.rms?.toFixed(4) }}</el-descriptions-item>
                <el-descriptions-item label="峭度">{{ fullAnalysisData.time_features.kurtosis?.toFixed(4) }}</el-descriptions-item>
                <el-descriptions-item label="偏度">{{ fullAnalysisData.time_features.skewness?.toFixed(4) }}</el-descriptions-item>
                <el-descriptions-item label="裕度">{{ fullAnalysisData.time_features.margin?.toFixed(4) }}</el-descriptions-item>
                <el-descriptions-item label="峰值因子">{{ fullAnalysisData.time_features.crest_factor?.toFixed(4) }}</el-descriptions-item>
                <el-descriptions-item label="波形因子">{{ fullAnalysisData.time_features.shape_factor?.toFixed(4) }}</el-descriptions-item>
                <el-descriptions-item label="脉冲因子">{{ fullAnalysisData.time_features.impulse_factor?.toFixed(4) }}</el-descriptions-item>
              </el-descriptions>
            </el-card>

            <!-- 轴承诊断各方法结果 -->
            <el-card size="small" style="margin-bottom: 12px">
              <template #header>
                <span style="font-weight: 600;">🔧 轴承诊断 — 各方法检出结论</span>
              </template>
              <el-table :data="bearingSummaryTable" size="small" border style="width: 100%">
                <template #empty>
                  <el-text type="info" size="small">
                    未配置轴承参数，请在<el-link type="primary" @click="$router.push('/devices')">设备配置</el-link>中设置轴承几何参数（n/d/D/α）
                  </el-text>
                </template>
                <el-table-column prop="method" label="诊断方法" width="160" />
                <el-table-column prop="faults" label="检出故障">
                  <template #default="{ row }">
                    <el-tag v-for="(f, idx) in row.faults" :key="idx" :type="f.snr > 5 ? 'danger' : 'warning'" size="small" style="margin-right: 6px; margin-bottom: 4px;">
                      {{ f.fault_type }} (SNR={{ f.snr }})
                    </el-tag>
                    <el-text v-if="row.faults.length === 0" type="info" size="small">未检出显著故障</el-text>
                  </template>
                </el-table-column>
                <el-table-column prop="params" label="关键参数" min-width="200">
                  <template #default="{ row }">
                    <el-text type="info" size="small">{{ row.params }}</el-text>
                  </template>
                </el-table-column>
              </el-table>

              <!-- 各方法详细故障指示器 -->
              <el-collapse style="margin-top: 12px;">
                <el-collapse-item title="查看各方法详细指标" name="1">
                  <div v-for="(bresult, methodKey) in fullAnalysisData.bearing_results" :key="methodKey" style="margin-bottom: 12px;">
                    <el-text type="primary" size="small" style="font-weight: 600;">{{ bearingMethodLabel(methodKey) }}</el-text>
                    <el-descriptions :column="3" size="small" border v-if="bresult.fault_indicators">
                      <el-descriptions-item
                        v-for="(info, fname) in bresult.fault_indicators"
                        :key="fname"
                        :label="fname"
                      >
                        <span v-if="info.significant" style="color: #F5222D; font-weight: 600;">
                          检出 ({{ info.detected_hz }}Hz, SNR={{ info.snr }})
                        </span>
                        <span v-else style="color: #999;">
                          未检出 (理论{{ info.theory_hz }}Hz)
                        </span>
                      </el-descriptions-item>
                    </el-descriptions>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </el-card>

            <!-- 齿轮诊断各方法结果 -->
            <el-card size="small" style="margin-bottom: 12px">
              <template #header>
                <span style="font-weight: 600;">⚙️ 齿轮诊断 — 各方法详细参数</span>
              </template>
              <el-table :data="gearSummaryTable" size="small" border style="width: 100%">
                <template #empty>
                  <el-text type="info" size="small">
                    未配置齿轮参数，请在<el-link type="primary" @click="$router.push('/devices')">设备配置</el-link>中设置齿数（input/output）
                  </el-text>
                </template>
                <el-table-column prop="method" label="诊断方法" width="140" />
                <el-table-column prop="ser" label="SER" width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.ser > 3 ? 'danger' : row.ser > 1.5 ? 'warning' : 'success'" size="small">{{ row.ser?.toFixed(3) ?? '-' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="fm0" label="FM0" width="90">
                  <template #default="{ row }">
                    <span :class="row.fm0 > 10 ? 'text-danger' : row.fm0 > 5 ? 'text-warning' : ''">{{ row.fm0?.toFixed(2) ?? '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="fm4" label="FM4" width="90">
                  <template #default="{ row }">
                    <span :class="row.fm4 > 10 ? 'text-danger' : row.fm4 > 5 ? 'text-warning' : ''">{{ row.fm4?.toFixed(2) ?? '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="car" label="CAR" width="90">
                  <template #default="{ row }">
                    <span :class="row.car > 2 ? 'text-danger' : row.car > 1.2 ? 'text-warning' : ''">{{ row.car?.toFixed(2) ?? '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="sideband_count" label="显著边频数" width="110" />
                <el-table-column prop="alerts" label="阈值告警">
                  <template #default="{ row }">
                    <el-tag v-for="(a, idx) in row.alerts" :key="idx" :type="a.level === 'critical' ? 'danger' : 'warning'" size="small" style="margin-right: 6px; margin-bottom: 4px;">
                      {{ a.indicator }}
                    </el-tag>
                    <el-text v-if="row.alerts.length === 0" type="info" size="small">无告警</el-text>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </div>
          <div v-else-if="loadingFullAnalysis" class="placeholder">
            <el-skeleton :rows="4" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="点击按钮运行全算法故障诊断对比分析" :image-size="80" />
            <div v-if="faultFreqAnnotations" style="margin-top: 8px; text-align: center;">
              <el-text type="success" size="small">
                💡 已有诊断缓存，特征频率已标注在频谱图上
              </el-text>
              <el-link type="primary" size="small" style="margin-left: 8px;" @click="gotoResearchDiagnosis">
                查看高级诊断详情 →
              </el-link>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 阶次追踪 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :span="24">
          <div class="section-header">
            <span class="chart-title">阶次谱（阶次跟踪）</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <template v-if="!computedOrder">
                <el-text type="info" size="small">转频范围</el-text>
                <el-input-number
                  v-model="orderFreqMin"
                  :min="1"
                  :max="500"
                  :step="5"
                  size="small"
                  style="width: 90px"
                  controls-position="right"
                />
                <el-text type="info" size="small">~</el-text>
                <el-input-number
                  v-model="orderFreqMax"
                  :min="1"
                  :max="500"
                  :step="5"
                  size="small"
                  style="width: 90px"
                  controls-position="right"
                />
                <el-text type="info" size="small">Hz</el-text>
                <el-text type="info" size="small" style="margin-left: 4px">每转采样</el-text>
                <el-input-number
                  v-model="orderSamplesPerRev"
                  :min="64"
                  :max="4096"
                  :step="64"
                  size="small"
                  style="width: 100px"
                  controls-position="right"
                />
                <el-button
                  type="primary"
                  size="small"
                  :loading="loadingOrder"
                  @click="computeOrder"
                >
                  <el-icon><DataAnalysis /></el-icon> 计算阶次谱
                </el-button>
              </template>
              <el-button v-else type="info" size="small" @click="clearOrder">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <div v-if="computedOrder && orderData" class="order-info">
            <el-tag type="success" size="small" effect="plain">
              估计转速 {{ orderData.rot_rpm }} RPM（转频 {{ orderData.rot_freq }} Hz）
            </el-tag>
            <el-tag type="info" size="small" effect="plain" style="margin-left: 8px;">
              每转 {{ orderData.samples_per_rev }} 点
            </el-tag>
          </div>
          <VibrationChart v-if="computedOrder" :option="orderOption" />
          <div v-else-if="loadingOrder" class="placeholder">
            <el-skeleton :rows="3" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="设置转频搜索范围后计算阶次谱" :image-size="80" />
          </div>
        </el-col>
      </el-row>

      <!-- 倒谱分析 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :span="24">
          <div class="section-header">
            <span class="chart-title">倒谱分析</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <template v-if="!computedCepstrum">
                <el-text type="info" size="small">最大倒频率</el-text>
                <el-input-number
                  v-model="cepstrumMaxQuefrency"
                  :min="10"
                  :max="2000"
                  :step="10"
                  size="small"
                  style="width: 110px"
                  controls-position="right"
                />
                <el-text type="info" size="small">ms</el-text>
                <el-button
                  type="primary"
                  size="small"
                  :loading="loadingCepstrum"
                  @click="computeCepstrum"
                >
                  <el-icon><DataAnalysis /></el-icon> 计算倒谱
                </el-button>
              </template>
              <el-button v-else type="info" size="small" @click="clearCepstrum">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <div v-if="computedCepstrum && cepstrumData" class="cepstrum-info">
            <el-text type="info" size="small" style="white-space: nowrap;">检测到峰值：</el-text>
            <el-tag
              v-for="(peak, idx) in cepstrumData.peaks"
              :key="idx"
              type="warning"
              size="small"
              effect="plain"
            >
              {{ peak.quefrency_ms }} ms → {{ peak.freq_hz }} Hz
            </el-tag>
            <el-text v-if="!cepstrumData.peaks || cepstrumData.peaks.length === 0" type="info" size="small">未检测到显著峰值</el-text>
          </div>
          <VibrationChart v-if="computedCepstrum" :option="cepstrumOption" />
          <div v-else-if="loadingCepstrum" class="placeholder">
            <el-skeleton :rows="3" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="点击按钮计算倒谱分析" :image-size="80" />
          </div>
        </el-col>
      </el-row>

      <!-- STFT 时频谱 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :span="24">
          <div class="section-header">
            <span class="chart-title">STFT 时频谱</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <template v-if="!computedSTFT">
                <el-text type="info" size="small">窗口</el-text>
                <el-input-number
                  v-model="stftNperseg"
                  :min="64"
                  :max="4096"
                  :step="64"
                  size="small"
                  style="width: 110px"
                  controls-position="right"
                />
                <el-text type="info" size="small">重叠</el-text>
                <el-input-number
                  v-model="stftNoverlap"
                  :min="0"
                  :max="4095"
                  :step="32"
                  size="small"
                  style="width: 110px"
                  controls-position="right"
                />
                <el-button
                  type="primary"
                  size="small"
                  :loading="loadingSTFT"
                  @click="computeSTFT"
                >
                  <el-icon><DataAnalysis /></el-icon> 计算 STFT
                </el-button>
              </template>
              <el-button v-else type="info" size="small" @click="clearSTFT">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <VibrationChart v-if="computedSTFT" :option="stftOption" height="600px" />
          <div v-else-if="loadingSTFT" class="placeholder">
            <el-skeleton :rows="4" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="设置窗口参数后计算 STFT 时频谱" :image-size="80" />
          </div>
        </el-col>
      </el-row>

      <!-- 阶次/包络诊断明细 -->
      <el-row :gutter="16" class="spectrum-row">
        <el-col :span="24">
          <div class="section-header">
            <span class="chart-title">🔍 频域/阶次诊断明细</span>
            <div style="display: flex; align-items: center; gap: 8px;">
              <template v-if="!showDiagnosisDetail">
                <el-button
                  type="primary"
                  size="small"
                  :loading="loadingDiagnosisDetail"
                  @click="loadDiagnosisDetail"
                >
                  <el-icon><DataAnalysis /></el-icon> 加载诊断明细
                </el-button>
              </template>
              <el-button v-else type="info" size="small" @click="showDiagnosisDetail = false">
                <el-icon><Close /></el-icon> 收起
              </el-button>
            </div>
          </div>
          <div v-if="showDiagnosisDetail">
            <DiagnosisDetail
              :order-analysis="selectedBatch.order_analysis"
              :rot-freq="orderData?.rot_freq ?? selectedBatch.rot_freq"
              :rot-rpm="orderData?.rot_rpm ?? (selectedBatch.rot_freq ? selectedBatch.rot_freq * 60 : null)"
            />
          </div>
          <div v-else class="placeholder">
            <el-empty description="点击按钮加载诊断明细" :image-size="80" />
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-empty v-else description="点击上方表格中的批次时间，查看详细数据" />


  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import VibrationChart from '../components/charts/VibrationChart.vue'
import DeviceTable from '../components/dataview/DeviceTable.vue'
import DetailHeader from '../components/dataview/DetailHeader.vue'
import DiagnosisAlert from '../components/dataview/DiagnosisAlert.vue'
import TimeDomainPanel from '../components/dataview/TimeDomainPanel.vue'
import {
  getAllDeviceData,
  getChannelData,
  getChannelFFT,
  getChannelSTFT,
  getChannelEnvelope,
  getChannelGear,
  getChannelAnalyze,
  getChannelStats,
  getChannelOrder,
  getChannelCepstrum,
  getChannelFullAnalysis,
  getChannelDiagnosis,
  deleteSpecialBatches,
  exportChannelCSV,
  updateBatchDiagnosis,
  reanalyzeBatch,
  reanalyzeAllDevice
} from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import DiagnosisDetail from '../components/DiagnosisDetail.vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const route = useRoute()
const loading = ref(false)
const deleteLoading = ref(false)
const reanalyzing = ref(false)
const reanalyzingAll = ref(false)
const deviceTableData = ref([])

// 批量删除事件处理（由 DeviceTable 子组件触发）
const onBatchDeleted = ({ deviceId, batchIndexes }) => {
  if (selectedDevice.value?.device_id === deviceId) {
    if (batchIndexes.includes(selectedBatch.value?.batch_index)) {
      selectedDevice.value = null
      selectedBatch.value = null
    }
  }
  loadAllDevices()
}

const selectedDevice = ref(null)
const selectedBatch = ref(null)
const selectedChannel = ref(1)
const maxFreq = ref(5000)
const channelOptions = ref([1, 2, 3])
const enableDetrend = ref(false)

// 诊断方法选择
const envelopeMethod = ref('envelope')
const envelopeDenoise = ref('none')
const gearMethod = ref('standard')
const denoiseMethod = ref('none')

const gearMethodLabel = computed(() => {
  const labels = {
    standard: '标准边频带',
    advanced: '高级指标',
  }
  return labels[gearMethod.value] || gearMethod.value
})

const envelopeMethodLabel = computed(() => {
  const labels = {
    envelope: '标准包络',
    kurtogram: '快速峭度图',
    cpw: 'CPW+包络',
    teager: 'TEO+包络',
    spectral_kurtosis: '谱峭度包络',
    med: 'MED+包络',
    sc_scoh: '谱相关/谱相干',
  }
  return labels[envelopeMethod.value] || envelopeMethod.value
})

const timeOption = ref(null)
const fftOption = ref(null)
const stftOption = ref(null)
const envelopeOption = ref(null)
const windowedOption = ref(null)
const orderOption = ref(null)
const cepstrumOption = ref(null)

// 按需计算状态
const computedFFT = ref(false)
const computedSTFT = ref(false)
const computedEnvelope = ref(false)
const computedStats = ref(false)
const computedOrder = ref(false)
const computedCepstrum = ref(false)
const computedGear = ref(false)
const loadingFFT = ref(false)
const loadingSTFT = ref(false)
const loadingEnvelope = ref(false)
const loadingStats = ref(false)
const loadingOrder = ref(false)
const loadingCepstrum = ref(false)
const loadingGear = ref(false)
const statsData = ref(null)
const orderData = ref(null)
const cepstrumData = ref(null)
const gearData = ref(null)
const envelopeData = ref(null)

// 综合故障诊断
const computedFullAnalysis = ref(false)
const loadingFullAnalysis = ref(false)
const fullAnalysisData = ref(null)
const fullAnalysisDenoise = ref('none')

// 策略快速诊断
const analyzeStrategy = ref('standard')
const analyzeDenoise = ref('none')
const computedStrategyAnalyze = ref(false)
const loadingStrategyAnalyze = ref(false)
const strategyAnalyzeData = ref(null)
const analyzeStrategyLabel = computed(() => {
  const labels = { standard: '标准策略', advanced: '高级策略', expert: '专家策略' }
  return labels[analyzeStrategy.value] || analyzeStrategy.value
})

// 频域/阶次诊断明细（手动加载）
const showDiagnosisDetail = ref(false)
const loadingDiagnosisDetail = ref(false)

// 特征频率标注（从诊断缓存提取，用于 FFT/包络谱 markLine）
const faultFreqAnnotations = ref(null)

// 统计指标加窗参数
const statsWindowSize = ref(1024)
const statsStep = ref(512)

// STFT 窗口参数
const stftNperseg = ref(512)
const stftNoverlap = ref(256)

// 阶次追踪参数
const orderFreqMin = ref(10)
const orderFreqMax = ref(100)
const orderSamplesPerRev = ref(1024)

// 倒谱分析参数
const cepstrumMaxQuefrency = ref(500)

// 综合故障诊断方法标签映射
const bearingMethodLabel = (key) => {
  const map = {
    envelope: '标准包络分析',
    kurtogram: '快速峭度图',
    cpw: 'CPW预白化+包络',
    teager: 'TEO能量算子+包络',
    spectral_kurtosis: '自适应谱峭度包络',
    med: 'MED最小熵解卷积+包络',
  }
  return map[key] || key
}

// 轴承诊断汇总表计算属性
const bearingSummaryTable = computed(() => {
  if (!fullAnalysisData.value?.bearing_results) return []
  const results = []
  for (const [methodKey, result] of Object.entries(fullAnalysisData.value.bearing_results)) {
    if (result.error) continue
    const faults = []
    const indicators = result.fault_indicators || {}
    for (const [fname, info] of Object.entries(indicators)) {
      if (info.significant) {
        faults.push({ fault_type: fname, snr: info.snr, detected_hz: info.detected_hz })
      }
    }
    // 关键参数
    const params = []
    if (result.optimal_fc != null) params.push(`最优频段 ${result.optimal_fc}Hz`)
    if (result.max_kurtosis != null) params.push(`峭度 ${result.max_kurtosis.toFixed(2)}`)
    if (result.kurtosis_after != null) params.push(`MED后峭度 ${result.kurtosis_after.toFixed(2)}`)
    if (result.kurtosis_before != null) params.push(`MED前峭度 ${result.kurtosis_before.toFixed(2)}`)
    results.push({
      method: bearingMethodLabel(methodKey),
      methodKey,
      faults,
      params: params.join(' | ') || '-',
    })
  }
  return results
})

// 齿轮诊断汇总表计算属性
const gearSummaryTable = computed(() => {
  if (!fullAnalysisData.value?.gear_results) return []
  const results = []
  for (const [methodKey, result] of Object.entries(fullAnalysisData.value.gear_results)) {
    if (result.error) continue
    const alerts = []
    const indicators = result.fault_indicators || {}
    for (const [iname, info] of Object.entries(indicators)) {
      if (typeof info === 'object') {
        if (info.critical) alerts.push({ indicator: iname, level: 'critical' })
        else if (info.warning) alerts.push({ indicator: iname, level: 'warning' })
      }
    }
    const sidebands = result.sidebands || []
    const sigSb = sidebands.filter(sb => sb.significant)
    results.push({
      method: methodKey === 'standard' ? '标准边频带' : '高级时域指标',
      methodKey,
      ser: result.ser,
      fm0: result.fm0,
      fm4: result.fm4,
      car: result.car,
      sideband_count: sigSb.length,
      alerts,
    })
  }
  return results
})

const statsDisplay = [
  { key: 'peak', label: '峰值', precision: 4, normal: '—' },
  { key: 'rms', label: '均方根', precision: 4, normal: '—' },
  { key: 'skewness', label: '偏度', precision: 4, normal: '≈ 0' },
  { key: 'kurtosis', label: '峭度', precision: 4, normal: '≈ 3 (正态)' },
  { key: 'windowed_kurtosis', label: '加窗峰度', precision: 4, normal: '—' },
  { key: 'crest_factor', label: '峰值因子', precision: 4, normal: '3~5' },
  { key: 'shape_factor', label: '波形因子', precision: 4, normal: '≈ 1.11 (正弦)' },
  { key: 'impulse_factor', label: '脉冲因子', precision: 4, normal: '—' },
  { key: 'margin', label: '裕度', precision: 4, normal: '—' },
]

// 统计指标分组
const statsGroups = [
  { title: '振动幅值', icon: '📊', items: [
    { key: 'peak', label: '峰值', precision: 4 },
    { key: 'rms', label: '均方根', precision: 4 },
  ]},
  { title: '分布形态', icon: '📈', items: [
    { key: 'skewness', label: '偏度', precision: 4, normal: '≈ 0' },
    { key: 'kurtosis', label: '峭度', precision: 4, normal: '≈ 3' },
    { key: 'windowed_kurtosis', label: '加窗峰度', precision: 4 },
  ]},
  { title: '无量纲因子', icon: '📐', items: [
    { key: 'crest_factor', label: '峰值因子', precision: 4, normal: '3~5' },
    { key: 'shape_factor', label: '波形因子', precision: 4, normal: '≈ 1.11' },
    { key: 'impulse_factor', label: '脉冲因子', precision: 4 },
    { key: 'margin', label: '裕度', precision: 4 },
  ]},
]



const diagnosisDesc = computed(() => {
  if (!selectedBatch.value) return ''
  const batch = selectedBatch.value
  const parts = []
  if (batch.health_score != null) {
    parts.push(`健康度评分: ${batch.health_score} 分`)
  }
  if (batch.rot_freq != null) {
    parts.push(`估计转速: ${(batch.rot_freq * 60).toFixed(0)} RPM`)
  }
  if (batch.top_fault) {
    parts.push(`主要异常: ${batch.top_fault}`)
  } else if (batch.diagnosis_status === 'fault') {
    parts.push('检测到故障特征，建议进一步分析频谱和阶次跟踪')
  } else if (batch.diagnosis_status === 'warning') {
    parts.push('检测到预警信号，建议关注设备运行状态')
  }
  return parts.join('；')
})

// ========== 加载设备表格 ==========
const loadAllDevices = async () => {
  loading.value = true
  try {
    const res = await getAllDeviceData()
    const data = res.data || []
    // 确保每个设备的批次按时间从近到远排序
    for (const dev of data) {
      if (dev.batches && dev.batches.length > 1) {
        dev.batches.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      }
    }
    deviceTableData.value = data
  } catch (e) {
    console.error('加载设备数据失败:', e)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

// ========== 加载诊断明细（手动触发） ==========
const loadDiagnosisDetail = async () => {
  loadingDiagnosisDetail.value = true
  try {
    // 先尝试加载通道级缓存诊断
    try {
      const res = await getChannelDiagnosis(
        selectedDevice.value.device_id,
        selectedBatch.value.batch_index,
        selectedChannel.value,
        fullAnalysisDenoise.value
      )
      const d = res.data
      if (d && d.order_analysis) {
        selectedBatch.value.order_analysis = d.order_analysis
      }
      if (d && d.rot_freq) {
        selectedBatch.value.rot_freq = d.rot_freq
      }
    } catch (e) {
      // 404 表示无缓存，不做处理
    }
    showDiagnosisDetail.value = true
  } catch (e) {
    console.error('加载诊断明细失败:', e)
    ElMessage.error('加载诊断明细失败')
  } finally {
    loadingDiagnosisDetail.value = false
  }
}

// ========== 自动查询数据库诊断结果（全分析用） ==========
const loadCachedDiagnosis = async () => {
  if (!selectedDevice.value || !selectedBatch.value || !selectedChannel.value) return
  try {
    const res = await getChannelDiagnosis(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      fullAnalysisDenoise.value
    )
    const d = res.data
    if (d) {
      fullAnalysisData.value = d
      computedFullAnalysis.value = true
    }
  } catch (e) {
    // 404 表示数据库中没有诊断结果，不做任何操作
    if (e.response?.status !== 404) {
      console.error('查询缓存诊断失败:', e)
    }
  }
}

const selectBatch = (device, batch) => {
  // 重置按需计算状态
  resetComputedState()

  selectedDevice.value = device
  selectedBatch.value = batch
  // 通道选项按该批次实际存储的通道数决定（旧批次可能是3通道，新批次可能是2通道）
  const actualChannels = batch.channel_count || device.channel_count || 3
  channelOptions.value = Array.from({ length: actualChannels }, (_, i) => i + 1)
  selectedChannel.value = 1

  nextTick(() => {
    loadTimeDomain()
    // 自动加载数据库中已保存的转频（阶次追踪权威值）
    loadSavedRotFreq()
  })
}

/** 自动从诊断表中加载已存转频，避免每次都要手动点击计算阶次谱 */
const loadSavedRotFreq = async () => {
  try {
    const res = await getChannelDiagnosis(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value  // 使用当前选中通道
    )
    const d = res.data
    if (d) {
      // rot_freq 优先取顶层字段，其次取 order_analysis 中的
      const savedRf = d.rot_freq ?? d.order_analysis?.rot_freq_hz
      if (savedRf != null && savedRf > 0) {
        selectedBatch.value.rot_freq = savedRf
        if (d.order_analysis) {
          selectedBatch.value.order_analysis = d.order_analysis
        }
      }
      // 提取特征频率标注信息（轴承特征频率 + 齿轮啮合频率）
      extractFaultFreqAnnotations(d)
    }
  } catch (e) {
    // 无缓存数据时不报错
  }
}

/** 从诊断结果提取特征频率列表，用于 FFT/包络谱的 markLine 标注 */
const extractFaultFreqAnnotations = (diagData) => {
  const annotations = []
  // 从 engine_result 或 full_analysis 中提取
  const engineResult = diagData.engine_result || diagData.full_analysis
  if (!engineResult) {
    faultFreqAnnotations.value = null
    return
  }

  // 轴承特征频率（从 fault_indicators 或 bearing_results 中提取）
  const bearingSource = engineResult.bearing?.fault_indicators
    || engineResult.bearing_results?.envelope?.fault_indicators
  if (bearingSource) {
    for (const [name, info] of Object.entries(bearingSource)) {
      if (info && typeof info === 'object') {
        const freq = info.detected_hz ?? info.theory_hz
        if (freq && freq > 0) {
          annotations.push({
            freq,
            name,
            detected: !!info.significant,
            type: 'bearing',
          })
        }
      }
    }
  }

  // 齿轮特征频率
  const gearSource = engineResult.gear?.fault_indicators
    || Object.values(engineResult.gear_results || {})[0]?.fault_indicators
  if (gearSource) {
    for (const [name, info] of Object.entries(gearSource)) {
      if (info && typeof info === 'object') {
        const freq = info.frequency_hz ?? info.detected_hz ?? info.theory_hz
        if (freq && freq > 0) {
          annotations.push({
            freq,
            name,
            detected: !!info.critical || !!info.significant,
            type: 'gear',
          })
        }
      }
    }
  }

  // 啮合频率（从齿轮结果中直接提取）
  for (const [, gResult] of Object.entries(engineResult.gear_results || {})) {
    if (gResult.mesh_freq_hz && gResult.mesh_freq_hz > 0) {
      annotations.push({
        freq: gResult.mesh_freq_hz,
        name: '啮合频率',
        detected: false,
        type: 'gear_mesh',
      })
    }
  }

  // 转频（如果有的话）
  const rotFreq = diagData.rot_freq ?? engineResult.rot_freq_hz
  if (rotFreq && rotFreq > 0) {
    annotations.push({
      freq: rotFreq,
      name: '1×fr',
      detected: false,
      type: 'rotation',
    })
    annotations.push({
      freq: rotFreq * 2,
      name: '2×fr',
      detected: false,
      type: 'rotation',
    })
  }

  faultFreqAnnotations.value = annotations.length > 0 ? annotations : null
}

/** 将特征频率标注叠加到 ECharts option 的 markLine 上 */
const addFreqAnnotationsToOption = (option, freqData) => {
  if (!faultFreqAnnotations.value || !freqData || freqData.length === 0) return option

  // category 轴需要换算频率到索引
  const freqStep = freqData.length > 1 ? freqData[1] - freqData[0] : 1
  const markLineData = []

  for (const ann of faultFreqAnnotations.value) {
    // 检查频率是否在图表范围内
    const maxF = parseFloat(freqData[freqData.length - 1])
    if (ann.freq > maxF) continue

    // 对 category 轴换算为索引位置
    const idx = Math.round(ann.freq / freqStep)
    if (idx < 0 || idx >= freqData.length) continue

    const isDetected = ann.detected
    const labelPrefix = ann.type === 'bearing' ? '🧩' : ann.type === 'gear' ? '⚙' : ann.type === 'gear_mesh' ? '🔧' : '🔄'

    markLineData.push({
      xAxis: idx,
      name: `${labelPrefix} ${ann.name}(${ann.freq.toFixed(1)}Hz)`,
      lineStyle: {
        type: isDetected ? 'solid' : 'dashed',
        color: isDetected ? '#F5222D' : ann.type === 'bearing' ? '#165DFF' : ann.type === 'gear' ? '#FAAD14' : '#999',
        width: isDetected ? 2 : 1,
      },
    })
  }

  if (markLineData.length === 0) return option

  // 添加或合并 markLine
  const series = option.series?.[0] || {}
  const existingMarkLine = series.markLine?.data || []
  series.markLine = {
    silent: true,
    symbol: 'none',
    lineStyle: { type: 'dashed', color: '#999' },
    data: [...existingMarkLine, ...markLineData],
    label: { formatter: '{b}', position: 'insideEndTop', fontSize: 10 },
  }
  option.series[0] = series
  return option
}

const resetComputedState = () => {
  computedFFT.value = false
  computedSTFT.value = false
  computedEnvelope.value = false
  computedStats.value = false
  computedOrder.value = false
  computedCepstrum.value = false
  computedGear.value = false
  computedFullAnalysis.value = false
  showDiagnosisDetail.value = false
  statsData.value = null
  orderData.value = null
  cepstrumData.value = null
  gearData.value = null
  fullAnalysisData.value = null
  timeOption.value = null
  fftOption.value = null
  stftOption.value = null
  envelopeOption.value = null
  windowedOption.value = null
  orderOption.value = null
  cepstrumOption.value = null
}

const onChannelChange = () => {
  // 通道切换时，时域图重新加载，其他收起
  resetComputedState()
  timeOption.value = null
  envelopeData.value = null
  gearData.value = null
  nextTick(() => {
    loadTimeDomain()
  })
}

const onDetrendChange = () => {
  // 去趋势开关切换时，重新加载当前已显示的内容
  timeOption.value = null
  nextTick(() => {
    loadTimeDomain()
  })
  if (computedFFT.value) computeFFT()
  if (computedSTFT.value) computeSTFT()
  if (computedEnvelope.value) computeEnvelope()
  if (computedOrder.value) computeOrder()
  if (computedCepstrum.value) computeCepstrum()
  if (computedStats.value) { windowedOption.value = null; computeStats() }
  if (computedGear.value) computeGear()
  if (computedFullAnalysis.value) computeFullAnalysis()
}

const onMaxFreqChange = () => {
  // 频率范围改变时，如果已计算 FFT/STFT/包络/阶次，重新计算
  if (computedFFT.value) computeFFT()
  if (computedSTFT.value) computeSTFT()
  if (computedEnvelope.value) computeEnvelope()
  if (computedOrder.value) computeOrder()
}

const onDenoiseChange = () => {
  // 预处理方法改变时，重新计算所有已展开的分析
  if (computedFFT.value) computeFFT()
  if (computedSTFT.value) computeSTFT()
  if (computedEnvelope.value) computeEnvelope()
  if (computedOrder.value) computeOrder()
  if (computedCepstrum.value) computeCepstrum()
  if (computedStats.value) computeStats()
  if (computedGear.value) computeGear()
  if (computedFullAnalysis.value) computeFullAnalysis()
}

// ========== 时域波形（始终自动加载） ==========
const loadTimeDomain = async () => {
  try {
    const res = await getChannelData(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      enableDetrend.value
    )
    const d = res.data
    if (!d) return

    const sr = d.sample_rate || 25600
    const timeData = d.data || []
    const timeX = timeData.map((_, i) => (i / sr).toFixed(4))

    timeOption.value = {
      tooltip: { trigger: 'axis', triggerOn: 'click' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: timeX, name: '时间 (s)', nameGap: 25 },
      yAxis: { type: 'value', name: '幅值' },
      dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 0 }],
      series: [{
        type: 'line',
        data: timeData,
        showSymbol: false,
        sampling: 'lttb',
        lineStyle: { width: 1, color: '#165DFF' }
      }]
    }
  } catch (e) {
    console.error('时域加载失败:', e)
  }
}

// ========== 按需计算：FFT ==========
const computeFFT = async () => {
  loadingFFT.value = true
  try {
    const res = await getChannelFFT(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      maxFreq.value,
      enableDetrend.value
    )
    const d = res.data
    if (!d) return

    computedFFT.value = true
    fftOption.value = {
      tooltip: { trigger: 'axis', triggerOn: 'click' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: d.fft_freq, name: '频率 (Hz)', nameGap: 25 },
      yAxis: { type: 'value', name: '幅值' },
      dataZoom: [{ type: 'inside' }],
      series: [{
        type: 'line',
        data: d.fft_amp,
        showSymbol: false,
        sampling: 'lttb',
        areaStyle: { color: 'rgba(22, 93, 255, 0.2)' },
        lineStyle: { width: 1.5, color: '#165DFF' }
      }]
    }
    // 叠加特征频率标注
    addFreqAnnotationsToOption(fftOption.value, d.fft_freq)
  } catch (e) {
    console.error('FFT 计算失败:', e)
    ElMessage.error('FFT 计算失败')
    computedFFT.value = false
  } finally {
    loadingFFT.value = false
  }
}

const clearFFT = () => {
  computedFFT.value = false
  fftOption.value = null
}

// ========== 按需计算：STFT ==========
const computeSTFT = async () => {
  loadingSTFT.value = true
  try {
    const res = await getChannelSTFT(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      maxFreq.value,
      stftNperseg.value,
      stftNoverlap.value,
      enableDetrend.value
    )
    const d = res.data
    if (!d) return

    computedSTFT.value = true
    const minVal = Math.min(...d.magnitude.flat())
    const maxVal = Math.max(...d.magnitude.flat())
    stftOption.value = {
      tooltip: { position: 'top', triggerOn: 'click' },
      grid: { left: '10%', right: '12%', bottom: '18%', top: '10%' },
      xAxis: { type: 'category', data: d.time, name: '时间 (s)' },
      yAxis: { type: 'category', data: d.freq, name: '频率 (Hz)' },
      dataZoom: [
        // 鼠标滚轮/拖拽缩放
        { type: 'inside', xAxisIndex: 0, filterMode: 'empty' },
        { type: 'inside', yAxisIndex: 0, filterMode: 'empty' },
        // X轴（时间）底部滑动条
        {
          type: 'slider', xAxisIndex: 0, filterMode: 'empty',
          height: 18, bottom: 38,
          handleSize: '80%', showDetail: false,
          borderColor: 'transparent', backgroundColor: '#f5f5f5',
          fillerColor: 'rgba(22, 93, 255, 0.15)',
          handleStyle: { color: '#165DFF' }
        },
        // Y轴（频率）右侧滑动条
        {
          type: 'slider', yAxisIndex: 0, filterMode: 'empty',
          width: 18, right: 10,
          handleSize: '80%', showDetail: false,
          borderColor: 'transparent', backgroundColor: '#f5f5f5',
          fillerColor: 'rgba(22, 93, 255, 0.15)',
          handleStyle: { color: '#165DFF' }
        }
      ],
      visualMap: {
        min: minVal, max: maxVal, calculable: true,
        orient: 'horizontal', left: 'center', bottom: '0%',
        inRange: { color: ['#0d0887', '#46039f', '#7201a8', '#9c179e', '#bd3786', '#d8576b', '#ed7953', '#fdb42f', '#f0f921'] }
      },
      series: [{
        type: 'heatmap',
        data: d.magnitude.flatMap((row, y) => row.map((val, x) => [x, y, val])),
        emphasis: { itemStyle: { borderColor: '#333', borderWidth: 1 } }
      }]
    }
  } catch (e) {
    console.error('STFT 计算失败:', e)
    ElMessage.error('STFT 计算失败')
    computedSTFT.value = false
  } finally {
    loadingSTFT.value = false
  }
}

const clearSTFT = () => {
  computedSTFT.value = false
  stftOption.value = null
}

// ========== 按需计算：包络谱 ==========
const computeEnvelope = async () => {
  loadingEnvelope.value = true
  try {
    const res = await getChannelEnvelope(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      1000,
      enableDetrend.value,
      envelopeMethod.value,
      envelopeDenoise.value
    )
    const d = res.data
    if (!d) return

    envelopeData.value = d
    computedEnvelope.value = true
    envelopeOption.value = {
      tooltip: { trigger: 'axis', triggerOn: 'click' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: d.envelope_freq, name: '频率 (Hz)', nameGap: 25 },
      yAxis: { type: 'value', name: '包络幅值' },
      dataZoom: [{ type: 'inside' }],
      series: [{
        type: 'line',
        data: d.envelope_amp,
        showSymbol: false,
        areaStyle: { color: 'rgba(250, 173, 20, 0.2)' },
        lineStyle: { width: 1.5, color: '#FAAD14' }
      }]
    }
    // 叠加特征频率标注（包络谱是轴承诊断核心视图，标注尤为重要）
    addFreqAnnotationsToOption(envelopeOption.value, d.envelope_freq)
  } catch (e) {
    console.error('包络谱计算失败:', e)
    ElMessage.error('包络谱计算失败: ' + (e.response?.data?.detail || e.message))
    computedEnvelope.value = false
  } finally {
    loadingEnvelope.value = false
  }
}

const clearEnvelope = () => {
  computedEnvelope.value = false
  envelopeOption.value = null
}

// ========== 按需计算：阶次追踪 ==========
const computeOrder = async () => {
  loadingOrder.value = true
  try {
    const res = await getChannelOrder(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      orderFreqMin.value,
      orderFreqMax.value,
      orderSamplesPerRev.value,
      50,
      enableDetrend.value
    )
    const d = res.data
    if (!d) return

    orderData.value = d
    computedOrder.value = true

    // 如果实时计算的转频与数据库历史值差异较大，写回数据库覆盖
    const batchRotFreq = selectedBatch.value?.rot_freq
    if (d.rot_freq != null && Math.abs(d.rot_freq - (batchRotFreq || 0)) > 0.1) {
      try {
        await updateBatchDiagnosis(
          selectedDevice.value.device_id,
          selectedBatch.value.batch_index,
          {
            order_analysis: {
              rot_freq_hz: d.rot_freq,
              rot_rpm: d.rot_rpm,
            },
            rot_freq: d.rot_freq,
          }
        )
        // 同步更新本地数据，避免刷新前显示不一致
        selectedBatch.value.rot_freq = d.rot_freq
        if (selectedBatch.value.order_analysis) {
          selectedBatch.value.order_analysis.rot_freq_hz = d.rot_freq
          selectedBatch.value.order_analysis.rot_rpm = d.rot_rpm
        }
        ElMessage.success('诊断转频已更新为实时计算值')
      } catch (err) {
        console.error('更新诊断数据失败:', err)
      }
    }

    // category 轴的 markLine xAxis 是索引而非数值，需换算
    const orderStep = d.orders[1] - d.orders[0]
    const idx1x = Math.min(Math.round(1 / orderStep), d.orders.length - 1)
    const idx2x = Math.min(Math.round(2 / orderStep), d.orders.length - 1)
    const idx3x = Math.min(Math.round(3 / orderStep), d.orders.length - 1)
    orderOption.value = {
      tooltip: { trigger: 'axis', triggerOn: 'click', formatter: (params) => {
        const p = params[0]
        return `阶次: ${p.name}<br/>幅值: ${p.value}`
      }},
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: d.orders, name: '阶次', nameGap: 25 },
      yAxis: { type: 'value', name: '幅值' },
      dataZoom: [{ type: 'inside' }],
      series: [{
        type: 'line',
        data: d.spectrum,
        showSymbol: false,
        areaStyle: { color: 'rgba(82, 196, 26, 0.2)' },
        lineStyle: { width: 1.5, color: '#52C41A' },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: '#999' },
          data: [
            { xAxis: idx1x, name: '1×转频' },
            { xAxis: idx2x, name: '2×转频' },
            { xAxis: idx3x, name: '3×转频' }
          ],
          label: { formatter: '{b}', position: 'insideEndTop', fontSize: 10 }
        }
      }]
    }
  } catch (e) {
    console.error('阶次谱计算失败:', e)
    ElMessage.error('阶次谱计算失败: ' + (e.response?.data?.detail || e.message))
    computedOrder.value = false
  } finally {
    loadingOrder.value = false
  }
}

const clearOrder = () => {
  computedOrder.value = false
  orderData.value = null
  orderOption.value = null
}

// ========== 按需计算：倒谱分析 ==========
const computeCepstrum = async () => {
  loadingCepstrum.value = true
  try {
    const res = await getChannelCepstrum(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      cepstrumMaxQuefrency.value,
      enableDetrend.value
    )
    const d = res.data
    if (!d) return

    cepstrumData.value = d
    computedCepstrum.value = true
    // value 轴避免 category 轴标签重叠（12800 个点）
    const xyData = d.quefrency.map((q, i) => [q, d.cepstrum[i]])
    const markLines = (d.peaks || []).map(p => ({
      xAxis: p.quefrency_ms,
      name: `${p.freq_hz}Hz`
    }))
    cepstrumOption.value = {
      tooltip: { trigger: 'axis', triggerOn: 'click', formatter: (params) => {
        const p = params[0]
        return `倒频率: ${p.value[0]} ms<br/>幅值: ${p.value[1]}`
      }},
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'value', name: '倒频率 (ms)', nameGap: 25, min: 0 },
      yAxis: { type: 'value', name: '倒谱幅值' },
      dataZoom: [{ type: 'inside' }],
      series: [{
        type: 'line',
        data: xyData,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#722ED1' },
        areaStyle: { color: 'rgba(114, 46, 209, 0.15)' },
        markLine: markLines.length > 0 ? {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: '#FAAD14' },
          data: markLines,
          label: { formatter: '{b}', position: 'insideEndTop', fontSize: 10 }
        } : undefined
      }]
    }
  } catch (e) {
    console.error('倒谱计算失败:', e)
    ElMessage.error('倒谱计算失败: ' + (e.response?.data?.detail || e.message))
    computedCepstrum.value = false
  } finally {
    loadingCepstrum.value = false
  }
}

const clearCepstrum = () => {
  computedCepstrum.value = false
  cepstrumData.value = null
  cepstrumOption.value = null
}

// ========== 按需计算：齿轮诊断 ==========
const computeGear = async () => {
  loadingGear.value = true
  try {
    const res = await getChannelGear(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      enableDetrend.value,
      gearMethod.value,
      denoiseMethod.value
    )
    const d = res.data
    if (!d) return

    gearData.value = d
    computedGear.value = true
  } catch (e) {
    console.error('齿轮诊断失败:', e)
    ElMessage.error('齿轮诊断失败: ' + (e.response?.data?.detail || e.message))
    computedGear.value = false
  } finally {
    loadingGear.value = false
  }
}

const clearGear = () => {
  computedGear.value = false
  gearData.value = null
}

const computeFullAnalysis = async () => {
  loadingFullAnalysis.value = true
  try {
    // 1. 先尝试查缓存（需确认是 full_analysis 结果，不是普通 engine_result）
    try {
      const cached = await getChannelDiagnosis(
        selectedDevice.value.device_id,
        selectedBatch.value.batch_index,
        selectedChannel.value,
        fullAnalysisDenoise.value
      )
      const d = cached.data
      // 全算法结果必须有 bearing_results 和 gear_results，否则是普通诊断缓存
      if (d && d.bearing_results && d.gear_results) {
        fullAnalysisData.value = d
        computedFullAnalysis.value = true
        // 从缓存数据提取特征频率标注
        extractFaultFreqAnnotations(d)
        return
      }
    } catch (e) {
      if (e.response?.status !== 404) {
        console.error('查询缓存诊断失败:', e)
      }
    }

    // 2. 无缓存，执行实时计算
    const res = await getChannelFullAnalysis(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      {
        detrend: enableDetrend.value,
        denoise: fullAnalysisDenoise.value,
      }
    )
    const d = res.data
    if (!d) return
    fullAnalysisData.value = d
    computedFullAnalysis.value = true
    // 从实时计算结果提取特征频率标注
    extractFaultFreqAnnotations(d)
  } catch (e) {
    console.error('全算法诊断失败:', e)
    ElMessage.error('全算法诊断失败: ' + (e.response?.data?.detail || e.message))
    computedFullAnalysis.value = false
  } finally {
    loadingFullAnalysis.value = false
  }
}

const clearFullAnalysis = () => {
  computedFullAnalysis.value = false
  fullAnalysisData.value = null
}

// ========== 策略快速诊断 ==========
const computeStrategyAnalyze = async () => {
  if (!selectedDevice.value || !selectedBatch.value) {
    ElMessage.warning('请先选择设备和批次')
    return
  }
  loadingStrategyAnalyze.value = true
  try {
    const res = await getChannelAnalyze(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      {
        strategy: analyzeStrategy.value,
        denoise: analyzeDenoise.value,
      }
    )
    const d = res.data
    if (!d) return
    strategyAnalyzeData.value = d
    computedStrategyAnalyze.value = true
    // 提取特征频率标注
    if (d.bearing_result?.fault_indicators) {
      extractFaultFreqAnnotations(d)
    }
  } catch (e) {
    console.error('策略诊断失败:', e)
    ElMessage.error('策略诊断失败: ' + (e.response?.data?.detail || e.message))
    computedStrategyAnalyze.value = false
  } finally {
    loadingStrategyAnalyze.value = false
  }
}

const clearStrategyAnalyze = () => {
  computedStrategyAnalyze.value = false
  strategyAnalyzeData.value = null
}

// ========== 按需计算：统计指标 ==========
const computeStats = async () => {
  loadingStats.value = true
  try {
    const res = await getChannelStats(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      statsWindowSize.value,
      statsStep.value,
      enableDetrend.value
    )
    statsData.value = res.data
    computedStats.value = true
    await nextTick()
    initWindowedChart()
  } catch (e) {
    console.error('统计指标计算失败:', e)
    ElMessage.error('统计指标计算失败')
    computedStats.value = false
  } finally {
    loadingStats.value = false
  }
}

const clearStats = () => {
  computedStats.value = false
  statsData.value = null
  windowedOption.value = null
}

// 初始化加窗统计量时序图
const initWindowedChart = () => {
  const ws = statsData.value?.window_series
  if (!ws || !ws.time || ws.time.length === 0) return

  windowedOption.value = {
    tooltip: { trigger: 'axis', triggerOn: 'click' },
    legend: {
      data: ['峭度', '偏度', 'RMS', '峰值', '裕度', '峰值因子', '波形因子', '脉冲因子'],
      type: 'scroll',
      bottom: 0
    },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
    xAxis: { type: 'category', data: ws.time, name: '时间 (s)', nameGap: 25 },
    yAxis: [
      { type: 'value', name: '无量纲指标', position: 'left' },
      { type: 'value', name: '幅值', position: 'right' }
    ],
    dataZoom: [{ type: 'inside' }],
    series: [
      {
        name: '峭度',
        type: 'line',
        data: ws.kurtosis,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#F5222D' }
      },
      {
        name: '偏度',
        type: 'line',
        data: ws.skewness,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#EB2F96' }
      },
      {
        name: '裕度',
        type: 'line',
        data: ws.margin,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#722ED1' }
      },
      {
        name: '峰值因子',
        type: 'line',
        data: ws.crest_factor,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#13C2C2' }
      },
      {
        name: '波形因子',
        type: 'line',
        data: ws.shape_factor,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#52C41A' }
      },
      {
        name: '脉冲因子',
        type: 'line',
        data: ws.impulse_factor,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#FA8C16' }
      },
      {
        name: 'RMS',
        type: 'line',
        yAxisIndex: 1,
        data: ws.rms,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#165DFF' }
      },
      {
        name: '峰值',
        type: 'line',
        yAxisIndex: 1,
        data: ws.peak,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#FAAD14' }
      }
    ]
  }
}

// ========== 导出 CSV ==========
const onExportCSV = () => {
  if (!selectedDevice.value || !selectedBatch.value) return
  exportChannelCSV(
    selectedDevice.value.device_id,
    selectedBatch.value.batch_index,
    selectedChannel.value,
    enableDetrend.value
  )
}

// ========== 重新诊断 ==========
const onReanalyze = async () => {
  if (!selectedDevice.value || !selectedBatch.value) return
  try {
    reanalyzing.value = true
    const res = await reanalyzeBatch(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index
    )
    const d = res.data || {}
    ElMessage.success(`重新诊断完成，健康度 ${d.health_score} 分`)
    // 更新本地选中批次数据
    selectedBatch.value.health_score = d.health_score
    selectedBatch.value.diagnosis_status = d.status
    selectedBatch.value.rot_freq = d.rot_freq
    if (d.order_analysis) {
      selectedBatch.value.order_analysis = d.order_analysis
    }
    // 刷新设备列表以同步最新状态
    await loadAllDevices()
  } catch (e) {
    console.error('重新诊断失败:', e)
    ElMessage.error('重新诊断失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    reanalyzing.value = false
  }
}

// ========== 全部重新诊断 ==========
const onReanalyzeAll = async () => {
  if (!selectedDevice.value) return
  try {
    await ElMessageBox.confirm(
      `确定对设备 ${selectedDevice.value.device_id} 的所有批次重新诊断吗？这可能需要较长时间。`,
      '全部重新诊断',
      { confirmButtonText: '开始', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    reanalyzingAll.value = true
    ElMessage.info('开始全部重新诊断，请耐心等待...')
    const res = await reanalyzeAllDevice(selectedDevice.value.device_id)
    const d = res.data || {}
    ElMessage.success(`全部重新诊断完成，成功 ${d.updated}/${d.total} 个批次`)
    // 刷新设备列表和当前选中批次数据
    await loadAllDevices()
  } catch (e) {
    console.error('全部重新诊断失败:', e)
    ElMessage.error('全部重新诊断失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    reanalyzingAll.value = false
  }
}

// ========== 删除 ==========
const onDeleteBatch = async (deviceId, batchIndex) => {
  try {
    await ElMessageBox.confirm(
      `确定删除设备 ${deviceId} 的批次 ${batchIndex} 吗？此操作不可恢复。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    deleteLoading.value = true
    await deleteBatch(deviceId, batchIndex)
    ElMessage.success('删除成功')
    if (selectedDevice.value?.device_id === deviceId && selectedBatch.value?.batch_index === batchIndex) {
      selectedDevice.value = null
      selectedBatch.value = null
    }
    await loadAllDevices()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('删除失败:', e)
      ElMessage.error('删除失败')
    }
  } finally {
    deleteLoading.value = false
  }
}



const onDeleteAllSpecial = async () => {
  try {
    await ElMessageBox.confirm(
      '确定清空所有设备的特殊数据吗？此操作不可恢复。',
      '确认删除',
      { confirmButtonText: '全部删除', cancelButtonText: '取消', type: 'danger' }
    )
    deleteLoading.value = true
    for (const dev of deviceTableData.value) {
      await deleteSpecialBatches(dev.device_id)
    }
    ElMessage.success('所有特殊数据已清空')
    selectedDevice.value = null
    selectedBatch.value = null
    await loadAllDevices()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('删除失败:', e)
      ElMessage.error('删除失败')
    }
  } finally {
    deleteLoading.value = false
  }
}

const autoSelectFromQuery = () => {
  const qDeviceId = route.query.device_id
  const qBatchIndex = route.query.batch_index
  if (!qDeviceId || !qBatchIndex) return

  const device = deviceTableData.value.find(d => d.device_id === qDeviceId)
  if (!device) return

  const batch = device.batches.find(b => String(b.batch_index) === String(qBatchIndex))
  if (!batch) return

  selectBatch(device, batch)
}

// 跳转到高级诊断页面，携带当前设备/批次/通道参数
const gotoResearchDiagnosis = () => {
  if (!selectedDevice.value || !selectedBatch.value) return
  router.push({
    path: '/research-diagnosis',
    query: {
      device_id: selectedDevice.value.device_id,
      batch_index: selectedBatch.value.batch_index,
      channel: selectedChannel.value,
    }
  })
}

onMounted(async () => {
  await loadAllDevices()
  autoSelectFromQuery()
})

onUnmounted(() => {
  // VibrationChart 组件内部会自动 dispose
})
</script>

<style scoped>
.data-view {
  padding: 0;
}

.header-card {
  margin-bottom: 16px;
}

.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 8px;
}

.detail-card {
  margin-bottom: 20px;
}

.chart-title {
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.chart {
  height: 320px;
  width: 100%;
}

.spectrum-row {
  margin-top: 16px;
}

.placeholder {
  height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 8px;
}

.stats-grouped {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stats-group {
  border-radius: 8px;
  padding: 12px 16px;
  background: #f5f7fa;
}

.stats-group-title {
  font-weight: 600;
  font-size: 14px;
  color: #1d2129;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #165DFF;
}

.stat-normal {
  margin-left: 6px;
  font-size: 12px;
}

.order-info {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
}

.cepstrum-info {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f9f0ff;
  border: 1px solid #d3adf7;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.envelope-info {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.gear-info {
  margin-bottom: 8px;
  padding: 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
}
</style>
