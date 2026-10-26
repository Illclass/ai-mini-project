import { onMounted, onBeforeUnmount } from 'vue'
export function useDialog(element, close) {
  let trigger, oldOverflow
  function key(event) {
    if (event.key === 'Escape') { event.preventDefault(); close(); return }
    if (event.key !== 'Tab') return
    const items = [...element.value.querySelectorAll('button:not(:disabled),a[href],input,select,textarea,[tabindex="0"]')].filter(el => el.getClientRects().length)
    const first = items[0], last = items.at(-1)
    if (!first) { event.preventDefault(); element.value.focus(); return }
    if (event.shiftKey && (document.activeElement === first || !element.value.contains(document.activeElement))) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && (document.activeElement === last || !element.value.contains(document.activeElement))) { event.preventDefault(); first.focus() }
  }
  onMounted(() => {
    trigger = document.activeElement; oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.getElementById('app')?.setAttribute('inert', '')
    element.value.addEventListener('keydown', key)
    element.value.querySelector('button')?.focus()
  })
  onBeforeUnmount(() => {
    element.value?.removeEventListener('keydown', key)
    document.body.style.overflow = oldOverflow
    document.getElementById('app')?.removeAttribute('inert')
    if (trigger?.isConnected) trigger.focus()
  })
}
