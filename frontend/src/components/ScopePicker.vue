<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'

const props = defineProps({ modelValue: { type: String, default: '' }, options: { type: Array, required: true }, label: { type: String, required: true }, disabled: Boolean })
const menuId = useId()
const emit = defineEmits(['update:modelValue'])
const codes = computed(() => props.options.map(option => option.value))
const trigger = ref(null), menu = ref(null), expanded = ref(false)
const position = ref({})
const selected = computed(() => props.options.find(option => option.value === props.modelValue)?.label || props.options[0]?.label)
function place() {
  const rect = trigger.value?.getBoundingClientRect()
  if (!rect) return
  const width = Math.min(Math.max(rect.width, 300), window.innerWidth - 24)
  const height = Math.min(menu.value?.getBoundingClientRect().height || codes.value.length * 43 + 12, Math.min(340, window.innerHeight - 24))
  const top = rect.bottom + 8 + height > window.innerHeight - 12 ? Math.max(12, rect.top - height - 8) : rect.bottom + 8
  position.value = { maxHeight: `${Math.min(340, window.innerHeight - 24)}px`, width: `${width}px`, left: `${Math.min(window.innerWidth - width - 12, Math.max(12, rect.right - width))}px`, top: `${top}px` }
}
async function open() {
  if (props.disabled) return
  expanded.value = true
  place()
  await nextTick()
  place()
  menu.value?.querySelectorAll('[role=option]')[Math.max(0, codes.value.indexOf(props.modelValue))]?.focus()
}
async function close(restore = true) {
  expanded.value = false
  if (restore) { await nextTick(); trigger.value?.focus() }
}
function choose(code) { if (!props.disabled) emit('update:modelValue', code); close() }
watch(() => props.disabled, value => { if (value) close(false) })
function keydown(event) {
  const options = [...menu.value.querySelectorAll('[role=option]')]
  const index = options.indexOf(document.activeElement)
  let next
  if (event.key === 'ArrowDown') next = (index + 1) % codes.value.length
  if (event.key === 'ArrowUp') next = (index - 1 + codes.value.length) % codes.value.length
  if (event.key === 'Home') next = 0
  if (event.key === 'End') next = codes.value.length - 1
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
defineExpose({ open })
</script>

<template>
  <button ref="trigger" type="button" class="glass-language-trigger scope-trigger" :aria-label="`${label}: ${selected}`" :disabled="disabled" :aria-controls="expanded ? menuId : undefined" aria-haspopup="listbox" :aria-expanded="expanded" @click="expanded ? close() : open()" @keydown.down.prevent="open" @keydown.up.prevent="open">
    <span>{{selected}}</span><svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="m3 4.5 3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" /></svg>
  </button>
  <Teleport to="body">
    <div v-if="expanded" ref="menu" class="glass-language-menu scope-menu" :id="menuId" role="listbox" :aria-label="label" :style="position" @keydown="keydown">
      <button v-for="option in options" :key="option.value" type="button" role="option" :aria-selected="modelValue===option.value" @click="choose(option.value)"><span>{{option.label}}</span><svg v-if="modelValue===option.value" width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m4 10 4 4 8-8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
    </div>
  </Teleport>
</template>

<style>
.scope-trigger { width:100%; min-height:54px; justify-content:space-between; border-radius:17px; font-size:16px; text-align:left; padding:13px 17px; backdrop-filter:blur(24px); -webkit-backdrop-filter:blur(24px); }
.scope-trigger>span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.scope-trigger:disabled { opacity:.5; cursor:default; }
.scope-menu button { font-size:15px; gap:14px; min-height:45px; }
.scope-menu button>svg { flex-shrink:0; }
</style>
