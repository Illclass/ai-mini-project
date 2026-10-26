import { createRouter, createWebHistory } from 'vue-router'
import contract from './api/contract.json' with { type: 'json' }

export const situations = ['before', 'handling', 'storage', 'during', 'after', 'emergency', 'free']
const shell = { render: () => null }

export function chatLocation(situation, topic = contract.topics.chemical) {
  return { name: 'chat', params: { situation: situations.includes(situation) ? situation : 'free' },
    query: topic === contract.topics.law ? { topic } : {} }
}

// Only allow a known internal screen as a post-login destination.
export function loginDestination(router, redirect) {
  if (typeof redirect !== 'string' || !redirect.startsWith('/') || redirect.startsWith('//')) return { name: 'home' }
  const target = router.resolve(redirect)
  return ['home', 'chat'].includes(target.name) ? target.fullPath : { name: 'home' }
}

export function createAppRouter({ checkSession, history = createWebHistory() }) {
  const router = createRouter({ history, routes: [
    { path: '/', redirect: { name: 'home' } },
    { path: '/login', name: 'login', component: shell },
    { path: '/home', name: 'home', component: shell },
    { path: `/chat/:situation(${situations.join('|')})`, name: 'chat', component: shell },
    { path: '/:pathMatch(.*)*', redirect: { name: 'home' } },
  ] })
  router.beforeEach(async to => {
    let authenticated = false
    try { authenticated = await checkSession() } catch { /* Protected views stay closed on network errors. */ }
    if (!authenticated && to.name !== 'login') return { name: 'login', query: { redirect: to.fullPath }, replace: true }
    if (authenticated && to.name === 'login') return loginDestination(router, to.query.redirect)
    if (to.name === 'chat' && to.query.topic && !Object.values(contract.topics).includes(to.query.topic)) {
      return { ...chatLocation(to.params.situation), replace: true }
    }
  })
  return router
}
