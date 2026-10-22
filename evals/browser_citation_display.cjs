/* UI-only replay with frozen P103 captions and constructed answer citations.
   Does not call the model or measure answer quality. */
const { chromium } = require('./runs/qa-tools/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const directory = path.join(__dirname, 'runs');
  const fixture = JSON.parse(fs.readFileSync(path.join(directory, 'citation-display-fixture.json'), 'utf8'));
  const stem = process.env.AI_VIDEO_CITATION_RUN ?? 'citation-display-01';
  assert.match(stem, /^[a-z0-9_-]+$/);
  const reportPath = path.join(directory, `${stem}.json`);
  assert.equal(fs.existsSync(reportPath), false, 'Use a new run name to preserve previous observations');
  const cases = [
    { answer: ['持久化避免每次使用时重复向量化。[', 'S6', ']'], ids: ['S6'] },
    { answer: ['多个要点[S6][S2]，补充[S6, S11]。'], ids: ['S6', 'S2', 'S11'] },
    { answer: ['现有资料不足以回答。'], ids: [] },
    { answer: ['无可用来源的标注[S999]。'], ids: [] },
  ];
  const report = { actor: 'Codex automated browser', scope: 'UI replay: mocked parse/subtitles/chat/summary; frozen captions; constructed answers',
    model_calls: 0, answer_quality_evaluated: false, page_errors: [], tasks: [] };
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(20000);
  page.on('pageerror', error => report.page_errors.push(error.message));
  const frame = (event, value) => `event: ${event}\ndata: ${JSON.stringify(value)}\n\n`;
  let nextCase = 0;
  let summaryRequests = 0;
  try {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/parse') {
        return route.fulfill({ json: { success: true, data: { title: 'P103 RAG 工作流程 · 来源展示回放',
          platform: 'Bilibili', uploader: '尚硅谷', duration_string: '8:51', formats: [] } } });
      }
      if (url.pathname === '/api/summarize') {
        summaryRequests++;
        return route.fulfill({ contentType: 'text/event-stream', body: frame('summary', '课程摘要回放。') +
          frame('mindmap', { markdown: '# RAG 工作流程\n## 加载文档\n## 切分\n## 向量化\n## 持久化' }) + 'event: done\ndata: [DONE]\n\n' });
      }
      if (url.pathname === '/api/subtitles') {
        return route.fulfill({ json: { has_subtitle: true, language: 'zh', subtitle_type: 'auto', segments: fixture.segments } });
      }
      if (url.pathname === '/api/chat') {
        const item = cases[nextCase++];
        assert.ok(item, 'Unexpected extra chat');
        return route.fulfill({ contentType: 'text/event-stream', body:
          frame('video', { video_id: '0123456789abcdef' }) + frame('sources', { sources: fixture.sources }) +
          item.answer.map(chunk => frame('answer', chunk)).join('') + 'event: done\ndata: [DONE]\n\n' });
      }
      (report.unexpected_requests ??= []).push(url.pathname);
      await route.abort();
    });
    await page.goto('http://127.0.0.1:5173/');
    await page.setViewportSize({ width: 390, height: 844 });
    const inputBox = await page.getByLabel('课程视频链接', { exact: true }).boundingBox();
    assert.ok(inputBox.height >= 44);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    report.mobile_input_height = inputBox.height;
    await page.screenshot({ path: path.join(directory, `${stem}-mobile-home.png`), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByLabel('课程视频链接', { exact: true })
      .fill('https://www.bilibili.com/video/BV1rv7A6oEeP/?p=103');
    await page.getByRole('button', { name: '打开课程', exact: true }).click();
    await page.getByRole('button', { name: 'AI 问答' }).click();
    assert.equal(summaryRequests, 0);
    for (const [index, item] of cases.entries()) {
      const input = page.getByPlaceholder('输入你的问题...');
      await input.fill(index === 0 ? '文档向量为什么需要持久化保存？' : `展示检查 ${index + 1}`);
      await page.getByRole('button', { name: '发送', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('input[placeholder="输入你的问题..."]').disabled);
      const bubble = page.locator('.chat-prose').nth(index).locator('..');
      const details = bubble.locator('details');
      assert.equal(await details.count(), item.ids.length ? 1 : 0);
      if (item.ids.length) {
        assert.equal(await details.evaluate(element => element.open), false);
        assert.ok((await details.locator('summary').innerText()).includes(`回答依据（${item.ids.length} 段）`));
        await details.locator('summary').click();
        const links = details.locator('a');
        assert.equal(await links.count(), item.ids.length);
        for (const [i, id] of item.ids.entries()) {
          const source = fixture.sources.find(source => source.id === id);
          assert.ok((await links.nth(i).innerText()).startsWith(`[${id}]`));
          assert.equal(await links.nth(i).getAttribute('href'), source.url);
          assert.equal(await details.locator('p').nth(i).textContent(), source.text);
        }
      }
      report.tasks.push({ input_sources: fixture.sources.length, displayed_ids: item.ids, passed: true });
      if (index === 0) {
        await page.screenshot({ path: path.join(directory, `${stem}-single.png`), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
        await page.screenshot({ path: path.join(directory, `${stem}-mobile-workspace.png`), fullPage: true });
        await page.setViewportSize({ width: 1440, height: 1000 });
      }
    }
    await page.getByRole('button', { name: '字幕文本' }).click();
    const captions = page.locator('span.text-sm.text-text-primary.leading-relaxed');
    assert.deepEqual(await captions.allTextContents(), fixture.segments.map(segment => segment.text));
    report.complete_subtitle_segments = await captions.count();
    assert.equal(summaryRequests, 0);
    await page.getByRole('button', { name: '总结摘要', exact: true }).click();
    await page.getByRole('button', { name: '生成摘要与思维导图', exact: true }).click();
    await page.getByText('课程摘要回放。', { exact: true }).waitFor();
    assert.equal(summaryRequests, 1);
    await page.getByRole('button', { name: '思维导图', exact: true }).click();
    await page.waitForFunction(() => {
      const svg = document.querySelector('.mindmap-wrapper svg');
      return svg?.querySelector('g') && !svg.innerHTML.includes('NaN');
    }, undefined, { timeout: 10000 });
    report.on_demand_summary_and_visible_mindmap = true;
    assert.deepEqual(report.page_errors, []);
    assert.deepEqual(report.unexpected_requests ?? [], []);
    report.passed = true;
    console.log(JSON.stringify({ passed: true, cases: report.tasks.length, complete_subtitle_segments: report.complete_subtitle_segments, on_demand_mindmap: true, model_calls: 0 }));
  } catch (error) {
    report.passed = false;
    report.error = String(error.stack ?? error);
    throw error;
  } finally {
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    await browser.close();
  }
})();
