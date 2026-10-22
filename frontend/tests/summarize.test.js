import test from 'node:test'
import assert from 'node:assert/strict'
import { chatWithVideo, summarizeVideo, getSubtitles } from '../src/api/summarize.js'

function streamResponse(text) {
  const bytes = new TextEncoder().encode(text)
  return new Response(new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7))
      controller.close()
    },
  }))
}

function mockFetch(t, implementation) {
  const previousFetch = globalThis.fetch
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  globalThis.fetch = implementation
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => 'old-unused-token' } })
  t.after(() => {
    globalThis.fetch = previousFetch
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage)
    else delete globalThis.localStorage
  })
}

test('chat sends no full transcript and consumes CRLF SSE across UTF-8 boundaries', async (t) => {
  let payload
  mockFetch(t, async (_, options) => {
    assert.deepEqual(options.headers, { 'Content-Type': 'application/json' })
    payload = JSON.parse(options.body)
    return streamResponse('event: video\r\ndata: {"video_id":"0123456789abcdef"}\r\n\r\nevent: sources\r\ndata: {"sources":[{"id":"S1","text":"复习片段"}]}\r\n\r\nevent: answer\r\ndata: "间隔复习。[S1]"\r\n\r\nevent: done\r\ndata: [DONE]\r\n\r\n')
  })
  const events = []
  await chatWithVideo('https://youtu.be/example', '如何复习？', null, Object.fromEntries(
    ['video', 'sources', 'answer', 'done'].map(event => [event, data => events.push([event, data])]),
  ))
  assert.deepEqual(payload, { url: 'https://youtu.be/example', question: '如何复习？' })
  assert.deepEqual(events.map(([name]) => name), ['video', 'sources', 'answer', 'done'])
  assert.equal(JSON.parse(events[2][1]), '间隔复习。[S1]')
})

test('subsequent chat sends the returned video ID', async (t) => {
  let payload
  mockFetch(t, async (_, options) => {
    payload = JSON.parse(options.body)
    return streamResponse('event: done\ndata: [DONE]\n\n')
  })
  await chatWithVideo('https://youtu.be/example', '如何复习？', '0123456789abcdef')
  assert.equal(payload.video_id, '0123456789abcdef')
  assert.equal('subtitle_text' in payload, false)
})

test('summary scope event is available to the UI', async (t) => {
  mockFetch(t, async () => streamResponse('event: summary_scope\ndata: {"partial":true}\n\nevent: done\ndata: [DONE]\n\n'))
  let scope
  await summarizeVideo('https://youtu.be/example', 'zh', { summary_scope: data => { scope = JSON.parse(data) } })
  assert.deepEqual(scope, { partial: true })
})

test('subtitles use their own anonymous endpoint without requesting a summary', async (t) => {
  const captions = { has_subtitle: true, segments: [{ start: 0, text: '课程原文' }] }
  mockFetch(t, async (url, options) => {
    assert.equal(url, '/api/subtitles')
    assert.deepEqual(options.headers, { 'Content-Type': 'application/json' })
    assert.deepEqual(JSON.parse(options.body), { url: 'https://youtu.be/example' })
    return new Response(JSON.stringify(captions))
  })
  assert.deepEqual(await getSubtitles('https://youtu.be/example'), captions)
})
