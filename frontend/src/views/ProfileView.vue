<template>
  <div class="profile-wrap">
    <el-card>
      <template #header>能力画像</template>

      <div v-if="profile" class="profile-body">
        <!-- 概览 -->
        <div class="overview">
          <div class="ov-item">
            <div class="ov-num">{{ profile.review_count }}</div>
            <div class="ov-label">评审次数</div>
          </div>
          <div class="ov-item">
            <div class="ov-num">{{ profile.avg_total_score ?? '—' }}</div>
            <div class="ov-label">平均总分</div>
          </div>
          <div class="ov-item">
            <div class="ov-num">{{ profile.overall_level ?? '—' }}</div>
            <div class="ov-label">整体等级</div>
          </div>
        </div>

        <!-- 六维熟练度 -->
        <el-card class="section" shadow="never">
          <template #header>六维能力熟练度</template>
          <div v-for="d in profile.dimensions" :key="d.dimension" class="dim-row">
            <span class="dim-name">{{ d.name }}</span>
            <el-progress
              class="dim-bar"
              :percentage="Math.round((d.avg_rate ?? 0) * 100)"
              :stroke-width="16"
              :color="barColor(d.avg_rate)"
            />
            <span class="dim-score">{{ d.avg_score ?? '—' }} / {{ d.weight }}</span>
          </div>
        </el-card>

        <!-- 薄弱点 -->
        <el-card class="section" shadow="never">
          <template #header>薄弱点</template>
          <el-empty v-if="!profile.weak_points.length" description="无明显薄弱维度" :image-size="60" />
          <div v-else class="weak-list">
            <el-tag
              v-for="w in profile.weak_points"
              :key="w.dimension"
              type="danger"
              effect="plain"
              size="large"
              class="weak-tag"
            >
              {{ w.name }}（熟练度 {{ Math.round(w.avg_rate * 100) }}%）
            </el-tag>
          </div>
        </el-card>

        <!-- 趋势 -->
        <el-card class="section" shadow="never">
          <template #header>历史得分趋势</template>
          <el-empty v-if="!profile.trend.length" description="暂无历史记录" :image-size="60" />
          <div v-else class="trend-list">
            <div v-for="t in profile.trend" :key="t.submission_id" class="trend-row">
              <el-tag :type="scoreType(t.total_score)" size="small">{{ t.total_score }}</el-tag>
              <span class="trend-time">{{ formatTime(t.created_at) }}</span>
            </div>
          </div>
        </el-card>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getProfile } from '../api'

const loading = ref(false)
const profile = ref(null)

async function load() {
  loading.value = true
  try {
    profile.value = await getProfile()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '查询失败')
    profile.value = null
  } finally {
    loading.value = false
  }
}

function barColor(rate) {
  if (rate == null) return '#c0c4cc'
  if (rate >= 0.8) return '#67c23a'
  if (rate >= 0.6) return '#e6a23c'
  return '#f56c6c'
}
function scoreType(score) {
  if (score >= 70) return 'success'
  if (score >= 50) return 'warning'
  return 'danger'
}
function formatTime(s) {
  return s ? s.replace('T', ' ').slice(0, 19) : ''
}

onMounted(load)
</script>

<style scoped>
.profile-wrap {
  max-width: 900px;
  margin: 0 auto;
}
.toolbar {
  margin-bottom: 16px;
}
.overview {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
}
.ov-item {
  flex: 1;
  text-align: center;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}
.ov-num {
  font-size: 28px;
  font-weight: 700;
  color: #409eff;
}
.ov-label {
  color: #909399;
  margin-top: 4px;
}
.section {
  margin-top: 16px;
}
.dim-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}
.dim-name {
  width: 110px;
  text-align: right;
  color: #606266;
  flex-shrink: 0;
}
.dim-bar {
  flex: 1;
}
.dim-score {
  width: 80px;
  color: #909399;
  font-variant-numeric: tabular-nums;
}
.weak-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.weak-tag {
  font-size: 14px;
}
.trend-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.trend-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.trend-time {
  color: #909399;
  font-size: 13px;
}
</style>
