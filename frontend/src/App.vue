<script setup lang="ts">
import { Toaster } from 'vue-sonner'
</script>

<template>
  <RouterView />
  <Toaster
    position="top-right"
    :visible-toasts="3"
    :gap="10"
    :offset="20"
    close-button
    class="fcc-toaster"
  />
</template>
