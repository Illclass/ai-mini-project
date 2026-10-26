<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
const GuideViewer = defineAsyncComponent(() => import('./components/GuideViewer.vue'))
import ReportModal from './components/ReportModal.vue'
import EmergencyContacts from './components/EmergencyContacts.vue'
import { clean } from './locales/clean'
import candidates from './api/candidates.json'
import { lawRecommendations } from './api/recommendations.js'
import { guideFor } from './api/guides'
import { spring as vSpring } from './directives/spring'
import './chat-glass.css'
import { copy } from './locales'
import * as api from './api'
import { failureKey } from './api/client.js'
import { answerLines, foldAnswer } from './api/sources.js'
import SourceLinks from './components/SourceLinks.vue'
const SourceViewer = defineAsyncComponent(() => import('./components/SourceViewer.vue'))
const sourceSelection=ref(null)
import { apiCopy } from './locales/api'
const page=ref('login'), language=ref('ko'), situation=ref('free'), question=ref(''), messages=ref([]), pending=ref(false), voice=ref('idle'), modal=ref(null), playing=ref(null), input=ref(null), thread=ref(null)
const signingIn=ref(false), checking=ref(true), signingOut=ref(false), loginError=ref(''), loginNotice=ref(''), globalError=ref('')
const topic=ref(api.contract.topics.chemical), a=computed(()=>apiCopy[language.value])
const contacts=ref(false), report=ref(null), c=computed(()=>clean[language.value]||clean.ko)
const productRequired=ref(false), productPicker=ref(null), scopePanel=ref(null), voiceError=ref('')
let recorder, audio, audioUrl, voiceDraft=false   // 음성 모드: 녹음기 · 재생 중 오디오 · 음성으로 만든 질문 여부(답변 자동 재생)
// 음성 대화 모드(손 없이): 켜 두면 말소리를 알아서 듣고 → 3초 뒤 자동 전송 → 답변을 읽고 → 다시 듣는다
const convo=ref(null)   // null = 꺼짐, { state, text, countdown, answer }
let listener, convoTimer, audioDone, lastPlay
const equipmentId=ref(''), productId=ref(''), s=computed(()=>scopeCopy[language.value])
watch(productId,value=>{if(value)productRequired.value=false})
const selectedEquipment=computed(()=>equipmentFor(equipmentId.value))
const voiceReady=computed(()=>api.VOICE_LANGUAGES.includes(language.value))   // 크메르어는 음성 모드 미지원
const equipmentOptions=computed(()=>[{value:'',label:s.value.allEquipment},...availableEquipment.map(item=>({value:item.equipment_id,label:equipmentLabel(item,language.value,s.value.demo)}))])
const productOptions=computed(()=>[{value:'',label:s.value.allProducts},...productsFor(equipmentId.value).map(item=>({value:item.product_id,label:productLabel(item,language.value)}))])
function selectEquipment(value){equipmentId.value=value;productId.value=normalizeScope(value,productId.value).product_id||''}
function scopeLabel(scope){return [equipmentFor(scope.equipment_id) ? equipmentLabel(equipmentFor(scope.equipment_id),language.value,s.value.demo) : '',catalog.products.find(p=>p.product_id===scope.product_id) ? productLabel(catalog.products.find(p=>p.product_id===scope.product_id),language.value) : ''].filter(Boolean).join(' / ')}
let requestController, resumeDraft
function errorKey(error){
 const diagnostic=failureKey(error)
 if(diagnostic)return diagnostic
 if(error.status===422)return 'invalid'
 if(error.status===503||error.status===502||error.status===504)return 'unavailable'
 if(error.code==='TIMEOUT')return 'timeout'
 if(error.code==='NETWORK')return 'connection'
 return 'unexpected'
}
function expire(message){
 resumeDraft={situation:message.situation||situation.value,topic:message.topic,question:message.question,equipmentId:message.equipment_id||'',productId:message.product_id||''}
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
const guide=computed(()=>guideFor(situation.value,topic.value,productId.value))
const guideUrl=computed(()=>guide.value?.url)
// 대화가 시작되면 지침서를 접어 답변에 화면 폭을 준다. 머리의 버튼으로 다시 펼친다 (김규빈 2026-10-26)
const guideOpen=ref(true), guideShown=computed(()=>guideUrl.value&&guideOpen.value)
watch(()=>messages.value.length,(n,o)=>{if(n&&!o)guideOpen.value=false;if(!n)guideOpen.value=true})
// 긴 목록은 앞 3개만 보이고 "N개 더 보기"로 펼친다. ⚠ 주의사항은 접지 않는다 (sources.js foldAnswer)
function answerView(message){const lines=foldAnswer(answerLines(message.response.answer));return {folds:lines.some(l=>l.extra),lines:message.expanded?lines:lines.filter(l=>!l.extra)}}
const faq=computed(()=>{
 const list=(candidates[language.value]||candidates.ko)[isLaw.value?'law':'chemical']||[]
 const groups=[]
 for(const item of list){let g=groups.find(x=>x.key===item.g);if(!g){g={key:item.g,items:[]};groups.push(g)}g.items.push(item)}
 return groups
})
function onKey(event){if(event.key!=='Enter'||event.shiftKey||event.isComposing||event.keyCode===229)return;event.preventDefault();send()}
const suggestions=computed(()=>topic.value===api.contract.topics.law?lawRecommendations(language.value).map(x=>x.q):suggestedQuestions({situation:situation.value,language:language.value,equipmentId:equipmentId.value,productId:productId.value}))
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
let version=0
watch(language,v=>{document.documentElement.lang=v;document.title=`ChemBridge · ${copy[v].service}`;try{localStorage.setItem('chembridge-language',v)}catch{}})
document.documentElement.lang=language.value
document.title=`ChemBridge · ${copy[language.value].service}`
function stop(){audio?.pause();audio=null;if(audioUrl){URL.revokeObjectURL(audioUrl);audioUrl=null}playing.value=null;audioDone?.();audioDone=null}
function cleanup(){clearTimeout(slowTimer);requestController?.abort();version++;pending.value=false;voice.value='idle';voiceError.value='';recorder?.cancel();recorder=null;voiceDraft=false;modal.value=null;report.value=null;contacts.value=false;sourceSelection.value=null;endConvo();stop()}
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
function fillFaq(item){if(busy.value)return;if(item.product_id){equipmentId.value=item.equipment_id||'';productId.value=item.product_id}fill(item.q)}
function fill(text){if(busy.value)return;voice.value='idle';voiceDraft=false;question.value=text;nextTick(()=>input.value?.focus())}
async function scroll(){await nextTick();thread.value?.lastElementChild?.scrollIntoView({behavior:'smooth',block:'start'})}   // 긴 답변도 질문부터 읽게 맨 위에 맞춘다
async function send(retryMessage){
 const retry=retryMessage?.error?retryMessage:null
 const text=retry?retry.question:question.value.trim()
 const length=Array.from(text).length
 if(busy.value||length<api.contract.question.minLength||length>api.contract.question.maxLength)return
 const scope=retry||requestScope(topic.value,equipmentId.value,productId.value)
 if(scope.equipment_id&&!scope.product_id){question.value=text;equipmentId.value=scope.equipment_id;productId.value='';productRequired.value=true;await nextTick();scopePanel.value?.scrollIntoView({behavior:'smooth',block:'center'});return}
 productRequired.value=false
 stop();voice.value='idle';voiceError.value=''
 const id=++version
 const message=retry||{id,situation:situation.value,question:text,response:null,error:null,spoken:voiceDraft,topic:topic.value,language:language.value,...requestScope(topic.value,equipmentId.value,productId.value)}
 voiceDraft=false
 if(retry){message.id=id;message.error=null;message.diagnostic=null}
 else {question.value='';messages.value.push(message)}
 pending.value=true;requestController=new AbortController();scroll()
 try{
  const response=await api.ask({question:text,topic:message.topic,product_id:message.product_id,equipment_id:message.equipment_id,language:message.language},{signal:requestController.signal})
  if(version===id)messages.value.find(m=>m.id===id).response=response
 }catch(error){
  if(version!==id)return
  if(error.status===401){question.value=text;expire(message)}
   else {
    const failed=messages.value.find(m=>m.id===id)
    failed.error=error.code==='CANCELLED'?'cancelled':errorKey(error)
    failed.diagnostic=error.diagnostic
   }
  }finally{if(version===id){pending.value=false;scroll();const done=messages.value.find(m=>m.id===id);if(done?.spoken&&done.response)lastPlay=play(done)}}
}
async function chooseProduct(){await nextTick();scopePanel.value?.scrollIntoView({behavior:'smooth',block:'center'});productPicker.value?.open()}
function cancelRequest(){requestController?.abort()}
function editQuestion(message){if(busy.value)return;const scope=requestScope(message.topic,message.equipment_id,message.product_id);equipmentId.value=scope.equipment_id||'';productId.value=scope.product_id||'';fill(message.question)}
// 비상 안내는 서버(rag/prompt.py TEXT.emergency)가 언어별로 정해진 머리말로 시작한다
const EMERGENCY_PREFIXES=['긴급 안내:','紧急提示：','Thông báo khẩn cấp:','Emergency notice:','សេចក្តីជូនដំណឹងបន្ទាន់៖']
function isEmergency(response){return response.handoff&&EMERGENCY_PREFIXES.some(prefix=>response.answer.startsWith(prefix))}
function sourceUrl(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)?url.href:null}catch{return null}}

// 음성 모드: 녹음 → STT(/voice/stt) → 질문 확인·수정 → 전송 → 답변을 TTS(/voice/tts)로 자동 재생
function startVoice(){if(busy.value)return;stop();voiceError.value='';modal.value='voice'}
function voiceFail(error){
 voice.value='idle'
 if(error.status===401){expire({question:question.value,topic:topic.value,...requestScope(topic.value,equipmentId.value,productId.value)});return}
 voiceError.value=error.code==='MIC_DENIED'?'micDenied':error.code==='VOICE_UNSUPPORTED'?'voiceUnsupported':(error.code==='VOICE_EMPTY'||error.status===422)?'voiceEmpty':'voiceFailed'
}
async function beginRecording(){
 modal.value=null;voiceError.value='';const id=++version
 try{const started=await api.startRecording();if(id!==version){started.cancel();return}recorder=started;voice.value='recording'}
 catch(error){if(id===version)voiceFail(error)}
}
async function finish(){
 if(!recorder)return
 const id=++version,current=recorder;recorder=null;voice.value='processing'
 try{
  const recording=await current.stop()
  const result=await api.transcribe({...recording,language:language.value})
  if(id!==version)return
  question.value=result.text;voiceDraft=true;voice.value='review';nextTick(()=>input.value?.focus())
 }catch(error){if(id===version)voiceFail(error)}
}
function cancel(){version++;recorder?.cancel();recorder=null;voice.value='idle'}
async function play(message){
 if(pending.value||['recording','processing'].includes(voice.value))return
 if(playing.value===message.id)return stop()
 stop();voiceError.value=''
 const text=api.speechText(message.response.answer,apiCopy[message.language].speechTail)
 if(!text)return
 const id=message.id;playing.value=id
 try{
  const blob=await api.speak({text,language:message.language})
  if(playing.value!==id)return
  audioUrl=URL.createObjectURL(blob);audio=new Audio(audioUrl);audio.onended=stop
  const finished=new Promise(resolve=>{audioDone=resolve})
  await audio.play()
  await finished   // 음성 대화 모드는 다 읽은 뒤에 다시 듣는다
 }catch(error){if(playing.value===id){stop();if(error.status===401){expire(message);return}voiceError.value='speakFailed'}}
}
// ── 음성 대화 모드 ──
async function startConvo(){
 if(busy.value||!voiceReady.value||convo.value)return
 stop();voiceError.value='';convo.value={state:'starting',text:'',countdown:0,answer:''}
 try{listener=await api.startListening({onSpeechStart:convoHeard,onUtterance:convoUtterance});if(convo.value)convo.value.state='listening';else listener.stop()}
 catch(error){convo.value=null;listener=null;voiceFail(error)}
}
function endConvo(){clearInterval(convoTimer);listener?.stop();listener=null;if(convo.value){convo.value=null;stop()}}
function convoHeard(){if(convo.value&&['listening','confirm'].includes(convo.value.state)){clearInterval(convoTimer);convo.value.state='hearing'}}
async function convoUtterance(recording){
 if(!convo.value)return
 convo.value.state='transcribing'
 let text
 try{text=(await api.transcribe({...recording,language:language.value})).text}
 catch(error){if(!convo.value)return;if(error.status===401){endConvo();voiceFail(error);return}convo.value.state='listening';convo.value.missed=true;return}
 if(!convo.value)return
 const command=api.voiceCommand(text)
 if(command==='exit')return endConvo()
 if(command==='cancel'||!text){clearInterval(convoTimer);Object.assign(convo.value,{state:'listening',text:'',missed:false});return}
 Object.assign(convo.value,{state:'confirm',text,countdown:3,missed:false})
 clearInterval(convoTimer)
 convoTimer=setInterval(()=>{if(!convo.value)return clearInterval(convoTimer);if(--convo.value.countdown<=0){clearInterval(convoTimer);convoSend()}},1000)
}
function convoCancel(){if(!convo.value)return;clearInterval(convoTimer);if(convo.value.state==='speaking')return stop();Object.assign(convo.value,{state:'listening',text:''})}
async function convoSend(){
 if(!convo.value?.text)return
 clearInterval(convoTimer);listener?.pause()
 convo.value.state='answering';question.value=convo.value.text;voiceDraft=true;lastPlay=null
 await send()
 if(!convo.value)return
 const answered=messages.value[messages.value.length-1]
 convo.value.answer=answered?.response?api.speechText(answered.response.answer):''
 if(lastPlay){convo.value.state='speaking';await lastPlay}
 if(!convo.value)return
 Object.assign(convo.value,{state:'listening',text:''});listener?.resume()
}
function escape(e){if(e.key==='Escape'){modal.value=null;endConvo()}}
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
<main v-else key="chat" class="clear-chat-main" :class="{'has-guide':guideShown}">
  <GuideViewer v-if="guideShown" :src="guideUrl" :title="guide.title" :source="guide.source" :language="language" />
  <div class="chat-pane">
  <div class="clear-chat-heading">
    <div class="clear-chat-title"><button v-spring class="chat-back" :aria-label="t.back" @click="navigate('home')"><Icon name="back" :size="22" /></button><h1>{{title}}</h1></div>
    <div class="chat-heading-actions"><button v-if="situation==='emergency' && !isLaw" type="button" class="emergency-btn" @click="contacts=true"><Icon name="alert" :size="18" />{{c.emergency}}</button><button v-if="guideUrl" type="button" class="guide-btn guide-toggle" :aria-pressed="guideOpen" @click="guideOpen=!guideOpen">{{guideOpen?c.guideHide:c.guideShow}}</button><a v-if="guideUrl" class="guide-btn" :href="guideUrl" target="_blank" rel="noopener noreferrer">{{c.view}}</a><a v-if="guideUrl" class="guide-btn filled" :href="guideUrl" :download="`${title}.pdf`">{{c.download}}</a><button v-spring class="chat-new" :aria-label="t.newChat" @click="open(situation,topic)"><Icon name="plus" :size="18" /><span>{{t.newChat}}</span></button></div>
  </div>

  <div class="chat-topic-picker" role="group" :aria-label="a.topics"><button v-for="(value,key) in api.contract.topics" :key="key" type="button" :aria-pressed="topic===value" :disabled="busy" @click="changeTopic(value)">{{a[key]}}</button></div>
  <div v-if="topic===api.contract.topics.chemical" class="chat-scope" :class="{'is-compact':messages.length}" ref="scopePanel">
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
      <div v-if="situation==='free'&&!equipmentId&&!productId" class="faq-board" :aria-label="c.faqTitle">
        <p class="faq-sub">{{c.faqTitle}} · {{c.faqSub}}</p>
        <section v-for="group in faq" :key="group.key" class="faq-group"><h3>{{c.g[group.key]}}</h3><div class="faq-items"><button v-for="item in group.items" :key="item.q" type="button" class="faq-item" @click="fillFaq(item)"><span>{{item.q}}</span><Icon name="arrow" :size="16" /></button></div></section>
      </div>
      <div v-else class="clear-suggestions" :aria-label="t.suggestions"><button v-for="suggestion in suggestions" :key="suggestion" v-spring @click="fill(suggestion)"><span>{{suggestion}}</span><Icon name="arrow" :size="18" /></button></div>
    </div>
    <article v-for="message in messages" :key="message.id" class="clear-exchange">
      <div class="clear-question"><span v-if="scopeLabel(message)" class="chat-scope-context">{{scopeLabel(message)}}</span><p>{{message.question}}</p></div>
      <div class="clear-answer">
        <div class="clear-answer-heading"><span class="clear-assistant-icon"><Icon name="bridge" :size="23" /></span><b>ChemBridge</b></div>
        <div v-if="message.error" class="chat-api-error" :class="{'is-cancelled':message.error==='cancelled'}" role="alert">
          <h3><Icon name="alert" :size="22" />{{message.error==='cancelled'?feedback.cancelledTitle:(a[message.error+'Title']||feedback.failed)}}</h3>
          <p>{{message.error==='cancelled'?feedback.cancelled:a[message.error]}}</p>
          <p v-if="message.diagnostic?.requestId">{{a.errorReference}}: {{message.diagnostic.requestId}}</p>
          <div class="chat-error-actions"><button v-if="!['experimentStopped','experimentScope'].includes(message.error)" type="button" :disabled="busy" @click="send(message)">{{a.retry}}</button><button type="button" :disabled="busy" @click="editQuestion(message)">{{feedback.edit}}</button></div>
        </div>
        <div v-else-if="!message.response" class="chat-loading-state">
          <div class="clear-loading" role="status"><span class="clear-loading-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>{{slowResponse?feedback.slow:feedback.waiting}}</span></div>
          <div class="chat-loading-lines" aria-hidden="true"><i></i><i></i></div>
          <button type="button" class="chat-cancel-request" @click="cancelRequest">{{feedback.cancel}}</button>
        </div>
        <template v-else>
          <!-- 답변 보류·비상(handoff)은 눈에 띄게, 답변은 했지만 현장 확인이 필요한 경우(needs_review, MSDS·법령 답변이면 거의 항상)는 작게.
               보류 이유(근거 부족·검증 실패·제품 확인 등)는 서버 응답 머리글로 받아 제목과 설명으로 보여 준다 (박진근 오류 진단) -->
          <div v-if="isEmergency(message.response)" class="clear-alert is-hold emergency" role="alert"><Icon name="alert" :size="20" /><b>{{a.emergencyBadge}}</b><button type="button" class="emergency-btn" @click="contacts=true">{{c.emergency}}</button></div>
          <div v-else-if="message.response.handoff" class="clear-alert is-hold" role="alert"><Icon name="alert" :size="20" /><b>{{a[failureKey(message.response)+'Title']||a.handoff}}</b></div>
          <p v-else-if="message.response.needs_review" class="clear-review-note"><Icon name="check" :size="15" />{{a.answerNote}}</p>
          <p v-if="message.response.handoff&&!isEmergency(message.response)&&failureKey(message.response)" class="clear-review-note" role="note">{{a[failureKey(message.response)]}}</p>
          <p v-if="message.response.handoff&&message.response.diagnostic?.requestId&&['providerError','providerLimited','generationError'].includes(failureKey(message.response))" class="clear-review-note">{{a.errorReference}}: {{message.response.diagnostic.requestId}}</p>
          <!-- 소제목은 굵게, 출처 번호 [n] 은 작고 흐리게 (줄바꿈은 pre-wrap 이 살리므로 한 줄로 쓴다).
               보류 이유를 위에서 보여 줬으면 서버의 일반 보류 문구는 같은 말이라 숨긴다. 오류 번호는 연결·생성 오류일 때만. -->
          <p v-if="!(message.response.handoff&&!isEmergency(message.response)&&failureKey(message.response))" class="clear-answer-text"><template v-for="view in [answerView(message)]" :key="'view'"><template v-for="(line,li) in view.lines" :key="li"><template v-if="li">{{'\n'}}</template><span :class="{'clear-answer-subhead':line.heading,'clear-original':line.original}"><template v-for="(part,pi) in line.parts" :key="pi"><sup v-if="part.mark" class="clear-mark">{{part.mark}}</sup><template v-else>{{part.text}}</template></template></span><template v-if="line.more&&!message.expanded">{{'\n'}}<button type="button" class="clear-more" @click="message.expanded=true">{{c.more.replace('{n}',line.more)}}</button></template></template><template v-if="view.folds&&message.expanded">{{'\n'}}<button type="button" class="clear-more" @click="message.expanded=false">{{c.less}}</button></template></template></p>
          <div class="clear-answer-tools">
            <SourceLinks :sources="message.response.sources" :language="language" @open="sourceSelection=$event" />
            <button v-if="api.VOICE_LANGUAGES.includes(message.language)" v-spring class="clear-listen" :disabled="busy" :aria-pressed="playing===message.id" @click="play(message)"><Icon :name="playing===message.id?'stop':'sound'" :size="19" />{{playing===message.id?t.stop:a.listenAnswer}}</button>
            <button v-spring type="button" class="clear-report" @click="report=message"><Icon name="file" :size="19" />{{c.makeReport}}</button>
          </div>
        </template>
      </div>
    </article>
  </section>

  <div v-if="messages.length&&!busy" class="clear-suggestions chat-followup" :aria-label="t.suggestions"><button v-for="suggestion in suggestions" :key="suggestion" v-spring @click="fill(suggestion)"><span>{{suggestion}}</span><Icon name="arrow" :size="18" /></button></div>
  <form class="clear-composer" @submit.prevent="send">
    <label class="sr-only" for="question">{{t.send}}</label>
    <textarea id="question" ref="input" v-model="question" :disabled="busy" :maxlength="api.contract.question.maxLength" :placeholder="t.placeholder" :rows="messages.length?1:3" @keydown="onKey"></textarea>
    <div v-if="voice!=='idle'" class="clear-voice-state" role="status">
      <template v-if="voice==='recording'"><span class="clear-record-dot"></span><b>{{t.recording}}</b><span class="clear-wave" aria-hidden="true"><i v-for="n in 14" :key="n" :style="{animationDelay:`${n*.09}s`}"></i></span><button type="button" v-spring @click="finish">{{t.finish}}</button><button type="button" @click="cancel">{{t.cancel}}</button></template>
      <template v-else-if="voice==='processing'"><span class="clear-loading-dots"><i></i><i></i><i></i></span>{{t.converting}}</template>
      <template v-else><Icon name="check" :size="18" />{{t.reviewVoice}}</template>
    </div>
    <p v-if="voiceError" class="chat-voice-error" role="alert"><Icon name="alert" :size="18" />{{a[voiceError]}}</p>
    <div class="clear-composer-controls"><button v-spring type="button" class="clear-mic" :disabled="busy||!voiceReady" :title="voiceReady?'':a.voiceLanguage" @click="startVoice"><Icon name="mic" :size="21" /><span>{{a.voiceInput}}</span></button><button v-spring type="button" class="clear-mic convo-start" :disabled="busy||!voiceReady" :title="voiceReady?a.convoHint:a.voiceLanguage" @click="startConvo"><Icon name="sound" :size="21" /><span>{{a.convoStart}}</span></button><button v-spring type="submit" class="clear-send" :disabled="busy||Array.from(question.trim()).length<api.contract.question.minLength" :aria-label="t.send"><Icon name="send" :size="23" /></button></div>
  </form>
  </div>
</main>
</Transition>
<section v-if="convo" class="voice-convo" role="dialog" aria-modal="true" :aria-label="a.convoStart" @click.self="convoCancel">
  <div class="voice-convo-orb" :class="`is-${convo.state}`" aria-hidden="true" @click="convoCancel"><Icon :name="convo.state==='speaking'?'sound':'mic'" :size="56" /></div>
  <p class="voice-convo-state" role="status">{{convo.state==='confirm'?a.convoConfirm.replace('{n}',convo.countdown):a[`convo_${convo.state}`]}}</p>
  <p v-if="convo.missed&&convo.state==='listening'" class="voice-convo-missed">{{a.convoMissed}}</p>
  <p v-if="convo.text" class="voice-convo-text">“{{convo.text}}”</p>
  <div v-if="convo.state==='confirm'" class="voice-convo-actions"><button type="button" class="primary" @click="convoSend">{{a.convoSendNow}}</button><button type="button" @click="convoCancel">{{a.convoCancel}}</button></div>
  <p v-if="convo.answer&&['speaking','listening'].includes(convo.state)" class="voice-convo-answer">{{convo.answer}}</p>
  <p class="voice-convo-hint">{{a.convoHint}}</p>
  <button type="button" class="voice-convo-end" @click="endConvo">{{a.convoEnd}}</button>
</section>
<SourceViewer v-if="sourceSelection" :selection="sourceSelection" :language="language" @close="sourceSelection=null" />
<EmergencyContacts v-if="contacts" :language="language" @close="contacts=false" />
<ReportModal v-if="report" :message="report" :title="title" :scope="scopeLabel(report)" :language="language" @close="report=null" @auth-expired="expire" />
<div v-if="modal" class="modal-backdrop" @click.self="modal=null"><section ref="modalElement" @keydown="trapFocus" role="dialog" aria-modal="true" aria-labelledby="modal-title" class="modal"><span class="modal-icon"><Icon :name="modal==='voice'?'mic':'file'" :size="28"/></span><h2 id="modal-title">{{modal==='voice'?t.permissionTitle:t.sourceTitle}}</h2><p>{{modal==='voice'?t.permissionBody:t.sourceBody}}</p><div class="modal-actions"><button class="secondary" autofocus @click="modal=null">{{t.close}}</button><button v-if="modal==='voice'" class="primary" @click="beginRecording">{{t.startVoice}}<Icon name="arrow" :size="17"/></button></div></section></div>
</div>
</template>
