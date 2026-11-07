<template>
  <el-card style="margin-top: 20px">
    <template #header>
      <span>配置说明</span>
    </template>
    <el-descriptions :column="1" border>
      <el-descriptions-item label="自动采集间隔">
        边端在无人干预的情况下，每隔该时间自动采集并上传一批振动数据。
        值越小数据越实时，但网络负载越高；值越大越节省带宽。
      </el-descriptions-item>
      <el-descriptions-item label="任务轮询间隔">
        边端每隔该时间向云端查询一次是否有手动触发的采集任务。
        该值应小于等于自动采集间隔，确保手动任务能被及时响应。
      </el-descriptions-item>
      <el-descriptions-item label="同步机制">
        边端每 30 秒自动拉取一次云端配置。保存后，最长等待 30 秒即可生效。
        也可重启边端客户端立即生效。
      </el-descriptions-item>
      <el-descriptions-item label="告警阈值">
        通道级阈值配置针对每个通道独立判断。当同一批数据中多个通道同时超标时，
        系统会分别生成多条通道级告警。诊断结果类告警（健康度/故障概率）不受此配置影响。
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>
