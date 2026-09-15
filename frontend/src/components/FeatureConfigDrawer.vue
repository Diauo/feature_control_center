<script setup lang="ts">
import { X } from '@lucide/vue'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import ModalDialog from '@/components/ModalDialog.vue'
import { ApiError, apiRequest } from '@/lib/api'
import { notify } from '@/lib/notify'
import { useSessionStore } from '@/stores/session'
import type { CustomerFeature } from '@/types'

interface ConfigField {
  key: string
  type: 'string' | 'text' | 'integer' | 'number' | 'boolean' | 'enum' | 'secret'
  label: string
  description: string
  required: boolean
  options?: Array<string | number>
  min?: number
  max?: number
  value?: unknown
  isSet?: boolean
}

const props = defineProps<{ featureId: string; featureName: string }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const session = useSessionStore()
const fields = ref<ConfigField[]>([])
const values = ref<Record<string, any>>({})
const clearSecrets = ref<string[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const complete = ref(false)
const maxRuntimeSeconds = ref<number | null>(null)
const reauthOpen = ref(false)
const password = ref('')
const reauthError = ref('')

let previousOverflow = ''
onMounted(() => {
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
  void load()
})
onBeforeUnmount(() => {
  document.body.style.overflow = previousOverflow
  document.removeEventListener('keydown', onKeydown)
})

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && !reauthOpen.value) requestClose()
}
function requestClose(): void { if (!busy.value) emit('close') }

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await apiRequest<{ fields: ConfigField[]; complete: boolean; maxRuntimeSeconds: number | null }>(`/api/customer-features/${props.featureId}/config`)
    fields.value = result.fields
    complete.value = result.complete
    maxRuntimeSeconds.value = result.maxRuntimeSeconds
    values.value = Object.fromEntries(result.fields.map((field) => [field.key, field.type === 'secret' ? '' : field.value]))
    clearSecrets.value = []
  } catch (reason) { error.value = readable(reason, '配置加载失败') }
  finally { loading.value = false }
}

async function save(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    const payload: Record<string, unknown> = {}
    for (const field of fields.value) {
      const value = values.value[field.key]
      if (field.type !== 'secret' || value !== '') payload[field.key] = value
    }
    const result = await apiRequest<{ fields: ConfigField[]; complete: boolean; maxRuntimeSeconds: number | null }>(`/api/customer-features/${props.featureId}/config`, {
      method: 'PUT', body: JSON.stringify({ values: payload, clearSecrets: clearSecrets.value }),
    })
    const normalizedMaximum = String(maxRuntimeSeconds.value ?? '').trim() === '' ? null : Number(maxRuntimeSeconds.value)
    const policy = await apiRequest<{ feature: CustomerFeature }>(`/api/admin/customer-features/${props.featureId}`, {
      method: 'PATCH', body: JSON.stringify({ maxRuntimeSeconds: normalizedMaximum }),
    })
    fields.value = result.fields
    complete.value = result.complete
    maxRuntimeSeconds.value = policy.feature.maxRuntimeSeconds
    values.value = Object.fromEntries(result.fields.map((field) => [field.key, field.type === 'secret' ? '' : field.value]))
    clearSecrets.value = []
    emit('saved')
    notify.success('配置已保存', { description: props.featureName })
  } catch (reason) {
    if (reason instanceof ApiError && reason.code === 'REAUTHENTICATION_REQUIRED') {
      password.value = ''; reauthError.value = ''; reauthOpen.value = true
    } else {
      error.value = readable(reason, '配置保存失败')
      notify.error('配置保存失败', { description: error.value })
    }
  } finally { busy.value = false }
}

async function confirmReauth(): Promise<void> {
  busy.value = true
  try { await session.reauthenticate(password.value); reauthOpen.value = false; busy.value = false; await save() }
  catch (reason) { reauthError.value = readable(reason, '密码验证失败') }
  finally { busy.value = false }
}

function readable(reason: unknown, fallback: string): string { return reason instanceof ApiError ? reason.message : fallback }
</script>

<template>
  <div class="drawer-layer" role="presentation" @mousedown.self="requestClose">
    <aside class="config-drawer" role="dialog" aria-modal="true" :aria-label="`${featureName} 配置管理`">
      <header class="config-drawer__header">
        <div><span>配置管理</span><h2>{{ featureName }}</h2><p>密钥只显示是否已设置，接口不会返回明文。</p></div>
        <button class="icon-button" type="button" aria-label="关闭配置" :disabled="busy" @click="requestClose"><X :size="19" /></button>
      </header>
      <div class="config-drawer__body">
        <p v-if="error" class="form-error page-error">{{ error }}</p>
        <div v-if="loading" class="loading-state">正在读取配置…</div>
        <form v-else id="feature-config-drawer" class="config-form config-form--single" @submit.prevent="save">
          <div class="config-state"><span>当前状态</span><span class="status-pill" :class="complete ? 'status-pill--on' : 'status-pill--warn'">{{ complete ? '配置完整' : '待补充' }}</span></div>
          <label v-for="field in fields" :key="field.key" class="field field--wide">
            <span>{{ field.label }} <small v-if="field.required">必填</small></span>
            <textarea v-if="field.type === 'text'" v-model="values[field.key]" :required="field.required" :minlength="field.min" :maxlength="field.max"></textarea>
            <select v-else-if="field.type === 'enum'" v-model="values[field.key]" :required="field.required"><option v-for="option in field.options" :key="String(option)" :value="option">{{ option }}</option></select>
            <span v-else-if="field.type === 'boolean'" class="toggle-field"><span><strong>{{ values[field.key] ? '已启用' : '未启用' }}</strong><small>{{ field.description }}</small></span><input v-model="values[field.key]" class="switch" type="checkbox" /></span>
            <template v-else-if="field.type === 'secret'"><input v-model="values[field.key]" type="password" autocomplete="new-password" :placeholder="field.isSet ? '已设置；留空保持不变' : '尚未设置'" /><small>{{ field.description || '平台不会显示已保存的密钥。' }}</small><label v-if="field.isSet" class="inline-check"><input v-model="clearSecrets" type="checkbox" :value="field.key" /> 清除已保存密钥</label></template>
            <input v-else-if="field.type === 'integer' || field.type === 'number'" v-model.number="values[field.key]" type="number" :step="field.type === 'integer' ? 1 : 'any'" :min="field.min" :max="field.max" :required="field.required" />
            <input v-else v-model="values[field.key]" type="text" :required="field.required" :minlength="field.min" :maxlength="field.max" />
            <small v-if="field.type !== 'boolean' && field.type !== 'secret'">{{ field.description }}</small>
          </label>
          <div v-if="fields.length === 0" class="empty-table field--wide">这个功能没有配置项。</div>
          <label class="field field--wide"><span>本功能最长运行时间（秒）</span><input v-model.number="maxRuntimeSeconds" type="number" min="1" max="2592000" placeholder="留空则使用系统默认" /><small>留空使用系统默认；停止按钮始终可用。</small></label>
        </form>
      </div>
      <footer class="config-drawer__footer"><button class="secondary-button" type="button" :disabled="busy" @click="requestClose">关闭</button><button class="primary-button" type="submit" form="feature-config-drawer" :disabled="busy || loading">{{ busy ? '正在保存…' : '保存配置' }}</button></footer>
    </aside>
    <ModalDialog :open="reauthOpen" title="再次验证身份" description="修改功能配置属于敏感操作。" width="small" :closeable="!busy" @close="reauthOpen = false"><form id="config-reauth" class="form-stack" @submit.prevent="confirmReauth"><label class="field"><span>当前密码</span><input v-model="password" type="password" autocomplete="current-password" required /></label><p v-if="reauthError" class="form-error">{{ reauthError }}</p></form><template #footer><button class="secondary-button" type="button" @click="reauthOpen = false">取消</button><button class="primary-button" type="submit" form="config-reauth" :disabled="busy">继续</button></template></ModalDialog>
  </div>
</template>
