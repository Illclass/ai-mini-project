<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './components/Icon.vue'
import LoginView from './views/LoginView.vue'
import HomeView from './views/HomeView.vue'
import SceneBackground from './components/SceneBackground.vue'
import { spring as vSpring } from './directives/spring'
import './chat-glass.css'
import { copy, languages } from './locales'
import * as api from './api'
const page=ref('login'), language=ref('ko'), situation=ref('free'), question=ref(''), messages=ref([]), pending=ref(false), voice=ref('idle'), modal=ref(null), playing=ref(null), input=ref(null), thread=ref(null)
const signingIn=ref(false)
try { const saved=localStorage.getItem('chembridge-language'); if(copy[saved])language.value=saved } catch {}
const t=computed(()=>copy[language.value]),keys=['before','handling','storage','during','after','emergency']
const index=computed(()=>keys.indexOf(situation.value)),title=computed(()=>index.value<0?t.value.free:t.value.topicTitles[index.value]),busy=computed(()=>pending.value||['recording','processing'].includes(voice.value))
const suggestions=computed(()=>[Math.max(0,index.value),index.value===2?1:2])
const modalElement = ref(null)
let modalTrigger
watch(modal, async value => {
 if (value) { modalTrigger = document.activeElement; await nextTick(); modalElement.value?.querySelector('button')?.focus() }
 else { await nextTick(); modalTrigger?.focus() }
})
function trapFocus(event) {
 if (event.key !== 'Tab') return
 const buttons = modalElement.value?.querySelectorAll('button')
 if (!buttons?.length) return
 const first = buttons[0], last = buttons[buttons.length - 1]
 if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
 else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
let version=0, timer
watch(language,v=>{document.documentElement.lang=v;try{localStorage.setItem('chembridge-language',v)}catch{}})
document.documentElement.lang=language.value
function stop(){clearTimeout(timer);playing.value=null}
function cleanup(){version++;pending.value=false;voice.value='idle';modal.value=null;stop()}
function navigate(p){cleanup();page.value=p;window.scrollTo({top:0})}
function open(key){navigate('chat');situation.value=key;question.value='';messages.value=[]}
function logout(){navigate('login');messages.value=[];question.value=''}
async function login(){if(signingIn.value)return;signingIn.value=true;await api.login();signingIn.value=false;navigate('home')}
function fill(text){if(busy.value)return;voice.value='idle';question.value=text;nextTick(()=>input.value?.focus())}
async function scroll(){await nextTick();thread.value?.lastElementChild?.scrollIntoView({behavior:'smooth',block:'nearest'})}
async function send(){if(busy.value||question.value.trim().length<2||question.value.length>500)return;stop();voice.value='idle';const id=++version,text=question.value.trim();question.value='';messages.value.push({id,question:text,response:null});pending.value=true;scroll();try{const response=await api.ask({question:text,topic:'chemical_safety',product_id:null,language:language.value},{situation:situation.value});if(version===id)messages.value.find(m=>m.id===id).response=response}finally{if(version===id){pending.value=false;scroll()}}}
function startVoice(){if(busy.value)return;stop();modal.value='voice'}
async function finish(){voice.value='processing';const id=++version,result=await api.transcribe({language:language.value,situationIndex:index.value});if(id!==version)return;question.value=result.text;voice.value='review';nextTick(()=>input.value?.focus())}
function cancel(){version++;voice.value='idle'}
function play(id){if(busy.value)return;if(playing.value===id)return stop();stop();playing.value=id;timer=setTimeout(stop,5500)}
function escape(e){if(e.key==='Escape')modal.value=null}
window.addEventListener('keydown',escape)
onBeforeUnmount(()=>{cleanup();window.removeEventListener('keydown',escape)})
</script>
<template>
<div class="app-shell" :class="{'login-page':page==='login', 'chat-page':page==='chat', 'home-page':page==='home'}">
<SceneBackground :reading="page === 'chat'" />
<header v-if="page !== 'login'" class="clear-chat-header">
  <button v-spring class="home-brand" aria-label="ChemBridge" @click="navigate('home')"><span class="home-brand-mark"><Icon name="bridge" :size="24" /></span><span>ChemBridge</span></button>
  <div class="home-controls">
    <label class="home-language"><Icon name="globe" :size="18" /><select v-model="language" aria-label="Language"><option v-for="(name,code) in languages" :value="code" :key="code">{{name}}</option></select><svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true"><path d="m3 4.5 3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" /></svg></label>
    <button v-spring class="home-logout" :aria-label="t.logout" @click="logout"><Icon name="logout" :size="19" /></button>
  </div>
</header>
<Transition name="scene" mode="out-in">
<LoginView key="login" v-if="page === 'login'" v-model:language="language" :loading="signingIn" @submit="login" />
<HomeView key="home" v-else-if="page === 'home'" v-model:language="language" @open="open" @logout="logout" />
<main v-else key="chat" class="clear-chat-main">
  <div class="clear-chat-heading">
    <div class="clear-chat-title"><button v-spring class="chat-back" :aria-label="t.back" @click="navigate('home')"><Icon name="back" :size="22" /></button><h1>{{title}}</h1></div>
    <button v-spring class="chat-new" :aria-label="t.newChat" @click="open(situation)"><Icon name="plus" :size="18" /><span>{{t.newChat}}</span></button>
  </div>

  <section ref="thread" class="clear-conversation" :aria-label="t.assistant" aria-live="polite" :aria-busy="pending">
    <div v-if="!messages.length" class="clear-chat-empty">
      <span class="clear-empty-icon"><Icon name="chat" :size="36" /></span>
      <h2>{{t.emptyTitle}}</h2>
      <div class="clear-suggestions"><button v-for="i in suggestions" :key="i" v-spring @click="fill(t.questions[i])"><span>{{t.questions[i]}}</span><Icon name="arrow" :size="18" /></button></div>
    </div>
    <article v-for="message in messages" :key="message.id" class="clear-exchange">
      <div class="clear-question"><p>{{message.question}}</p></div>
      <div class="clear-answer">
        <div class="clear-answer-heading"><span class="clear-assistant-icon"><Icon name="bridge" :size="23" /></span><b>ChemBridge</b><span v-if="message.response" class="clear-demo">{{t.demoAnswer}}</span></div>
        <div v-if="!message.response" class="clear-loading" role="status"><span class="clear-loading-dots"><i></i><i></i><i></i></span>{{t.loading}}</div>
        <template v-else>
          <div v-if="message.response.needs_review || message.response.handoff" class="clear-alert" :class="{emergency:message.response.handoff}"><Icon name="alert" :size="18" />{{message.response.handoff?t.emergency:t.review}}</div>
          <p class="clear-answer-text">{{message.response.answer}}</p>
          <div class="clear-answer-tools">
            <button v-for="source in message.response.sources" :key="source.doc_id" v-spring class="clear-source" :aria-label="`${t.sources}: ${source.title}`" @click="modal='source'"><Icon name="file" :size="18" /><span>{{source.title}}</span><Icon name="arrow" :size="16" /></button>
            <button v-spring class="clear-listen" :disabled="busy" :aria-pressed="playing===message.id" @click="play(message.id)"><Icon :name="playing===message.id?'stop':'sound'" :size="19" />{{playing===message.id?t.stop:t.listen}}</button>
          </div>
        </template>
      </div>
    </article>
  </section>

  <form class="clear-composer" @submit.prevent="send">
    <label class="sr-only" for="question">{{t.send}}</label>
    <textarea id="question" ref="input" v-model="question" :disabled="busy" maxlength="500" :placeholder="t.placeholder" rows="3" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send"></textarea>
    <div v-if="voice!=='idle'" class="clear-voice-state" role="status">
      <template v-if="voice==='recording'"><span class="clear-record-dot"></span><b>{{t.recording}}</b><span class="clear-wave" aria-hidden="true"><i v-for="n in 14" :key="n" :style="{animationDelay:`${n*.09}s`}"></i></span><button type="button" v-spring @click="finish">{{t.finish}}</button><button type="button" @click="cancel">{{t.cancel}}</button></template>
      <template v-else-if="voice==='processing'"><span class="clear-loading-dots"><i></i><i></i><i></i></span>{{t.converting}}</template>
      <template v-else><Icon name="check" :size="18" />{{t.reviewVoice}}</template>
    </div>
    <div class="clear-composer-controls"><button v-spring type="button" class="clear-mic" :disabled="busy" @click="startVoice"><Icon name="mic" :size="21" /><span>{{t.voice}}</span></button><button v-spring type="submit" class="clear-send" :disabled="busy||question.trim().length<2" :aria-label="t.send"><Icon name="send" :size="23" /></button></div>
  </form>
</main>
</Transition>
<div v-if="modal" class="modal-backdrop" @click.self="modal=null"><section ref="modalElement" @keydown="trapFocus" role="dialog" aria-modal="true" aria-labelledby="modal-title" class="modal"><span class="modal-icon"><Icon :name="modal==='voice'?'mic':'file'" :size="28"/></span><h2 id="modal-title">{{modal==='voice'?t.permissionTitle:t.sourceTitle}}</h2><p>{{modal==='voice'?t.permissionBody:t.sourceBody}}</p><div class="modal-actions"><button class="secondary" autofocus @click="modal=null">{{t.close}}</button><button v-if="modal==='voice'" class="primary" @click="modal=null;voice='recording'">{{t.startVoice}}<Icon name="arrow" :size="17"/></button></div></section></div>
</div>
</template>
