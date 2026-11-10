<template>
  <div class="login-wrap">
    <el-card class="card">
      <h2>{{ isRegister ? '注册' : '登录' }}</h2>
      <el-form label-width="60px" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="submit">
            {{ isRegister ? '注册' : '登录' }}
          </el-button>
          <el-button text @click="isRegister = !isRegister">
            {{ isRegister ? '已有账号？去登录' : '没有账号？去注册' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div v-if="isRegister" class="rules">
        <p class="rules-title">账号要求</p>
        <ul>
          <li>用户名：2 ~ 64 个字符，需唯一</li>
          <li>密码：4 ~ 128 个字符</li>
        </ul>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, register, setToken } from '../api'

const route = useRoute()
const router = useRouter()
const isRegister = ref(false)
const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const fn = isRegister.value ? register : login
    const d = await fn(username.value, password.value)
    setToken(d.access_token)
    ElMessage.success(isRegister.value ? '注册成功' : '登录成功')
    router.push(route.query.redirect || '/')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  max-width: 400px;
  margin: 80px auto;
}
.card h2 {
  margin: 0 0 20px;
}
.rules {
  margin-top: 12px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}
.rules-title {
  margin: 0 0 4px;
  font-weight: 600;
}
.rules ul {
  margin: 0;
  padding-left: 18px;
}
</style>
