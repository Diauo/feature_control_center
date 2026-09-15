<script setup lang="ts">
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'motion-v'
import { onBeforeUnmount, ref } from 'vue'

defineProps<{ systemName: string }>()

const panel = ref<HTMLElement | null>(null)
const reduceMotion = useReducedMotion()
const pointerX = useMotionValue(0)
const pointerY = useMotionValue(0)
const smoothX = useSpring(pointerX, { stiffness: 150, damping: 26, mass: 0.65 })
const smoothY = useSpring(pointerY, { stiffness: 150, damping: 26, mass: 0.65 })
const backX = useTransform(smoothX, [-1, 1], [-2, 2])
const backY = useTransform(smoothY, [-1, 1], [-1.5, 1.5])
const frontX = useTransform(smoothX, [-1, 1], [-4, 4])
const frontY = useTransform(smoothY, [-1, 1], [-3, 3])
let frame = 0
let nextPointer: PointerEvent | null = null

function move(event: PointerEvent): void {
  if (reduceMotion.value || event.pointerType === 'touch') return
  nextPointer = event
  if (frame) return
  frame = window.requestAnimationFrame(() => {
    frame = 0
    const target = panel.value
    const point = nextPointer
    if (!target || !point) return
    const rect = target.getBoundingClientRect()
    const localX = Math.max(0, Math.min(rect.width, point.clientX - rect.left))
    const localY = Math.max(0, Math.min(rect.height, point.clientY - rect.top))
    target.style.setProperty('--spotlight-x', `${localX}px`)
    target.style.setProperty('--spotlight-y', `${localY}px`)
    target.style.setProperty('--spotlight-opacity', '1')
    pointerX.set((localX / rect.width - 0.5) * 2)
    pointerY.set((localY / rect.height - 0.5) * 2)
  })
}

function leave(): void {
  const target = panel.value
  target?.style.setProperty('--spotlight-opacity', '0')
  pointerX.set(0)
  pointerY.set(0)
}

onBeforeUnmount(() => {
  if (frame) window.cancelAnimationFrame(frame)
})
</script>

<template>
  <section ref="panel" class="gothic-panel" aria-labelledby="auth-visual-title" @pointermove="move" @pointerleave="leave">
    <div class="gothic-panel__grain" aria-hidden="true"></div>
    <motion.div
      class="gothic-panel__architecture gothic-panel__architecture--back"
      :style="reduceMotion ? undefined : { x: backX, y: backY }"
      :initial="reduceMotion ? false : { opacity: 0, scale: 0.985 }"
      :animate="{ opacity: 1, scale: 1 }"
      :transition="{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }"
      aria-hidden="true"
    >
      <svg viewBox="0 0 900 900" preserveAspectRatio="xMidYMid slice">
        <g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
          <path d="M450 74C251 195 171 372 171 613v214h558V613C729 372 649 195 450 74Z" />
          <path d="M450 119C287 224 219 384 219 619v165h462V619c0-235-68-395-231-500Z" />
          <path d="M450 119v665M219 619h462M278 418h344M257 523h386" />
          <circle cx="450" cy="365" r="118" />
          <circle cx="450" cy="365" r="73" />
          <path d="M450 247v236M332 365h236M367 282l166 166M533 282 367 448" />
          <path d="M450 292 486 365 450 438 414 365 450 292Z" />
          <path d="M219 619c74-44 151-66 231-66s157 22 231 66M219 706c74-40 151-60 231-60s157 20 231 60" />
          <path d="M104 827h692M137 855h626" />
        </g>
      </svg>
    </motion.div>

    <motion.div
      class="gothic-panel__architecture gothic-panel__architecture--front"
      :style="reduceMotion ? undefined : { x: frontX, y: frontY }"
      :initial="reduceMotion ? false : { opacity: 0 }"
      :animate="{ opacity: 1 }"
      :transition="{ duration: 0.8, delay: 0.08 }"
      aria-hidden="true"
    >
      <svg viewBox="0 0 900 900" preserveAspectRatio="xMidYMid slice">
        <g fill="none" stroke="currentColor" stroke-linecap="round">
          <path d="M77 831c70-61 92-127 66-198-13-36-5-74 24-112M823 831c-70-61-92-127-66-198 13-36 5-74-24-112" />
          <path d="M102 775c46-7 80-33 102-77M798 775c-46-7-80-33-102-77" />
          <path d="M122 690c31 3 57-8 79-35M778 690c-31 3-57-8-79-35" />
          <path d="M143 610c23-1 43-13 59-36M757 610c-23-1-43-13-59-36" />
          <path d="M98 832c20-18 34-38 41-61M802 832c-20-18-34-38-41-61" />
          <circle cx="450" cy="365" r="145" />
          <path d="M450 220c18 37 27 85 27 145s-9 108-27 145c-18-37-27-85-27-145s9-108 27-145Z" />
          <path d="M305 365c37-18 85-27 145-27s108 9 145 27c-37 18-85 27-145 27s-108-9-145-27Z" />
        </g>
      </svg>
    </motion.div>

    <div class="gothic-panel__spotlight" aria-hidden="true"></div>
    <motion.div
      class="gothic-panel__copy"
      :initial="reduceMotion ? false : { opacity: 0, y: 10 }"
      :animate="{ opacity: 1, y: 0 }"
      :transition="{ duration: 0.55, delay: 0.12, ease: [0.22, 1, 0.36, 1] }"
    >
      <p id="auth-visual-title">{{ systemName }}</p>
      <h2>脚本任务控制台</h2>
      <span>统一管理任务运行、实时日志、数据源与客户功能</span>
    </motion.div>
  </section>
</template>

<style scoped>
.gothic-panel {
  --spotlight-x: 50%;
  --spotlight-y: 50%;
  --spotlight-opacity: 0;
  position: relative;
  min-width: 0;
  overflow: hidden;
  isolation: isolate;
  background:
    radial-gradient(circle at 18% 16%, rgba(105, 31, 51, 0.18), transparent 31rem),
    radial-gradient(circle at 78% 68%, rgba(67, 55, 111, 0.15), transparent 36rem),
    linear-gradient(145deg, #07080a 0%, #101014 52%, #171017 100%);
  color: #f4f1f2;
}

.gothic-panel::after {
  position: absolute;
  inset: 0 0 0 auto;
  z-index: 5;
  width: 1px;
  background: rgba(255, 255, 255, 0.11);
  content: '';
}

.gothic-panel__grain {
  position: absolute;
  inset: 0;
  z-index: 1;
  opacity: 0.17;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.018) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.012) 1px, transparent 1px);
  background-size: 5px 5px, 7px 7px;
  mask-image: linear-gradient(to bottom, black, transparent 110%);
}

.gothic-panel__architecture {
  position: absolute;
  z-index: 2;
  top: -7%;
  right: -2%;
  width: min(78vw, 900px);
  height: 114%;
  color: rgba(214, 205, 209, 0.11);
  will-change: transform;
}

.gothic-panel__architecture svg {
  width: 100%;
  height: 100%;
}

.gothic-panel__architecture--back g { stroke-width: 1.25; }
.gothic-panel__architecture--front {
  z-index: 3;
  color: rgba(229, 218, 222, 0.075);
}
.gothic-panel__architecture--front g { stroke-width: 1; }

.gothic-panel__spotlight {
  position: absolute;
  inset: 0;
  z-index: 4;
  pointer-events: none;
  opacity: var(--spotlight-opacity);
  background:
    radial-gradient(
      circle 290px at var(--spotlight-x) var(--spotlight-y),
      rgba(236, 227, 231, 0.14),
      rgba(115, 65, 110, 0.075) 36%,
      transparent 72%
    );
  mix-blend-mode: screen;
  transition: opacity 240ms ease;
}

.gothic-panel__copy {
  position: absolute;
  z-index: 6;
  left: clamp(38px, 5vw, 80px);
  bottom: clamp(38px, 7vh, 74px);
  max-width: 410px;
}

.gothic-panel__copy p {
  margin: 0 0 20px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 14px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.gothic-panel__copy h2 {
  margin: 0 0 10px;
  color: #fff;
  font-size: clamp(31px, 3vw, 48px);
  font-weight: 680;
  letter-spacing: -0.045em;
}

.gothic-panel__copy span {
  color: rgba(242, 235, 238, 0.58);
  font-size: 14px;
  line-height: 1.7;
}

@media (max-width: 1199px) {
  .gothic-panel__architecture { right: -18%; width: 86vw; }
}

@media (max-width: 899px) {
  .gothic-panel { min-height: 168px; }
  .gothic-panel__architecture { top: -125%; right: -12%; width: 90vw; height: 290%; }
  .gothic-panel__copy { left: 24px; bottom: 24px; }
  .gothic-panel__copy p { margin-bottom: 8px; font-size: 12px; }
  .gothic-panel__copy h2 { margin-bottom: 0; font-size: 25px; }
  .gothic-panel__copy span { display: none; }
}

@media (hover: none), (pointer: coarse) {
  .gothic-panel__spotlight { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .gothic-panel__spotlight { display: none; }
  .gothic-panel__architecture { will-change: auto; }
}
</style>
