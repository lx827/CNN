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
    <el-card class="table-card">
      <el-table
        :data="deviceTableData"
        style="width: 100%"
        v-loading="loading"
        row-key="device_id"
        border
      >
        <el-table-column prop="device_id" label="设备ID" width="140" />
        <el-table-column prop="device_name" label="设备名称" width="160" />
        <el-table-column label="历史数据批次" min-width="400">
          <template #default="{ row }">
            <div class="batch-tags">
              <el-tag
                v-for="batch in row.batches"
                :key="batch.batch_index"
                :type="getBatchTagType(batch)"
                class="batch-tag"
                :class="{ active: isSelected(row.device_id, batch.batch_index) }"
                @click="selectBatch(row, batch)"
                size="small"
                effect="light"
              >
                #{{ batch.batch_index }} {{ formatTime(batch.created_at) }}
                <el-icon v-if="batch.is_special" class="special-icon"><Star-Filled /></el-icon>
              </el-tag>
              <el-text v-if="row.batches.length === 0" type="info" size="small">暂无数据</el-text>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              @click="openBatchDeleteDialog(row)"
            >
              批量删除
            </el-button>
            <el-button
              link
              type="danger"
              size="small"
              @click="onDeleteDeviceSpecial(row.device_id)"
            >
              删除特殊数据
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 选中批次详情 -->
    <el-card v-if="selectedDevice && selectedBatch" class="detail-card">
      <template #header>
        <div class="detail-header">
          <span>
            数据详情 — <b>{{ selectedDevice.device_name }}</b>
            批次 <b>{{ selectedBatch.batch_index }}</b>
            <el-tag v-if="selectedBatch.is_special" type="danger" size="small" effect="dark">特殊数据</el-tag>
            <el-tag type="info" size="small">采样率 {{ selectedBatch.sample_rate || 25600 }} Hz</el-tag>
          </span>
          <div class="detail-actions">
            <el-select v-model="selectedChannel" style="width: 180px" size="small" @change="onChannelChange">
              <el-option
                v-for="i in channelOptions"
                :key="i"
                :label="getChannelName(i)"
                :value="i"
              />
            </el-select>
            <el-select v-model="maxFreq" style="width: 120px; margin-left: 8px" size="small" @change="onMaxFreqChange">
              <el-option label="1000 Hz" :value="1000" />
              <el-option label="2500 Hz" :value="2500" />
              <el-option label="5000 Hz" :value="5000" />
              <el-option label="8192 Hz" :value="8192" />
            </el-select>
            <el-button
              type="primary"
              size="small"
              style="margin-left: 8px"
              @click="onExportCSV"
            >
              <el-icon><Download /></el-icon> 导出 CSV
            </el-button>
            <el-button
              type="danger"
              size="small"
              style="margin-left: 8px"
              @click="onDeleteBatch(selectedDevice.device_id, selectedBatch.batch_index)"
            >
              <el-icon><Delete /></el-icon> 删除此批次
            </el-button>
          </div>
        </div>
      </template>

      <!-- 时域波形：始终自动加载 -->
      <el-row :gutter="16">
        <el-col :span="24">
          <div class="chart-title">时域波形</div>
          <div ref="timeChart" class="chart"></div>
        </el-col>
      </el-row>

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
          <div v-if="computedStats && statsData" class="stats-grid">
            <el-row :gutter="16">
              <el-col :xs="12" :sm="8" :md="6" v-for="item in statsDisplay" :key="item.key">
                <el-statistic :title="item.label" :value="statsData[item.key]" :precision="item.precision" />
              </el-col>
            </el-row>
            <el-text v-if="statsData.window_params" type="info" size="small" style="display: block; margin-top: 8px;">
              加窗参数：窗口大小 {{ statsData.window_params.window_size }} 点，滑动步长 {{ statsData.window_params.step }} 点
            </el-text>
          </div>
          <div v-if="computedStats && statsData?.window_series" style="margin-top: 16px;">
            <div class="chart-title">加窗统计量时序图</div>
            <div ref="windowedChart" class="chart" style="height: 280px"></div>
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
          <div v-if="computedFFT" ref="fftChart" class="chart"></div>
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
            <el-button
              v-if="!computedEnvelope"
              type="primary"
              size="small"
              :loading="loadingEnvelope"
              @click="computeEnvelope"
            >
              <el-icon><DataAnalysis /></el-icon> 计算包络谱
            </el-button>
            <el-button v-else type="info" size="small" @click="clearEnvelope">
              <el-icon><Close /></el-icon> 收起
            </el-button>
          </div>
          <div v-if="computedEnvelope" ref="envelopeChart" class="chart"></div>
          <div v-else-if="loadingEnvelope" class="placeholder">
            <el-skeleton :rows="3" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="点击按钮计算包络谱" :image-size="80" />
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
          <div v-if="computedOrder" ref="orderChart" class="chart"></div>
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
            <span class="chart-title">倒谱分析（Cepstrum）</span>
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
          <div v-if="computedCepstrum" ref="cepstrumChart" class="chart"></div>
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
          <div v-if="computedSTFT" ref="stftChart" class="chart" style="height: 600px"></div>
          <div v-else-if="loadingSTFT" class="placeholder">
            <el-skeleton :rows="4" animated />
          </div>
          <div v-else class="placeholder">
            <el-empty description="设置窗口参数后计算 STFT 时频谱" :image-size="80" />
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-empty v-else description="点击上方表格中的批次时间，查看详细数据" />

    <!-- 批量删除对话框 -->
    <el-dialog
      v-model="batchDeleteDialogVisible"
      title="批量删除批次"
      width="400px"
    >
      <div v-if="batchDeleteTargetDevice">
        <p style="margin-bottom: 12px;">设备：<b>{{ batchDeleteTargetDevice.device_name }}</b></p>
        <p style="margin-bottom: 12px; color: #666; font-size: 13px;">请选择要删除的普通数据批次：</p>
        <el-checkbox-group v-model="batchDeleteSelected">
          <el-checkbox
            v-for="batch in batchDeleteTargetDevice.batches.filter(b => !b.is_special)"
            :key="batch.batch_index"
            :label="batch.batch_index"
          >
            批次 #{{ batch.batch_index }} {{ formatTime(batch.created_at) }}
          </el-checkbox>
        </el-checkbox-group>
        <p v-if="batchDeleteTargetDevice.batches.filter(b => !b.is_special).length === 0" style="color: #999;">该设备没有普通数据批次</p>
      </div>
      <template #footer>
        <el-button @click="batchDeleteDialogVisible = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="batchDeleteSelected.length === 0"
          @click="confirmBatchDelete"
        >
          删除选中的 {{ batchDeleteSelected.length }} 个批次
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import {
  getAllDeviceData,
  getChannelData,
  getChannelFFT,
  getChannelSTFT,
  getChannelEnvelope,
  getChannelStats,
  getChannelOrder,
  getChannelCepstrum,
  deleteBatch,
  deleteSpecialBatches,
  exportChannelCSV
} from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const loading = ref(false)
const deleteLoading = ref(false)
const deviceTableData = ref([])

// 批量删除
const batchDeleteDialogVisible = ref(false)
const batchDeleteTargetDevice = ref(null)
const batchDeleteSelected = ref([])

const openBatchDeleteDialog = (device) => {
  batchDeleteTargetDevice.value = device
  batchDeleteSelected.value = []
  batchDeleteDialogVisible.value = true
}

const confirmBatchDelete = async () => {
  if (batchDeleteSelected.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${batchDeleteSelected.value.length} 个批次吗？此操作不可恢复。`,
      '确认批量删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    deleteLoading.value = true
    const deviceId = batchDeleteTargetDevice.value.device_id
    for (const batchIndex of batchDeleteSelected.value) {
      await deleteBatch(deviceId, batchIndex)
    }
    ElMessage.success(`已删除 ${batchDeleteSelected.value.length} 个批次`)
    batchDeleteDialogVisible.value = false
    // 如果当前选中的批次被删除了，清空详情
    if (selectedDevice.value?.device_id === deviceId) {
      const deleted = batchDeleteSelected.value.includes(selectedBatch.value?.batch_index)
      if (deleted) {
        selectedDevice.value = null
        selectedBatch.value = null
      }
    }
    await loadAllDevices()
  } catch (e) {
    if (e !== 'cancel') {
      console.error('批量删除失败:', e)
      ElMessage.error('批量删除失败')
    }
  } finally {
    deleteLoading.value = false
  }
}

const selectedDevice = ref(null)
const selectedBatch = ref(null)
const selectedChannel = ref(1)
const maxFreq = ref(5000)
const channelOptions = ref([1, 2, 3])

const timeChart = ref(null)
const fftChart = ref(null)
const stftChart = ref(null)
const envelopeChart = ref(null)
const windowedChart = ref(null)
const orderChart = ref(null)
const cepstrumChart = ref(null)
let timeInstance = null
let fftInstance = null
let stftInstance = null
let envelopeInstance = null
let windowedInstance = null
let orderInstance = null
let cepstrumInstance = null

// 按需计算状态
const computedFFT = ref(false)
const computedSTFT = ref(false)
const computedEnvelope = ref(false)
const computedStats = ref(false)
const computedOrder = ref(false)
const computedCepstrum = ref(false)
const loadingFFT = ref(false)
const loadingSTFT = ref(false)
const loadingEnvelope = ref(false)
const loadingStats = ref(false)
const loadingOrder = ref(false)
const loadingCepstrum = ref(false)
const statsData = ref(null)
const orderData = ref(null)
const cepstrumData = ref(null)

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

const statsDisplay = [
  { key: 'peak', label: '峰值', precision: 4 },
  { key: 'rms', label: '均方根 (RMS)', precision: 4 },
  { key: 'kurtosis', label: '峭度', precision: 4 },
  { key: 'windowed_kurtosis', label: '加窗峰度', precision: 4 },
  { key: 'skewness', label: '偏度', precision: 4 },
  { key: 'margin', label: '裕度', precision: 4 },
  { key: 'crest_factor', label: '峰值因子', precision: 4 },
  { key: 'shape_factor', label: '波形因子', precision: 4 },
  { key: 'impulse_factor', label: '脉冲因子', precision: 4 },
]

const formatTime = (iso) => {
  if (!iso) return ''
  const isoStr = /[Z+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + 'Z'
  const d = new Date(isoStr)
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }).replace(/\//g, '-')
}

const getChannelName = (chNum) => {
  const names = selectedDevice.value?.channel_names
  if (names && names[String(chNum)]) {
    return names[String(chNum)]
  }
  const defaults = { 1: '通道1-轴承附近', 2: '通道2-驱动端', 3: '通道3-风扇端' }
  return defaults[chNum] || `通道${chNum}`
}

const isSelected = (deviceId, batchIndex) => {
  return selectedDevice.value?.device_id === deviceId && selectedBatch.value?.batch_index === batchIndex
}

const getBatchTagType = (batch) => {
  if (batch.diagnosis_status === 'fault') return 'danger'
  if (batch.diagnosis_status === 'warning') return 'warning'
  return 'info'
}

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

// ========== 选择批次 ==========
const selectBatch = (device, batch) => {
  // 清理旧图表实例
  timeInstance?.dispose(); timeInstance = null
  fftInstance?.dispose(); fftInstance = null
  stftInstance?.dispose(); stftInstance = null
  envelopeInstance?.dispose(); envelopeInstance = null

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
  })
}

const resetComputedState = () => {
  computedFFT.value = false
  computedSTFT.value = false
  computedEnvelope.value = false
  computedStats.value = false
  computedOrder.value = false
  computedCepstrum.value = false
  statsData.value = null
  orderData.value = null
  cepstrumData.value = null
  windowedInstance?.dispose(); windowedInstance = null
  orderInstance?.dispose(); orderInstance = null
  cepstrumInstance?.dispose(); cepstrumInstance = null
}

const onChannelChange = () => {
  // 通道切换时，时域图重新加载，其他收起
  resetComputedState()
  timeInstance?.dispose(); timeInstance = null
  fftInstance?.dispose(); fftInstance = null
  stftInstance?.dispose(); stftInstance = null
  envelopeInstance?.dispose(); envelopeInstance = null
  windowedInstance?.dispose(); windowedInstance = null
  orderInstance?.dispose(); orderInstance = null
  cepstrumInstance?.dispose(); cepstrumInstance = null
  nextTick(() => {
    loadTimeDomain()
  })
}

const onMaxFreqChange = () => {
  // 频率范围改变时，如果已计算 FFT/STFT/包络/阶次，重新计算
  if (computedFFT.value) computeFFT()
  if (computedSTFT.value) computeSTFT()
  if (computedEnvelope.value) computeEnvelope()
  if (computedOrder.value) computeOrder()
}

// ========== 时域波形（始终自动加载） ==========
const loadTimeDomain = async () => {
  try {
    const res = await getChannelData(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value
    )
    const d = res.data
    if (!d) return

    const sr = d.sample_rate || 25600
    const timeData = d.data || []
    const timeX = timeData.map((_, i) => (i / sr).toFixed(4))

    if (!timeInstance) timeInstance = echarts.init(timeChart.value)
    timeInstance.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: timeX, name: '时间 (s)', nameGap: 25 },
      yAxis: { type: 'value', name: '幅值' },
      dataZoom: [{ type: 'inside' }, { type: 'slider', bottom: 0 }],
      series: [{
        type: 'line',
        data: timeData,
        showSymbol: false,
        lineStyle: { width: 1, color: '#165DFF' }
      }]
    }, true)
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
      maxFreq.value
    )
    const d = res.data
    if (!d) return

    computedFFT.value = true
    await nextTick()

    if (!fftInstance) fftInstance = echarts.init(fftChart.value)
    fftInstance.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: d.fft_freq, name: '频率 (Hz)', nameGap: 25 },
      yAxis: { type: 'value', name: '幅值' },
      dataZoom: [{ type: 'inside' }],
      series: [{
        type: 'line',
        data: d.fft_amp,
        showSymbol: false,
        areaStyle: { color: 'rgba(22, 93, 255, 0.2)' },
        lineStyle: { width: 1.5, color: '#165DFF' }
      }]
    }, true)
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
  fftInstance?.dispose()
  fftInstance = null
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
      stftNoverlap.value
    )
    const d = res.data
    if (!d) return

    computedSTFT.value = true
    await nextTick()

    if (!stftInstance) stftInstance = echarts.init(stftChart.value)
    const minVal = Math.min(...d.magnitude.flat())
    const maxVal = Math.max(...d.magnitude.flat())
    stftInstance.setOption({
      tooltip: { position: 'top' },
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
    }, true)
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
  stftInstance?.dispose()
  stftInstance = null
}

// ========== 按需计算：包络谱 ==========
const computeEnvelope = async () => {
  loadingEnvelope.value = true
  try {
    const res = await getChannelEnvelope(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      1000
    )
    const d = res.data
    if (!d) return

    computedEnvelope.value = true
    await nextTick()

    if (!envelopeInstance) envelopeInstance = echarts.init(envelopeChart.value)
    envelopeInstance.setOption({
      tooltip: { trigger: 'axis' },
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
    }, true)
  } catch (e) {
    console.error('包络谱计算失败:', e)
    ElMessage.error('包络谱计算失败')
    computedEnvelope.value = false
  } finally {
    loadingEnvelope.value = false
  }
}

const clearEnvelope = () => {
  computedEnvelope.value = false
  envelopeInstance?.dispose()
  envelopeInstance = null
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
      orderSamplesPerRev.value
    )
    const d = res.data
    if (!d) return

    orderData.value = d
    computedOrder.value = true
    await nextTick()

    if (!orderInstance) orderInstance = echarts.init(orderChart.value)
    // category 轴的 markLine xAxis 是索引而非数值，需换算
    const orderStep = d.orders[1] - d.orders[0]
    const idx1x = Math.min(Math.round(1 / orderStep), d.orders.length - 1)
    const idx2x = Math.min(Math.round(2 / orderStep), d.orders.length - 1)
    const idx3x = Math.min(Math.round(3 / orderStep), d.orders.length - 1)
    orderInstance.setOption({
      tooltip: { trigger: 'axis', formatter: (params) => {
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
    }, true)
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
  orderInstance?.dispose()
  orderInstance = null
}

// ========== 按需计算：倒谱分析 ==========
const computeCepstrum = async () => {
  loadingCepstrum.value = true
  try {
    const res = await getChannelCepstrum(
      selectedDevice.value.device_id,
      selectedBatch.value.batch_index,
      selectedChannel.value,
      cepstrumMaxQuefrency.value
    )
    const d = res.data
    if (!d) return

    cepstrumData.value = d
    computedCepstrum.value = true
    await nextTick()

    if (!cepstrumInstance) cepstrumInstance = echarts.init(cepstrumChart.value)
    // value 轴避免 category 轴标签重叠（12800 个点）
    const xyData = d.quefrency.map((q, i) => [q, d.cepstrum[i]])
    const markLines = (d.peaks || []).map(p => ({
      xAxis: p.quefrency_ms,
      name: `${p.freq_hz}Hz`
    }))
    cepstrumInstance.setOption({
      tooltip: { trigger: 'axis', formatter: (params) => {
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
    }, true)
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
  cepstrumInstance?.dispose()
  cepstrumInstance = null
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
      statsStep.value
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
  windowedInstance?.dispose()
  windowedInstance = null
}

// 初始化加窗统计量时序图
const initWindowedChart = () => {
  const ws = statsData.value?.window_series
  if (!ws || !ws.time || ws.time.length === 0) return

  if (!windowedInstance) windowedInstance = echarts.init(windowedChart.value)
  windowedInstance.setOption({
    tooltip: { trigger: 'axis' },
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
  }, true)
}

// ========== 导出 CSV ==========
const onExportCSV = () => {
  if (!selectedDevice.value || !selectedBatch.value) return
  exportChannelCSV(
    selectedDevice.value.device_id,
    selectedBatch.value.batch_index,
    selectedChannel.value
  )
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

const onDeleteDeviceSpecial = async (deviceId) => {
  try {
    await ElMessageBox.confirm(
      `确定删除设备 ${deviceId} 的所有特殊数据吗？此操作不可恢复。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    deleteLoading.value = true
    await deleteSpecialBatches(deviceId)
    ElMessage.success('特殊数据已删除')
    if (selectedDevice.value?.device_id === deviceId && selectedBatch.value?.is_special) {
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

onMounted(async () => {
  await loadAllDevices()
  autoSelectFromQuery()
  window.addEventListener('resize', () => {
    timeInstance?.resize()
    fftInstance?.resize()
    stftInstance?.resize()
    envelopeInstance?.resize()
    windowedInstance?.resize()
    orderInstance?.resize()
    cepstrumInstance?.resize()
  })
})

onUnmounted(() => {
  timeInstance?.dispose()
  fftInstance?.dispose()
  stftInstance?.dispose()
  envelopeInstance?.dispose()
  windowedInstance?.dispose()
  orderInstance?.dispose()
  cepstrumInstance?.dispose()
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

.table-card {
  margin-bottom: 16px;
}

.batch-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.batch-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.batch-tag:hover {
  transform: scale(1.05);
}

.batch-tag.active {
  box-shadow: 0 0 0 2px #165DFF;
}

.special-icon {
  margin-left: 2px;
  font-size: 10px;
}

.detail-card {
  margin-bottom: 20px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.detail-actions {
  display: flex;
  align-items: center;
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

.stats-grid {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.stats-grid :deep(.el-statistic__content) {
  font-size: 20px;
  font-weight: 600;
  color: #165DFF;
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

.stats-grid :deep(.el-statistic__head) {
  font-size: 13px;
  color: #666;
}
</style>
