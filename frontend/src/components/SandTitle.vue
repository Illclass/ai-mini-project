<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({ text: { type: String, required: true } })
const heading = ref(null)
const textElement = ref(null)
const canvas = ref(null)
const settled = ref(false)
let frame, observer, disposed = false
const padding = 42
const noise = n => { const value = Math.sin(n * 127.1 + 311.7) * 43758.5453; return value - Math.floor(value) }

async function paint() {
  cancelAnimationFrame(frame)
  if (disposed || !heading.value) return
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  settled.value = reduced
  await nextTick()
  if (disposed || reduced || !canvas.value) return
  const bounds = heading.value.getBoundingClientRect()
  const width = Math.ceil(bounds.width + padding * 2)
  const height = Math.ceil(bounds.height + padding * 2)
  const sample = document.createElement('canvas')
  sample.width = width
  sample.height = height
  const context = sample.getContext('2d', { willReadFrequently: true })
  const output = canvas.value.getContext('2d')
  if (!context || !output) { settled.value = true; return }
  const style = getComputedStyle(textElement.value)
  const fontSize = parseFloat(style.fontSize)
  context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
  context.fillStyle = '#fff'
  context.textBaseline = 'alphabetic'
  // DOM ranges retain the actual wrapping and kerning of all three languages.
  const node = textElement.value.firstChild
  if (!node) { settled.value = true; return }
  const range = document.createRange()
  let offset = 0
  for (const char of props.text) {
    range.setStart(node, offset)
    offset += char.length
    range.setEnd(node, offset)
    const rect = range.getBoundingClientRect()
    if (char.trim()) context.fillText(char, rect.left - bounds.left + padding, rect.top - bounds.top + padding + (rect.height - fontSize) / 2 + fontSize * .84)
  }
  const pixels = context.getImageData(0, 0, width, height).data
  const points = []
  for (let y = 0; y < height; y += 3) {
    for (let x = 0; x < width; x += 3) {
      if (pixels[(y * width + x) * 4 + 3] < 90) continue
      const seed = x * 7 + y * 13
      points.push({ x, y, dx: -65 - noise(seed) * 65, dy: (noise(seed + 1) - .5) * 82, delay: x / width * 680 + noise(seed + 2) * 180, size: .65 + noise(seed + 3) * .65 })
    }
  }
  const dpr = Math.min(devicePixelRatio || 1, 2)
  canvas.value.width = Math.ceil(width * dpr)
  canvas.value.height = Math.ceil(height * dpr)
  output.setTransform(dpr, 0, 0, dpr, 0, 0)
  output.fillStyle = style.color
  let start
  function render(time) {
    start ??= time
    const elapsed = time - start
    output.clearRect(0, 0, width, height)
    const fade = Math.max(0, 1 - Math.max(0, elapsed - 1900) / 950)
    for (const point of points) {
      const progress = Math.max(0, Math.min(1, (elapsed - point.delay) / 1700))
      if (!progress) continue
      const remaining = Math.pow(1 - progress, 3)
      output.globalAlpha = Math.min(progress * 3, 1) * fade * .95
      output.fillRect(point.x + point.dx * remaining, point.y + point.dy * remaining, point.size, point.size)
    }
    if (elapsed > 1750) settled.value = true
    if (elapsed < 2900) frame = requestAnimationFrame(render)
    else output.clearRect(0, 0, width, height)
  }
  frame = requestAnimationFrame(render)
}
onMounted(() => {
  let lastWidth = 0
  observer = new ResizeObserver(([entry]) => {
    const width = Math.round(entry.contentRect.width)
    if (width !== lastWidth) { lastWidth = width; paint() }
  })
  observer.observe(heading.value)
})
watch(() => props.text, paint, { flush: 'post' })
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); cancelAnimationFrame(frame) })
</script>

<template>
  <h1 ref="heading" class="sand-title">
    <span ref="textElement" class="sand-title-text" :class="{ settled }">{{ text }}</span>
    <canvas ref="canvas" class="sand-title-particles" aria-hidden="true"></canvas>
  </h1>
</template>

<style scoped>
.sand-title { position: relative; }
.sand-title-text { opacity: 0; filter: blur(1px); transition: opacity 1s ease, filter 1s ease; }
.sand-title-text.settled { opacity: 1; filter: blur(0); }
.sand-title-particles { position: absolute; inset: -42px; width: calc(100% + 84px); height: calc(100% + 84px); pointer-events: none; }
@media (prefers-reduced-motion: reduce) { .sand-title-text { opacity: 1; filter: none; transition: none; } .sand-title-particles { display: none; } }
</style>
