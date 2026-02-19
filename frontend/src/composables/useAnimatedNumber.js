import { ref, watch, onUnmounted } from 'vue'

/**
 * Composable that animates a number from its previous value to a new target.
 * Uses requestAnimationFrame with easeOutExpo for smooth counting.
 *
 * @param {import('vue').Ref<number>} source - reactive source number
 * @param {object} opts
 * @param {number} opts.duration - animation duration in ms (default 800)
 * @returns {{ displayed: import('vue').Ref<number> }}
 */
export function useAnimatedNumber(source, { duration = 800 } = {}) {
  const displayed = ref(0)
  let raf = null
  let startTime = null
  let from = 0
  let to = 0

  function easeOutExpo(t) {
    return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)
  }

  function tick(now) {
    if (!startTime) startTime = now
    const elapsed = now - startTime
    const progress = Math.min(elapsed / duration, 1)
    const eased = easeOutExpo(progress)

    displayed.value = Math.round(from + (to - from) * eased)

    if (progress < 1) {
      raf = requestAnimationFrame(tick)
    } else {
      displayed.value = to
    }
  }

  watch(
    source,
    (newVal) => {
      const target = typeof newVal === 'number' ? newVal : 0
      if (raf) cancelAnimationFrame(raf)
      from = displayed.value
      to = target
      startTime = null
      raf = requestAnimationFrame(tick)
    },
    { immediate: true }
  )

  onUnmounted(() => {
    if (raf) cancelAnimationFrame(raf)
  })

  return { displayed }
}
