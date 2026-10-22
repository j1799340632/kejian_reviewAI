<template>
  <section :class="compact ? 'py-6' : 'pt-12 sm:pt-16 pb-10'">
    <div class="max-w-6xl mx-auto px-4 sm:px-6">
      <div v-if="!compact" class="mb-8 sm:mb-10">
        <p class="text-xs font-medium tracking-[0.2em] text-primary mb-4">课程 · 提问 · 核对</p>
        <h1 class="text-3xl sm:text-[42px] leading-tight font-semibold tracking-tight">把课程里的问题，<br class="sm:hidden" />带回原文核对。</h1>
        <p class="text-sm sm:text-base text-text-secondary leading-7 mt-4 max-w-2xl">打开一节课，围绕知识点提问。回答附上字幕来源和视频时间点，方便复习时确认每一步。</p>
      </div>
      <form @submit.prevent="onSubmit" aria-label="打开课程" class="max-w-4xl">
        <label for="video-url-input" class="block text-xs font-medium text-text-secondary mb-2">课程视频链接</label>
        <div class="flex flex-col sm:flex-row gap-2">
          <input id="video-url-input" v-model="url" type="url" placeholder="粘贴 B 站或 YouTube 课程链接"
            class="min-w-0 w-full sm:w-auto sm:flex-1 h-12 shrink-0 px-4 rounded-xl border border-border bg-white text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            :disabled="loading" autocomplete="url" required />
          <button type="submit" :disabled="loading || !url.trim()"
            class="h-12 px-6 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors">
            {{ loading ? '正在打开…' : '打开课程' }}
          </button>
        </div>
        <p v-if="error" role="alert" class="text-sm text-error mt-3">{{ error }}</p>
      </form>
      <div v-if="!compact" class="flex flex-wrap items-center gap-x-4 gap-y-2 mt-4 text-xs text-text-secondary">
        <span>示例课程</span>
        <button v-for="example in examples" :key="example.label" @click="url = example.url" :disabled="loading"
          class="underline underline-offset-4 decoration-border hover:text-primary cursor-pointer disabled:opacity-50">{{ example.label }}</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
defineProps({ loading: Boolean, compact: Boolean, error: { type: String, default: '' } })
const emit = defineEmits(['parse'])
const url = ref('')
const examples = [
  { label: 'LangChain · RAG 工作流程', url: 'https://www.bilibili.com/video/BV1rv7A6oEeP/?p=103' },
  { label: '李宏毅 · 生成式 AI 原理', url: 'https://www.bilibili.com/video/BV1pLWFz1Eew/?p=1' },
]
function onSubmit() {
  const trimmed = url.value.trim()
  if (trimmed) emit('parse', trimmed)
}
</script>
