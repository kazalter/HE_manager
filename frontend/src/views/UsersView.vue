<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { Pencil, Plus, RefreshCw, ShieldAlert, ShieldCheck, Trash2, Users } from 'lucide-vue-next'
import { API_BASE_URL } from '../config'
import { authState } from '../auth'
import type { User } from '../types'
import { EmptyState, PageHeader, UiBadge, UiButton, UiCard, UiIconButton, UiModal, controlClass, fieldHintClass, fieldLabelClass, listRowClass } from '../components/ui'

const users = ref<User[]>([])
const loading = ref(false)
const refreshSpinning = ref(false)
const showDialog = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const username = ref('')
const password = ref('')
const isAdmin = ref(false)
const isActive = ref(true)
const editingUser = ref<User | null>(null)

const fetchUsers = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await axios.get(`${API_BASE_URL}/users`)
    users.value = res.data
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || '读取用户失败'
  } finally {
    loading.value = false
  }
}

const onRefreshClick = () => {
  refreshSpinning.value = true
  window.setTimeout(() => { refreshSpinning.value = false }, 1000)
  fetchUsers()
}

const openDialog = (user?: User) => {
  if (user && typeof user === 'object' && 'id' in user) {
    editingUser.value = user
    username.value = user.username
    password.value = ''
    isAdmin.value = user.is_admin
    isActive.value = user.is_active
  } else {
    editingUser.value = null
    username.value = ''
    password.value = ''
    isAdmin.value = false
    isActive.value = true
  }
  errorMessage.value = ''
  showDialog.value = true
}

const closeDialog = () => {
  showDialog.value = false
}

const saveUser = async () => {
  if (!username.value.trim()) return
  if (!editingUser.value && !password.value) return
  saving.value = true
  errorMessage.value = ''
  try {
    if (editingUser.value) {
      await axios.put(`${API_BASE_URL}/users/${editingUser.value.id}`, {
        username: username.value.trim(),
        password: password.value || undefined,
        is_admin: isAdmin.value,
        is_active: isActive.value,
      })
    } else {
      await axios.post(`${API_BASE_URL}/users`, {
        username: username.value.trim(),
        password: password.value,
        is_admin: isAdmin.value,
      })
    }
    closeDialog()
    await fetchUsers()
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

const deleteUser = async (user: User) => {
  if (!confirm(`确定要删除用户 "${user.username}" 吗？`)) return
  try {
    await axios.delete(`${API_BASE_URL}/users/${user.id}`)
    await fetchUsers()
  } catch (err: any) {
    alert(err.response?.data?.detail || '删除失败')
  }
}

const initial = (name: string) => (name.trim()[0] || '?').toUpperCase()
const formatCreated = (value: string) => new Date(value).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })

onMounted(fetchUsers)
</script>

<template>
  <div class="min-h-full">
    <PageHeader title="用户管理" :count="authState.user?.is_admin ? `${users.length} 个用户` : undefined" description="管理可以登录网页端和安卓端的账号">
      <template #actions>
        <UiButton variant="secondary" class="pointer-coarse:h-11" :disabled="loading" @click="onRefreshClick">
          <template #icon><RefreshCw :size="16" :class="(loading || refreshSpinning) ? 'animate-spin' : ''" /></template>
          刷新
        </UiButton>
        <UiButton v-if="authState.user?.is_admin" variant="primary" class="pointer-coarse:h-11" @click="openDialog()">
          <template #icon><Plus :size="16" /></template>
          创建用户
        </UiButton>
      </template>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container">
        <div class="max-w-[960px]">
          <div v-if="!authState.user?.is_admin" role="alert" class="flex items-start gap-3 rounded-lg border border-warning/25 bg-warning/10 px-3.5 py-3 text-meta text-warning">
            <ShieldAlert :size="18" class="mt-0.5 shrink-0" aria-hidden="true" />
            <p><span class="font-medium text-ink">没有权限</span><br>当前账号不是管理员，不能管理用户。</p>
          </div>

          <template v-else>
            <p v-if="errorMessage && !showDialog" role="alert" class="mb-4 flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">{{ errorMessage }}</p>
            <UiCard padding="none" class="divide-y divide-line overflow-hidden">
              <div v-for="user in users" :key="user.id" :class="listRowClass">
                <div class="grid size-10 shrink-0 place-items-center rounded-full bg-surface-3 text-body font-medium text-muted" aria-hidden="true">{{ initial(user.username) }}</div>
                <div class="min-w-0 flex-1">
                  <p class="flex min-w-0 items-center gap-2">
                    <span class="truncate text-body font-medium text-ink">{{ user.username }}</span>
                    <span v-if="user.id === authState.user?.id" class="shrink-0 text-caption text-subtle">（你）</span>
                  </p>
                  <div class="mt-1 flex min-w-0 items-center gap-1.5 sm:mt-0.5">
                    <UiBadge v-if="user.is_admin" tone="accent" class="sm:hidden">管理员</UiBadge>
                    <UiBadge :tone="user.is_active ? 'success' : 'danger'" class="sm:hidden">{{ user.is_active ? '启用' : '停用' }}</UiBadge>
                    <p class="min-w-0 truncate text-meta text-subtle tabular-nums"><span class="hidden sm:inline">创建于 </span>{{ formatCreated(user.created_at) }}</p>
                  </div>
                </div>
                <div class="hidden shrink-0 items-center gap-1.5 sm:flex">
                  <UiBadge v-if="user.is_admin" tone="accent"><ShieldCheck :size="12" aria-hidden="true" />管理员</UiBadge>
                  <UiBadge :tone="user.is_active ? 'success' : 'danger'">{{ user.is_active ? '启用' : '停用' }}</UiBadge>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <UiIconButton :label="`编辑用户 ${user.username}`" @click="openDialog(user)"><Pencil :size="16" /></UiIconButton>
                  <UiIconButton
                    v-if="user.id !== authState.user?.id"
                    :label="`删除用户 ${user.username}`"
                    class="hover:!bg-danger/12 hover:!text-danger"
                    @click="deleteUser(user)"
                  ><Trash2 :size="16" /></UiIconButton>
                  <span v-else class="size-9 pointer-coarse:size-11" aria-hidden="true" />
                </div>
              </div>
              <EmptyState v-if="!users.length && !loading" compact :icon="Users" title="还没有用户" description="创建账号后即可登录网页端和安卓端。" />
            </UiCard>
          </template>
        </div>
      </div>
    </div>

    <UiModal
      v-model:open="showDialog"
      :title="editingUser ? '修改用户' : '创建用户'"
      :description="editingUser ? '修改账号属性或密码' : '新用户可登录手机 app 和网页端'"
      size="sm"
      :close-on-backdrop="false"
    >
      <form id="user-form" class="space-y-5" @submit.prevent="saveUser">
        <label class="block">
          <span :class="fieldLabelClass">用户名</span>
          <input v-model="username" autocomplete="username" :class="controlClass('md')" />
        </label>

        <label class="block">
          <span :class="fieldLabelClass">{{ editingUser ? '新密码' : '初始密码' }}</span>
          <input v-model="password" type="password" autocomplete="new-password" :class="controlClass('md')" />
          <p v-if="editingUser" :class="fieldHintClass">留空则保持原密码不变</p>
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="flex h-10 cursor-pointer items-center gap-2.5 rounded-lg border border-line bg-surface-2 px-3 transition-colors hover:border-line-strong">
            <input v-model="isAdmin" type="checkbox" class="size-4 rounded-sm accent-accent" />
            <span class="text-body text-ink">管理员</span>
          </label>
          <label class="flex h-10 cursor-pointer items-center gap-2.5 rounded-lg border border-line bg-surface-2 px-3 transition-colors hover:border-line-strong">
            <input v-model="isActive" type="checkbox" class="size-4 rounded-sm accent-accent" />
            <span class="text-body text-ink">启用账号</span>
          </label>
        </div>

        <p v-if="errorMessage" role="alert" class="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">
          {{ errorMessage }}
        </p>
      </form>
      <template #footer>
        <UiButton variant="ghost" @click="closeDialog">取消</UiButton>
        <UiButton variant="primary" type="submit" form="user-form" :loading="saving" :disabled="saving || !username.trim() || (!editingUser && !password)">
          {{ editingUser ? '保存' : '创建' }}
        </UiButton>
      </template>
    </UiModal>
  </div>
</template>
