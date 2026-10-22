<template>
  <div class="min-h-screen flex flex-col bg-bg-main">
    <AppHeader />
    <main class="flex-1">
      <HeroSection @parse="handleParse" :loading="loading" :compact="!!videoData" :error="parseError" />
      <section v-if="videoData" class="max-w-6xl mx-auto px-4 sm:px-6 pb-10" aria-label="课程复习工作区">
        <div class="grid lg:grid-cols-[280px_minmax(0,1fr)] gap-5 items-start">
          <VideoResult :video="videoData" :videoUrl="currentUrl" :downloading="downloading" @download="handleDownload" />
          <VideoSummary :videoUrl="currentUrl" :videoTitle="videoData.title" :key="summaryKey" />
        </div>
      </section>
      <section v-else class="max-w-6xl mx-auto px-4 sm:px-6 pb-12">
        <div class="grid md:grid-cols-[1.4fr_1fr] gap-8 border-t border-border pt-8">
          <div>
            <h2 class="text-sm font-semibold text-text-primary mb-5">一次复习，三个动作</h2>
            <ol class="space-y-4">
              <li v-for="(step, index) in steps" :key="step.title" class="flex items-start gap-4">
                <span class="font-mono text-xs text-primary pt-1">0{{ index + 1 }}</span>
                <div><p class="text-sm font-medium">{{ step.title }}</p><p class="text-sm text-text-secondary mt-1">{{ step.detail }}</p></div>
              </li>
            </ol>
          </div>
          <aside class="md:border-l border-border md:pl-8">
            <h2 class="text-sm font-semibold mb-3">适合什么场景</h2>
            <p class="text-sm text-text-secondary leading-7">看过一节课，想重新找回概念、例子或步骤。先提出一个具体问题，再用来源片段核对老师的原话。</p>
            <p class="text-xs text-text-secondary leading-6 mt-4">当前围绕有字幕的 B 站与 YouTube 课程验证。自动字幕可能识别错误，重要结论请回到原视频确认。</p>
          </aside>
        </div>
      </section>
    </main>
    <AppFooter />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AppHeader from './components/AppHeader.vue'
import HeroSection from './components/HeroSection.vue'
import VideoResult from './components/VideoResult.vue'
import VideoSummary from './components/VideoSummary.vue'
import AppFooter from './components/AppFooter.vue'
import { parseVideo, downloadViaServer } from './api/video.js'

const loading = ref(false)
const downloading = ref(false)
const videoData = ref(null)
const currentUrl = ref('')
const summaryKey = ref(0)
const parseError = ref('')
const steps = [
  { title: '打开一节课程', detail: '粘贴课程视频链接，也可以先用示例体验。' },
  { title: '提出一个复习问题', detail: '询问概念、例子或步骤，查看带来源编号的回答。' },
  { title: '回到原视频核对', detail: '展开回答依据，点击时间点确认原文，再整理自己的笔记。' },
]

async function handleParse(url) {
  if (loading.value) return
  loading.value = true
  parseError.value = ''
  videoData.value = null
  currentUrl.value = url
  try {
    const res = await parseVideo(url)
    if (!res.success) throw new Error(res.error || '暂时无法打开课程，请检查链接后重试。')
    videoData.value = res.data
    summaryKey.value++
  } catch (err) {
    const detail = err.response?.data?.detail
    parseError.value = detail?.error || (typeof detail === 'string' ? detail : err.message)
  } finally {
    loading.value = false
  }
}

async function handleDownload(formatId) {
  downloading.value = true
  try {
    const response = await downloadViaServer(currentUrl.value, formatId)
    const disposition = response.headers['content-disposition']
    const match = disposition?.match(/filename\*?=(?:UTF-8'')?([^;\n]+)/i)
    const filename = match ? decodeURIComponent(match[1].replace(/"/g, '')) : 'video.mp4'
    const url = URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    alert('暂时无法下载视频，请稍后重试。')
  } finally {
    downloading.value = false
  }
}
</script>
