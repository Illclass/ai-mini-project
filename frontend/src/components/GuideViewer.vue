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
// Remove only blank outer margins; preserve all visible document content.
function trimPage(canvas) {
  const ctx=canvas.getContext('2d'), {width,height}=canvas
  const pixels=ctx.getImageData(0,0,width,height).data
  let left=width,top=height,right=-1,bottom=-1
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=(y*width+x)*4
    if(Math.min(pixels[i],pixels[i+1],pixels[i+2])<230){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y)}
  }
  if(right<left)return canvas
  const margin=18
  left=Math.max(0,left-margin);top=Math.max(0,top-margin)
  right=Math.min(width-1,right+margin);bottom=Math.min(height-1,bottom+margin)
  const cropped=document.createElement('canvas')
  cropped.width=W*2;cropped.height=H*2
  const out=cropped.getContext('2d'),cw=right-left+1,ch=bottom-top+1
  const scale=Math.min(cropped.width/cw,cropped.height/ch)
  out.fillStyle='#fff';out.fillRect(0,0,cropped.width,cropped.height)
  out.drawImage(canvas,left,top,cw,ch,(cropped.width-cw*scale)/2,(cropped.height-ch*scale)/2,cw*scale,ch*scale)
  return cropped
}
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
      const scale = Math.min((W * 2) / base.width, (H * 2) / base.height)
      const viewport = page.getViewport({ scale })
      const canvas = document.createElement('canvas')
      canvas.width = W * 2; canvas.height = H * 2
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
      const dx = (canvas.width - viewport.width) / 2, dy = (canvas.height - viewport.height) / 2
      renderTask = page.render({ canvasContext: ctx, viewport, transform: [1, 0, 0, 1, dx, dy] })
      await renderTask.promise
      renderTask = null
      if (id !== token) return
      const cropped=trimPage(canvas)
      urls.push(cropped.toDataURL('image/jpeg', 0.95))
      if(cropped!==canvas)cropped.width=cropped.height=0
      canvas.width = canvas.height = 0; page.cleanup()
    }
    if (id !== token) return
    shown.value = urls.length
    state.value = 'ready'
    await nextTick()
    if (id !== token || !wrap.value) return
    const el = document.createElement('div')
    wrap.value.replaceChildren(el)
    flip = new PageFlip(el, { width: W, height: H, size: 'stretch', minWidth: W, maxWidth: 560, minHeight: 1, maxHeight: 792, autoSize: false, showCover: true, usePortrait: true, maxShadowOpacity: 0.35, mobileScrollSupport: false, flippingTime: 700 })
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
