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
const W = 460, H = 651, MAX = 40
let flip = null, token = 0
function destroy() { try { flip?.destroy() } catch {} flip = null; wrap.value?.replaceChildren() }
async function load() {
  const id = ++token
  state.value = 'loading'; current.value = 0; destroy()
  try {
    const pdf = await pdfjs.getDocument(props.src).promise
    total.value = pdf.numPages
    const count = Math.min(pdf.numPages, MAX), urls = []
    for (let i = 1; i <= count; i++) {
      const page = await pdf.getPage(i)
      const base = page.getViewport({ scale: 1 })
      const scale = Math.min((W * 2) / base.width, (H * 2) / base.height)
      const viewport = page.getViewport({ scale })
      const canvas = document.createElement('canvas')
      canvas.width = W * 2; canvas.height = H * 2
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
      const dx = (canvas.width - viewport.width) / 2, dy = (canvas.height - viewport.height) / 2
      await page.render({ canvasContext: ctx, viewport, transform: [1, 0, 0, 1, dx, dy] }).promise
      if (id !== token) return
      urls.push(canvas.toDataURL('image/jpeg', 0.85))
    }
    if (id !== token) return
    shown.value = urls.length
    state.value = 'ready'
    await nextTick()
    const el = document.createElement('div')
    wrap.value.replaceChildren(el)
    flip = new PageFlip(el, { width: W, height: H, size: 'stretch', minWidth: 400, maxWidth: 560, minHeight: 566, maxHeight: 792, showCover: true, usePortrait: true, maxShadowOpacity: 0.35, mobileScrollSupport: false, flippingTime: 700 })
    flip.loadFromImages(urls)
    flip.on('flip', e => { current.value = e.data })
  } catch (e) { if (id === token) state.value = 'error' }
}
onMounted(load)
watch(() => props.src, load)
onBeforeUnmount(() => { token++; destroy() })
const label = computed(() => state.value === 'ready' ? `${Math.min(current.value + 1, shown.value)} / ${total.value}` : '')
const progress = computed(() => shown.value > 1 ? Math.round(current.value / (shown.value - 1) * 100) : 0)
</script>

<template>
  <section class="guide-viewer" :aria-label="c.guide">
    <header class="guide-head"><div><span class="guide-eyebrow">{{ c.guide }} · {{ source }}</span><b>{{ title }}</b></div><span class="guide-page">{{ label }}</span></header>
    <div class="guide-stage">
      <div ref="wrap" class="guide-book" :class="{ hidden: state !== 'ready' }"></div>
      <p v-if="state === 'loading'" class="guide-state" role="status">{{ c.loading }}</p>
      <p v-else-if="state === 'error'" class="guide-state" role="alert">{{ c.loadFail }}</p>
    </div>
    <div class="guide-controls">
      <button type="button" :aria-label="c.prev" :disabled="state !== 'ready'" @click="flip?.flipPrev()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>
      <div class="guide-bar" aria-hidden="true"><i :style="{ width: progress + '%' }"></i></div>
      <button type="button" :aria-label="c.next" :disabled="state !== 'ready'" @click="flip?.flipNext()"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button>
    </div>
  </section>
</template>
