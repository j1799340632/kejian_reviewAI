<template>
  <aside class="bg-white rounded-2xl border border-border overflow-hidden">
    <div class="relative aspect-video bg-primary-light">
      <img v-if="video.thumbnail" :src="thumbnailUrl" :alt="video.title" class="w-full h-full object-cover" @error="event => event.target.style.display = 'none'" />
      <div v-else class="h-full flex items-center justify-center text-primary text-sm">课程视频</div>
      <span v-if="video.duration_string" class="absolute bottom-2 right-2 text-xs bg-black/70 text-white px-2 py-1 rounded-md">{{ video.duration_string }}</span>
    </div>
    <div class="p-5">
      <p class="text-[11px] text-primary tracking-wider mb-2">当前课程</p>
      <h2 class="text-sm font-semibold leading-6">{{ video.title }}</h2>
      <p class="text-xs text-text-secondary mt-3">{{ video.uploader }}<span v-if="video.platform"> · {{ video.platform }}</span></p>
      <a :href="videoUrl" target="_blank" rel="noopener noreferrer" class="inline-block mt-5 text-sm text-primary hover:underline">打开原课程 ↗</a>
      <details v-if="video.formats?.length" class="mt-5 pt-4 border-t border-border-light">
        <summary class="text-xs text-text-secondary cursor-pointer">视频下载选项</summary>
        <label for="download-format" class="sr-only">选择下载格式</label>
        <select id="download-format" v-model="selectedFormat" class="w-full mt-3 text-xs border border-border rounded-lg p-2 bg-white">
          <option v-for="format in video.formats" :key="format.format_id" :value="format.format_id">{{ format.label }}</option>
        </select>
        <button @click="$emit('download', selectedFormat)" :disabled="downloading || !selectedFormat"
          class="mt-2 text-xs text-primary border border-border rounded-lg px-3 py-2 hover:bg-primary-light disabled:opacity-50 cursor-pointer">
          {{ downloading ? '正在下载…' : '下载视频' }}
        </button>
      </details>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
const props = defineProps({ video: { type: Object, required: true }, videoUrl: { type: String, required: true }, downloading: Boolean })
defineEmits(['download'])
const selectedFormat = ref(props.video.formats?.[0]?.format_id || '')
const thumbnailUrl = computed(() => '/api/proxy/thumbnail?url=' + encodeURIComponent(props.video.thumbnail))
</script>
