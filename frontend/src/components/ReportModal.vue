<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as api from '../api'
import { languages } from '../locales'
import { clean } from '../locales/clean'
let relatedCache
function loadRelated() { return relatedCache || (relatedCache = fetch('/related.json').then(r => r.ok ? r.json() : null).catch(() => null)) }
const props = defineProps({ message: Object, title: String, source: { type: String, default: '' }, language: { type: String, default: 'ko' } })
const emit = defineEmits(['close'])
const lang = ref(props.message.language || props.language)
const cache = { [props.message.language || props.language]: { answer: props.message.response.answer, sources: props.message.response.sources || [] } }
const data = ref(cache[lang.value]), loading = ref(false), error = ref(false), note = ref('')
const c = computed(() => clean[lang.value] || clean.ko)
const related = ref(null)
onMounted(async () => { related.value = await loadRelated() })
const neighbors = computed(() => {
  if (!related.value) return []
  const out = [], used = new Set((data.value.sources || []).map(s => `${s.doc_id}|${s.section}`))
  for (const s of data.value.sources || []) {
    const arr = related.value[s.doc_id]; if (!arr) continue
    const i = arr.findIndex(x => x.s === s.section); if (i < 0) continue
    for (const [dir, j] of [['prev', i - 1], ['next', i + 1]]) {
      const n = arr[j]; if (!n) continue
      const key = `${s.doc_id}|${n.s}`
      if (used.has(key)) continue
      used.add(key)
      const text = n.t.startsWith(n.s) ? n.t.slice(n.s.length).trim() : n.t
      out.push({ key, dir, doc: s.title, section: n.s, text: text.slice(0, 110) + (text.length > 110 ? '…' : '') })
    }
  }
  return out.slice(0, 4)
})
const date = computed(() => new Date().toLocaleDateString({ ko: 'ko-KR', zh: 'zh-CN', vi: 'vi-VN', en: 'en-US', km: 'km-KH' }[lang.value] || 'ko-KR'))
async function choose(code) {
  lang.value = code; error.value = false; note.value = ''
  if (cache[code]) { data.value = cache[code]; return }
  loading.value = true
  try {
    const r = await api.ask({ question: props.message.question, topic: props.message.topic, product_id: null, language: code })
    cache[code] = { answer: r.answer, sources: r.sources || [] }
    if (lang.value === code) data.value = cache[code]
  } catch { if (lang.value === code) error.value = true }
  finally { if (lang.value === code) loading.value = false }
}
function print() { note.value = c.value.printHint; const old = document.title; document.title = `${props.title} - ${c.value.reportTitle}`; window.print(); document.title = old }
async function share() {
  const text = `${props.title} · ${c.value.reportTitle}\n${c.value.question}: ${props.message.question}\n\n${data.value.answer}\n\n${c.value.disclaimer}`
  try {
    if (navigator.share) { await navigator.share({ title: `${props.title} · ${c.value.reportTitle}`, text }); return }
    await navigator.clipboard.writeText(text); note.value = c.value.copied
  } catch {}
}
function key(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => { window.addEventListener('keydown', key); document.body.classList.add('report-open') })
onBeforeUnmount(() => { window.removeEventListener('keydown', key); document.body.classList.remove('report-open') })
</script>

<template>
  <Teleport to="body">
    <div class="report-overlay" role="dialog" aria-modal="true" :aria-label="c.reportTitle">
      <aside class="report-side">
        <button type="button" class="report-close" @click="emit('close')">← {{ c.back }}</button>
        <h2>{{ c.makeReport }}</h2>
        <div class="report-langs" role="group" :aria-label="c.lang"><span>{{ c.lang }}</span>
          <div><button v-for="(label, code) in languages" :key="code" type="button" :aria-pressed="lang === code" :class="{ on: lang === code }" :disabled="loading" @click="choose(code)">{{ label }}</button></div>
        </div>
        <div class="report-actions">
          <button type="button" class="report-main" :disabled="loading || error" @click="print">{{ c.pdf }}</button>
          <div><button type="button" :disabled="loading || error" @click="print">{{ c.print }}</button><button type="button" :disabled="loading || error" @click="share">{{ c.share }}</button></div>
          <p v-if="note" role="status">{{ note }}</p>
        </div>
      </aside>
      <main class="report-stage">
        <article class="report-sheet">
          <header><div><span>ChemBridge · {{ title }}</span><h1>{{ c.reportTitle }}</h1></div><time>{{ date }}</time></header>
          <p v-if="loading" class="report-state" role="status">{{ c.translating }}</p>
          <p v-else-if="error" class="report-state" role="alert">{{ c.failed }}</p>
          <template v-else>
            <section class="report-q"><b>{{ c.question }}</b><template v-if="lang !== (message.language || language)"> ({{ c.original }})</template> · {{ message.question }}</section>
            <section class="report-a"><h3>{{ c.answer }}</h3><p>{{ data.answer }}</p></section>
            <section v-if="neighbors.length" class="report-near">
              <h3>{{ c.nearTitle }}</h3>
              <ul><li v-for="n in neighbors" :key="n.key"><div><b>{{ n.doc }} · {{ n.section }}</b><p>{{ n.text }}</p></div></li></ul>
            </section>
            <footer>
              <div v-if="data.sources.length"><h3>{{ c.sources }}</h3><ul><li v-for="(s, i) in data.sources" :key="i">{{ s.title }}<template v-if="s.section"> · {{ s.section }}</template></li></ul></div>
              <small>{{ c.disclaimer }}</small>
            </footer>
          </template>
        </article>
      </main>
    </div>
  </Teleport>
</template>
