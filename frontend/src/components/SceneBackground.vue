<script setup>
defineProps({ reading: Boolean })
</script>

<template>
  <div class="scene-background" :class="{ reading }" aria-hidden="true">
    <div class="home-blue-haze"></div>
    <div class="home-warm-arc"></div>
    <div class="home-arc-edge"></div>
    <div class="home-grain"></div>
    <div class="scene-reading-light"></div>
  </div>
</template>

<style>
.app-shell { position: relative; isolation: isolate; min-height: 100svh; }
.scene-background { position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; background: linear-gradient(118deg, var(--chem-spectrum)); }
.scene-reading-light { position: absolute; inset: 0; background: linear-gradient(118deg, transparent 22%, #45488c44 62%, #394985cc 100%); opacity: 0; transition: opacity 1.65s cubic-bezier(.22, 1, .36, 1); }
.scene-background.reading .scene-reading-light { opacity: .62; }
.scene-background .home-warm-arc, .scene-background .home-arc-edge { transition: opacity 1.65s cubic-bezier(.22, 1, .36, 1); }
.scene-background.reading .home-warm-arc, .scene-background.reading .home-arc-edge { opacity: .35; }
.home-page { color: #fff; }
.clear-chat-header .home-brand, .clear-chat-header .home-language, .clear-chat-header .home-language select, .clear-chat-header .home-logout { transition: color 1.2s ease, background 1.2s ease, border-color 1.2s ease; }
.scene-enter-active { transition: opacity 1.1s cubic-bezier(.22, 1, .36, 1), transform 1.25s cubic-bezier(.22, 1, .36, 1); }
.scene-leave-active { transition: opacity .3s ease, transform .35s ease; pointer-events: none; }
.scene-enter-from { opacity: 0; transform: translateY(18px) scale(.994); }
.scene-leave-to { opacity: 0; transform: translateY(-8px) scale(.996); }
@media (prefers-reduced-motion: reduce) {
 .scene-reading-light, .scene-enter-active, .scene-leave-active, .clear-chat-header * { transition: none !important; }
 .scene-enter-from, .scene-leave-to { transform: none; }
}
</style>
