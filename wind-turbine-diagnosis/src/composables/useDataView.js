/**
 * DataView 数据查看页逻辑
 *
 * 职责:设备/批次表格加载与选择、时域波形自动加载、FFT/STFT/包络/阶次/倒谱/
 *       统计/齿轮等按需计算与图表 option 组装、特征频率标注、综合与策略诊断、
 *       诊断缓存读写、删除与重新诊断、路由联动。
 */
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { formatErrorMessage } from '../utils/errorMessage'
import { getDiagnosisView } from '../utils/diagnosisStatus'
import { useRoute, useRouter } from 'vue-router'
import {
  getAllDeviceData,
  getChannelData,
  getChannelFFT,
  getChannelSTFT,
  getChannelEnvelope,
  getChannelGear,
  getChannelStats,
  getChannelOrder,
  getChannelCepstrum,
  deleteBatch,
  deleteSpecialBatches,
  exportChannelCSV
} from '../api/data'
import {
  getChannelAnalyze,
  getChannelFullAnalysis,
  getChannelDiagnosis,
  updateBatchDiagnosis,
  reanalyzeBatch,
  reanalyzeAllDevice
} from '../api/diagnosis'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  bearingFrequencyAnnotations,
  significantBearingFaults,
  bearingMethodLabel,
} from '../utils/bearingDiagnosis'


export const statsDisplay = [
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

export const statsGroups = [
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

export function useDataView() {
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
      filter_bank_sk: '二叉滤波器组谱峭度',
      cpw: 'CPW+包络',
      teager: 'TEO+包络',
      spectral_kurtosis: '谱峭度包络',
      med: 'MED+包络',
      sc_scoh: '谱相关/谱相干',
      mckd: 'MCKD增强包络',
      wp: 'WP包络',
      dwt: 'DWT包络',
      emd_envelope: 'EMD包络',
      ceemdan_envelope: 'CEEMDAN包络',
      vmd_envelope: 'VMD包络',
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
  const analyzeDenoise = ref('none')
  const computedStrategyAnalyze = ref(false)
  const loadingStrategyAnalyze = ref(false)
  const strategyAnalyzeData = ref(null)

  // 频域/阶次诊断明细（手动加载）
  const showDiagnosisDetail = ref(false)
  const loadingDiagnosisDetail = ref(false)
  const diagnosisDetailData = ref(null)

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

  // 轴承诊断汇总表计算属性
  const bearingSummaryTable = computed(() => {
    if (!fullAnalysisData.value?.bearing_results) return []
    const results = []
    for (const [methodKey, result] of Object.entries(fullAnalysisData.value.bearing_results)) {
      if (result.error) continue
      const faults = significantBearingFaults(result)
      // 关键参数优先使用新契约中的实际分析频带
      const params = []
      if (result.band?.center_hz != null) {
        params.push(`频带 ${result.band.low_hz}~${result.band.high_hz}Hz`)
      }
      if (result.max_kurtosis != null) params.push(`峭度 ${result.max_kurtosis.toFixed(2)}`)
      if (result.kurtosis_after != null) params.push(`MED后峭度 ${result.kurtosis_after.toFixed(2)}`)
      if (result.kurtosis_before != null) params.push(`MED前峭度 ${result.kurtosis_before.toFixed(2)}`)
      results.push({
        method: bearingMethodLabel(methodKey),
        methodKey,
        faults,
        evaluationStatus: result.evaluation?.evaluation_status ?? null,
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

  // 统计指标分组

  const diagnosisDesc = computed(() => {
    if (!selectedBatch.value) return ''
    const batch = selectedBatch.value
    const parts = []
    const view = getDiagnosisView(batch)
    parts.push(`诊断：${view.label}`)
    if (view.scoreText !== '-') parts.push(`健康度评分: ${view.scoreText} 分`)
    if (batch.rot_freq != null) {
      parts.push(`估计转速: ${(batch.rot_freq * 60).toFixed(0)} RPM`)
    }
    if (batch.top_fault) {
      parts.push(`主要异常: ${batch.top_fault}`)
    }
    if (batch.coverage === 'partial') parts.push('仅部分对象形成有效评估')
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
      ElMessage.error(formatErrorMessage(e, '加载数据失败'))
    } finally {
      loading.value = false
    }
  }

  // ========== 加载诊断明细（手动触发） ==========
  const loadDiagnosisDetail = async () => {
    loadingDiagnosisDetail.value = true
    try {
      const res = await getChannelDiagnosis(
        selectedDevice.value.device_id,
        selectedBatch.value.batch_index,
        selectedChannel.value,
        { denoise_method: denoiseMethod.value }
      )
      diagnosisDetailData.value = res.data || null
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
        { denoise_method: fullAnalysisDenoise.value }
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
        selectedChannel.value,
        { denoise_method: 'none' }
      )
      const d = res.data
      if (d) {
        const savedRf = d.rot_freq_hz
        if (savedRf != null && savedRf > 0) selectedBatch.value.rot_freq = savedRf
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
    const engineResult = diagData
    if (!engineResult) {
      faultFreqAnnotations.value = null
      return
    }

    // 轴承特征频率只读新 evaluation / SC/SCoh 专属字段，避免误用齿轮旧契约
    const bearingResult = engineResult.bearing
      || engineResult.bearing_results?.envelope
      || Object.values(engineResult.bearing_results || {})[0]
    annotations.push(...bearingFrequencyAnnotations(bearingResult))

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

  /** 实时包络计算只替换轴承标注，保留缓存中的齿轮与转频标注。 */
  const updateBearingFreqAnnotations = (bearingResult) => {
    const retained = (faultFreqAnnotations.value || []).filter(
      ann => ann.type !== 'bearing' && ann.type !== 'bearing_sc_scoh'
    )
    const annotations = [...retained, ...bearingFrequencyAnnotations(bearingResult)]
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
      const isBearing = ann.type === 'bearing' || ann.type === 'bearing_sc_scoh'
      const labelPrefix = isBearing ? '🧩' : ann.type === 'gear' ? '⚙' : ann.type === 'gear_mesh' ? '🔧' : '🔄'

      markLineData.push({
        xAxis: idx,
        name: `${labelPrefix} ${ann.name}(${ann.freq.toFixed(1)}Hz)`,
        lineStyle: {
          type: isDetected ? 'solid' : 'dashed',
          color: isDetected ? '#F5222D' : isBearing ? '#165DFF' : ann.type === 'gear' ? '#FAAD14' : '#999',
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
    diagnosisDetailData.value = null
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

  watch(enableDetrend, () => {
    if (!selectedDevice.value || !selectedBatch.value) return
    timeOption.value = null
    nextTick(() => loadTimeDomain())
    if (computedFFT.value) computeFFT()
    if (computedSTFT.value) computeSTFT()
    if (computedEnvelope.value) computeEnvelope()
    if (computedOrder.value) computeOrder()
    if (computedCepstrum.value) computeCepstrum()
    if (computedStats.value) { windowedOption.value = null; computeStats() }
    if (computedGear.value) computeGear()
    if (computedFullAnalysis.value) computeFullAnalysis()
  })

  watch(maxFreq, () => {
    if (computedFFT.value) computeFFT()
    if (computedSTFT.value) computeSTFT()
    if (computedEnvelope.value) computeEnvelope()
    if (computedOrder.value) computeOrder()
  })

  watch(denoiseMethod, () => {
    if (!selectedDevice.value || !selectedBatch.value) return
    showDiagnosisDetail.value = false
    diagnosisDetailData.value = null
    timeOption.value = null
    nextTick(() => loadTimeDomain())
    if (computedFFT.value) computeFFT()
    if (computedSTFT.value) computeSTFT()
    if (computedEnvelope.value) computeEnvelope()
    if (computedOrder.value) computeOrder()
    if (computedCepstrum.value) computeCepstrum()
    if (computedStats.value) computeStats()
    if (computedGear.value) computeGear()
  })

  // ========== 时域波形（始终自动加载） ==========
  const loadTimeDomain = async () => {
    try {
      const res = await getChannelData(
        selectedDevice.value.device_id,
        selectedBatch.value.batch_index,
        selectedChannel.value,
        enableDetrend.value,
        denoiseMethod.value
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
        enableDetrend.value,
        denoiseMethod.value
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
      ElMessage.error(formatErrorMessage(e, 'FFT 计算失败'))
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
        enableDetrend.value,
        denoiseMethod.value
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
      ElMessage.error(formatErrorMessage(e, 'STFT 计算失败'))
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
        denoiseMethod.value
      )
      const d = res.data
      if (!d) return

      envelopeData.value = d
      computedEnvelope.value = true
      updateBearingFreqAnnotations(d)

      const spectrum = d.spectrum
      if (spectrum?.frequency_hz?.length && spectrum?.amplitude?.length) {
        envelopeOption.value = {
          tooltip: { trigger: 'axis', triggerOn: 'click' },
          grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
          xAxis: { type: 'category', data: spectrum.frequency_hz, name: '频率 (Hz)', nameGap: 25 },
          yAxis: {
            type: 'value',
            name: `包络幅值 (${spectrum.amplitude_unit || 'input_signal'}；${spectrum.scaling || 'unnormalized'})`,
          },
          dataZoom: [{ type: 'inside' }],
          series: [{
            type: 'line',
            data: spectrum.amplitude,
            showSymbol: false,
            areaStyle: { color: 'rgba(250, 173, 20, 0.2)' },
            lineStyle: { width: 1.5, color: '#FAAD14' }
          }]
        }
        // 叠加特征频率标注（包络谱是轴承诊断核心视图，标注尤为重要）
        addFreqAnnotationsToOption(envelopeOption.value, spectrum.frequency_hz)
      } else {
        // SC/SCoh 只返回专属循环频率指标，没有包络谱数组。
        envelopeOption.value = null
      }
    } catch (e) {
      console.error('包络谱计算失败:', e)
      ElMessage.error('包络谱计算失败: ' + formatErrorMessage(e))
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
        enableDetrend.value,
        denoiseMethod.value
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
              rot_freq: d.rot_freq,
            }
          )
          // 同步更新本地数据，避免刷新前显示不一致
          selectedBatch.value.rot_freq = d.rot_freq
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
      ElMessage.error('阶次谱计算失败: ' + formatErrorMessage(e))
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
        enableDetrend.value,
        denoiseMethod.value
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
      ElMessage.error('倒谱计算失败: ' + formatErrorMessage(e))
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
      ElMessage.error('齿轮诊断失败: ' + formatErrorMessage(e))
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
          { denoise_method: fullAnalysisDenoise.value }
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
      ElMessage.error('全算法诊断失败: ' + formatErrorMessage(e))
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
          denoise: analyzeDenoise.value,
        }
      )
      const d = res.data
      if (!d) return
      strategyAnalyzeData.value = d
      computedStrategyAnalyze.value = true
      // 策略结果中的轴承同样使用 evaluation.indicators
      extractFaultFreqAnnotations(d)
    } catch (e) {
      console.error('策略诊断失败:', e)
      ElMessage.error('策略诊断失败: ' + formatErrorMessage(e))
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
        enableDetrend.value,
        denoiseMethod.value
      )
      statsData.value = res.data
      computedStats.value = true
      await nextTick()
      initWindowedChart()
    } catch (e) {
      console.error('统计指标计算失败:', e)
      ElMessage.error(formatErrorMessage(e, '统计指标计算失败'))
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
      enableDetrend.value,
      denoiseMethod.value
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
      const view = getDiagnosisView(d)
      ElMessage.success(`重新诊断完成：${view.label}${view.scoreText === '-' ? '' : `，健康度 ${view.scoreText} 分`}`)
      Object.assign(selectedBatch.value, d)
      diagnosisDetailData.value = d.channels?.[`ch${selectedChannel.value}`] || null
      // 刷新设备列表以同步最新状态
      await loadAllDevices()
    } catch (e) {
      console.error('重新诊断失败:', e)
      ElMessage.error('重新诊断失败: ' + formatErrorMessage(e))
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
      ElMessage.error('全部重新诊断失败: ' + formatErrorMessage(e))
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

  return {
    loading, deleteLoading, reanalyzing, reanalyzingAll, deviceTableData,
    selectedDevice, selectedBatch, selectedChannel, maxFreq, channelOptions, enableDetrend,
    envelopeMethod, envelopeMethodLabel, gearMethod, gearMethodLabel, denoiseMethod,
    timeOption, fftOption, stftOption, envelopeOption, windowedOption, orderOption, cepstrumOption,
    computedFFT, computedSTFT, computedEnvelope, computedStats, computedOrder, computedCepstrum, computedGear,
    loadingFFT, loadingSTFT, loadingEnvelope, loadingStats, loadingOrder, loadingCepstrum, loadingGear,
    statsData, orderData, cepstrumData, gearData, envelopeData,
    computedFullAnalysis, loadingFullAnalysis, fullAnalysisData, fullAnalysisDenoise,
    computedStrategyAnalyze, loadingStrategyAnalyze, strategyAnalyzeData, analyzeDenoise,
    showDiagnosisDetail, loadingDiagnosisDetail, diagnosisDetailData, faultFreqAnnotations,
    statsWindowSize, statsStep, stftNperseg, stftNoverlap,
    orderFreqMin, orderFreqMax, orderSamplesPerRev, cepstrumMaxQuefrency,
    bearingSummaryTable, gearSummaryTable, diagnosisDesc,
    onBatchDeleted, loadAllDevices, loadDiagnosisDetail, loadCachedDiagnosis, selectBatch,
    computeFFT, clearFFT, computeSTFT, clearSTFT, computeEnvelope, clearEnvelope,
    computeOrder, clearOrder, computeCepstrum, clearCepstrum, computeGear, clearGear,
    computeFullAnalysis, clearFullAnalysis, computeStrategyAnalyze, clearStrategyAnalyze,
    computeStats, clearStats, onExportCSV, onReanalyze, onReanalyzeAll,
    onDeleteBatch, onDeleteAllSpecial, gotoResearchDiagnosis,
  }
}
