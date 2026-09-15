<script setup lang="ts">
import { ChevronDown, ChevronUp } from 'lucide'
import { MorphIcon } from 'morphicons/vue'

withDefaults(defineProps<{ title: string; description: string; open: boolean; dirty?: boolean; sectionId: string }>(), { dirty: false })
const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <article class="content-card settings-card settings-section" :class="{ 'settings-section--open': open }">
    <button class="settings-section__trigger" type="button" :aria-expanded="open" :aria-controls="`${sectionId}-panel`" @click="emit('toggle')">
      <span><strong>{{ title }}</strong><small>{{ description }}</small></span>
      <span class="settings-section__state"><em v-if="dirty">已修改</em><MorphIcon :icon="open ? ChevronUp : ChevronDown" :size="18" reduced-motion="user" aria-hidden="true" /></span>
    </button>
    <div :id="`${sectionId}-panel`" class="settings-section__grid" :aria-hidden="!open" :inert="open ? undefined : true">
      <div class="settings-section__body"><slot /></div>
    </div>
  </article>
</template>
