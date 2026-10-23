<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Icon from './components/Icon.vue'
import LanguagePicker from './components/LanguagePicker.vue'
import ScopePicker from './components/ScopePicker.vue'
import { scopeCopy } from './locales/scope'
import { feedbackCopy } from './locales/feedback'
import { suggestedQuestions } from './api/suggestions'
import { catalog, availableEquipment, equipmentFor, productsFor, normalizeScope, requestScope, productLabel, equipmentLabel } from './api/scope'
import LoginView from './views/LoginView.vue'
import HomeView from './views/HomeView.vue'
import SceneBackground from './components/SceneBackground.vue'
import GuideViewer from './components/GuideViewer.vue'
import ReportModal from './components/ReportModal.vue'
import EmergencyContacts from './components/EmergencyContacts.vue'
import { clean } from './locales/clean'
import candidates from './api/candidates.json'
import { spring as vSpring } from './directives/spring'
import './chat-glass.css'
import { copy } from './locales'
import * as api from './api'
import { apiCopy } from './locales/api'
const page=ref('login'), language=ref('ko'), situation=ref('free'), question=ref(''), messages=ref([]), pending=ref(false), voice=ref('idle'), modal=ref(null), playing=ref(null), input=ref(null), thread=ref(null)
const signingIn=ref(false), checking=ref(true), signingOut=ref(false), loginError=ref(''), loginNotice=ref(''), globalError=ref('')
const topic=ref(api.contract.topics.chemical), a=computed(()=>apiCopy[language.value])
const contacts=ref(false), report=ref(null), c=computed(()=>clean[language.value]||clean.ko)
const productRequired=ref(false), productPicker=ref(null), scopePanel=ref(null)
const equipmentId=ref(''), productId=ref(''), s=computed(()=>scopeCopy[language.value])
watch(productId,value=>{if(value)productRequired.value=false})
const selectedEquipment=computed(()=>equipmentFor(equipmentId.value))
const equipmentOptions=computed(()=>[{value:'',label:s.value.allEquipment},...availableEquipment.map(item=>({value:item.equipment_id,label:equipmentLabel(item,language.value,s.value.demo)}))])
const productOptions=computed(()=>[{value:'',label:s.value.allProducts},...productsFor(equipmentId.value).map(item=>({value:item.product_id,label:productLabel(item,language.value)}))])
function selectEquipment(value){equipmentId.value=value;productId.value=normalizeScope(value,productId.value).product_id||''}
function scopeLabel(scope){return [equipmentFor(scope.equipment_id) ? equipmentLabel(equipmentFor(scope.equipment_id),language.value,s.value.demo) : '',catalog.products.find(p=>p.product_id===scope.product_id) ? productLabel(catalog.products.find(p=>p.product_id===scope.product_id),language.value) : ''].filter(Boolean).join(' / ')}
let requestController, resumeDraft
function errorKey(error){
 if(error.status===422)return 'invalid'
 if(error.status===503||error.status===502||error.status===504)return 'unavailable'
 if(error.code==='TIMEOUT')return 'timeout'
 if(error.code==='NETWORK')return 'connection'
 return 'unexpected'
}
function expire(message){
 resumeDraft={situation:situation.value,topic:message.topic,question:message.question,equipmentId:message.equipment_id||'',productId:message.product_id||''}
 navigate('login');messages.value=[];loginError.value='expired'
}
onMounted(async()=>{
 try{if(await api.checkSession())navigate('home')}
 catch(error){loginError.value=errorKey(error)}
 finally{checking.value=false}
})
try { const saved=localStorage.getItem('chembridge-language'); if(copy[saved])language.value=saved } catch {}
const t=computed(()=>copy[language.value]),keys=['before','handling','storage','during','after','emergency']
const index=computed(()=>keys.indexOf(situation.value)),title=computed(()=>topic.value===api.contract.topics.law?a.value.law:index.value<0?t.value.free:t.value.topicTitles[index.value]),busy=computed(()=>pending.value||['recording','processing'].includes(voice.value))
const isLaw=computed(()=>topic.value===api.contract.topics.law)
const guideUrl=computed(()=>isLaw.value?'/guides/law.pdf':index.value>=0?`/guides/${situation.value}.pdf`:null)
const faq=computed(()=>{
 const list=(candidates[language.value]||candidates.ko)[isLaw.value?'law':'chemical']||[]
 const groups=[]
 for(const item of list){let g=groups.find(x=>x.key===item.g);if(!g){g={key:item.g,items:[]};groups.push(g)}g.items.push(item.q)}
 return groups
})
function onKey(event){if(event.key!=='Enter'||event.shiftKey||event.isComposing||event.keyCode===229)return;event.preventDefault();send()}
const suggestions=computed(()=>topic.value===api.contract.topics.law?[a.value.lawQuestion]:suggestedQuestions({situation:situation.value,language:language.value,equipmentId:equipmentId.value,productId:productId.value}))
const feedback=computed(()=>feedbackCopy[language.value]), slowResponse=ref(false)
let slowTimer
watch(pending,value=>{clearTimeout(slowTimer);slowResponse.value=false;if(value)slowTimer=setTimeout(()=>{slowResponse.value=true},12000)})
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
watch(language,v=>{document.documentElement.lang=v;document.title=`ChemBridge · ${copy[v].service}`;try{localStorage.setItem('chembridge-language',v)}catch{}})
document.documentElement.lang=language.value
document.title=`ChemBridge · ${copy[language.value].service}`
function stop(){clearTimeout(timer);playing.value=null}
function cleanup(){clearTimeout(slowTimer);requestController?.abort();version++;pending.value=false;voice.value='idle';modal.value=null;stop()}
function navigate(p){cleanup();page.value=p;window.scrollTo({top:0})}
function open(key,selectedTopic=api.contract.topics.chemical){productRequired.value=false;navigate('chat');topic.value=selectedTopic;situation.value=key;question.value='';messages.value=[];globalError.value='';equipmentId.value='';productId.value=''}
function changeTopic(value){if(busy.value)return;open(situation.value,value)}
async function logout(){
 if(signingOut.value)return
 signingOut.value=true;globalError.value=''
 try{await api.logout();navigate('login');messages.value=[];question.value='';resumeDraft=null;loginError.value=''}
 catch(error){globalError.value='logoutFailed'}
 finally{signingOut.value=false}
}
async function login(credentials){
 if(signingIn.value||checking.value)return
 if(!credentials.username.trim()||!credentials.password.trim()){loginError.value='required';return}
 signingIn.value=true;loginError.value='';loginNotice.value=''
 try{
  await api.login(credentials)
  if(resumeDraft){const draft=resumeDraft;resumeDraft=null;open(draft.situation,draft.topic);question.value=draft.question;equipmentId.value=draft.equipmentId;productId.value=draft.productId}
  else navigate('home')
 }catch(error){loginError.value=error.status===401?'credentials':errorKey(error)}
 finally{signingIn.value=false}
}
async function signup(credentials){
 if(signingIn.value||checking.value)return
 if(!credentials.username.trim()||!credentials.password.trim()){loginError.value='required';return}
 signingIn.value=true;loginError.value='';loginNotice.value=''
 try{await api.signup(credentials);credentials.onSuccess();loginNotice.value='signupSuccess'}
 catch(error){loginError.value=error.status===400?'signupDuplicate':errorKey(error)}
 finally{signingIn.value=false}
}
function fill(text){if(busy.value)return;voice.value='idle';question.value=text;nextTick(()=>input.value?.focus())}
async function scroll(){await nextTick();thread.value?.lastElementChild?.scrollIntoView({behavior:'smooth',block:'nearest'})}
async function send(retryMessage){
 const retry=retryMessage?.error?retryMessage:null
 const text=retry?retry.question:question.value.trim()
 const length=Array.from(text).length
 if(busy.value||length<api.contract.question.minLength||length>api.contract.question.maxLength)return
 const scope=retry||requestScope(topic.value,equipmentId.value,productId.value)
 if(scope.equipment_id&&!scope.product_id){question.value=text;equipmentId.value=scope.equipment_id;productId.value='';productRequired.value=true;await nextTick();scopePanel.value?.scrollIntoView({behavior:'smooth',block:'center'});return}
 productRequired.value=false
 stop();voice.value='idle'
 const id=++version
 const message=retry||{id,question:text,response:null,error:null,topic:topic.value,language:language.value,...requestScope(topic.value,equipmentId.value,productId.value)}
 if(retry){message.id=id;message.error=null}
 else {question.value='';messages.value.push(message)}
 pending.value=true;requestController=new AbortController();scroll()
 try{
  const response=await api.ask({question:text,topic:message.topic,product_id:message.product_id,equipment_id:message.equipment_id,language:message.language},{signal:requestController.signal})
  if(version===id)messages.value.find(m=>m.id===id).response=response
 }catch(error){
  if(version!==id)return
  if(error.status===401){question.value=text;expire(message)}
  else messages.value.find(m=>m.id===id).error=error.code==='CANCELLED'?'cancelled':errorKey(error)
 }finally{if(version===id){pending.value=false;scroll()}}
}
async function chooseProduct(){await nextTick();scopePanel.value?.scrollIntoView({behavior:'smooth',block:'center'});productPicker.value?.open()}
function cancelRequest(){requestController?.abort()}
function editQuestion(message){if(busy.value)return;const scope=requestScope(message.topic,message.equipment_id,message.product_id);equipmentId.value=scope.equipment_id||'';productId.value=scope.product_id||'';fill(message.question)}
function sourceUrl(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)?url.href:null}catch{return null}}

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
    <LanguagePicker v-model="language" />
    <button v-spring class="home-logout" :aria-label="t.logout" :disabled="signingOut" @click="logout"><Icon name="logout" :size="19" /></button>
  </div>
</header>
<p v-if="globalError" class="api-global-error" role="alert">{{a[globalError]}}</p>
<Transition name="scene" mode="out-in">
<LoginView key="login" v-if="page === 'login'" v-model:language="language" :loading="signingIn" :checking="checking" :error="loginError ? a[loginError] : ''" :notice="loginNotice ? a[loginNotice] : ''" @clear-error="loginError='';loginNotice=''" @submit="login" @signup="signup" />
<HomeView key="home" v-else-if="page === 'home'" v-model:language="language" @open="open" @logout="logout" />
<main v-else key="chat" class="clear-chat-main" :class="{'has-guide':guideUrl}">
  <GuideViewer v-if="guideUrl" :src="guideUrl" :title="title" :source="isLaw?'국가법령정보센터':'KOSHA GUIDE'" :language="language" />
  <div class="chat-pane">
  <div class="clear-chat-heading">
    <div class="clear-chat-title"><button v-spring class="chat-back" :aria-label="t.back" @click="navigate('home')"><Icon name="back" :size="22" /></button><h1>{{title}}</h1></div>
    <div class="chat-heading-actions"><button v-if="situation==='emergency' && !isLaw" type="button" class="emergency-btn" @click="contacts=true"><Icon name="alert" :size="18" />{{c.emergency}}</button><a v-if="guideUrl" class="guide-btn" :href="guideUrl" target="_blank" rel="noopener noreferrer">{{c.view}}</a><a v-if="guideUrl" class="guide-btn filled" :href="guideUrl" :download="`${title}.pdf`">{{c.download}}</a><button v-spring class="chat-new" :aria-label="t.newChat" @click="open(situation,topic)"><Icon name="plus" :size="18" /><span>{{t.newChat}}</span></button></div>
  </div>

  <div class="chat-topic-picker" role="group" :aria-label="a.topics"><button v-for="(value,key) in api.contract.topics" :key="key" type="button" :aria-pressed="topic===value" :disabled="busy" @click="changeTopic(value)">{{a[key]}}</button></div>
  <div v-if="topic===api.contract.topics.chemical" class="chat-scope" ref="scopePanel">
    <div class="chat-scope-controls">
      <label><span>{{s.equipment}}</span><ScopePicker :model-value="equipmentId" :options="equipmentOptions" :label="s.equipment" :disabled="busy" @update:model-value="selectEquipment" /></label>
      <label><span>{{s.product}}</span><ScopePicker ref="productPicker" v-model="productId" :options="productOptions" :label="s.product" :disabled="busy||selectedEquipment?.coverage==='none'" /></label>
    </div>
    <div v-if="productRequired" class="chat-product-required" role="alert"><span>{{feedback.selectProduct}}</span><button type="button" @click="chooseProduct">{{feedback.chooseProduct}}</button></div>
    <p v-if="selectedEquipment && selectedEquipment.coverage!=='full'" class="chat-scope-warning" role="status"><Icon name="alert" :size="18" />{{s[selectedEquipment.coverage]}}</p>
  </div>
  <section ref="thread" class="clear-conversation" :aria-label="t.assistant" aria-live="polite" :aria-busy="pending">
    <div v-if="!messages.length" class="clear-chat-empty">
      <span class="clear-empty-icon"><Icon name="chat" :size="36" /></span>
      <h2>{{t.emptyTitle}}</h2>
      <div v-if="situation==='free'" class="faq-board" :aria-label="c.faqTitle">
        <p class="faq-sub">{{c.faqTitle}} · {{c.faqSub}}</p>
        <section v-for="group in faq" :key="group.key" class="faq-group"><h3>{{c.g[group.key]}}</h3><div class="faq-items"><button v-for="q in group.items" :key="q" type="button" class="faq-item" @click="fill(q)"><span>{{q}}</span><Icon name="arrow" :size="16" /></button></div></section>
      </div>
      <div v-else class="clear-suggestions" :aria-label="t.suggestions"><button v-for="suggestion in suggestions" :key="suggestion" v-spring @click="fill(suggestion)"><span>{{suggestion}}</span><Icon name="arrow" :size="18" /></button></div>
    </div>
    <article v-for="message in messages" :key="message.id" class="clear-exchange">
      <div class="clear-question"><span v-if="scopeLabel(message)" class="chat-scope-context">{{scopeLabel(message)}}</span><p>{{message.question}}</p></div>
      <div class="clear-answer">
        <div class="clear-answer-heading"><span class="clear-assistant-icon"><Icon name="bridge" :size="23" /></span><b>ChemBridge</b></div>
        <div v-if="message.error" class="chat-api-error" :class="{'is-cancelled':message.error==='cancelled'}" role="alert">
          <h3><Icon name="alert" :size="22" />{{message.error==='cancelled'?feedback.cancelledTitle:feedback.failed}}</h3>
          <p>{{message.error==='cancelled'?feedback.cancelled:a[message.error]}}</p>
          <div class="chat-error-actions"><button type="button" :disabled="busy" @click="send(message)">{{a.retry}}</button><button type="button" :disabled="busy" @click="editQuestion(message)">{{feedback.edit}}</button></div>
        </div>
        <div v-else-if="!message.response" class="chat-loading-state">
          <div class="clear-loading" role="status"><span class="clear-loading-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>{{slowResponse?feedback.slow:feedback.waiting}}</span></div>
          <div class="chat-loading-lines" aria-hidden="true"><i></i><i></i></div>
          <button type="button" class="chat-cancel-request" @click="cancelRequest">{{feedback.cancel}}</button>
        </div>
        <template v-else>
          <div v-if="message.response.needs_review || message.response.handoff" class="clear-alert" role="note"><Icon name="alert" :size="18" />{{message.response.handoff?a.handoff:t.review}}</div>
          <p class="clear-answer-text">{{message.response.answer}}</p>
          <div class="clear-answer-tools">
            <template v-for="(source,i) in message.response.sources" :key="`${source.doc_id}-${i}`"><a v-if="sourceUrl(source.url)" v-spring class="clear-source" :href="sourceUrl(source.url)" target="_blank" rel="noopener noreferrer"><span class="clear-source-number">[{{i + 1}}]</span><span>{{source.title}}<template v-if="source.section"> · {{source.section}}</template></span><Icon name="arrow" :size="16" /></a><span v-else class="clear-source" :title="a.noLink"><span class="clear-source-number">[{{i + 1}}]</span><span>{{source.title}}<template v-if="source.section"> · {{source.section}}</template></span></span></template>
            <button v-spring class="clear-listen" :disabled="busy" :aria-pressed="playing===message.id" @click="play(message.id)"><Icon :name="playing===message.id?'stop':'sound'" :size="19" />{{playing===message.id?t.stop:a.listenPreview}}</button>
            <button v-spring type="button" class="clear-report" @click="report=message"><Icon name="file" :size="19" />{{c.makeReport}}</button>
          </div>
        </template>
      </div>
    </article>
  </section>

  <div v-if="messages.length&&!busy" class="clear-suggestions chat-followup" :aria-label="t.suggestions"><button v-for="suggestion in suggestions" :key="suggestion" v-spring @click="fill(suggestion)"><span>{{suggestion}}</span><Icon name="arrow" :size="18" /></button></div>
  <form class="clear-composer" @submit.prevent="send">
    <label class="sr-only" for="question">{{t.send}}</label>
    <textarea id="question" ref="input" v-model="question" :disabled="busy" :maxlength="api.contract.question.maxLength" :placeholder="t.placeholder" rows="3" @keydown="onKey"></textarea>
    <div v-if="voice!=='idle'" class="clear-voice-state" role="status">
      <template v-if="voice==='recording'"><span class="clear-record-dot"></span><b>{{t.recording}}</b><span class="clear-wave" aria-hidden="true"><i v-for="n in 14" :key="n" :style="{animationDelay:`${n*.09}s`}"></i></span><button type="button" v-spring @click="finish">{{t.finish}}</button><button type="button" @click="cancel">{{t.cancel}}</button></template>
      <template v-else-if="voice==='processing'"><span class="clear-loading-dots"><i></i><i></i><i></i></span>{{t.converting}}</template>
      <template v-else><Icon name="check" :size="18" />{{t.reviewVoice}}</template>
    </div>
    <div class="clear-composer-controls"><button v-spring type="button" class="clear-mic" :disabled="busy" @click="startVoice"><Icon name="mic" :size="21" /><span>{{a.voicePreview}}</span></button><button v-spring type="submit" class="clear-send" :disabled="busy||Array.from(question.trim()).length<api.contract.question.minLength" :aria-label="t.send"><Icon name="send" :size="23" /></button></div>
  </form>
  </div>
</main>
</Transition>
<EmergencyContacts v-if="contacts" :language="language" @close="contacts=false" />
<ReportModal v-if="report" :message="report" :title="title" :source="guideUrl?(isLaw?'국가법령정보센터':'KOSHA GUIDE'):''" :language="language" @close="report=null" />
<div v-if="modal" class="modal-backdrop" @click.self="modal=null"><section ref="modalElement" @keydown="trapFocus" role="dialog" aria-modal="true" aria-labelledby="modal-title" class="modal"><span class="modal-icon"><Icon :name="modal==='voice'?'mic':'file'" :size="28"/></span><h2 id="modal-title">{{modal==='voice'?t.permissionTitle:t.sourceTitle}}</h2><p>{{modal==='voice'?t.permissionBody:t.sourceBody}}</p><div class="modal-actions"><button class="secondary" autofocus @click="modal=null">{{t.close}}</button><button v-if="modal==='voice'" class="primary" @click="modal=null;voice='recording'">{{t.startVoice}}<Icon name="arrow" :size="17"/></button></div></section></div>
</div>
</template>
