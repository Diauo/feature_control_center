<script setup lang="ts">
import type { Pagination } from '@/types'

const props = defineProps<{ pagination: Pagination; disabled?: boolean }>()
const emit = defineEmits<{ change: [page: number, pageSize: number] }>()

function changePage(page: number): void {
  if (props.disabled || page < 1 || page > props.pagination.totalPages) return
  emit('change', page, props.pagination.pageSize)
}

function changeSize(event: Event): void {
  emit('change', 1, Number((event.target as HTMLSelectElement).value))
}
</script>

<template>
  <nav class="pagination-bar" aria-label="列表分页">
    <span>共 {{ pagination.total }} 条</span>
    <label>每页
      <select :value="pagination.pageSize" :disabled="disabled" @change="changeSize">
        <option :value="20">20</option><option :value="50">50</option><option :value="100">100</option>
      </select>
    </label>
    <div class="pagination-bar__actions">
      <button type="button" :disabled="disabled || pagination.page <= 1" @click="changePage(pagination.page - 1)">上一页</button>
      <strong>{{ pagination.page }} / {{ pagination.totalPages }}</strong>
      <button type="button" :disabled="disabled || pagination.page >= pagination.totalPages" @click="changePage(pagination.page + 1)">下一页</button>
    </div>
  </nav>
</template>
