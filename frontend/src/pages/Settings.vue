<template>
  <div>
    <h1 class="brand">设置</h1>
    <label>家庭名 <input v-model="household" /></label>
    <label style="display:block;margin-top:12px">
      生成视野（周数，≥1）
      <input v-model="horizon" type="number" min="1" step="1" style="width:6em" />
    </label>
    <p class="muted">一次「生成周表」会按视野连续生成多周，跨周相位首尾相接。</p>
    <button @click="save">保存</button>
    <p v-if="err" class="err">{{ err }}</p>
    <p v-if="ok" class="muted">已保存</p>
    <p class="muted" style="margin-top:16px">健康检查：{{ health }}</p>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const household = ref('')
const horizon = ref(1)
const health = ref('')
const err = ref('')
const ok = ref(false)
async function load() {
  const s = await api('/settings'); household.value = s.household || ''
  horizon.value = Number(s.horizon_weeks) || 1
  const h = await api('/health'); health.value = JSON.stringify(h)
}
async function save() {
  err.value = ''; ok.value = false
  try {
    await api('/settings', { method: 'PUT', body: JSON.stringify({ household: household.value, horizon_weeks: Number(horizon.value) }) })
    ok.value = true
  } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
