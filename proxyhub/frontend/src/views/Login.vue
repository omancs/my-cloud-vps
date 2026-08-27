<template>
  <div class="login-wrap">
    <n-card class="login-card" :bordered="false">
      <div class="login-header">
        <div class="logo">🔗</div>
        <h1>ProxyHub</h1>
        <p>代理订阅管理平台</p>
      </div>
      <n-form @submit.prevent="handleLogin">
        <n-form-item label="用户名">
          <n-input v-model:value="form.username" placeholder="admin" size="large" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input
            v-model:value="form.password"
            type="password"
            placeholder="输入密码"
            size="large"
            show-password-on="click"
            @keyup.enter="handleLogin"
          />
        </n-form-item>
        <n-button
          type="primary"
          block
          size="large"
          :loading="loading"
          @click="handleLogin"
        >
          登 录
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NCard, NForm, NFormItem, NInput, NButton } from 'naive-ui'
import { useAuthStore } from '../store/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const form = ref({ username: 'admin', password: '' })
const loading = ref(false)

async function handleLogin() {
  if (!form.value.password) {
    message.warning('请输入密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.value.username, form.value.password)
    message.success('登录成功')
    router.push('/dashboard')
  } catch (e) {
    message.error(e.response?.data?.detail || '用户名或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.login-card {
  width: 400px;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.logo { font-size: 48px; margin-bottom: 12px; }
.login-header h1 { font-size: 28px; color: #1a1a2e; margin-bottom: 4px; }
.login-header p { color: #888; font-size: 14px; }
</style>
