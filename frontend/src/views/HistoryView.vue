<template>
  <div class="history-wrap">
    <el-card>
      <template #header>历史评审记录</template>
      <el-table :data="items" stripe v-loading="loading" empty-text="暂无历史记录">
        <el-table-column prop="submission_id" label="ID" min-width="180" />
        <el-table-column prop="language" label="语言" width="90" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="得分" width="90">
          <template #default="{ row }">{{ row.total_score ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="title" label="称号" min-width="140" />
        <el-table-column prop="level" label="等级" width="80">
          <template #default="{ row }">
            <el-tag size="small" type="warning">Lv{{ row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button size="small" @click="view(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listReviews } from '../api'

const router = useRouter()
const loading = ref(false)
const items = ref([])

async function load() {
  loading.value = true
  try {
    const d = await listReviews()
    items.value = d.items
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '查询失败')
  } finally {
    loading.value = false
  }
}

function view(row) {
  router.push({ name: 'report', params: { id: row.submission_id } })
}

function formatTime(s) {
  return s ? s.replace('T', ' ').slice(0, 19) : ''
}
function statusText(s) {
  return { pending: '评审中', completed: '完成', failed: '失败' }[s] || s || '未知'
}
function statusType(s) {
  return { pending: 'info', completed: 'success', failed: 'danger' }[s] || 'info'
}

onMounted(load)
</script>

<style scoped>
.history-wrap {
  max-width: 1000px;
  margin: 0 auto;
}
.toolbar {
  margin-bottom: 16px;
}
</style>
