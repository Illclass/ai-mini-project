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
const stage=ref(null), zoom=ref(1), pageImages=ref([]), stageSize=ref({width:460,height:651})
const W = 460, H = 651
const zoomSize=computed(()=>{const scale=Math.min(stageSize.value.width/W,stageSize.value.height/H)*zoom.value;return {width:`${W*scale}px`,height:`${H*scale}px`}})
let resizeObserver
function changeZoom(value){zoom.value=Math.max(1,Math.min(3,Math.round(value*100)/100))}
function turn(direction){if(zoom.value>1)flip?.turnToPage(current.value+direction);else if(direction>0)flip?.flipNext();else flip?.flipPrev()}
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
  state.value = 'loading'; current.value = 0; zoom.value=1; pageImages.value=[]; destroy(); cancelPdf()
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
    pageImages.value=urls
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
onMounted(()=>{
  resizeObserver=new ResizeObserver(entries=>{const {width,height}=entries[0].contentRect;stageSize.value={width,height}})
  if(stage.value)resizeObserver.observe(stage.value)
  load()
})
watch(() => props.src, load)
onBeforeUnmount(() => { resizeObserver?.disconnect(); token++; cancelPdf(); destroy() })
const label = computed(() => state.value === 'ready' ? `${Math.min(current.value + 1, shown.value)} / ${total.value}` : '')
const progress = computed(() => shown.value > 1 ? Math.round(current.value / (shown.value - 1) * 100) : 0)
</script>

<template>
  <section class="guide-viewer" :aria-label="c.guide">
    <header class="guide-head"><div><span class="guide-eyebrow">{{ c.guide }} · {{ source }}</span><b>{{ title }}</b><small>{{ c.originalKo }}</small></div><span class="guide-page">{{ label }}</span></header>
    <div ref="stage" class="guide-stage">
      <div v-if="state==='ready' && zoom>1" class="guide-zoom-viewport" tabindex="0" :aria-label="c.zoomIn"><div class="guide-zoom-sheet" :style="{minWidth:zoomSize.width,minHeight:zoomSize.height}"><img :src="pageImages[current]" :alt="`${title} · ${current+1} / ${total}`" :style="zoomSize" draggable="false" /></div></div>
      <div ref="wrap" class="guide-book" :class="{ hidden: state !== 'ready', 'is-zoomed':zoom>1 }"></div>
      <p v-if="state === 'loading'" class="guide-state" role="status">{{ c.loading }}</p>
      <p v-else-if="state === 'error'" class="guide-state" role="alert">{{ c.loadFail }} <button type="button" @click="load">{{ c.retry }}</button></p>
    </div>
    <div class="guide-zoom-controls" role="group" :aria-label="c.zoomIn">
      <button type="button" :disabled="state!=='ready'||zoom<=1" :aria-label="c.zoomOut" :title="c.zoomOut" @click="changeZoom(zoom-.25)"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6M7 10h6"/></svg></button>
      <button type="button" class="guide-zoom-fit" :disabled="state!=='ready'" :aria-label="c.fitPage" :title="c.fitPage" @click="changeZoom(1)">{{Math.round(zoom*100)}}%</button>
      <button type="button" :disabled="state!=='ready'||zoom>=3" :aria-label="c.zoomIn" :title="c.zoomIn" @click="changeZoom(zoom+.25)"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6M7 10h6M10 7v6"/></svg></button>
    </div>
    <div class="guide-controls">
      <button type="button" :aria-label="c.prev" :disabled="state !== 'ready' || current === 0" @click="turn(-1)"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>
      <div class="guide-bar" aria-hidden="true"><i :style="{ width: progress + '%' }"></i></div>
      <button type="button" :aria-label="c.next" :disabled="state !== 'ready' || current >= shown - 1" @click="turn(1)"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button>
    </div>
  </section>
</template>
