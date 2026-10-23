<script setup>
import { computed, ref } from 'vue'
import { useDialog } from '../composables/useDialog'
import { clean } from '../locales/clean'
const props = defineProps({ language: { type: String, default: 'ko' } })
const emit = defineEmits(['close'])
const c = computed(() => clean[props.language] || clean.ko)
const list = [{ n: '119', k: 'fire', primary: true }, { n: '112', k: 'police' }, { n: '1350', k: 'labor' }]
const dialog = ref(null)
useDialog(dialog, () => emit('close'))
</script>

<template>
  <Teleport to="body"><div class="modal-backdrop" @click.self="emit('close')">
    <section ref="dialog" tabindex="-1" class="em-modal" role="dialog" aria-modal="true" aria-labelledby="em-title">
      <h2 id="em-title">{{ c.em.title }}</h2>
      <p class="em-note">{{ c.em.note }}</p>
      <ul class="em-list">
        <li v-for="item in list" :key="item.n">
          <div><b>{{ c.em[item.k] }}</b><span>{{ c.em[item.k + 'Desc'] }}</span></div>
          <a :href="`tel:${item.n}`" :class="{ primary: item.primary }">{{ item.n }}</a>
        </li>
        <li class="em-site"><div><b>{{ c.em.site1 }}</b><span>{{ c.em.siteDesc }}</span></div><em>{{ c.em.fill }}</em></li>
        <li class="em-site"><div><b>{{ c.em.site2 }}</b><span>{{ c.em.siteDesc }}</span></div><em>{{ c.em.fill }}</em></li>
      </ul>
      <button type="button" class="em-close" autofocus @click="emit('close')">{{ c.close }}</button>
    </section>
  </div></Teleport>
</template>
