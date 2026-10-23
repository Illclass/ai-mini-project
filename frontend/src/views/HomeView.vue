<script setup>
import { computed } from 'vue'
import Icon from '../components/Icon.vue'
import { copy } from '../locales'
import { spring as vSpring } from '../directives/spring'
import '../home-glass.css'

const props = defineProps({ language: { type: String, default: 'ko' } })
const emit = defineEmits(['update:language', 'open', 'logout'])
const t = computed(() => copy[props.language])
const situations = [
  { key: 'before', icon: 'check' },
  { key: 'handling', icon: 'flask' },
  { key: 'storage', icon: 'box' },
  { key: 'during', icon: 'activity' },
  { key: 'after', icon: 'tidy' },
  { key: 'emergency', icon: 'alert' },
]
function reflect(event) {
  if (event.pointerType === 'touch') return
  const card = event.currentTarget
  const bounds = card.getBoundingClientRect()
  card.style.setProperty('--highlight-x', `${(event.clientX - bounds.left) / bounds.width * 100}%`)
  card.style.setProperty('--highlight-y', `${(event.clientY - bounds.top) / bounds.height * 100}%`)
}
function reset(event) {
  event.currentTarget.style.removeProperty('--highlight-x')
  event.currentTarget.style.removeProperty('--highlight-y')
}
</script>

<template>
  <div class="glass-home">
    <main class="glass-home-main">
      <h1 class="sand-title"><span class="sand-title-text settled">{{ t.homeTitle.replace('\n', ' ') }}</span></h1>
      <p class="clean-home-sub">{{ t.homeDesc }}</p>
      <div class="glass-situation-grid" :aria-label="t.situations">
        <button
          v-for="(item, i) in situations" :key="item.key" v-spring
          class="glass-situation" :class="`situation-${item.key}`"
          @pointermove="reflect" @pointerleave="reset" @click="emit('open', item.key)"
        >
          <span class="home-tile-symbol"><Icon :name="item.icon" :size="31" /></span>
          <span class="home-tile-title">{{ t.topicTitles[i] }}</span>
          <span class="home-tile-sub">{{ t.topicSubs[i] }}</span>
          <span class="home-tile-arrow"><Icon name="arrow" :size="20" /></span>
        </button>
      </div>
      <button v-spring class="home-free-question" @click="emit('open', 'free')"><Icon name="chat" :size="21" /><span>{{ t.free }}</span><Icon name="arrow" :size="18" /></button>
    </main>
  </div>
</template>
