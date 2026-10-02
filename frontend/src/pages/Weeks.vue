<template>
  <div>
    <h1 class="brand">周表</h1>
    <p class="muted">
      当前视野 {{ horizon }} 周 · 一键从第1周起连续生成；每周起止相位与格位落库即钉住，
      只改视野长度不会重排已生成周。skipped 周不落格但相位照常推进。
    </p>
    <div style="display:flex;gap:8px;margin:12px 0">
      <button @click="generate">按视野连续生成</button>
      <button class="ghost" @click="load">刷新</button>
    </div>
    <p v-if="err" class="err">{{ err }}</p>
    <ul class="list">
      <li v-for="w in weeks" :key="w.id" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <router-link :to="'/weeks/' + w.id" style="font-weight:600;min-width:64px">
          {{ w.label || ('第' + w.id + '周') }}
        </router-link>
        <span class="chip" :class="{ coral: w.status === 'skipped' }">{{ w.status }}</span>
        <span class="muted">
          相位 {{ w.start_phase ?? '—' }} → {{ w.end_phase ?? '—' }} · 格位 {{ w.assignment_count }}
        </span>
        <span style="flex:1"></span>
        <button v-if="w.status === 'draft'" class="ghost" @click="skip(w.id)">跳过本周</button>
        <button v-else-if="w.status === 'skipped'" class="ghost" @click="unskip(w.id)">恢复</button>
      </li>
    </ul>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
const weeks = ref([])
const horizon = ref(1)
const err = ref('')
async function load() {
  err.value = ''
  try {
    weeks.value = await api('/weeks')
    const s = await api('/settings')
    horizon.value = s.horizon_weeks || 1
  } catch (e) { err.value = e.message }
}
async function generate() {
  err.value = ''
  try { await api('/weeks/1/generate', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}
async function skip(id) {
  err.value = ''
  try { await api('/weeks/' + id + '/skip', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}
async function unskip(id) {
  err.value = ''
  try { await api('/weeks/' + id + '/unskip', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}
onMounted(load)
</script>
