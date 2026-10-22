<template>
  <div class="bg-white rounded-2xl border border-border overflow-hidden min-w-0 flex flex-col">
        <!-- 标签页导航 -->
        <div class="flex overflow-x-auto border-b border-border-light" aria-label="复习工具">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="activeTab = tab.key"
            :class="[
              'flex shrink-0 items-center gap-2 px-4 py-4 text-sm font-medium transition-all relative cursor-pointer whitespace-nowrap',
              activeTab === tab.key
                ? 'text-primary'
                : 'text-text-secondary hover:text-text-primary'
            ]"
          >
            <span>{{ tab.label }}</span>
            <div
              v-if="activeTab === tab.key"
              class="absolute bottom-0 left-0 right-0 h-0.5 bg-primary"
            ></div>
          </button>
        </div>

        <!-- 内容区域 -->
        <div class="p-5 sm:p-6 min-h-[400px] flex-1 overflow-y-auto">
          <!-- 加载状态 -->
          <div v-if="loading && !summaryText && activeTab === 'summary'" class="flex flex-col items-center justify-center py-16">
            <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-4"></div>
            <p class="text-text-secondary text-sm">{{ loadingMessage }}</p>
          </div>

          <!-- 总结摘要 Tab -->
          <div v-show="activeTab === 'summary'">
            <p v-if="summaryScope?.partial" class="text-sm text-amber-700 mb-4">
              当前摘要仅覆盖部分字幕，可能遗漏视频后续内容，复习时请结合原视频核对。
            </p>
            <div
              v-if="summaryText"
              class="prose prose-slate prose-sm max-w-none summary-prose"
              v-html="renderedSummary"
            ></div>
            <div v-if="loading && summaryText" class="mt-2 inline-flex items-center gap-1.5 text-xs text-text-muted">
              <span class="w-1.5 h-1.5 bg-primary rounded-full animate-pulse"></span>
              AI 正在生成中...
            </div>
            <div v-if="!summaryText && !loading" class="py-12 text-center">
              <h2 class="text-base font-medium mb-2">先整理课程重点</h2>
              <p class="text-sm text-text-secondary mb-5">按需生成摘要和思维导图，复习时仍需核对原课程。</p>
              <button @click="startSummarize" class="px-4 py-2.5 rounded-lg bg-primary text-white text-sm cursor-pointer hover:bg-primary-dark">生成摘要与思维导图</button>
            </div>
            <button v-if="summaryText && !loading" @click="startSummarize" class="mt-4 text-xs text-primary hover:underline cursor-pointer">重新生成摘要与思维导图</button>
            <p v-if="summaryError" role="alert" class="mt-4 text-sm text-error">{{ summaryError }}</p>
          </div>

          <!-- 字幕文本 Tab -->
          <div v-show="activeTab === 'subtitle'">
            <div v-if="subtitleData.segments && subtitleData.segments.length > 0">
              <div class="flex items-center justify-between mb-4">
                <div class="text-sm text-text-secondary">
                  共 {{ subtitleData.segments.length }} 条字幕
                  <span v-if="subtitleData.language" class="ml-2 px-2 py-0.5 bg-primary-light text-primary rounded-full text-xs">
                    {{ subtitleData.subtitle_type === 'manual' ? '人工字幕' : '自动字幕' }} · {{ subtitleData.language }}
                  </span>
                </div>
                <div class="flex items-center gap-3">
                  <!-- 下载字幕按钮 -->
                  <div class="relative" ref="subtitleDropdownRef">
                    <button
                      @click="showSubtitleDropdown = !showSubtitleDropdown"
                      class="flex items-center gap-1.5 text-xs text-primary hover:text-primary-dark transition-colors cursor-pointer px-2.5 py-1.5 rounded-lg hover:bg-primary-light"
                    >
                      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      下载字幕
                      <svg class="w-3 h-3 transition-transform" :class="showSubtitleDropdown ? 'rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <div
                      v-if="showSubtitleDropdown"
                      class="absolute right-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-border-light py-1 z-10 min-w-[120px]"
                    >
                      <button
                        v-for="fmt in subtitleFormats"
                        :key="fmt.key"
                        @click="downloadSubtitle(fmt.key)"
                        class="w-full text-left px-3 py-2 text-xs text-text-primary hover:bg-bg-section transition-colors cursor-pointer flex items-center justify-between"
                      >
                        <span>{{ fmt.label }}</span>
                        <span class="text-text-muted">.{{ fmt.ext }}</span>
                      </button>
                    </div>
                  </div>
                  <button
                    @click="subtitleExpanded = !subtitleExpanded"
                    class="text-xs text-primary hover:text-primary-dark transition-colors cursor-pointer"
                  >
                    {{ subtitleExpanded ? '收起' : '展开全部' }}
                  </button>
                </div>
              </div>
              <div
                :class="['space-y-1 overflow-y-auto', subtitleExpanded ? 'max-h-none' : 'max-h-[500px]']"
              >
                <div
                  v-for="(seg, idx) in subtitleData.segments"
                  :key="idx"
                  class="flex gap-3 py-2 px-3 rounded-lg hover:bg-bg-section transition-colors group"
                >
                  <span class="flex-shrink-0 text-xs text-primary font-mono pt-0.5 min-w-[60px]">
                    {{ formatTime(seg.start) }}
                  </span>
                  <span class="text-sm text-text-primary leading-relaxed">{{ seg.text }}</span>
                </div>
              </div>
            </div>
            <div v-else-if="!subtitleLoading" class="flex flex-col items-center justify-center py-16 text-text-muted">
              <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p class="text-sm" :role="subtitleError ? 'alert' : undefined">{{ subtitleError || '该视频暂无可用字幕' }}</p>
              <button v-if="subtitleError" @click="loadSubtitles" class="mt-3 text-sm text-primary cursor-pointer hover:underline">重试读取字幕</button>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-16">
              <div class="w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-3"></div>
              <p class="text-text-muted text-sm">正在提取字幕...</p>
            </div>
          </div>

          <!-- 思维导图 Tab -->
          <div v-show="activeTab === 'mindmap'">
            <p v-if="summaryScope?.partial" class="text-sm text-amber-700 mb-4">
              当前思维导图仅覆盖部分字幕，不能作为整段课程的完整提纲。
            </p>
            <div v-if="mindmapMarkdown" class="relative">
              <!-- 工具栏 -->
              <div class="flex items-center justify-end gap-2 mb-3">
                <button
                  @click="downloadMindmapPng"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-primary hover:bg-primary-light transition-colors cursor-pointer"
                  title="下载 PNG 图片"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  PNG
                </button>
                <button
                  @click="downloadMindmapSvg"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-primary hover:bg-primary-light transition-colors cursor-pointer"
                  title="下载 SVG 矢量图"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  SVG
                </button>
                <button
                  @click="toggleFullscreen"
                  class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg text-primary hover:bg-primary-light transition-colors cursor-pointer"
                  :title="isFullscreen ? '退出全屏' : '全屏展示'"
                >
                  <svg v-if="!isFullscreen" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                  </svg>
                  <svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
                  </svg>
                  {{ isFullscreen ? '退出全屏' : '全屏' }}
                </button>
              </div>
              <div
                ref="mindmapContainer"
                class="mindmap-wrapper w-full border border-border-light rounded-xl bg-white overflow-hidden"
                :class="isFullscreen ? 'mindmap-fullscreen' : 'min-h-[500px]'"
              >
                <svg ref="mindmapSvg" class="w-full h-full" :style="isFullscreen ? 'height: 100%' : 'min-height: 500px'"></svg>
                <!-- 全屏模式下的退出按钮 -->
                <button
                  v-if="isFullscreen"
                  @click="toggleFullscreen"
                  class="fixed top-4 right-4 z-50 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white/90 backdrop-blur shadow-lg text-sm text-text-primary hover:bg-white transition-colors cursor-pointer border border-border-light"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  退出全屏
                </button>
              </div>
            </div>
            <div v-else-if="loading" class="flex flex-col items-center justify-center py-16">
              <div class="w-10 h-10 border-4 border-primary/20 border-t-primary rounded-full animate-spin mb-3"></div>
              <p class="text-text-muted text-sm">正在生成思维导图...</p>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-16 text-text-muted">
              <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
              <h2 class="text-base font-medium text-text-primary mb-2">把知识点串起来</h2>
              <p class="text-sm mb-5">生成后可以缩放查看，也可以导出图片。</p>
              <button @click="startSummarize" class="px-4 py-2.5 rounded-lg bg-primary text-white text-sm cursor-pointer hover:bg-primary-dark">生成摘要与思维导图</button>
              <p v-if="summaryError" role="alert" class="mt-4 text-sm text-error">{{ summaryError }}</p>
            </div>
          </div>

          <!-- AI 问答 Tab -->
          <div v-show="activeTab === 'qa'">
            <div class="space-y-4">
              <!-- 对话列表 -->
              <div
                ref="chatContainer"
                class="space-y-4 max-h-[520px] overflow-y-auto pr-1"
              >
                <div v-if="chatMessages.length === 0" class="flex flex-col items-center justify-center py-12 text-text-muted">
                  <svg class="w-12 h-12 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  <h2 class="text-base font-medium text-text-primary mb-2">从一个复习问题开始</h2>
                  <p class="text-sm text-text-secondary text-center leading-6">问一个概念、例子或步骤，<br />再展开回答依据，回到课程中核对。</p>
                  <button @click="chatInput = '这节课的主要步骤是什么？每一步有什么作用？'" class="mt-5 px-3 py-2 rounded-lg border border-border text-xs text-primary hover:bg-primary-light cursor-pointer">试问：这节课的主要步骤是什么？</button>
                </div>
                <div
                  v-for="(msg, idx) in chatMessagesWithCitations"
                  :key="idx"
                  :class="[
                    'flex',
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  ]"
                >
                  <div
                    :class="[
                      'px-4 py-2.5 rounded-2xl text-sm leading-relaxed',
                      msg.role === 'user'
                        ? 'max-w-[90%] sm:max-w-[80%] bg-primary text-white rounded-br-md'
                        : 'w-full sm:w-auto sm:max-w-[90%] bg-bg-section text-text-primary rounded-bl-md border border-border-light'
                    ]"
                  >
                    <div v-if="msg.role === 'assistant'" class="chat-prose prose prose-slate prose-sm max-w-none" v-html="renderMarkdown(msg.content)"></div>
                    <span v-else>{{ msg.content }}</span>
                    <p v-if="msg.loading && !msg.content" class="text-xs text-text-muted">
                      {{ msg.status || '正在准备回答…' }}
                    </p>
                    <details v-if="msg.citedSources.length" class="mt-3 pt-3 border-t border-border-light space-y-2">
                      <summary class="text-xs text-text-muted cursor-pointer">查看回答依据（{{ msg.citedSources.length }} 段）· 点击时间点核对原文</summary>
                      <div v-for="source in msg.citedSources" :key="source.id" class="text-xs leading-relaxed">
                        <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer" class="text-primary hover:underline">
                          [{{ source.id }}] {{ source.timestamp }} ↗
                        </a>
                        <span v-else class="text-primary">[{{ source.id }}] {{ source.timestamp }}</span>
                        <p class="text-text-secondary mt-1">{{ source.text }}</p>
                      </div>
                    </details>
                    <span
                      v-if="msg.role === 'assistant' && msg.loading"
                      class="inline-block w-1.5 h-4 bg-primary/60 rounded-sm animate-pulse ml-0.5 align-text-bottom"
                    ></span>
                  </div>
                </div>
              </div>

              <!-- 输入区域 -->
              <div class="flex gap-2 pt-3 border-t border-border-light">
                <input
                  v-model="chatInput"
                  @keydown.enter.prevent="sendQuestion"
                  type="text"
                  placeholder="输入你的问题..."
                  class="flex-1 h-11 px-4 rounded-xl border border-border bg-white text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                  :disabled="chatLoading"
                />
                <button
                  @click="sendQuestion"
                  :disabled="!chatInput.trim() || chatLoading"
                  class="h-11 px-5 rounded-xl bg-primary hover:bg-primary-dark text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1.5"
                >
                  <svg v-if="chatLoading" class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                  发送
                </button>
              </div>
            </div>
          </div>
        </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'
import { summarizeVideo, chatWithVideo, getSubtitles } from '../api/summarize.js'
import { getCitedSources } from '../utils/citations.js'

const props = defineProps({
  videoUrl: { type: String, required: true },
  videoTitle: { type: String, default: '' },
})

const tabs = [
  { key: 'qa', label: 'AI 问答' },
  { key: 'summary', label: '总结摘要' },
  { key: 'subtitle', label: '字幕文本' },
  { key: 'mindmap', label: '思维导图' },
]

const activeTab = ref('qa')
const loading = ref(false)
const loadingMessage = ref('正在提取视频字幕...')

const summaryText = ref('')
const summaryError = ref('')
const summaryScope = ref(null)
const subtitleData = ref({ segments: [], has_subtitle: false })
const subtitleLoading = ref(false)
const subtitlesLoaded = ref(false)
const subtitleError = ref('')
const subtitleExpanded = ref(false)
const mindmapMarkdown = ref('')
const mindmapSvg = ref(null)
const mindmapContainer = ref(null)
let markmapInstance = null

const chatMessages = ref([])
const chatMessagesWithCitations = computed(() => chatMessages.value.map(message => ({
  ...message,
  citedSources: getCitedSources(message.content, message.sources),
})))
const indexedVideoId = ref(null)
const chatInput = ref('')
const chatLoading = ref(false)
const chatContainer = ref(null)

const renderedSummary = ref('')

// 思维导图全屏状态
const isFullscreen = ref(false)

// 字幕下载下拉菜单
const showSubtitleDropdown = ref(false)
const subtitleDropdownRef = ref(null)
const subtitleFormats = [
  { key: 'srt', label: 'SRT 字幕', ext: 'srt' },
  { key: 'vtt', label: 'VTT 字幕', ext: 'vtt' },
  { key: 'txt', label: '纯文本', ext: 'txt' },
]

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

watch(activeTab, (tab) => {
  if (tab === 'subtitle') loadSubtitles()
})

watch(summaryText, (val) => {
  renderedSummary.value = renderMarkdown(val)
})

watch([activeTab, mindmapMarkdown], async ([tab, markdown]) => {
  if (tab === 'mindmap' && markdown) {
    await nextTick()
    renderMindmap(markdown)
  }
})

function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text)
}

function renderMindmap(md) {
  if (!mindmapSvg.value) return
  try {
    markmapInstance?.destroy()
    mindmapSvg.value.innerHTML = ''
    const transformer = new Transformer()
    const { root } = transformer.transform(md)
    markmapInstance = Markmap.create(mindmapSvg.value, { autoFit: true }, root)
  } catch (e) {
    console.warn('思维导图渲染失败:', e)
  }
}

function formatTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

// ===== 思维导图全屏 =====
function toggleFullscreen() {
  if (!mindmapContainer.value) return

  if (!isFullscreen.value) {
    if (mindmapContainer.value.requestFullscreen) {
      mindmapContainer.value.requestFullscreen()
    } else if (mindmapContainer.value.webkitRequestFullscreen) {
      mindmapContainer.value.webkitRequestFullscreen()
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen()
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen()
    }
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
  nextTick(() => {
    if (markmapInstance) {
      markmapInstance.fit()
    }
  })
}

// ===== 构建可导出的纯 SVG（将 foreignObject 替换为 text） =====
function buildExportableSvg() {
  if (!mindmapSvg.value) return null

  const cloned = mindmapSvg.value.cloneNode(true)

  cloned.querySelectorAll('[transform]').forEach(el => {
    const t = el.getAttribute('transform')
    if (t && t.includes('NaN')) {
      el.setAttribute('transform', 'translate(0,0) scale(1)')
    }
  })

  cloned.querySelectorAll('foreignObject').forEach(fo => {
    const textContent = fo.textContent?.trim() || ''
    if (!textContent) { fo.remove(); return }

    const x = parseFloat(fo.getAttribute('x')) || 0
    const y = parseFloat(fo.getAttribute('y')) || 0
    const h = parseFloat(fo.getAttribute('height')) || 20

    const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    textEl.setAttribute('x', String(x + 4))
    textEl.setAttribute('y', String(y + h / 2 + 5))
    textEl.setAttribute('font-size', '14')
    textEl.setAttribute('font-family', 'sans-serif')
    textEl.setAttribute('fill', '#333')
    textEl.setAttribute('dominant-baseline', 'middle')
    textEl.textContent = textContent

    fo.parentNode.replaceChild(textEl, fo)
  })

  return cloned
}

function serializeSvg(svgEl) {
  const serializer = new XMLSerializer()
  let svgString = serializer.serializeToString(svgEl)

  if (!svgString.includes('xmlns=')) {
    svgString = svgString.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"')
  }

  const styles = document.querySelectorAll('style')
  let markmapCss = ''
  styles.forEach(s => {
    if (s.textContent.includes('.markmap')) {
      markmapCss += s.textContent
    }
  })
  if (markmapCss) {
    svgString = svgString.replace('>', `><defs><style>${markmapCss}</style></defs>`)
  }

  return svgString
}

// ===== 获取思维导图完整内容边界（不受用户缩放/平移影响） =====
function getContentBBox() {
  const svgEl = mindmapSvg.value
  const gRoot = svgEl.querySelector('g')
  if (gRoot) {
    try {
      const bbox = gRoot.getBBox()
      if (bbox.width > 0 && bbox.height > 0) {
        const transform = gRoot.getAttribute('transform') || ''
        const translateMatch = transform.match(/translate\(\s*([-\d.e]+)\s*[,\s]\s*([-\d.e]+)\s*\)/)
        const scaleMatch = transform.match(/scale\(\s*([-\d.e]+)/)
        const tx = translateMatch ? parseFloat(translateMatch[1]) : 0
        const ty = translateMatch ? parseFloat(translateMatch[2]) : 0
        const sc = scaleMatch ? parseFloat(scaleMatch[1]) : 1
        return {
          x: bbox.x * sc + tx,
          y: bbox.y * sc + ty,
          width: bbox.width * sc,
          height: bbox.height * sc,
        }
      }
    } catch {}
  }
  try {
    const bbox = svgEl.getBBox()
    if (bbox.width > 0 && bbox.height > 0) return bbox
  } catch {}
  return { x: 0, y: 0, width: 800, height: 600 }
}

// ===== 为导出 SVG 设置完整内容的 viewBox =====
function setFullViewBox(svgClone) {
  const dims = getContentBBox()
  const padding = 60
  const vx = dims.x - padding
  const vy = dims.y - padding
  const vw = dims.width + padding * 2
  const vh = dims.height + padding * 2
  svgClone.setAttribute('viewBox', `${vx} ${vy} ${vw} ${vh}`)
  svgClone.setAttribute('width', String(vw))
  svgClone.setAttribute('height', String(vh))
  return { vw, vh }
}

// ===== 思维导图下载 PNG（4K 超清，完整内容） =====
async function downloadMindmapPng() {
  if (!mindmapSvg.value) return

  const exportSvg = buildExportableSvg()
  if (!exportSvg) return

  const { vw, vh } = setFullViewBox(exportSvg)
  const scale = Math.max(4, Math.ceil(3840 / vw))

  let svgString = serializeSvg(exportSvg)

  const canvas = document.createElement('canvas')
  canvas.width = vw * scale
  canvas.height = vh * scale
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const img = new Image()
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)

  return new Promise((resolve) => {
    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      canvas.toBlob((pngBlob) => {
        if (pngBlob) {
          triggerDownload(pngBlob, getSafeFilename() + ' - 思维导图.png')
        }
        resolve()
      }, 'image/png')
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      alert('PNG 导出失败，请使用 SVG 下载')
      resolve()
    }
    img.src = url
  })
}

// ===== 思维导图下载 SVG（完整内容，不受视口影响） =====
function downloadMindmapSvg() {
  if (!mindmapSvg.value) return

  const cloned = mindmapSvg.value.cloneNode(true)
  cloned.querySelectorAll('[transform]').forEach(el => {
    const t = el.getAttribute('transform')
    if (t && t.includes('NaN')) {
      el.setAttribute('transform', 'translate(0,0) scale(1)')
    }
  })

  setFullViewBox(cloned)

  const svgString = serializeSvg(cloned)
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  triggerDownload(blob, getSafeFilename() + ' - 思维导图.svg')
}

// ===== 字幕文件下载 =====
function downloadSubtitle(format) {
  showSubtitleDropdown.value = false
  const segments = subtitleData.value.segments
  if (!segments || segments.length === 0) return

  let content = ''
  let ext = format
  const filename = getSafeFilename()

  if (format === 'srt') {
    content = segmentsToSrt(segments)
  } else if (format === 'vtt') {
    content = segmentsToVtt(segments)
  } else {
    content = segmentsToTxt(segments)
  }

  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  triggerDownload(blob, `${filename} - 字幕.${ext}`)
}

function segmentsToSrt(segments) {
  return segments.map((seg, i) => {
    const start = formatSrtTime(seg.start)
    const end = formatSrtTime(seg.end)
    return `${i + 1}\n${start} --> ${end}\n${seg.text}\n`
  }).join('\n')
}

function segmentsToVtt(segments) {
  const header = 'WEBVTT\n\n'
  const body = segments.map((seg) => {
    const start = formatVttTime(seg.start)
    const end = formatVttTime(seg.end)
    return `${start} --> ${end}\n${seg.text}\n`
  }).join('\n')
  return header + body
}

function segmentsToTxt(segments) {
  return segments.map((seg) => seg.text).join('\n')
}

function formatSrtTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.round((seconds % 1) * 1000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`
}

function formatVttTime(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.round((seconds % 1) * 1000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

// ===== 通用工具函数 =====
function getSafeFilename() {
  return (props.videoTitle || '视频').replace(/[\\/*?:"<>|]/g, '_').substring(0, 80)
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function handleClickOutside(e) {
  if (subtitleDropdownRef.value && !subtitleDropdownRef.value.contains(e.target)) {
    showSubtitleDropdown.value = false
  }
}

async function loadSubtitles() {
  if (subtitleLoading.value || subtitlesLoaded.value) return
  subtitleLoading.value = true
  subtitleError.value = ''
  try {
    subtitleData.value = await getSubtitles(props.videoUrl)
    subtitlesLoaded.value = true
  } catch (err) {
    subtitleError.value = err.message
  } finally {
    subtitleLoading.value = false
  }
}

async function startSummarize() {
  if (loading.value) return
  loading.value = true
  summaryError.value = ''
  summaryText.value = ''
  summaryScope.value = null
  mindmapMarkdown.value = ''
  loadingMessage.value = '正在提取视频字幕...'

  try {
    await summarizeVideo(props.videoUrl, 'zh', {
      subtitle: (data) => {
        try {
          subtitleData.value = JSON.parse(data)
          subtitlesLoaded.value = true
          if (subtitleData.value.has_subtitle) {
            loadingMessage.value = 'AI 正在分析视频内容...'
          }
        } catch (e) { /* ignore parse error */ }
      },
      summary: (data) => {
        try { summaryText.value += JSON.parse(data) } catch { summaryText.value += data }
      },
      summary_scope: (data) => {
        try { summaryScope.value = JSON.parse(data) } catch {}
      },
      mindmap: (data) => {
        try {
          const parsed = JSON.parse(data)
          mindmapMarkdown.value = parsed.markdown || ''
        } catch (e) { /* ignore parse error */ }
      },
      done: () => {
        loading.value = false
      },
      error: (data) => {
        loading.value = false
        try {
          const parsed = JSON.parse(data)
          summaryError.value = parsed.message || '暂时无法生成摘要，请重试。'
        } catch (e) {
          summaryError.value = '暂时无法生成摘要，请重试。'
        }
      },
    })
  } catch (err) {
    loading.value = false
    summaryError.value = '暂时无法生成摘要，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function sendQuestion() {
  const question = chatInput.value.trim()
  if (!question || chatLoading.value) return

  chatInput.value = ''
  chatMessages.value.push({ role: 'user', content: question })

  const aiMessage = reactive({ role: 'assistant', content: '', loading: true, status: '', sources: [] })
  chatMessages.value.push(aiMessage)
  chatLoading.value = true

  await nextTick()
  scrollChatToBottom()

  try {
    await chatWithVideo(
      props.videoUrl,
      question,
      indexedVideoId.value,
      {
        video: (data) => {
          indexedVideoId.value = JSON.parse(data).video_id
        },
        status: (data) => {
          aiMessage.status = JSON.parse(data).message
        },
        sources: (data) => {
          aiMessage.sources = JSON.parse(data).sources || []
        },
        answer: (data) => {
          try { aiMessage.content += JSON.parse(data) } catch { aiMessage.content += data }
          scrollChatToBottom()
        },
        done: () => {
          aiMessage.loading = false
          chatLoading.value = false
        },
        error: (data) => {
          aiMessage.loading = false
          chatLoading.value = false
          try {
            const parsed = JSON.parse(data)
            aiMessage.content = '❌ ' + (parsed.message || '回答失败')
          } catch (e) {
            aiMessage.content = '❌ 回答失败'
          }
        },
      }
    )
    if (aiMessage.loading) {
      aiMessage.content += (aiMessage.content ? '\n\n' : '') + '连接已中断，请重新提问。'
    }
  } catch (err) {
    aiMessage.loading = false
    chatLoading.value = false
    aiMessage.content = '❌ 请求失败: ' + err.message
  } finally {
    aiMessage.loading = false
    chatLoading.value = false
  }
}

function scrollChatToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('webkitfullscreenchange', onFullscreenChange)
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  markmapInstance?.destroy()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
/* 总结摘要 Markdown 排版定制 */
.summary-prose :deep(h1) {
  font-size: 1.25rem;
  font-weight: 700;
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--color-text-primary);
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--color-primary-light);
}
.summary-prose :deep(h2) {
  font-size: 1.125rem;
  font-weight: 700;
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  color: var(--color-text-primary);
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-border-light);
}
.summary-prose :deep(h3) {
  font-size: 1rem;
  font-weight: 600;
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
  color: var(--color-text-primary);
}
.summary-prose :deep(p) {
  margin-bottom: 0.75rem;
  line-height: 1.8;
  color: var(--color-text-primary);
}
.summary-prose :deep(ul), .summary-prose :deep(ol) {
  margin-bottom: 0.75rem;
  padding-left: 1.5rem;
}
.summary-prose :deep(li) {
  margin-bottom: 0.35rem;
  line-height: 1.8;
}
.summary-prose :deep(li::marker) {
  color: var(--color-primary);
}
.summary-prose :deep(strong) {
  color: var(--color-text-primary);
  font-weight: 600;
}
.summary-prose :deep(hr) {
  margin: 1.5rem 0;
  border-color: var(--color-border-light);
}
.summary-prose :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  padding-left: 1rem;
  color: var(--color-text-secondary);
  font-style: normal;
  margin: 1rem 0;
  background: var(--color-bg-section);
  border-radius: 0 8px 8px 0;
  padding: 0.75rem 1rem;
}
.summary-prose :deep(code) {
  background: var(--color-bg-section);
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  font-size: 0.85em;
  color: var(--color-primary-dark);
  font-weight: 500;
}
.summary-prose :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 1rem;
  overflow-x: auto;
  margin: 1rem 0;
}
.summary-prose :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
  font-weight: normal;
}
.summary-prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
  font-size: 0.875rem;
}
.summary-prose :deep(th) {
  background: var(--color-bg-section);
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid var(--color-border);
}
.summary-prose :deep(td) {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border-light);
}
.summary-prose :deep(a) {
  color: var(--color-primary);
  text-decoration: none;
}
.summary-prose :deep(a:hover) {
  text-decoration: underline;
}

/* AI 问答 Markdown 排版（更紧凑） */
.chat-prose :deep(p) {
  margin-bottom: 0.5rem;
  line-height: 1.7;
}
.chat-prose :deep(p:last-child) {
  margin-bottom: 0;
}
.chat-prose :deep(ul), .chat-prose :deep(ol) {
  margin-bottom: 0.5rem;
  padding-left: 1.25rem;
}
.chat-prose :deep(li) {
  margin-bottom: 0.2rem;
  line-height: 1.7;
}
.chat-prose :deep(li::marker) {
  color: var(--color-primary);
}
.chat-prose :deep(code) {
  background: rgba(0,0,0,0.06);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.85em;
}
.chat-prose :deep(blockquote) {
  border-left: 2px solid var(--color-primary);
  padding-left: 0.75rem;
  color: var(--color-text-secondary);
  margin: 0.5rem 0;
}
.chat-prose :deep(strong) {
  font-weight: 600;
}

/* 思维导图：确保 markmap 的 foreignObject 文字正常显示 */
.mindmap-wrapper :deep(.markmap-foreign) {
  display: inline-block !important;
}
.mindmap-wrapper :deep(foreignObject) {
  overflow: visible !important;
}
.mindmap-wrapper :deep(foreignObject div) {
  font: 300 16px/20px sans-serif;
  color: #333;
}

/* 思维导图全屏样式 */
.mindmap-fullscreen {
  position: fixed !important;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  border-radius: 0 !important;
  border: none !important;
  background: #ffffff;
}
</style>
