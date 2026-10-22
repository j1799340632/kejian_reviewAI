/* Real local stack: anonymous parse, question, captions and on-demand summary.
   Calls configured model services; no API responses are replaced. */
const { chromium } = require('./runs/qa-tools/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

function frames(raw) {
  return raw.replace(/\r\n/g, '\n').split('\n\n').filter(Boolean).map(block => {
    const lines = block.split('\n');
    return { event: lines.find(line => line.startsWith('event:'))?.slice(6).trim(),
      data: lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n') };
  });
}

(async () => {
  const { getCitedSources } = await import('../frontend/src/utils/citations.js');
  const directory = path.join(__dirname, 'runs');
  const stem = process.env.AI_VIDEO_PERSONAL_RUN ?? 'personal-demo-01';
  assert.match(stem, /^[a-z0-9_-]+$/);
  const output = path.join(directory, `${stem}.json`);
  assert.equal(fs.existsSync(output), false, 'Use a new run name to preserve history');
  const report = { actor: 'Codex automated browser', scope: 'Real anonymous local stack; no mocked services; functional checks only',
    video_playback_verified: false, human_learning_task: false, page_errors: [], requests: [] };
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(120000);
  page.on('pageerror', error => report.page_errors.push(error.message));
  page.on('request', request => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.startsWith('/api/')) report.requests.push({ path: pathname, method: request.method(), has_authorization: 'authorization' in request.headers() });
  });
  try {
    await page.goto('http://127.0.0.1:5173/');
    assert.match(await page.title(), /课间/);
    assert.doesNotMatch(await page.locator('body').innerText(), /SaveAny|1800|永久免费|工具对比|免费注册/);
    assert.equal(await page.getByRole('button', { name: /登录|注册/ }).count(), 0);
    await page.screenshot({ path: path.join(directory, `${stem}-home.png`), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.getByRole('button', { name: '打开课程', exact: true }).isVisible());
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: path.join(directory, `${stem}-mobile-home.png`), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: 'LangChain · RAG 工作流程', exact: true }).click();
    const parseResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/parse');
    await page.getByRole('button', { name: '打开课程', exact: true }).click();
    const parsed = await parseResponse;
    assert.equal(parsed.status(), 200);
    assert.equal((await parsed.json()).success, true);
    await page.getByPlaceholder('输入你的问题...').waitFor({ state: 'visible' });
    assert.equal(report.requests.some(request => request.path === '/api/summarize'), false);
    assert.equal(await page.getByRole('dialog').count(), 0);
    report.default_qa_without_generation = true;

    await page.getByPlaceholder('输入你的问题...').fill('文档向量为什么需要持久化保存？');
    const chatResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/chat');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    const chat = await chatResponse;
    assert.equal(chat.status(), 200);
    const chatFrames = frames(await chat.text());
    assert.equal(chatFrames.some(frame => frame.event === 'error'), false);
    assert.ok(chatFrames.some(frame => frame.event === 'done'));
    const sources = JSON.parse(chatFrames.find(frame => frame.event === 'sources').data).sources;
    const answer = chatFrames.filter(frame => frame.event === 'answer').map(frame => JSON.parse(frame.data)).join('');
    const cited = getCitedSources(answer, sources);
    assert.ok(answer.length > 30 && cited.length > 0 && cited.length < sources.length);
    await page.waitForFunction(() => !document.querySelector('input[placeholder="输入你的问题..."]').disabled);
    const evidence = page.locator('.chat-prose').first().locator('..').locator('details');
    await evidence.locator('summary').click();
    assert.equal(await evidence.locator('a').count(), cited.length);
    for (const [index, source] of cited.entries()) assert.equal(await evidence.locator('a').nth(index).getAttribute('href'), source.url);
    report.chat = { answer, input_source_count: sources.length, displayed_source_ids: cited.map(source => source.id), completed: true };
    await page.screenshot({ path: path.join(directory, `${stem}-workspace.png`), fullPage: true });
    console.log(JSON.stringify({ phase: 'anonymous_chat', input_sources: sources.length, displayed_sources: cited.length }));

    const subtitleResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/subtitles');
    await page.getByRole('button', { name: '字幕文本', exact: true }).click();
    const subtitleResult = await subtitleResponse;
    assert.equal(subtitleResult.status(), 200);
    const captions = await subtitleResult.json();
    await page.locator('span.text-sm.text-text-primary.leading-relaxed').first().waitFor();
    assert.deepEqual(await page.locator('span.text-sm.text-text-primary.leading-relaxed').allTextContents(), captions.segments.map(segment => segment.text));
    assert.equal(report.requests.some(request => request.path === '/api/summarize'), false);
    report.subtitle_segments = captions.segments.length;

    await page.getByRole('button', { name: '总结摘要', exact: true }).click();
    const summaryResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/summarize');
    await page.getByRole('button', { name: '生成摘要与思维导图', exact: true }).click();
    const summary = await summaryResponse;
    assert.equal(summary.status(), 200);
    const summaryFrames = frames(await summary.text());
    assert.equal(summaryFrames.some(frame => frame.event === 'error' || frame.event === 'quota'), false);
    const summaryText = summaryFrames.filter(frame => frame.event === 'summary').map(frame => JSON.parse(frame.data)).join('');
    const mindmap = JSON.parse(summaryFrames.find(frame => frame.event === 'mindmap').data).markdown;
    assert.ok(summaryText.length > 30 && mindmap.length > 20);
    assert.ok(summaryFrames.some(frame => frame.event === 'done'));
    report.on_demand_generation = { summary_chars: summaryText.length, mindmap_chars: mindmap.length, summary_text: summaryText, mindmap_markdown: mindmap, completed: true };
    await page.getByRole('button', { name: '思维导图', exact: true }).click();
    await page.waitForFunction(() => {
      const svg = document.querySelector('.mindmap-wrapper svg');
      return svg?.querySelector('g') && !svg.innerHTML.includes('NaN');
    }, undefined, { timeout: 10000 });
    assert.equal(await page.locator('.mindmap-wrapper svg').evaluate(svg => svg.innerHTML.includes('NaN')), false);
    report.mindmap_rendered = true;

    await page.getByRole('button', { name: 'AI 问答', exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: path.join(directory, `${stem}-mobile-workspace.png`), fullPage: true });
    report.mobile_overflow = false;
    report.account_endpoints = {};
    for (const name of ['login', 'register']) {
      const response = await page.request.post(`http://127.0.0.1:8000/api/auth/${name}`, { data: {} });
      report.account_endpoints[name] = response.status();
      assert.equal(response.status(), 404);
    }
    assert.equal(report.requests.some(request => request.has_authorization || request.path.startsWith('/api/auth/')), false);
    assert.deepEqual(report.page_errors, []);
    report.passed = true;
    console.log(JSON.stringify({ passed: true, subtitle_segments: report.subtitle_segments, summary_chars: summaryText.length, mindmap_chars: mindmap.length, account_endpoints: report.account_endpoints }));
  } catch (error) {
    report.passed = false;
    report.error = String(error.stack ?? error);
    throw error;
  } finally {
    fs.writeFileSync(output, JSON.stringify(report, null, 2));
    await browser.close();
  }
})();
