<script setup lang="ts">
import { Check, ChevronDown, Search } from '@lucide/vue'
import {
  ComboboxAnchor,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxPortal,
  ComboboxRoot,
  ComboboxTrigger,
  ComboboxViewport,
} from 'reka-ui'

export interface ComboboxOption {
  value: string
  label: string
  description?: string
}

const props = withDefaults(defineProps<{
  modelValue: string
  options: ComboboxOption[]
  placeholder?: string
  disabled?: boolean
  searchPlaceholder?: string
  appearance?: 'toolbar' | 'form'
}>(), {
  placeholder: '请选择',
  disabled: false,
  searchPlaceholder: '搜索…',
  appearance: 'form',
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

function labelFor(value: unknown): string {
  const normalized = typeof value === 'string' ? value : ''
  return props.options.find((item) => item.value === normalized)?.label ?? props.placeholder
}

function selectValue(value: unknown): void {
  if (typeof value === 'string') emit('update:modelValue', value)
}
</script>

<template>
  <ComboboxRoot
    :model-value="modelValue"
    :disabled="disabled"
    class="app-combobox"
    :class="`app-combobox--${appearance}`"
    @update:model-value="selectValue"
  >
    <ComboboxAnchor class="app-combobox__anchor">
      <ComboboxTrigger class="app-combobox__trigger" :aria-label="`${labelFor(modelValue)}，展开选项`">
        <span class="app-combobox__value">{{ labelFor(modelValue) }}</span>
        <ChevronDown class="app-combobox__chevron" :size="15" aria-hidden="true" />
      </ComboboxTrigger>
    </ComboboxAnchor>
    <ComboboxPortal>
      <ComboboxContent class="app-combobox__content" position="popper" :side-offset="6">
        <div class="app-combobox__search-row">
          <Search :size="15" aria-hidden="true" />
          <ComboboxInput class="app-combobox__input" :placeholder="searchPlaceholder" :aria-label="searchPlaceholder" :display-value="() => ''" />
        </div>
        <ComboboxViewport class="app-combobox__viewport">
          <ComboboxEmpty class="app-combobox__empty">没有匹配项</ComboboxEmpty>
          <ComboboxItem
            v-for="option in options"
            :key="option.value"
            class="app-combobox__item"
            :class="{ 'app-combobox__item--scope-all': option.value === '__all__' }"
            :value="option.value"
          >
            <span class="app-combobox__item-copy">
              <strong>{{ option.label }}</strong>
              <small v-if="option.description">{{ option.description }}</small>
            </span>
            <ComboboxItemIndicator class="app-combobox__indicator">
              <Check :size="15" aria-hidden="true" />
            </ComboboxItemIndicator>
          </ComboboxItem>
        </ComboboxViewport>
      </ComboboxContent>
    </ComboboxPortal>
  </ComboboxRoot>
</template>
