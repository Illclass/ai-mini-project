import test from 'node:test'
import assert from 'node:assert/strict'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter, chatLocation, loginDestination } from '../src/router.js'
import contract from '../src/api/contract.json' with { type: 'json' }

function setup(authenticated = true) {
  const session = { authenticated }
  const router = createAppRouter({ history:createMemoryHistory(), checkSession:async()=>session.authenticated })
  return { router, session }
}
function move(router, delta) {
  return new Promise(resolve=>{
    const off=router.afterEach(()=>{off();resolve()})
    router.go(delta)
  })
}

test('direct protected chat entry returns to the requested screen after login',async()=>{
  const {router,session}=setup(false)
  await router.push(chatLocation('storage',contract.topics.law))
  assert.equal(router.currentRoute.value.name,'login')
  const redirect=router.currentRoute.value.query.redirect
  assert.equal(redirect,'/chat/storage?topic=serious_accident_law')
  session.authenticated=true
  await router.replace(loginDestination(router,redirect))
  assert.equal(router.currentRoute.value.params.situation,'storage')
  assert.equal(router.currentRoute.value.query.topic,contract.topics.law)
})

test('back and forward restore home and each chat situation',async()=>{
  const {router}=setup()
  await router.push('/home')
  await router.push(chatLocation('before'))
  await router.push(chatLocation('handling'))
  await move(router,-1)
  assert.equal(router.currentRoute.value.params.situation,'before')
  await move(router,-1)
  assert.equal(router.currentRoute.value.name,'home')
  await move(router,1)
  assert.equal(router.currentRoute.value.params.situation,'before')
  await move(router,1)
  assert.equal(router.currentRoute.value.params.situation,'handling')
})

test('logout prevents access to protected views through browser history',async()=>{
  const {router,session}=setup()
  await router.push('/home')
  await router.push(chatLocation('after'))
  session.authenticated=false
  await router.replace('/login')
  await move(router,-1)
  assert.equal(router.currentRoute.value.name,'login')
})

test('root and unknown paths resolve to a valid authenticated home',async()=>{
  const {router}=setup()
  for(const path of ['/','/chat/not-a-situation','/missing']){
    await router.push(path)
    assert.equal(router.currentRoute.value.name,'home')
  }
})

test('invalid topic is normalized rather than sent to the API',async()=>{
  const {router}=setup()
  await router.push('/chat/storage?topic=invalid')
  assert.equal(router.currentRoute.value.fullPath,'/chat/storage')
})

test('login redirects reject external URLs and unknown internal routes',async()=>{
  const {router}=setup()
  for(const redirect of ['https://example.com','//example.com','/missing','/login',['/home']]){
    assert.deepEqual(loginDestination(router,redirect),{name:'home'})
  }
})

test('a failed session check never exposes a protected screen',async()=>{
  const router=createAppRouter({history:createMemoryHistory(),checkSession:async()=>{throw new Error('offline')}})
  await router.push('/chat/free')
  assert.equal(router.currentRoute.value.name,'login')
})

test('authenticated login entry redirects home without adding a login screen',async()=>{
  const {router}=setup()
  await router.push('/login')
  assert.equal(router.currentRoute.value.name,'home')
})
