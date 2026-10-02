<template>
  <div>
    <h1 class="brand">设置</h1>
    <label>
      家庭名
      <input v-model="household" />
    </label>
    <label>
      视野周数（horizon_weeks，≥1 的整数）
      <input v-model.number="horizon" type="number" min="1" step="1" />
    </label>
    <p class="muted">一键生成时从锚定周起连续落这么多周；后一周相位紧接前一周末格。≤0 会被拒写。</p>
    <button @click="save">保存</button>
    <p v-if="msg" :class="msg.ok ? 'muted' : 'err'">{{ msg.text }}</p>
    <p class="muted" style="margin-top:16px">健康检查：{{ health }}</p>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const household = ref('')
const horizon = ref(1)
const health = ref('')
const msg = ref(null)
async function load() {
  const s = await api('/settings')
  household.value = s.household || ''
  horizon.value = s.horizon_weeks ? Number(s.horizon_weeks) : 1
  const h = await api('/health'); health.value = JSON.stringify(h)
}
async function save() {
  msg.value = null
  try {
    await api('/settings', {
      method: 'PUT',
      body: JSON.stringify({ household: household.value, horizon_weeks: horizon.value }),
    })
    msg.value = { ok: true, text: '已保存' }
  } catch (e) {
    msg.value = { ok: false, text: '保存被拒：' + e.message }
  }
}
onMounted(load)
</script>
