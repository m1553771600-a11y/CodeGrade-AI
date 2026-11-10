<template>
  <div v-if="loading" class="loading">
    <el-skeleton :rows="10" animated />
  </div>

  <div v-else-if="pending" class="pending">
    <el-result icon="info" title="评审进行中" :sub-title="stageMessage || '正在解析、静态分析并由 LLM 评审，请稍候…'">
      <template #extra>
        <el-icon class="is-loading" :size="30"><loading /></el-icon>
      </template>
    </el-result>
    <el-steps :active="currentStep" align-center finish-status="success" class="steps">
      <el-step title="代码解析" />
      <el-step title="静态分析" />
      <el-step title="LLM 评审" />
      <el-step title="生成称号" />
    </el-steps>
  </div>

  <div v-else-if="failed" class="empty">
    <el-result icon="error" title="评审失败" :sub-title="failed">
      <template #extra>
        <el-button type="primary" @click="$router.push('/')">重新提交</el-button>
      </template>
    </el-result>
  </div>

  <div v-else-if="!data" class="empty">
    <el-empty description="未找到该评审记录" />
  </div>

  <div v-else class="report">
    <!-- 称号卡片 -->
    <el-card class="hero" shadow="hover">
      <div class="hero-score">
        <div class="score-num">
          {{ data.total_score }}<span class="score-total"> / {{ data.full_score }}</span>
        </div>
        <div class="score-label">综合得分</div>
      </div>
      <div class="hero-title">
        <div class="title-line">
          <span class="title-text">{{ data.title_award?.title || '—' }}</span>
          <el-tag v-if="data.title_award?.level" type="warning" effect="dark" size="large">
            Lv{{ data.title_award.level }}
          </el-tag>
          <el-tag v-if="data.title_award?.easter_egg" type="danger" effect="dark" size="large">
            彩蛋 · {{ data.title_award.easter_egg }}
          </el-tag>
        </div>
        <p v-if="data.title_award?.reason" class="reason">「{{ data.title_award.reason }}」</p>
        <div class="meta">
          <el-tag size="small">{{ data.language }}</el-tag>
          <el-tag size="small" type="info">源码 {{ data.stats?.source_count ?? 0 }} 个文件</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 评审总结 -->
    <el-card v-if="data.summary" class="section" shadow="hover">
      <template #header>评审总结</template>
      <p class="summary-text">{{ data.summary }}</p>
    </el-card>

    <!-- 六维得分 -->
    <el-card class="section" shadow="hover">
      <template #header>六维得分</template>
      <template v-if="data.dimension_scores?.length">
        <div v-for="d in data.dimension_scores" :key="d.dimension" class="dim-row">
          <span class="dim-name">{{ dimName(d.dimension) }}</span>
          <el-progress
            class="dim-bar"
            :percentage="ratio(d)"
            :stroke-width="16"
            :color="barColor(d)"
          />
          <span class="dim-score">{{ d.score }} / {{ d.weight }}</span>
        </div>
      </template>
      <el-empty v-else description="暂无维度评分数据" :image-size="80" />
    </el-card>

    <!-- 问题明细 -->
    <el-card class="section" shadow="hover">
      <template #header>问题明细（{{ totalIssues }} 条）</template>
      <el-table :data="flattenIssues" stripe style="width: 100%" empty-text="暂无问题">
        <el-table-column prop="dimension" label="维度" width="140" />
        <el-table-column prop="file" label="文件" width="170" />
        <el-table-column prop="line" label="行" width="70" />
        <el-table-column prop="severity" label="级别" width="90">
          <template #default="{ row }">
            <el-tag :type="severityType(row.severity)" size="small">{{ row.severity }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="问题说明" min-width="260" />
        <el-table-column prop="suggestion" label="建议" min-width="260" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { getReview, getToken } from '../api'

const props = defineProps({ id: { type: String, required: true } })

const loading = ref(true)
const pending = ref(false)
const failed = ref('')
const data = ref(null)

let timer = null
let es = null

const currentStep = ref(0)
const stageMessage = ref('')
const STAGE_INDEX = { parse: 1, lint: 2, review: 3, award: 4 }

function openStream() {
  if (es) return
  try {
    es = new EventSource(`/api/v1/review/${props.id}/stream?token=${encodeURIComponent(getToken())}`)
    es.addEventListener('progress', (e) => {
      try {
        const d = JSON.parse(e.data)
        stageMessage.value = d.message || ''
        currentStep.value = STAGE_INDEX[d.stage] || currentStep.value
      } catch (_) {}
    })
    es.onerror = () => { /* SSE 失败由轮询兜底 */ }
  } catch (_) {}
}

const DIM_NAMES = {
  structure: '结构·模块化',
  robustness: '健壮性·安全',
  maintainability: '可维护·设计',
  complexity: '复杂度·重复',
  style: '规范·风格',
  readability: '可读·注释',
}

const totalIssues = computed(() =>
  data.value ? data.value.dimension_scores.reduce((n, d) => n + (d.issues?.length || 0), 0) : 0
)

const flattenIssues = computed(() => {
  if (!data.value) return []
  const rows = []
  for (const d of data.value.dimension_scores) {
    for (const i of d.issues || []) {
      rows.push({ dimension: dimName(d.dimension), ...i })
    }
  }
  return rows
})

function dimName(k) {
  return DIM_NAMES[k] || k
}
function ratio(d) {
  return d.weight ? Math.round((d.score / d.weight) * 100) : 0
}
function barColor(d) {
  const r = d.weight ? d.score / d.weight : 0
  if (r >= 0.8) return '#67c23a'
  if (r >= 0.6) return '#e6a23c'
  return '#f56c6c'
}
function severityType(s) {
  return { high: 'danger', medium: 'warning', low: 'info' }[s] || 'info'
}

async function load() {
  try {
    const r = await getReview(props.id)
    if (r.status === 'pending') {
      pending.value = true
      loading.value = false
      openStream()
      timer = setTimeout(load, 2000) // 2 秒后轮询
      return
    }
    if (r.status === 'failed') {
      failed.value = r.error || '未知错误'
      pending.value = false
      loading.value = false
      return
    }
    data.value = r
    pending.value = false
    loading.value = false
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载评审结果失败')
    loading.value = false
  }
}

onMounted(load)
onUnmounted(() => {
  if (timer) clearTimeout(timer)
  if (es) es.close()
})
</script>

<style scoped>
.loading,
.empty,
.pending {
  max-width: 900px;
  margin: 40px auto;
}
.report {
  max-width: 1000px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.steps {
  max-width: 640px;
  margin: 24px auto 0;
}
.hero {
  display: flex;
  align-items: center;
  gap: 48px;
  padding: 8px 8px;
}
.hero-score {
  text-align: center;
  min-width: 160px;
  border-right: 1px solid #ebeef5;
  padding-right: 48px;
}
.score-num {
  font-size: 56px;
  font-weight: 700;
  color: #409eff;
  line-height: 1;
}
.score-total {
  font-size: 20px;
  color: #909399;
  font-weight: 400;
}
.score-label {
  color: #909399;
  margin-top: 8px;
}
.title-line {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.title-text {
  font-size: 32px;
  font-weight: 700;
}
.reason {
  font-size: 16px;
  color: #606266;
  margin: 12px 0 8px;
}
.summary-text {
  margin: 0;
  line-height: 1.7;
  color: #606266;
  white-space: pre-wrap;
}
.meta {
  display: flex;
  gap: 8px;
}
.dim-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}
.dim-name {
  width: 120px;
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
</style>
