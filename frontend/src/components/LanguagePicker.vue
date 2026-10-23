<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { languages } from '../locales'
import Icon from './Icon.vue'

const props = defineProps({ modelValue: { type: String, default: 'ko' } })
const emit = defineEmits(['update:modelValue'])
const codes = Object.keys(languages)
const trigger = ref(null), menu = ref(null), expanded = ref(false)
const position = ref({})
const label = computed(() => languages[props.modelValue] || languages.ko)
function place() {
  const rect = trigger.value?.getBoundingClientRect()
  if (!rect) return
  const width = Math.min(184, window.innerWidth - 24)
  position.value = { width: `${width}px`, left: `${Math.min(window.innerWidth - width - 12, Math.max(12, rect.right - width))}px`, top: `${rect.bottom + 8 + 160 > window.innerHeight ? Math.max(12, rect.top - 164) : rect.bottom + 8}px` }
}
async function open() {
  expanded.value = true
  place()
  await nextTick()
  menu.value?.querySelectorAll('[role=option]')[Math.max(0, codes.indexOf(props.modelValue))]?.focus()
}
async function close(restore = true) {
  expanded.value = false
  if (restore) { await nextTick(); trigger.value?.focus() }
}
function choose(code) { emit('update:modelValue', code); close() }
function keydown(event) {
  const options = [...menu.value.querySelectorAll('[role=option]')]
  const index = options.indexOf(document.activeElement)
  let next
  if (event.key === 'ArrowDown') next = (index + 1) % codes.length
  if (event.key === 'ArrowUp') next = (index - 1 + codes.length) % codes.length
  if (event.key === 'Home') next = 0
  if (event.key === 'End') next = codes.length - 1
  if (next !== undefined) { event.preventDefault(); options[next].focus() }
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close() }
  if (event.key === 'Tab') close(false)
}
function outside(event) {
  if (expanded.value && !trigger.value?.contains(event.target) && !menu.value?.contains(event.target)) close(false)
}
function reflow(event) {
  if (event?.target && menu.value?.contains(event.target)) return
  if (expanded.value) place()
}
onMounted(() => { document.addEventListener('pointerdown', outside); window.addEventListener('resize', reflow); window.addEventListener('scroll', reflow, true) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', reflow); window.removeEventListener('scroll', reflow, true) })
</script>

<template>
  <button ref="trigger" type="button" class="glass-language-trigger" aria-label="Language" aria-haspopup="listbox" :aria-expanded="expanded" @click="expanded ? close() : open()" @keydown.down.prevent="open" @keydown.up.prevent="open">
    <Icon name="globe" :size="17" /><span>{{label}}</span><svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="m3 4.5 3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" /></svg>
  </button>
  <Teleport to="body">
    <div v-if="expanded" ref="menu" class="glass-language-menu" role="listbox" aria-label="Language" :style="position" @keydown="keydown">
      <button v-for="code in codes" :key="code" type="button" role="option" :lang="code" :aria-selected="modelValue===code" @click="choose(code)"><span>{{languages[code]}}</span><svg v-if="modelValue===code" width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m4 10 4 4 8-8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
    </div>
  </Teleport>
</template>

<style>
.glass-language-trigger { display: inline-flex; align-items: center; justify-content: center; gap: 9px; padding: 10px 14px; min-height: 41px; border: 1px solid #ffffff40; border-radius: 999px; color: #fff; background: linear-gradient(140deg, #ffffff12, #ffffff03); box-shadow: inset 0 1px 1px #ffffff59, 0 3px 10px #1e2b4512; font-size: 13px; font-weight: 500; cursor: pointer; }
.glass-language-trigger>span { min-width: 43px; }
.glass-language-trigger>svg:last-child { margin-left: 2px; transition: transform .2s; }
.glass-language-trigger[aria-expanded=true]>svg:last-child { transform: rotate(180deg); }
.glass-language-trigger:hover { background: #ffffff17; }
.glass-language-trigger:focus-visible { outline: 2px solid #a9c8ef; outline-offset: 4px; }
.glass-language-menu { position: fixed; z-index: 100; padding: 6px; border: 1px solid #ffffff38; border-radius: 17px; background: linear-gradient(145deg, #354363e8, #29324bd9); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); box-shadow: inset 0 1px 1px #ffffff47, 0 12px 32px #111b3d33; }
.glass-language-menu button { display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 43px; padding: 10px 12px; border: 0; border-radius: 11px; background: transparent; color: #fff; font: inherit; font-size: 14px; text-align: left; cursor: pointer; }
.glass-language-menu button:hover, .glass-language-menu button:focus-visible { outline: none; background: #ffffff1a; }
.glass-language-menu button[aria-selected=true] { background: #ffffff12; }
@media (max-width: 600px) { .glass-language-trigger { gap: 7px; min-height: 37px; padding: 9px 11px; font-size: 12px; } }
@media (prefers-reduced-transparency: reduce) { .glass-language-menu { background: #303b56; backdrop-filter: none; -webkit-backdrop-filter: none; } }
@media (prefers-reduced-motion: reduce) { .glass-language-trigger>svg { transition: none; } }
</style>
