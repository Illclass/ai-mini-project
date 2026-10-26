<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { useDialog } from '../composables/useDialog'
import { originalUrl } from '../api/source-assets'
import { sourceCopy } from '../locales/sources'
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl
const props = defineProps({ selection: { type: Object, required: true }, language: { type: String, default: 'ko' } })
const emit = defineEmits(['close'])
const dialog = ref(null), canvas = ref(null), paper = ref(null), state = ref('loading')
const page = ref(props.selection.target.page), selected = ref(props.selection.target.sectionNo)
const c = computed(() => sourceCopy[props.language] || sourceCopy.ko)
const target = computed(() => props.selection.target)
const url = computed(() => originalUrl(target.value.file))
const pageUrl = computed(() => url.value ? `${url.value}#page=${page.value}&zoom=page-width` : null)
let loadingTask, pdf, rendering, version = 0, disposed = false
useDialog(dialog, () => emit('close'))
async function render() {
 const id = ++version
 rendering?.cancel(); state.value='loading'
 try {
  const p = await pdf.getPage(page.value)
  if (disposed || id !== version) return
  const base = p.getViewport({scale:1})
  const viewport = p.getViewport({scale:Math.min(2, 1350/base.width)})
  canvas.value.width=viewport.width; canvas.value.height=viewport.height
  rendering=p.render({canvasContext:canvas.value.getContext('2d'),viewport})
  await rendering.promise
  if (disposed || id !== version) return
  rendering=null
  let sectionY=0
  // Keep the complete page, but scroll to its actual section heading when found.
  // PDF text positions are used only for navigation, never as answer evidence.
  if (selected.value) {
   try {
    const text=await p.getTextContent(), rows=new Map()
    for(const item of text.items) {
     if(!item.str || !item.transform)continue
     const y=Math.round(item.transform[5]*2)/2
     rows.set(y,`${rows.get(y)||''} ${item.str}`)
    }
    const heading=props.selection.targets.find(t=>t.sectionNo===selected.value)?.heading.replace(/\s+/g,'')
    for(const [y,line] of rows)if(heading && line.replace(/\s+/g,'').startsWith(heading)) {
     sectionY=Math.max(0,viewport.convertToViewportPoint(0,y)[1]-viewport.scale*22);break
    }
   } catch { /* The page remains available if its text layer is unavailable. */ }
  }
  if(disposed || id!==version)return
  state.value='ready';p.cleanup()
  await nextTick()
  if(!disposed && id===version)paper.value?.scrollTo({top:sectionY*(canvas.value.clientWidth/canvas.value.width)})
 } catch { if (!disposed && id===version) state.value='error' }
}
async function load() {
 state.value='loading'
 try {
  if (!url.value) throw new Error('Missing original')
  loadingTask=pdfjs.getDocument(url.value);pdf=await loadingTask.promise
  if (!disposed) await render()
 } catch { if (!disposed) state.value='error' }
}
function choose(item) { selected.value=item.sectionNo; if(page.value===item.page) render();else page.value=item.page }
function move(offset) { selected.value=null;page.value+=offset }
function retry() { if(pdf)render();else{loadingTask?.destroy().catch(()=>{});load()} }
watch(page,()=>{if(pdf)render()})
onMounted(load)
onBeforeUnmount(()=>{disposed=true;version++;rendering?.cancel();loadingTask?.destroy().catch(()=>{})})
</script>
<template>
 <Teleport to="body">
  <div class="source-overlay" @click.self="emit('close')">
   <section ref="dialog" class="source-viewer" role="dialog" aria-modal="true" :aria-label="`${c.original} · ${target.title}`" tabindex="-1" :lang="language">
    <header class="source-viewer-heading"><div><span>{{c.original}}</span><h2>{{target.title}}</h2></div><button type="button" class="source-close" @click="emit('close')">{{c.close}} ✕</button></header>
    <nav class="source-viewer-sections" :aria-label="c.section"><button v-for="item in selection.targets" :key="item.sectionNo" type="button" :aria-pressed="selected===item.sectionNo" @click="choose(item)">{{item.section}}</button></nav>
    <p class="source-original-note">{{c.note}}</p>
    <div ref="paper" class="source-paper" :aria-busy="state==='loading'">
     <p v-if="state==='loading'" role="status">{{c.loading}}</p>
     <div v-if="state==='error'" role="alert">{{c.failed}} <button type="button" @click="retry">{{c.retry}}</button></div>
     <canvas ref="canvas" v-show="state==='ready'" :aria-label="`${target.title} · ${c.page} ${page}`" role="img"></canvas>
    </div>
    <footer class="source-viewer-controls"><button type="button" :disabled="page<=1" @click="move(-1)">← {{c.prev}}</button><span aria-live="polite">{{c.page}} {{page}} / {{target.pageCount}}</span><button type="button" :disabled="page>=target.pageCount" @click="move(1)">{{c.next}} →</button><a v-if="pageUrl" :href="pageUrl" target="_blank" rel="noopener noreferrer">{{c.open}} ↗</a><a v-if="selection.publisher" :href="selection.publisher" target="_blank" rel="noopener noreferrer">{{c.publisher}} ↗</a></footer>
   </section>
  </div>
 </Teleport>
</template>
