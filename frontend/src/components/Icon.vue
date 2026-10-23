<script setup>
defineProps({ name: String, size: { type: Number, default: 22 } })
const paths = {
 bridge: 'M4 18V8l8-4 8 4v10l-8 4-8-4Z M4 8l8 4 8-4 M12 12v10 M8 10v7 M16 10v7',
 arrow: 'M5 12h14 M13 6l6 6-6 6', back: 'M19 12H5 M11 6l-6 6 6 6',
 check: 'M9 12l2 2 4-4 M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z',
 flask: 'M9 3h6 M10 3v7L4 20h16l-6-10V3 M8 14h8',
 box: 'M3 7l9-4 9 4-9 4-9-4Z M3 7v11l9 4 9-4V7 M12 11v11',
 activity: 'M3 12h4l3-8 4 16 3-8h4',
 tidy: 'M4 7h16 M9 7V4h6v3 M6 7l1 14h10l1-14 M10 11v6 M14 11v6',
 alert: 'M12 3L2 21h20L12 3Z M12 9v5 M12 17h.01',
 mic: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0V5Z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M9 22h6',
 send: 'M12 19V5 M6 11l6-6 6 6',
 sound: 'M11 5L6 9H3v6h3l5 4V5Z M15 8a6 6 0 0 1 0 8 M18 5a10 10 0 0 1 0 14',
 file: 'M14 2H5v20h14V7l-5-5Z M14 2v5h5 M8 12h8 M8 16h6',
 globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z M3 12h18 M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z',
 logout: 'M9 4H4v16h5 M10 12h11 M17 8l4 4-4 4',
 chat: 'M21 4H3v14h5l4 4v-4h9V4Z M7 9h10 M7 13h6',
 close: 'M6 6l12 12 M18 6L6 18', eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
 lock: 'M5 10h14v11H5V10Z M8 10V6a4 4 0 0 1 8 0v4 M12 14v3',
 stop: 'M6 6h12v12H6V6Z', plus: 'M12 5v14 M5 12h14'
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.chat" /></svg></template>
