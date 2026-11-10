<template>
  <div class="upload-wrap">
    <el-card class="card">
      <h2>提交代码评审</h2>
      <p class="hint">上传 zip 或提供 git 仓库地址，平台将异步进行六维代码质量评审并授予称号。</p>
      <el-form label-width="80px">
        <el-form-item label="输入方式">
          <el-radio-group v-model="inputType">
            <el-radio-button value="zip">上传 zip</el-radio-button>
            <el-radio-button value="git">git 仓库地址</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="inputType === 'zip'" label="工程文件">
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            accept=".zip"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
          >
            <el-icon class="el-icon--upload"><upload-filled /></el-icon>
            <div class="el-upload__text">拖拽 zip 到这里，或 <em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">仅支持 .zip，上传 ≤ 200MB</div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item v-else label="仓库地址">
          <el-input
            v-model="gitUrl"
            placeholder="https://github.com/owner/repo.git"
            style="max-width: 480px"
            @keyup.enter="submit"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="submitting"
            :disabled="!canSubmit"
            @click="submit"
          >
            {{ submitting ? '提交中…' : '提交评审' }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { submitReview } from '../api'

const inputType = ref('zip')
const file = ref(null)
const gitUrl = ref('')
const submitting = ref(false)

const canSubmit = computed(() =>
  inputType.value === 'zip' ? !!file.value : !!gitUrl.value.trim()
)

function onFileChange(uploadFile) {
  file.value = uploadFile.raw
}
function onFileRemove() {
  file.value = null
}

async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    await submitReview(
      inputType.value === 'zip' ? file.value : null,
      '',
      inputType.value === 'git' ? gitUrl.value.trim() : ''
    )
    ElMessage.success('已提交，正在后台评审')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.upload-wrap {
  max-width: 720px;
  margin: 0 auto;
}
.card h2 {
  margin: 0 0 8px;
}
.hint {
  color: #909399;
  margin: 0 0 24px;
}
</style>
