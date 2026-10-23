<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { copy } from '../locales'
import LanguagePicker from '../components/LanguagePicker.vue'
import { spring as vSpring } from '../directives/spring'
import '../login-glass.css'

const props = defineProps({ language: { type: String, default: 'ko' }, loading: Boolean })
const emit = defineEmits(['update:language', 'submit'])
const t = computed(() => copy[props.language])
const username = ref('')
const password = ref('')
const visible = ref(false)
const glass = ref(null)
let frame
function reflect(event) {
  if (event.pointerType === 'touch') return
  const bounds = event.currentTarget.getBoundingClientRect()
  const x = ((event.clientX - bounds.left) / bounds.width) * 100
  const y = ((event.clientY - bounds.top) / bounds.height) * 100
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    glass.value?.style.setProperty('--light-x', `${x}%`)
    glass.value?.style.setProperty('--light-y', `${y}%`)
  })
}
function resetLight() {
  cancelAnimationFrame(frame)
  glass.value?.style.removeProperty('--light-x')
  glass.value?.style.removeProperty('--light-y')
}
function submit() {
  if (props.loading) return
  emit('submit')
  password.value = ''
}
onBeforeUnmount(() => cancelAnimationFrame(frame))
</script>

<template>
  <div class="liquid-login">
    <div class="liquid-landscape" aria-hidden="true">
      <div class="landscape-grain"></div>
    </div>



    <main class="liquid-main">
      <section class="liquid-form-area">
        <div ref="glass" class="liquid-card" @pointermove="reflect" @pointerleave="resetLight">
          <div class="card-specular" aria-hidden="true"></div>
    <div class="liquid-card-language">
      <LanguagePicker :model-value="language" @update:model-value="emit('update:language', $event)" />
    </div>
          <div class="liquid-card-heading">
            <span class="liquid-app-icon"><Icon name="bridge" :size="36" /></span>
            <h1>ChemBridge</h1>
          </div>
          <form class="liquid-form" @submit.prevent="submit">
            <label for="username">{{ t.id }}</label>
            <div class="liquid-field">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="8" r="3.5" /><path d="M5 21v-2a7 7 0 0 1 14 0v2" stroke-linecap="round" /></svg>
              <input id="username" v-model="username" autocomplete="username" :placeholder="t.idPlaceholder" :disabled="loading" />
            </div>
            <label for="password">{{ t.password }}</label>
            <div class="liquid-field">
              <Icon name="lock" :size="18" />
              <input id="password" v-model="password" :type="visible ? 'text' : 'password'" autocomplete="current-password" :placeholder="t.passwordPlaceholder" :disabled="loading" />
              <button v-spring type="button" class="liquid-eye" :aria-label="t.showPassword" :aria-pressed="visible" @click="visible = !visible"><Icon name="eye" :size="18" /><span v-if="visible" class="eye-slash" aria-hidden="true"></span></button>
            </div>
            <button v-spring type="submit" class="liquid-submit" :disabled="loading" :aria-busy="loading">
              <span v-if="loading" class="liquid-loader" aria-hidden="true"></span>
              <span>{{ loading ? t.loggingIn : t.login }}</span>
              <Icon v-if="!loading" name="arrow" :size="19" />
            </button>
          </form>
        </div>
      </section>
    </main>

  </div>
</template>
