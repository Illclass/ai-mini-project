<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { copy } from '../locales'
import { apiCopy } from '../locales/api'
import LanguagePicker from '../components/LanguagePicker.vue'
import { spring as vSpring } from '../directives/spring'
import '../login-glass.css'

const props = defineProps({ language: { type: String, default: 'ko' }, loading: Boolean, checking: Boolean, error: String, notice: String })
const emit = defineEmits(['update:language', 'submit', 'signup', 'clear-error'])
const t = computed(() => copy[props.language])
const a = computed(() => apiCopy[props.language])
const username = ref('')
const password = ref('')
const visible = ref(false), registering = ref(false), confirmation = ref(''), localError = ref('')
function switchMode(){if(props.loading || props.checking)return;registering.value=!registering.value;password.value='';confirmation.value='';localError.value='';emit('clear-error')}
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
  if (props.loading || props.checking) return
  localError.value=''
  if(registering.value){
    if(password.value!==confirmation.value){localError.value='mismatch';return}
    if(password.value!==password.value.trim() || new TextEncoder().encode(password.value).length>72){localError.value='passwordFormat';return}
  }
  emit(registering.value?'signup':'submit', { username: username.value, password: password.value, onSuccess: () => { registering.value=false;password.value='';confirmation.value='' } })
}
onBeforeUnmount(() => cancelAnimationFrame(frame))
</script>

<template>
  <div class="liquid-login">
    <div class="liquid-landscape" aria-hidden="true">
      <div class="landscape-grain"></div>
    </div>



    <aside class="clean-brand"><span class="clean-brand-mark"><Icon name="bridge" :size="26" /></span><b>ChemBridge</b><h2>{{ t.loginTitle }}</h2><p>{{ t.loginDesc }}</p></aside>
    <main class="liquid-main">
      <section class="liquid-form-area">
        <div ref="glass" class="liquid-card" @pointermove="reflect" @pointerleave="resetLight">
          <div class="card-specular" aria-hidden="true"></div>
    <div class="liquid-card-language">
      <LanguagePicker :model-value="language" @update:model-value="emit('update:language', $event)" />
    </div>
          <div class="liquid-card-heading">
            <span class="liquid-app-icon"><Icon name="bridge" :size="36" /></span>
            <h1>ChemBridge</h1><h2 v-if="registering" class="signup-heading">{{a.signup}}</h2>
          </div>
          <form class="liquid-form" @submit.prevent="submit">
            <label for="username">{{ t.id }}</label>
            <div class="liquid-field">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="8" r="3.5" /><path d="M5 21v-2a7 7 0 0 1 14 0v2" stroke-linecap="round" /></svg>
              <input id="username" v-model="username" name="username" autocomplete="username" maxlength="100" required :placeholder="t.idPlaceholder" :disabled="loading || checking" />
            </div>
            <label for="password">{{ t.password }}</label>
            <div class="liquid-field">
              <Icon name="lock" :size="18" />
              <input id="password" v-model="password" :type="visible ? 'text' : 'password'" name="password" :autocomplete="registering ? 'new-password' : 'current-password'" required :placeholder="t.passwordPlaceholder" :disabled="loading || checking" />
              <button v-spring type="button" class="liquid-eye" :aria-label="t.showPassword" :aria-pressed="visible" @click="visible = !visible"><Icon name="eye" :size="18" /><span v-if="visible" class="eye-slash" aria-hidden="true"></span></button>
            </div>
            <template v-if="registering"><label for="password-confirmation">{{a.confirmPassword}}</label><div class="liquid-field"><Icon name="lock" :size="18" /><input id="password-confirmation" v-model="confirmation" type="password" autocomplete="new-password" required :placeholder="a.confirmPassword" :disabled="loading || checking" /></div></template>
            <p v-if="localError || error" class="login-api-error" role="alert">{{localError ? a[localError] : error}}</p>
            <p v-else-if="notice" class="login-api-notice" role="status">{{notice}}</p>
            <button v-spring type="submit" class="liquid-submit" :disabled="loading || checking" :aria-busy="loading">
              <span v-if="loading" class="liquid-loader" aria-hidden="true"></span>
              <span>{{ checking ? a.checking : loading ? (registering ? a.signingUp : t.loggingIn) : (registering ? a.signup : t.login) }}</span>
              <Icon v-if="!loading" name="arrow" :size="19" />
            </button>
            <button type="button" class="auth-switch" :disabled="loading || checking" @click="switchMode">{{registering ? a.loginLink : a.signup}}</button>
          </form>
        </div>
      </section>
    </main>

  </div>
</template>
