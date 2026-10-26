<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as api from '../api'
import { languages } from '../locales'
import { clean } from '../locales/clean'
import { apiCopy } from '../locales/api'
import { createReportSession, reportLabels, reportText, sourceUrl } from '../api/report'
import { locateSource } from '../api/source-pages'
import { originalUrl } from '../api/source-assets'
import { sourceCopy } from '../locales/sources'
import { useDialog } from '../composables/useDialog'
const props = defineProps({ message: Object, title: String, scope: String, language: { type: String, default: 'ko' } })
const emit = defineEmits(['close', 'auth-expired'])
const original = JSON.parse(JSON.stringify(props.message))
const lang = ref(original.language || props.language)
const session = createReportSession(original, api.ask)
const data = ref(original.response), loading = ref(false), error = ref(false), note = ref(''), dialog = ref(null)
const c = computed(() => clean[lang.value] || clean.ko)
const labels = computed(() => reportLabels(original, lang.value))
const review = computed(() => data.value?.handoff ? apiCopy[lang.value].handoff : apiCopy[lang.value].answerNote)   // 보류와 참고용 안내를 구분
const date = new Date().toLocaleDateString()
let version = 0
useDialog(dialog, () => emit('close'))
async function choose(code) {
  const id = ++version
  lang.value = code; error.value = false; note.value = ''; loading.value = true
  try {
    const result = await session.choose(code)
    if (id === version && result) data.value = result
  } catch (failure) {
    if (id !== version) return
    if (failure.status === 401) { emit('auth-expired', original); return }
    if (failure.code !== 'CANCELLED') error.value = true
  } finally { if (id === version) loading.value = false }
}
function originalLink(source) {
 const target=locateSource(source)
 const url=target && originalUrl(target.file)
 return url ? `${url}#page=${target.page}&zoom=page-width` : null
}
function print() {
  note.value = c.value.printHint
  const old = document.title
  document.title = `${labels.value.title} - ${c.value.reportTitle}`
  try { window.print() } finally { document.title = old }
}
async function share() {
  const text = reportText(original, data.value, { ...c.value, review: review.value }, labels.value.scope)
  try {
    if (navigator.share) { await navigator.share({ title: c.value.reportTitle, text }); return }
    await navigator.clipboard.writeText(text); note.value = c.value.copied
  } catch (failure) { if (failure.name !== 'AbortError') note.value = c.value.shareFailed }
}
onMounted(() => document.body.classList.add('report-open'))
onBeforeUnmount(() => { version++; session.cancel(); document.body.classList.remove('report-open') })
</script>

<template>
  <Teleport to="body">
    <div ref="dialog" class="report-overlay" :lang="lang" role="dialog" aria-modal="true" :aria-label="c.reportTitle" tabindex="-1">
      <aside class="report-side">
        <button type="button" class="report-close" @click="emit('close')">← {{ c.back }}</button>
        <h2>{{ c.makeReport }}</h2>
        <div class="report-langs" role="group" :aria-label="c.lang"><span>{{ c.lang }}</span>
          <div><button v-for="(label, code) in languages" :key="code" type="button" :aria-pressed="lang === code" :class="{ on: lang === code }" @click="choose(code)">{{ label }}</button></div>
        </div>
        <p class="report-language-note">{{ c.regeneration }}</p>
        <div class="report-actions">
          <button type="button" class="report-main" :disabled="loading || error" @click="print">{{ c.pdf }}</button>
          <div><button type="button" :disabled="loading || error" @click="print">{{ c.print }}</button><button type="button" :disabled="loading || error" @click="share">{{ c.share }}</button></div>
          <p>{{ c.printHint }}</p><p v-if="note" role="status">{{ note }}</p>
        </div>
      </aside>
      <main class="report-stage">
        <article class="report-sheet" :lang="lang">
          <header><div><span>ChemBridge · {{ labels.title }}</span><h1>{{ c.reportTitle }}</h1></div><time>{{ date }}</time></header>
          <p v-if="loading" class="report-state" role="status">{{ c.translating }}</p>
          <div v-else-if="error" class="report-state" role="alert">{{ c.failed }} <button type="button" @click="choose(lang)">{{ c.retry }}</button></div>
          <template v-else>
            <p v-if="labels.scope" class="report-scope">{{ labels.scope }}</p>
            <p v-if="data.handoff || data.needs_review" class="report-review" role="alert">⚠ {{ review }}</p>
            <section class="report-q"><b>{{ c.question }}</b><template v-if="lang !== original.language"> ({{ c.original }})</template> · {{ original.question }}</section>
            <section class="report-a"><h3>{{ c.answer }}</h3><p>{{ data.answer }}</p></section>
            <footer>
              <div v-if="data.sources.length"><h3>{{ c.sources }}</h3><ol class="report-sources"><li v-for="(s, i) in data.sources" :key="i"><span>[{{ i + 1 }}] {{ s.title }}<template v-if="s.section"> · {{ s.section }}</template></span><a v-if="originalLink(s)" :href="originalLink(s)" target="_blank" rel="noopener noreferrer">{{ (sourceCopy[lang] || sourceCopy.ko).open }}</a><a v-if="sourceUrl(s.url)" :href="sourceUrl(s.url)" target="_blank" rel="noopener noreferrer">{{ sourceUrl(s.url) }}</a></li></ol></div>
              <small>{{ c.disclaimer }}</small>
            </footer>
          </template>
        </article>
      </main>
    </div>
  </Teleport>
</template>
