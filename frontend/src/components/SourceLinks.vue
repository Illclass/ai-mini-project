<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'
import { groupSources } from '../api/sources'
import { locateSource } from '../api/source-pages'
import { sourceUrl } from '../api/report'
import { sourceCopy } from '../locales/sources'
const props = defineProps({ sources: { type: Array, default: () => [] }, language: { type: String, default: 'ko' } })
const emit = defineEmits(['open'])
const c = computed(() => sourceCopy[props.language] || sourceCopy.ko)
const groups = computed(() => groupSources(props.sources).map(group => {
 const refs = props.sources.filter(s => `${s.doc_id}\u0000${s.title}` === group.key)
 const seen = new Set()
 const targets = refs.map(locateSource).filter(target => target && !seen.has(target.sectionNo) && seen.add(target.sectionNo))
 return { ...group, targets }
}))
function open(group, target = group.targets[0]) { emit('open', { target, targets: group.targets, publisher: sourceUrl(group.url) }) }
</script>
<template>
 <template v-for="group in groups" :key="group.key">
  <div v-if="group.targets.length" class="source-group">
   <button type="button" class="clear-source source-document" @click="open(group)"><span class="clear-source-number">[{{ group.label }}]</span><span>{{ group.title }}</span><Icon name="file" :size="16" /></button>
   <div class="source-sections">
    <button v-for="target in group.targets" :key="target.sectionNo" type="button" :aria-label="`${group.title} · ${target.section} · ${c.original}`" @click="open(group,target)">{{ target.kind==='msds' && language!=='ko' ? `${c.section} ${target.sectionNo}` : target.label }}<Icon name="arrow" :size="14" /></button>
    <a v-if="sourceUrl(group.url)" :href="sourceUrl(group.url)" target="_blank" rel="noopener noreferrer">{{ c.publisher }}</a>
   </div>
  </div>
  <a v-else-if="sourceUrl(group.url)" class="clear-source" :href="sourceUrl(group.url)" target="_blank" rel="noopener noreferrer"><span class="clear-source-number">[{{group.label}}]</span><span>{{group.title}}<template v-if="group.sections.length"> · {{group.sections.join(' · ')}}</template></span><Icon name="arrow" :size="16" /></a>
  <span v-else class="clear-source"><span class="clear-source-number">[{{group.label}}]</span><span>{{group.title}}<template v-if="group.sections.length"> · {{group.sections.join(' · ')}}</template></span></span>
 </template>
</template>
