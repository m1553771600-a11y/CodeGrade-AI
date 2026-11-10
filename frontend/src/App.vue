<template>
  <el-container class="app">
    <el-header class="app-header">
      <div class="brand">🧪 代码能力评测平台</div>
      <el-menu mode="horizontal" :default-active="$route.name" router class="nav">
        <el-menu-item index="upload" route="/">提交评审</el-menu-item>
        <el-menu-item index="history" route="/history">历史记录</el-menu-item>
        <el-menu-item index="profile" route="/profile">能力画像</el-menu-item>
      </el-menu>
      <div class="auth-box">
        <el-button v-if="!isAuthed" text @click="$router.push('/login')">登录</el-button>
        <el-button v-else text @click="logout">退出</el-button>
      </div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getToken, clearToken } from './api'

const route = useRoute()
const router = useRouter()
const isAuthed = ref(false)

watch(() => route.fullPath, () => { isAuthed.value = !!getToken() }, { immediate: true })

function logout() {
  clearToken()
  router.push('/login')
}
</script>

<style>
body {
  margin: 0;
  background: #f5f7fa;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.app-header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}
.brand {
  font-weight: 600;
  font-size: 18px;
  margin-right: 40px;
  white-space: nowrap;
}
.nav {
  flex: 1;
  border-bottom: none;
}
.auth-box {
  margin-left: auto;
}
</style>
