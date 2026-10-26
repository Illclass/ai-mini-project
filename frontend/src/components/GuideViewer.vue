<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { PageFlip } from 'page-flip'
import { clean } from '../locales/clean'
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl
const props = defineProps({ src: String, title: String, source: { type: String, default: 'KOSHA GUIDE' }, language: { type: String, default: 'ko' } })
const c = computed(() => clean[props.language] || clean.ko)
const wrap = ref(null), state = ref('loading'), current = ref(0), total = ref(0), shown = ref(0)
const W = 460, H = 651
let flip = null, token = 0, loadingTask = null, renderTask = null
function destroy() { try { flip?.destroy() } catch {} flip = null; wrap.value?.replaceChildren() }
function cancelPdf() { renderTask?.cancel(); renderTask = null; loadingTask?.destroy().catch(() => {}); loadingTask = null }
async function load() {
  const id = ++token
  state.value = 'loading'; current.value = 0; destroy(); cancelPdf()
  let task
  try {
    task = loadingTask = pdfjs.getDocument(props.src)
    const pdf = await task.promise
    if (id !== token) return
    total.value = pdf.numPages
    const count = pdf.numPages, urls = []
    for (let i = 1; i <= count; i++) {
      const page = await pdf.getPage(i)
      const base = page.getViewport({ scale: 1 })
      const scale = Math.min((W * 1.5) / base.width, (H * 1.5) / base.height)
      const viewport = page.getViewport({ scale })
      const canvas = document.createElement('canvas')
      canvas.width = W * 1.5; canvas.height = H * 1.5
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
      const dx = (canvas.width - viewport.width) / 2, dy = (canvas.height - viewport.height) / 2
      renderTask = page.render({ canvasContext: ctx, viewport, transform: [1, 0, 0, 1, dx, dy] })
      await renderTask.promise
      renderTask = null
      if (id !== token) return
      urls.push(canvas.toDataURL('image/jpeg', 0.85))
      canvas.width = canvas.height = 0; page.cleanup()
    }
    if (id !== token) return
    shown.value = urls.length
    state.value = 'ready'
    await nextTick()
    if (id !== token || !wrap.value) return
    const el = document.createElement('div')
    wrap.value.replaceChildren(el)
    flip = new PageFlip(el, { width: W, height: H, size: 'stretch', minWidth: 240, maxWidth: 560, minHeight: 340, maxHeight: 792, showCover: true, usePortrait: true, maxShadowOpacity: 0.35, mobileScrollSupport: false, flippingTime: 700 })
    flip.loadFromImages(urls)
    flip.on('flip', e => { current.value = e.data })
  } catch (e) { if (id === token) state.value = 'error' }
  finally { if (loadingTask === task) loadingTask = null; await task?.destroy().catch(() => {}) }
}
onMounted(load)
watch(() => props.src, load)
onBeforeUnmount(() => { token++; cancelPdf(); destroy() })
const label = computed(() => state.value === 'ready' ? `${Math.min(current.value + 1, shown.value)} / ${total.value}` : '')
const progress = computed(() => shown.value > 1 ? Math.round(current.value / (shown.value - 1) * 100) : 0)
</script>

<template>
  <section class="guide-viewer" :aria-label="c.guide">
    <header class="guide-head"><div><span class="guide-eyebrow">{{ c.guide }} · {{ source }}</span><b>{{ title }}</b><small>{{ c.originalKo }}</small></div><span class="guide-page">{{ label }}</span></header>
    <div class="guide-stage">
      <div ref="wrap" class="guide-book" :class="{ hidden: state !== 'ready' }"></div>
      <p v-if="state === 'loading'" class="guide-state" role="status">{{ c.loading }}</p>
      <p v-else-if="state === 'error'" class="guide-state" role="alert">{{ c.loadFail }} <button type="button" @click="load">{{ c.retry }}</button></p>
    </div>
    <div class="guide-controls">
      <button type="button" :aria-label="c.prev" :disabled="state !== 'ready' || current === 0" @click="flip?.flipPrev()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>
      <div class="guide-bar" aria-hidden="true"><i :style="{ width: progress + '%' }"></i></div>
      <button type="button" :aria-label="c.next" :disabled="state !== 'ready' || current >= shown - 1" @click="flip?.flipNext()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button>
    </div>
  </section>
</template>
