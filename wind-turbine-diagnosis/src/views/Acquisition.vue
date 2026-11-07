<template>
  <div class="acquisition-page">
    <header><div><h1>DC24 实时示波与采集</h1><p>先看现场信号，随时开始保存。四通道直接来自采集器。</p></div><el-tag :type="view?.fresh ? 'success' : 'info'">{{ stateLabel }}</el-tag></header>
    <div class="console-layout">
      <aside class="control-panel">
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="现场边端"><el-select v-model="form.agent_id" :disabled="sessionActive || selectingDirectory" placeholder="等待现场边端上线" aria-label="现场边端"><el-option v-for="a in realAgents" :key="a.id" :value="a.id" :disabled="!a.online" :label="`${a.id}${a.online ? '' : '（离线）'}`" /></el-select></el-form-item>
          <el-form-item label="采样率（每通道）"><el-select v-model="form.sample_rate" :disabled="sessionActive" filterable aria-label="采样率"><el-option v-for="rate in rates" :key="rate" :value="rate" :label="`${rate.toLocaleString()} Hz`" /></el-select><p class="help">原厂支持的全部档位。更改采样率前先停止示波。</p></el-form-item>
          <div class="actions"><el-button type="primary" :disabled="sessionActive || !selectedAgent?.online" :loading="starting" @click="startPreview">示波</el-button><el-button :disabled="!sessionActive" :loading="stopping" @click="stopPreview">停止示波</el-button></div>
          <p class="help">示波只更新画面，不保存采样文件。</p>
          <p v-if="selectedAgent?.state?.input_configuration" class="help">输入：{{ selectedAgent.state.input_configuration.measurement }} · {{ selectedAgent.state.input_configuration.coupling }} · {{ selectedAgent.state.input_configuration.upper_frequency }}。频谱：汉宁窗。</p>
          <el-divider /><strong>显示内容 · 可随时切换</strong>
          <div class="display-options"><el-checkbox v-model="show.waveform">原始信号</el-checkbox><el-checkbox v-model="show.fft">原始信号频谱</el-checkbox><el-checkbox v-model="show.rms">RMS / 均值</el-checkbox><el-checkbox v-model="show.envelope">包络谱</el-checkbox></div>
          <el-form-item label="波形时间窗（秒）"><el-input-number v-model="form.wave_seconds" :min=".01" :max="2" :step=".05" :precision="2" controls-position="right" aria-label="波形时间窗" /></el-form-item>
          <div v-if="show.envelope" class="band-fields"><el-form-item label="包络带通下限（Hz）"><el-input-number v-model="form.band_low" :controls="false" aria-label="包络带通下限" /></el-form-item><el-form-item label="包络带通上限（Hz）"><el-input-number v-model="form.band_high" :controls="false" aria-label="包络带通上限" /></el-form-item><p v-if="bandError" class="error-text" role="alert">{{ bandError }}</p></div>
          <el-divider /><strong>保存原始数据</strong><br><el-checkbox v-model="form.manual" :disabled="recordBusy">手动结束采集</el-checkbox>
          <el-form-item v-if="!form.manual" label="采集时长（秒）"><el-input-number v-model="form.duration" :min="1" :precision="0" :disabled="recordBusy" controls-position="right" aria-label="采集时长" /><p class="help">可自行填写，按完整数据帧收尾。</p></el-form-item>
          <el-form-item label="现场电脑保存目录"><el-input v-model="form.save_directory" :disabled="recordBusy" placeholder="例如 D:\采集数据" aria-label="保存目录" @input="directoryEdited = true" /><el-button class="directory-button" :disabled="!selectedAgent?.online || recordBusy" :loading="selectingDirectory" @click="chooseDirectory">选择目录…</el-button></el-form-item>
          <div class="actions"><el-button type="success" :disabled="recordBusy || !selectedAgent?.online || !!bandError" :loading="saving" @click="startRecording">开始采集</el-button><el-button type="danger" plain :disabled="!recordBusy || recording?.stop_requested" @click="stopRecording">停止保存</el-button></div>
          <p class="help">开始后从下一完整帧保存四路原件，示波继续。后端另存完整副本。</p>
        </el-form>
      </aside>
      <main class="scope-panel" aria-live="polite">
        <div class="status-strip"><span><i :class="['status-dot', { live: view?.fresh }]" />{{ view?.fresh ? '设备实时数据' : sessionActive ? '等待新数据' : '尚未示波 / 已停止' }}</span><span>{{ session?.sample_rate || form.sample_rate }} Hz × 4通道</span><span v-if="session?.frame_sequence != null">设备帧序号 {{ session.frame_sequence }}</span></div>
        <el-alert v-if="session?.error" type="error" :closable="false" :title="session.error" show-icon />
        <el-alert v-if="connectionError" type="warning" :closable="false" :title="connectionError" show-icon />
        <el-alert v-if="!realAgents.some(a => a.online)" type="info" :closable="false" title="等待现场边端：请运行 start_dc24.bat 一键启动" show-icon />
        <div v-if="recording" class="record-strip"><strong>{{ recordLabel }}</strong><span>每通道 {{ (recording.samples_per_channel || 0).toLocaleString() }} 点</span><span>{{ ((recording.samples_per_channel || 0) / (session?.sample_rate || form.sample_rate)).toFixed(3) }} 秒</span><p v-if="recording.saved_directory">现场原件：{{ recording.saved_directory }}</p><p v-if="recording.error" class="error-text">{{ recording.error }}</p><el-button v-if="recording.status === 'completed'" size="small" @click="download(recording.id, 'samples.csv')">下载完整 CSV</el-button></div>
        <div class="source-line"><span>来源：DC24 192.168.2.101 → TCP 192.168.2.100:6800</span><span v-if="session?.received_at">最后收到：{{ new Date(session.received_at).toLocaleTimeString() }}</span></div>
        <template v-if="view?.channels?.length">
          <p class="help">实时分析窗口：{{ view.window_start.toFixed(3) }}～{{ view.window_end.toFixed(3) }} 秒。波形仅展开最近 {{ form.wave_seconds }} 秒，频谱使用上述连续窗口；长图保留极值显示，保存文件不抽点。</p>
          <el-table v-if="show.rms" :data="view.channels" size="small"><el-table-column prop="label" label="通道" min-width="150" /><el-table-column label="均值（counts）"><template #default="{row}">{{ row.mean.toFixed(5) }}</template></el-table-column><el-table-column label="去均值 RMS（counts）"><template #default="{row}">{{ row.rms?.toFixed(5) }}</template></el-table-column></el-table>
          <section v-for="kind in visibleKinds" :key="kind.key"><h2>{{ kind.label }}</h2><div class="channel-grid"><div v-for="channel in view.channels" :key="channel.channel" class="channel-scope"><div :ref="el => bindChart(kind.key, channel.channel, el)" class="chart" :aria-label="`${channel.label}${kind.label}`" /></div></div></section>
          <el-empty v-if="!visibleKinds.length" description="显示项已全部关闭，采样和原始保存仍照常进行" :image-size="65" />
        </template>
        <el-empty v-else :description="sessionActive ? '等待设备连接和首个完整采样帧' : '点击示波查看现场四通道，或直接开始采集'" :image-size="110" />
        <p class="help">纵轴为 ADC 原始计数（counts），尚未换算为 m/s²。各路单独绘制；可调整波形时间窗查看整体或局部。</p>
      </main>
    </div>
    <el-card shadow="never" class="history-panel"><template #header><strong>已保存记录</strong></template><el-table :data="jobs" empty-text="还没有保存记录" size="small"><el-table-column label="时间" min-width="180"><template #default="{row}">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column><el-table-column label="来源"><template #default="{row}">{{ row.source === 'dc24_tcp' ? 'DC24 设备' : '历史回放' }}</template></el-table-column><el-table-column label="采样率"><template #default="{row}">{{ row.sample_rate }} Hz</template></el-table-column><el-table-column label="每路点数"><template #default="{row}">{{ row.metadata?.samples_per_channel?.toLocaleString() || '—' }}</template></el-table-column><el-table-column label="现场保存位置" min-width="260"><template #default="{row}">{{ row.metadata?.saved_directory || '见采集记录' }}</template></el-table-column><el-table-column label="文件" min-width="160"><template #default="{row}"><el-button v-if="row.metadata" link type="primary" @click="download(row.id, 'samples.csv')">原始 CSV</el-button><el-button v-if="row.metadata" link @click="download(row.id, 'metadata.json')">采集记录</el-button></template></el-table-column></el-table></el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { getAcquisitionAgents, getAcquisitionJobs, downloadAcquisitionFile, getAcquisitionCapabilities, startLiveSession, getLiveSession, getCurrentLiveSession, stopLiveSession, getLiveView, startLiveRecording, stopLiveRecording, selectAcquisitionDirectory, getAcquisitionDirectory } from '../api/acquisition'
import { createWebSocketClient } from '../utils/websocket'
const agents = ref([]), jobs = ref([]), session = ref(null), view = ref(null), nativeRates = ref([])
const connectionError = ref('')
const starting = ref(false), stopping = ref(false), saving = ref(false), selectingDirectory = ref(false), directoryEdited = ref(false)
const form = reactive({ agent_id: '', sample_rate: 10000, duration: 60, manual: false, save_directory: '', wave_seconds: .2, band_low: undefined, band_high: undefined })
const show = reactive({ waveform: true, fft: true, rms: false, envelope: false })
const realAgents = computed(() => agents.value.filter(a => a.source === 'dc24_tcp' && a.state?.version >= 3))
const selectedAgent = computed(() => realAgents.value.find(a => a.id === form.agent_id))
const rates = computed(() => selectedAgent.value?.state?.sample_rates || nativeRates.value)
const sessionActive = computed(() => session.value && !['stopped', 'failed'].includes(session.value.status))
const recording = computed(() => session.value?.recording)
const recordBusy = computed(() => recording.value && ['pending', 'waiting_device', 'capturing', 'uploading', 'analyzing'].includes(recording.value.status))
const stateLabel = computed(() => session.value?.stop_requested && sessionActive.value ? '正在停止与保存' : ({ waiting_device: '等待采集器', configuring: '配置设备', streaming: '实时示波中', stopping: '正在停止与保存', stopped: '示波已停止', failed: '连接失败' }[session.value?.status] || '未连接'))
const recordLabel = computed(() => ({ waiting_device: '等待开始保存', capturing: '正在保存', uploading: '原件已保存，正在传后端副本', completed: '采集已保存，示波可继续', failed: '保存失败' }[recording.value?.status] || recording.value?.status))
const bandError = computed(() => show.envelope && !(Number.isFinite(form.band_low) && Number.isFinite(form.band_high) && 0 < form.band_low && form.band_low < form.band_high && form.band_high < form.sample_rate/2) ? `请填写 0 < 下限 < 上限 < ${form.sample_rate/2} Hz 的包络频带` : '')
const kinds = [{ key: 'waveform', label: '原始信号', axis: 's' }, { key: 'fft', label: '原始信号频谱', axis: 'Hz' }, { key: 'rms', label: '去均值 RMS', axis: 's' }, { key: 'envelope', label: '包络谱', axis: 'Hz' }]
const visibleKinds = computed(() => kinds.filter(k => show[k.key]))
const containers = new Map(), charts = new Map()
let disposed = false, timer, turn = 0, lastRevision = -1, lastOptions = '', pickerId = '', pollCount = 0
function analysisOptions() { return { fft: show.fft, rms: show.rms, envelope: show.envelope, band_low: show.envelope ? form.band_low : null, band_high: show.envelope ? form.band_high : null } }

// —— 实时窗口订阅(issue #51):view 数据优先经 WS 推送;WS 未连上时回退 REST 轮询 ——
let viewSocket = null, viewSocketOpen = false, viewSocketId = ''
function viewOptions() {
  const options = { ...analysisOptions(), waveform: show.waveform, wave_seconds: form.wave_seconds }
  if (bandError.value) options.envelope = false
  return options
}
function closeViewSocket() {
  viewSocketId = ''
  if (viewSocket) {
    viewSocketOpen = false
    const sock = viewSocket
    viewSocket = null
    sock.close()
  }
}
function sendViewOptions() {
  if (viewSocket && viewSocketOpen) viewSocket.send({ type: 'options', ...viewOptions() })
}
function openViewSocket(id) {
  if (viewSocketId === id && viewSocket) return
  closeViewSocket()
  viewSocketId = id
  const sock = createWebSocketClient(`/ws/acquisition/sessions/${id}/view`)
  viewSocket = sock
  sock.on('open', () => { if (viewSocket !== sock) return; viewSocketOpen = true; sendViewOptions() })
  sock.on('view', data => {
    if (disposed || viewSocket !== sock || session.value?.id !== id) return
    view.value = data
    if (data?.session) { session.value = data.session; lastRevision = data.session.revision ?? lastRevision }
    lastOptions = JSON.stringify(viewOptions())
    draw()
  })
  sock.on('session', data => {
    if (disposed || viewSocket !== sock || session.value?.id !== id) return
    session.value = data
  })
  sock.on('close', () => { if (viewSocket === sock) viewSocketOpen = false })
  sock.connect()
}
watch(() => session.value && !['stopped', 'failed'].includes(session.value.status) ? session.value.id : null,
  id => { if (id) openViewSocket(id); else closeViewSocket() })
watch([show, () => form.wave_seconds, () => form.band_low, () => form.band_high], sendViewOptions, { deep: true })
async function refreshAgents() {
  const [a, j] = await Promise.all([getAcquisitionAgents(), getAcquisitionJobs()])
  if (disposed) return
  agents.value = a.data || []; jobs.value = j.data || []
  connectionError.value = ''
  if (!form.agent_id) form.agent_id = realAgents.value.find(a => a.online)?.id || ''
  if (!directoryEdited.value && selectedAgent.value?.state?.save_directory) form.save_directory = selectedAgent.value.state.save_directory
}
async function ensureSession() {
  if (sessionActive.value) return session.value
  const version = ++turn
  const result = await startLiveSession({ agent_id: form.agent_id, sample_rate: form.sample_rate })
  if (disposed || version !== turn) return null
  session.value = result.data; view.value = null; lastRevision = -1; disposeCharts()
  return session.value
}
async function startPreview() { if (starting.value) return; starting.value = true; try { await ensureSession() } catch {} finally { starting.value = false } }
async function stopPreview() { if (!session.value || stopping.value) return; stopping.value = true; try { const r = await stopLiveSession(session.value.id); if (!disposed) session.value = r.data } catch {} finally { stopping.value = false } }
async function startRecording() {
  if (saving.value || recordBusy.value) return
  if (!form.save_directory.trim()) { ElMessage.warning('请先选择或填写现场电脑保存目录'); return }
  if (bandError.value) { ElMessage.warning(bandError.value); return }
  saving.value = true
  try {
    const current = await ensureSession(); if (!current || disposed) return
    await startLiveRecording(current.id, { duration: form.manual ? 0 : form.duration, save_directory: form.save_directory, analysis: analysisOptions() })
    const status = await getLiveSession(current.id)
    if (!disposed && session.value?.id === current.id) session.value = status.data
    ElMessage.success('开始保存真实四通道，示波继续')
  } catch {} finally { saving.value = false }
}
async function stopRecording() { if (session.value) { try { await stopLiveRecording(session.value.id) } catch {} } }
async function chooseDirectory() { selectingDirectory.value = true; try { const r = await selectAcquisitionDirectory(form.agent_id); pickerId = r.data.id } catch { selectingDirectory.value = false } }
async function download(id, name) { try { await downloadAcquisitionFile(id, name) } catch {} }
function bindChart(kind, channel, element) { const key = `${kind}-${channel}`; if (!element) { charts.get(key)?.dispose(); charts.delete(key); containers.delete(key) } else containers.set(key, element) }
function disposeCharts() { charts.forEach(c => c.dispose()); charts.clear(); containers.clear() }
async function draw() {
  await nextTick(); if (disposed || !view.value?.channels?.length) return
  for (const kind of visibleKinds.value) for (const c of view.value.channels) {
    const key = `${kind.key}-${c.channel}`, element = containers.get(key); if (!element) continue
    let chart = charts.get(key); if (!chart) { chart = echarts.init(element); charts.set(key, chart) }
    const data = kind.key === 'rms' ? c.rms_curve : c[kind.key]
    chart.setOption({ animation: false, title: { text: `${c.label} (counts)`, left: 12, top: 8, textStyle: { fontSize: 12, fontWeight: 500 } }, grid: { left: 75, right: 28, top: 42, bottom: 46 }, tooltip: { trigger: 'axis' }, xAxis: { type: 'value', name: kind.axis, scale: kind.axis === 's', min: kind.axis === 's' ? 'dataMin' : 0, max: kind.axis === 's' ? 'dataMax' : undefined, axisLabel: { hideOverlap: true, formatter: kind.axis === 's' ? value => value.toFixed(3) : undefined } }, yAxis: { type: 'value', scale: true }, dataZoom: [{ type: 'inside' }], series: [{ type: 'line', showSymbol: false, smooth: false, lineStyle: { width: 1, color: ['#165DFF', '#008B7A', '#B86B11', '#7854B5'][c.channel] }, data: data || [] }] }, true)
  }
}
function resize() { charts.forEach(c => c.resize()) }
async function poll() {
  try {
    if (pollCount++ % 4 === 0) await refreshAgents(); if (disposed) return
    if (selectingDirectory.value && pickerId) {
      const r = await getAcquisitionDirectory(form.agent_id)
      if (!disposed && r.data?.id === pickerId && r.data.status === 'done') { selectingDirectory.value = false; if (r.data.directory) { form.save_directory = r.data.directory; directoryEdited.value = true } if (r.data.error) ElMessage.warning(r.data.error) }
    }
    const id = session.value?.id, version = turn
    if (id) {
      let r
      try { r = await getLiveSession(id) }
      catch (error) {
        if (error.response?.status !== 404) throw error
        const current = await getCurrentLiveSession(form.agent_id)
        if (disposed || version !== turn) return
        turn++; session.value = current.data; view.value = null; lastRevision = -1; disposeCharts()
        connectionError.value = current.data ? '' : '上次示波会话已结束，请重新点击示波'
        return
      }
      if (disposed || version !== turn || session.value?.id !== id) return
      connectionError.value = ''
      session.value = r.data
      if (viewSocketOpen) {
        // view 数据经 WS 推送到达;轮询只负责会话状态与新鲜度回退显示
        if (view.value) view.value.fresh = r.data.status === 'streaming' && Date.now()-new Date(r.data.received_at).getTime() < Math.max(3000, 508000/r.data.sample_rate)
      } else {
        const options = { ...analysisOptions(), waveform: show.waveform, wave_seconds: form.wave_seconds }
        if (bandError.value) options.envelope = false
        const key = JSON.stringify(options)
        if (r.data.revision !== lastRevision || key !== lastOptions) {
          const result = await getLiveView(id, options); if (disposed || version !== turn || session.value?.id !== id) return
          view.value = result.data; lastRevision = r.data.revision; lastOptions = key; await draw()
        } else if (view.value) view.value.fresh = r.data.status === 'streaming' && Date.now()-new Date(r.data.received_at).getTime() < Math.max(3000, 508000/r.data.sample_rate)
      }
    }
  } catch { if (!disposed) { connectionError.value = '实时连接中断，正在重试；当前显示最后收到的数据'; if (view.value) view.value.fresh = false } } finally { if (!disposed) timer = setTimeout(poll, 500) }
}
watch(() => form.agent_id, async id => {
  turn++; const version = turn; if (!id) return
  directoryEdited.value = false; form.save_directory = selectedAgent.value?.state?.save_directory || ''
  try { const r = await getCurrentLiveSession(id); if (disposed || version !== turn) return; session.value = r.data; view.value = null; lastRevision = -1; disposeCharts(); if (r.data) form.sample_rate = r.data.sample_rate } catch {}
})
onMounted(async () => { window.addEventListener('resize', resize); try { const c = await getAcquisitionCapabilities(); if (!disposed) nativeRates.value = c.data.sample_rates; await refreshAgents() } finally { if (!disposed) poll() } })
onBeforeUnmount(() => { disposed = true; turn++; clearTimeout(timer); closeViewSocket(); window.removeEventListener('resize', resize); disposeCharts() })
</script>

<style scoped>
.acquisition-page { max-width:1680px;margin:0 auto; } header { display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:16px; } h1 { margin:0 0 6px;font-size:24px;font-weight:600; } header p,.help,.source-line { color:#586576;font-size:12px;line-height:1.7; } header p { margin:0;font-size:14px; }
.console-layout { display:grid;grid-template-columns:310px minmax(0,1fr);gap:18px;align-items:start; }.control-panel,.scope-panel { padding:20px;background:white;border:1px solid #e2e7ee;border-radius:6px;min-width:0; }.control-panel :deep(.el-select),.control-panel :deep(.el-input-number) { width:100%; }.actions { display:flex;flex-wrap:wrap;gap:8px; }.actions :deep(.el-button) { margin-left:0;min-height:44px;flex:1; }.display-options { display:grid;grid-template-columns:1fr 1fr;margin:12px 0; }.display-options :deep(.el-checkbox) { margin-right:0;min-height:36px; }.band-fields { border-left:3px solid #165DFF;padding-left:12px; }.error-text { color:#b42318;font-size:12px;line-height:1.7; }.directory-button { margin-top:8px; }
.status-strip { display:flex;flex-wrap:wrap;gap:20px;align-items:center;padding-bottom:14px;border-bottom:1px solid #e2e7ee;font-size:13px; }.status-dot { display:inline-block;width:8px;height:8px;margin-right:7px;border-radius:50%;background:#8592a3; }.status-dot.live { background:#008B7A; }.source-line { display:flex;flex-wrap:wrap;gap:20px;margin-top:12px;overflow-wrap:anywhere; }.record-strip { margin-top:16px;padding:12px;background:#eff8f5;border-left:3px solid #008B7A;font-size:13px;line-height:1.8;overflow-wrap:anywhere; }.record-strip>span { margin-left:16px; }.record-strip p { margin:4px 0; } section h2 { margin:20px 0 10px;font-size:15px;font-weight:600; }.channel-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px; }.channel-scope { min-width:0;border:1px solid #e7ecf2;border-radius:4px; }.chart { height:225px; }.history-panel { margin-top:20px; }
@media(max-width:1100px) { .console-layout { grid-template-columns:280px minmax(0,1fr); }.channel-grid { grid-template-columns:1fr; } } @media(max-width:750px) { .console-layout { grid-template-columns:1fr; } h1 { font-size:21px; }.control-panel,.scope-panel { padding:15px; } }
</style>
