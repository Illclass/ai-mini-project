// A short, damped spring for pointer and keyboard activation.
// WAAPI keeps the press responsive without adding a motion library.
export const spring = {
  mounted(element) {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    let animation
    let pressed = false
    function press() {
      if (element.disabled || pressed) return
      pressed = true
      animation?.cancel()
      element.dataset.pressed = 'true'
      if (!reduced.matches) {
        animation = element.animate(
          [{ transform: 'scale(1)' }, { transform: 'scale(.962)' }],
          { duration: 110, easing: 'ease-out', fill: 'forwards' },
        )
      }
    }
    function release() {
      if (!pressed) return
      pressed = false
      const current = getComputedStyle(element).transform
      animation?.cancel()
      delete element.dataset.pressed
      if (!reduced.matches) {
        animation = element.animate(
          [
            { transform: current, offset: 0 },
            { transform: 'scale(1.026)', offset: .33 },
            { transform: 'scale(.994)', offset: .57 },
            { transform: 'scale(1.003)', offset: .78 },
            { transform: 'scale(1)', offset: 1 },
          ],
          { duration: 570, easing: 'linear' },
        )
      }
    }
    function keydown(event) {
      if (['Enter', ' '].includes(event.key) && !event.repeat) press()
    }
    function keyup(event) {
      if (['Enter', ' '].includes(event.key)) release()
    }
    element.addEventListener('pointerdown', press)
    element.addEventListener('keydown', keydown)
    element.addEventListener('keyup', keyup)
    element.addEventListener('blur', release)
    window.addEventListener('pointerup', release)
    window.addEventListener('pointercancel', release)
    element._disposeSpring = () => {
      animation?.cancel()
      element.removeEventListener('pointerdown', press)
      element.removeEventListener('keydown', keydown)
      element.removeEventListener('keyup', keyup)
      element.removeEventListener('blur', release)
      window.removeEventListener('pointerup', release)
      window.removeEventListener('pointercancel', release)
    }
  },
  unmounted(element) { element._disposeSpring?.() },
}
