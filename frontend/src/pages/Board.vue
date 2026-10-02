<template>
  <div>
    <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
      <h1 class="brand" style="margin:0">{{ week.label || ('第' + weekId + '周') }}</h1>
      <span class="chip" :class="{ coral: week.status === 'skipped' }">{{ week.status }}</span>
      <span class="muted">钉位相位 {{ week.start_phase ?? '—' }} → {{ week.end_phase ?? '—' }}</span>
    </div>
    <p class="muted">周卡片网格 · round-robin 落位后可去「对调」申请交换</p>
    <div style="display:flex;gap:8px;margin:12px 0">
      <router-link to="/" class="btn ghost" style="text-decoration:none">← 周表</router-link>
      <button @click="generate">从此周按视野生成</button>
      <button v-if="week.status === 'draft'" class="ghost" @click="skip">跳过本周</button>
      <button class="ghost" @click="load">刷新</button>
    </div>
    <p v-if="week.status === 'skipped'" class="muted">
      本周已跳过：不落任何格，但相位仍按整周格数推进，后续周节奏不断档。
    </p>
    <p v-if="err" class="err">{{ err }}</p>
    <div class="week-grid">
      <article v-for="d in days" :key="d" class="week-card">
        <header>Day {{ d }}</header>
        <div v-for="a in byDay(d)" :key="a.id">
          <span class="chip">{{ a.task_title }}</span>
          <span class="chip coral">{{ a.member_name }}</span>
        </div>
        <p v-if="!byDay(d).length" class="muted">空</p>
      </article>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted, watch } from 'vue'
import { api } from '../api'
const props = defineProps({ id: { type: [String, Number], required: true } })
const weekId = Number(props.id)
const assigns = ref([])
const week = ref({})
const days = [0,1,2,3,4,5,6]
const err = ref('')
function byDay(d) { return assigns.value.filter(a => a.day === d) }
async function load() {
  err.value = ''
  try {
    const b = await api('/weeks/' + weekId + '/board')
    week.value = b.week || {}
    assigns.value = b.assignments || []
  } catch (e) { err.value = e.message }
}
async function generate() {
  err.value = ''
  try { await api('/weeks/' + weekId + '/generate', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}
async function skip() {
  err.value = ''
  try { await api('/weeks/' + weekId + '/skip', { method: 'POST', body: '{}' }); await load() }
  catch (e) { err.value = e.message }
}
watch(() => props.id, load)
onMounted(load)
</script>
