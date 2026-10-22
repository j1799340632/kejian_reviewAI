import test from 'node:test'
import assert from 'node:assert/strict'
import { getCitedSources } from '../src/utils/citations.js'

const sources = Array.from({ length: 11 }, (_, index) => ({
  id: `S${index + 1}`, text: `片段 ${index + 1}`, timestamp: `00:${index + 10}`,
  url: `https://www.bilibili.com/video/example/?p=103&t=${index + 10}`,
}))

test('an answer citing S6 displays only S6 with its original ID, text and time link', () => {
  assert.deepEqual(getCitedSources('持久化避免重复向量化。[S6]', sources), [sources[5]])
})

test('multiple and grouped citations are deduplicated in first citation order', () => {
  const answer = '第一点[S6, S2]，第二点[S2][S11]，补充[S6、S3]。'
  assert.deepEqual(getCitedSources(answer, sources), [sources[5], sources[1], sources[10], sources[2]])
})

test('missing, unavailable and unbracketed references never fall back to all sources', () => {
  for (const answer of ['', '资料不足，无法回答。', '提到 S6 但没有引用。', '[S99]', '[S6-S11]']) {
    assert.deepEqual(getCitedSources(answer, sources), [])
  }
  assert.deepEqual(getCitedSources('回答[S6]'), [])
})

test('streamed partial references appear only after their closing bracket arrives', () => {
  let answer = '回答['
  assert.deepEqual(getCitedSources(answer, sources), [])
  answer += 'S6'
  assert.deepEqual(getCitedSources(answer, sources), [])
  answer += ']，补充[S'
  assert.deepEqual(getCitedSources(answer, sources), [sources[5]])
  answer += '11]'
  assert.deepEqual(getCitedSources(answer, sources), [sources[5], sources[10]])
})
