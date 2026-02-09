<template>
  <div v-if="enabled" class="meteor-container" aria-hidden="true">
    <div
      v-for="m in meteors"
      :key="m.id"
      class="meteor"
      :style="m.style"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const enabled = import.meta.env.VITE_METEOR_ENABLED !== 'false'
const count = parseInt(import.meta.env.VITE_METEOR_COUNT || '5', 10)
const minDur = parseFloat(import.meta.env.VITE_METEOR_MIN_DURATION || '0.8')
const maxDur = parseFloat(import.meta.env.VITE_METEOR_MAX_DURATION || '1.5')
const maxDelay = parseFloat(import.meta.env.VITE_METEOR_MAX_DELAY || '15')

// 用固定 seed 產生偽隨機，避免每次 re-render 閃爍
function seededRandom(seed) {
  const x = Math.sin(seed * 9301 + 49297) * 233280
  return x - Math.floor(x)
}

const meteors = computed(() => {
  if (!enabled) return []
  return Array.from({ length: count }, (_, i) => {
    const r1 = seededRandom(i + 1)
    const r2 = seededRandom(i + 100)
    const r3 = seededRandom(i + 200)
    const r4 = seededRandom(i + 300)

    const duration = minDur + r1 * (maxDur - minDur)
    const delay = r2 * maxDelay
    const left = 5 + r3 * 90       // 5%–95% horizontal
    const length = 60 + r4 * 100   // 60–160px tail length

    return {
      id: i,
      style: {
        left: `${left}%`,
        animationDuration: `${duration.toFixed(2)}s`,
        animationDelay: `${delay.toFixed(2)}s`,
        '--meteor-length': `${length.toFixed(0)}px`,
      },
    }
  })
})
</script>

<style scoped>
.meteor-container {
  position: fixed;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}

.meteor {
  position: absolute;
  top: -10%;
  width: 2px;
  height: var(--meteor-length, 80px);
  background: linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0),
    rgba(148, 210, 255, 0.4),
    rgba(255, 255, 255, 0.8)
  );
  border-radius: 999px;
  transform: rotate(215deg);
  animation: meteor-fall linear infinite;
  opacity: 0;
  filter: drop-shadow(0 0 3px rgba(148, 210, 255, 0.6));
}

@keyframes meteor-fall {
  0% {
    opacity: 0;
    transform: rotate(215deg) translateY(0);
  }
  5% {
    opacity: 1;
  }
  60% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: rotate(215deg) translateY(calc(100vh + 200px));
  }
}
</style>
