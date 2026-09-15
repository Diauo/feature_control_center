<script setup lang="ts">
import { motion } from 'motion-v'

export interface AnimatedTabOption { value: string; label: string; count?: number }
const props = defineProps<{ modelValue: string; options: AnimatedTabOption[]; ariaLabel?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

function select(value: string): void {
  if (value !== props.modelValue) emit('update:modelValue', value)
}

function move(event: KeyboardEvent, offset: number): void {
  const current = event.currentTarget as HTMLButtonElement
  const buttons = Array.from(current.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? [])
  const index = buttons.indexOf(current)
  if (index < 0 || buttons.length === 0) return
  const target = buttons[(index + offset + buttons.length) % buttons.length]
  target?.focus()
  target?.click()
}

function edge(event: KeyboardEvent, position: 'first' | 'last'): void {
  const current = event.currentTarget as HTMLButtonElement
  const buttons = Array.from(current.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? [])
  const target = position === 'first' ? buttons[0] : buttons.at(-1)
  target?.focus(); target?.click()
}
</script>

<template>
  <div class="section-tabs" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="tab"
      :aria-selected="modelValue === option.value"
      :tabindex="modelValue === option.value ? 0 : -1"
      :class="{ active: modelValue === option.value }"
      @click="select(option.value)"
      @keydown.left.prevent="move($event, -1)"
      @keydown.right.prevent="move($event, 1)"
      @keydown.home.prevent="edge($event, 'first')"
      @keydown.end.prevent="edge($event, 'last')"
    >
      <motion.span v-if="modelValue === option.value" class="section-tabs__indicator" layout-id="active-section-tab" />
      <span class="section-tabs__label">{{ option.label }}<small v-if="option.count !== undefined">{{ option.count }}</small></span>
    </button>
  </div>
</template>
