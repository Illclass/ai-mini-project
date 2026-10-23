import test from 'node:test'
import assert from 'node:assert/strict'
import { createApi } from '../src/api/client.js'
import contract from '../src/api/contract.json' with {type:'json'}
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}})
const request={question:'작업 전 확인 사항',topic:contract.topics.chemical,product_id:null,equipment_id:null,language:contract.languages[0]}
const answer={answer:'확인하세요',sources:[{doc_id:'L2',section:'제2조',title:'법령',url:'https://www.law.go.kr/'}],needs_review:false,handoff:false,latency_ms:12}
test('login submits encoded credentials, sends cookies and checks session; ignores legacy redirect',async()=>{
 const calls=[]
 const api=createApi(async(path,options)=>{calls.push({path,...options});return json(path.endsWith('check')?{ok:true,username:'worker'}:{ok:true,redirect:'http://localhost:8008/index.html'})})
 await api.login({username:' worker ',password:'a&b=c'})
 assert.deepEqual(calls.map(c=>c.path),['/api/login','/api/auth/check'])
 assert.equal(calls[0].body.get('username'),'worker');assert.equal(calls[0].body.get('password'),'a&b=c')
 assert(calls.every(c=>c.credentials==='include'))
})
test('signup accepts Java redirect HTML and uses form encoding',async()=>{
 let options
 await createApi(async(path,o)=>{assert.equal(path,'/api/signup');options=o;return new Response('<html>login</html>')}).signup({username:'worker',password:'new-password'})
 assert.equal(options.body.get('username'),'worker');assert.equal(options.method,'POST');assert.equal(options.credentials,'include')
})
test('signup duplicate HTTP 400 stays available to UI',async()=>{
 await assert.rejects(createApi(async()=>new Response('username already exists',{status:400})).signup({username:'worker',password:'pass'}),e=>e.status===400)
})
test('login rejects missing authentication cookie',async()=>{
 await assert.rejects(createApi(async path=>path.endsWith('check')?json({},401):json({ok:true})).login({username:'a',password:'b'}),e=>e.code==='AUTH_COOKIE')
})
test('RAG sends exactly the shared contract fields and preserves source/handoff',async()=>{
 let sent
 const response=await createApi(async(path,options)=>{assert.equal(path,'/rag-query');assert.equal(options.credentials,'include');sent=JSON.parse(options.body);return json({...answer,handoff:true})}).ask({...request,internal:'omit'})
 assert.deepEqual(sent,request);assert.deepEqual(response.sources,answer.sources);assert.equal(response.handoff,true)
})
for(const status of [401,422,503])test(`RAG exposes HTTP ${status} to navigation/error UI`,async()=>{
 await assert.rejects(createApi(async()=>json({},status)).ask(request),e=>e.status===status)
})
test('rejects malformed responses instead of rendering fake answers',async()=>{
 for(const response of [json({answer:'missing fields'}),json({...answer,sources:[{title:'incomplete'}]}),new Response('<html/>'),new Response('{',{headers:{'Content-Type':'application/json'}})])
 await assert.rejects(createApi(async()=>response).ask(request),e=>e.code==='INVALID_RESPONSE')
})
test('distinguishes network failure, timeout and caller cancellation',async()=>{
 await assert.rejects(createApi(async()=>{throw new TypeError('offline')}).ask(request),e=>e.code==='NETWORK')
 const blocked=(_path,{signal})=>new Promise((_,reject)=>{if(signal.aborted)reject(new Error('aborted'));else signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true})})
 await assert.rejects(createApi(blocked,{timeoutMs:5}).ask(request),e=>e.code==='TIMEOUT')
 const controller=new AbortController();const promise=createApi(blocked).ask(request,{signal:controller.signal});controller.abort()
 await assert.rejects(promise,e=>e.code==='CANCELLED')
})
test('logout accepts HTML redirect but verifies session is actually gone',async()=>{
 await createApi(async path=>path.endsWith('check')?json({},401):new Response('<html/>')).logout()
 await assert.rejects(createApi(async path=>path.endsWith('check')?json({ok:true}):new Response('<html/>')).logout(),e=>e.code==='LOGOUT_FAILED')
})
test('both topics and all supported languages use the shared schema values',async()=>{
 const received=[]
 const api=createApi(async(_path,options)=>{received.push(JSON.parse(options.body));return json(answer)})
 for(const topic of Object.values(contract.topics))for(const language of contract.languages)await api.ask({...request,topic,language})
 assert.equal(received.length,Object.keys(contract.topics).length*contract.languages.length)
 assert(received.every(body=>Object.values(contract.topics).includes(body.topic)&&contract.languages.includes(body.language)))
})
test('optional product and equipment fields are serialized as null when not selected',async()=>{
 let payload
 const api=createApi(async(_path,options)=>{payload=JSON.parse(options.body);return json(answer)})
 const {product_id,equipment_id,...minimal}=request
 await api.ask(minimal)
 for(const field of contract.nullableFields)assert.equal(payload[field],null)
})
