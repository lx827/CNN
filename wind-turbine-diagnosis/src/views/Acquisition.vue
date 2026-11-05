<template>
  <div class="acquisition-page">
    <div class="page-heading">
      <div><h1>真实采集</h1><p>设置参数，让现场边端采集 DC24 四通道完整数据。</p></div>
      <el-button @click="refresh">刷新边端与记录</el-button>
    </div>

    <div class="capture-grid">
      <el-card shadow="never" class="parameter-panel">
        <template #header><strong>采集参数</strong></template>
        <el-form ref="formRef" :model="form" label-position="top" :disabled="busy">
          <el-form-item label="采集边端" prop="agent_id" :rules="[{ required: true, message: '请选择在线边端', trigger: 'change' }]">
            <el-select v-model="form.agent_id" placeholder="选择已启动的边端" class="full-width">
              <el-option v-for="a in agents" :key="a.id" :value="a.id" :disabled="!a.online"
                :label="`${a.id} · ${sourceLabel(a.source)}${a.online ? '' : '（离线）'}`" />
            </el-select>
          </el-form-item>
          <el-alert v-if="!agents.some(a => a.online)" type="info" :closable="false" title="尚无在线边端"
            description="请在连接采集器的电脑启动 DC24 边端。登录云端不代表采集器已连接。" show-icon />
          <div class="field-row">
            <el-form-item label="采样率">
              <el-select v-model="form.sample_rate" aria-label="采样率">
                <el-option v-for="rate in availableRates" :key="rate" :value="rate" :label="`${rate.toLocaleString()} Hz`" />
              </el-select>
            </el-form-item>
            <el-form-item label="最少采集时长">
              <el-input-number v-model="form.duration" :min="1" :max="60" :precision="0" controls-position="right" aria-label="采集时长（秒）" />
              <span class="field-help">秒，按完整帧收尾</span>
            </el-form-item>
          </div>
          <p class="field-help">固定采集四通道，原始数据不抽点。预计至少 {{ expectedPoints.toLocaleString() }} 点/通道。</p>
          <el-divider content-position="left">可选分析</el-divider>
          <el-checkbox v-model="form.fft">原始信号频谱</el-checkbox>
          <el-checkbox v-model="form.rms">RMS（去均值）</el-checkbox>
          <el-checkbox v-model="form.envelope">包络谱</el-checkbox>
          <p class="field-help">可全部取消，只保存原始数据。频谱使用去均值和 Hann 窗，原始 CSV 不变。</p>
          <div v-if="form.envelope" class="band-panel">
            <p>包络分析频带</p>
            <div class="field-row">
              <el-form-item label="下限（Hz）" prop="band_low" :rules="bandRules">
                <el-input-number v-model="form.band_low" :min="0" :max="form.sample_rate / 2" :controls="false" placeholder="输入下限" aria-label="包络频带下限" />
              </el-form-item>
              <el-form-item label="上限（Hz）" prop="band_high" :rules="bandRules">
                <el-input-number v-model="form.band_high" :min="0" :max="form.sample_rate / 2" :controls="false" placeholder="输入上限" aria-label="包络频带上限" />
              </el-form-item>
            </div>
            <p class="field-help">必须满足 0 &lt; 下限 &lt; 上限 &lt; {{ form.sample_rate / 2 }} Hz。不会自动猜测频带。</p>
          </div>
        </el-form>
        <div class="capture-actions">
          <el-button type="primary" :loading="submitting" :disabled="busy || !selectedAgent?.online" @click="startCapture">开始采集</el-button>
          <el-button type="danger" plain :disabled="!busy || job?.cancel_requested" :loading="stopping" @click="stopCapture">{{ job?.cancel_requested ? '等待边端停止' : '停止采集' }}</el-button>
        </div>
        <p class="field-help">真实采集前，请让原厂软件释放电脑 TCP 6800 端口。</p>
      </el-card>

      <el-card shadow="never" class="status-panel" aria-live="polite">
        <template #header><strong>本次任务</strong></template>
        <div v-if="job" class="job-state">
          <div class="state-line"><el-tag :type="statusType(job.status)">{{ statusLabel(job.status) }}</el-tag><el-tag effect="plain">{{ sourceLabel(job.source) }}</el-tag></div>
          <h2>{{ statusMessage }}</h2>
          <el-progress :percentage="percentage" :status="job.status === 'failed' ? 'exception' : job.status === 'completed' ? 'success' : undefined" />
          <div class="job-facts">
            <div><span>实际采样率</span><strong>{{ job.metadata?.sample_rate_hz || job.sample_rate }} Hz</strong></div>
            <div><span>每通道已保存 / 已收到</span><strong>{{ actualPoints.toLocaleString() }} 点</strong></div>
            <div><span>样本时长</span><strong>{{ (actualPoints / job.sample_rate).toFixed(4) }} s</strong></div>
            <div><span>目标时长</span><strong>{{ job.duration }} s</strong></div>
          </div>
          <el-alert v-if="job.error" type="error" :closable="false" :title="job.error" show-icon />
          <el-alert v-if="job.source === 'recording_replay'" type="warning" :closable="false" title="本次来自历史文件回放，不是真实设备实时采样。" />
          <div v-if="job.metadata" class="downloads">
            <el-button @click="download('samples.csv')">下载原始 CSV</el-button>
            <el-button @click="download('metadata.json')">采集记录</el-button>
            <el-button v-if="analysis && Object.values(job.analysis_options).some(v => v === true)" @click="download('analysis_arrays.npz')">完整分析数组</el-button>
          </div>
        </div>
        <el-empty v-else description="尚未选择采集任务" :image-size="90" />
        <div class="source-note">
          <strong>四通道原始 ADC 计数</strong>
          <p>本页不把计数直接标为加速度，也不自动给出设备健康结论。原始文件先保存在边端，再完整上传。</p>
          <p v-if="selectedAgent">边端：{{ selectedAgent.online ? '在线' : '离线' }}；采集器：{{ selectedAgent.state?.hardware_connected ? 'TCP 已连接' : '任务开始后建立连接' }}</p>
        </div>
      </el-card>
    </div>

    <el-card v-if="analysis" shadow="never" class="results-panel">
      <template #header><div class="result-heading"><strong>采集结果与所选分析</strong><el-select v-model="selectedChannel" aria-label="显示通道"><el-option v-for="c in analysis.channels" :key="c.channel" :label="c.label" :value="c.channel" /></el-select></div></template>
      <p class="field-help">统计基于完整记录。长图按极值精简显示；使用下方区间查看原始分辨率波形。完整分析数组可下载。</p>
      <el-table :data="analysis.channels" size="small">
        <el-table-column prop="label" label="通道" min-width="150" />
        <el-table-column prop="samples" label="样本点数" />
        <el-table-column prop="minimum" label="最小计数" />
        <el-table-column prop="maximum" label="最大计数" />
        <el-table-column v-if="job.analysis_options.rms" label="去均值 RMS"><template #default="{row}">{{ row.rms?.toFixed(3) }}</template></el-table-column>
        <el-table-column prop="rail_samples" label="满量程样本" />
      </el-table>
      <div class="wave-controls">
        <span>原始波形区间</span>
        <label>起点（s） <el-input-number v-model="waveStart" :min="0" :max="Math.max(0, analysis.duration - .001)" :precision="3" :controls="false" /></label>
        <label>时长（s） <el-input-number v-model="waveSeconds" :min=".01" :max="5" :precision="2" :controls="false" /></label>
        <el-button :loading="waveLoading" @click="loadWaveform">查看原始区间</el-button>
      </div>
      <div ref="waveChart" class="chart" aria-label="原始波形图" />
      <div v-if="job.analysis_options.fft" ref="fftChart" class="chart" aria-label="原始信号频谱图" />
      <div v-if="job.analysis_options.rms" ref="rmsChart" class="chart" aria-label="RMS变化曲线" />
      <div v-if="job.analysis_options.envelope" ref="envelopeChart" class="chart" aria-label="所选频带包络谱图" />
    </el-card>

    <el-card shadow="never" class="history-panel">
      <template #header><strong>最近采集</strong></template>
      <el-table :data="jobs" size="small" empty-text="尚无记录">
        <el-table-column label="创建时间" min-width="180"><template #default="{row}">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column prop="agent_id" label="边端" min-width="140" />
        <el-table-column label="来源"><template #default="{row}">{{ sourceLabel(row.source) }}</template></el-table-column>
        <el-table-column label="采样率"><template #default="{row}">{{ row.sample_rate }} Hz</template></el-table-column>
        <el-table-column label="目标时长"><template #default="{row}">{{ row.duration }} s</template></el-table-column>
        <el-table-column label="状态"><template #default="{row}">{{ statusLabel(row.status) }}</template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{row}"><el-button link type="primary" @click="selectJob(row)">查看</el-button></template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { getAcquisitionAgents, getAcquisitionJobs, createAcquisition, getAcquisition, stopAcquisition, getAcquisitionAnalysis, getAcquisitionWaveform, downloadAcquisitionFile } from '../api/acquisition'

const agents = ref([]), jobs = ref([]), job = ref(null), analysis = ref(null)
const formRef = ref(), submitting = ref(false), stopping = ref(false), waveLoading = ref(false)
const selectedChannel = ref(0), waveStart = ref(0), waveSeconds = ref(.2), waveform = ref(null)
const form = ref({ agent_id: '', sample_rate: 5000, duration: 60, fft: true, rms: true, envelope: false, band_low: undefined, band_high: undefined })
const waveChart = ref(), fftChart = ref(), rmsChart = ref(), envelopeChart = ref()
const activeStates = ['pending', 'waiting_device', 'configuring', 'capturing', 'uploading', 'analyzing']
const busy = computed(() => job.value && activeStates.includes(job.value.status))
const selectedAgent = computed(() => agents.value.find(a => a.id === form.value.agent_id))
const availableRates = computed(() => selectedAgent.value?.state?.sample_rates || [2000, 5000])
const expectedPoints = computed(() => form.value.sample_rate * form.value.duration)
const actualPoints = computed(() => job.value?.metadata?.samples_per_channel ?? job.value?.progress?.samples_per_channel ?? 0)
const percentage = computed(() => job.value?.status === 'completed' ? 100 : Math.min(99, Math.round(actualPoints.value / ((job.value?.sample_rate || 1) * (job.value?.duration || 1)) * 100)))
const labels = { pending: '等待边端', waiting_device: '等待采集器', configuring: '配置设备', capturing: '正在采集', uploading: '上传完整记录', analyzing: '计算所选分析', completed: '已完成', failed: '失败', cancelled: '已停止' }
const statusLabel = s => labels[s] || s
const statusType = s => s === 'failed' ? 'danger' : s === 'completed' ? 'success' : s === 'cancelled' ? 'info' : 'primary'
const sourceLabel = s => s === 'dc24_tcp' ? 'DC24 实时采集' : '历史文件回放'
const statusMessage = computed(() => job.value?.cancel_requested && busy.value ? '已请求停止，等待设备应答并保存已采数据' : statusLabel(job.value?.status))
const bandRules = [{ validator: (_rule, _value, callback) => {
  const f = form.value
  callback(!f.envelope || (Number.isFinite(f.band_low) && Number.isFinite(f.band_high) && f.band_low > 0 && f.band_low < f.band_high && f.band_high < f.sample_rate / 2) ? undefined : new Error('频带必须满足 0 < 下限 < 上限 < 采样率/2'))
}, trigger: 'change' }]
let timer, disposed = false, loadingAnalysisId = '', selectionVersion = 0, waveRequestVersion = 0
const charts = new Map()

async function refresh() {
  const [a, j] = await Promise.all([getAcquisitionAgents(), getAcquisitionJobs()])
  if (disposed) return
  agents.value = a.data || []; jobs.value = j.data || []
  if (!form.value.agent_id) form.value.agent_id = agents.value.find(x => x.online)?.id || ''
  if (!job.value && jobs.value.length) await selectJob(jobs.value[0])
}
async function startCapture() {
  if (submitting.value || busy.value) return
  if (!await formRef.value.validate().catch(() => false)) return
  submitting.value = true
  try {
    const f = form.value
    const r = await createAcquisition({ agent_id: f.agent_id, sample_rate: f.sample_rate, duration: f.duration,
      analysis: { fft: f.fft, rms: f.rms, envelope: f.envelope, band_low: f.envelope ? f.band_low : null, band_high: f.envelope ? f.band_high : null } })
    if (disposed) return
    await selectJob(r.data)
    ElMessage.success('任务已创建，等待现场边端执行')
    await refresh()
  } finally { submitting.value = false }
}
async function stopCapture() {
  if (!busy.value || stopping.value) return
  stopping.value = true
  try { const r = await stopAcquisition(job.value.id); if (!disposed) job.value = r.data }
  finally { stopping.value = false }
}
async function selectJob(item) {
  selectionVersion++; loadingAnalysisId = ''
  job.value = item; analysis.value = null; waveform.value = null; waveStart.value = 0
  disposeCharts()
  if (item.status === 'completed') await loadAnalysis(item.id)
}
async function loadAnalysis(id) {
  if (loadingAnalysisId === id || analysis.value || disposed) return
  loadingAnalysisId = id
  const version = selectionVersion
  try {
    const r = await getAcquisitionAnalysis(id)
    if (disposed || version !== selectionVersion || job.value?.id !== id) return
    analysis.value = r.data; selectedChannel.value = 0
    await loadWaveform()
    await draw()
  } finally { if (loadingAnalysisId === id) loadingAnalysisId = '' }
}
async function loadWaveform() {
  if (!job.value?.metadata || !analysis.value) return
  const version = selectionVersion, id = job.value.id, channel = selectedChannel.value, requestVersion = ++waveRequestVersion
  waveLoading.value = true
  try {
    const r = await getAcquisitionWaveform(id, { channel, start: waveStart.value, seconds: waveSeconds.value })
    if (disposed || version !== selectionVersion || requestVersion !== waveRequestVersion || job.value?.id !== id || channel !== selectedChannel.value) return
    waveform.value = r.data
    await draw()
  } finally { if (requestVersion === waveRequestVersion) waveLoading.value = false }
}
async function download(name) { if (job.value) await downloadAcquisitionFile(job.value.id, name) }
function plot(element, title, points, xName, yName) {
  if (!element) return
  let chart = charts.get(element)
  if (!chart) { chart = echarts.init(element); charts.set(element, chart) }
  chart.setOption({ animation: false, title: { text: title, textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' }, grid: { left: 85, right: 30, top: 45, bottom: 65 },
    xAxis: { type: 'value', name: xName }, yAxis: { type: 'value', name: yName, scale: true },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 10 }],
    series: [{ type: 'line', showSymbol: false, lineStyle: { width: 1.2 }, data: points }] }, true)
}
async function draw() {
  await nextTick()
  if (disposed || !analysis.value) return
  const c = analysis.value.channels[selectedChannel.value]
  plot(waveChart.value, '原始波形 · ADC counts', waveform.value || c.waveform, 's', 'counts')
  if (c.fft) plot(fftChart.value, '原始信号频谱 · 去均值、Hann 窗', c.fft, 'Hz', 'counts')
  if (c.rms_curve) plot(rmsChart.value, '去均值 RMS · 按 1 秒分段', c.rms_curve, 's', 'counts')
  if (c.envelope) plot(envelopeChart.value, `包络谱 · 频带 ${job.value.analysis_options.band_low}～${job.value.analysis_options.band_high} Hz`, c.envelope, 'Hz', 'counts')
}
function disposeCharts() { charts.forEach(chart => chart.dispose()); charts.clear() }
function resize() { charts.forEach(chart => chart.resize()) }
async function poll() {
  try {
    const [a, h] = await Promise.all([getAcquisitionAgents(), getAcquisitionJobs()])
    if (disposed) return
    agents.value = a.data || []; jobs.value = h.data || []
    if (job.value) {
      const id = job.value.id, version = selectionVersion
      const r = await getAcquisition(id)
      if (disposed || version !== selectionVersion || job.value?.id !== id) return
      job.value = r.data
      if (r.data.status === 'completed') await loadAnalysis(id)
    }
  } catch { /* 网络错误由统一请求层显示；保留当前任务和已加载结果。 */ }
  finally { if (!disposed) timer = setTimeout(poll, 1500) }
}
watch(selectedChannel, () => { waveform.value = null; loadWaveform() })
watch(availableRates, rates => { if (!rates.includes(form.value.sample_rate)) form.value.sample_rate = rates[0] })
onMounted(async () => { window.addEventListener('resize', resize); try { await refresh() } finally { if (!disposed) poll() } })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); window.removeEventListener('resize', resize); disposeCharts() })
</script>

<style scoped>
.acquisition-page { max-width: 1500px; margin: 0 auto; }
.page-heading, .result-heading, .state-line, .capture-actions, .downloads { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.page-heading, .result-heading { justify-content: space-between; }
.page-heading { margin-bottom: 20px; }
h1 { margin: 0 0 8px; font-size: 24px; font-weight: 600; }
.page-heading p, .field-help { color: #586576; font-size: 13px; line-height: 1.7; }
.page-heading p { margin: 0; }
.capture-grid { display: grid; grid-template-columns: minmax(320px, 1fr) minmax(340px, 1.35fr); gap: 20px; }
.full-width { width: 100%; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.field-row :deep(.el-input-number), .field-row :deep(.el-select) { width: 100%; }
.parameter-panel :deep(.el-checkbox) { min-height: 36px; }
.band-panel { margin-top: 12px; padding: 12px; background: #f5f8fc; border-left: 3px solid var(--color-primary); }
.capture-actions { margin-top: 20px; }
.capture-actions :deep(.el-button) { min-height: 42px; }
.job-state h2 { margin: 20px 0 24px; font-size: 20px; font-weight: 500; }
.job-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 28px 0; }
.job-facts span { display: block; color: #586576; font-size: 13px; margin-bottom: 8px; }
.job-facts strong { font-size: 22px; font-weight: 500; }
.source-note { border-top: 1px solid #e5e9ef; padding-top: 18px; margin-top: 26px; color: #586576; font-size: 13px; line-height: 1.8; }
.source-note p { margin: 6px 0; }
.results-panel, .history-panel { margin-top: 20px; }
.result-heading :deep(.el-select) { width: 220px; }
.wave-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; margin-top: 24px; font-size: 14px; }
.wave-controls label { display: flex; align-items: center; gap: 8px; }
.wave-controls :deep(.el-input-number) { width: 100px; }
.chart { height: 290px; margin-top: 24px; }
@media (max-width: 850px) { .capture-grid { grid-template-columns: 1fr; } .job-facts strong { font-size: 19px; } }
@media (max-width: 420px) { .field-row, .job-facts { grid-template-columns: 1fr; } .page-heading h1 { font-size: 21px; } }
</style>
