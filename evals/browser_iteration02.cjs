/* Real Edge verification; requires the existing local Playwright QA install.
   No requests, extractor, vector store or model responses are mocked. */
const { chromium } = require('./runs/qa-tools/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

function events(raw) {
  return raw.replace(/\r\n/g, '\n').split('\n\n').filter(Boolean).map(block => {
    const lines = block.split('\n');
    return { event: lines.find(x => x.startsWith('event:'))?.slice(6).trim(),
      data: lines.filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n') };
  });
}

(async () => {
  const directory = path.join(__dirname, 'runs');
  const stem = process.env.AI_VIDEO_BROWSER_RUN ?? 'iteration02-browser-02';
  assert.match(stem, /^[a-z0-9_-]+$/);
  const resultPath = path.join(directory, `${stem}.json`);
  assert.equal(fs.existsSync(resultPath), false, 'Keep previous observations; use a new result name for another attempt');
  const report = { tested_at: new Date().toISOString(), actor: 'Codex automated browser',
    browser: 'Microsoft Edge headless / Playwright', page_errors: [], requests: [], tasks: [],
    scope: 'Real homepage, public parser, live captions/index/model; no mocked services',
    video_playback_verified: false, human_learning_task: false };
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(120000);
  page.on('pageerror', error => report.page_errors.push(error.message));
  const videoUrl = 'https://www.bilibili.com/video/BV1pLWFz1Eew/?p=1';
  let firstSources;
  try {
    await page.goto('http://127.0.0.1:5173/');
    report.home_title = await page.title();
    await page.getByPlaceholder('https://www.youtube.com/watch?v=... 粘贴视频链接').fill(videoUrl);
    const parsePromise = page.waitForResponse(r => r.url().endsWith('/api/parse'));
    const parseStarted = Date.now();
    await page.getByRole('button', { name: '解析视频', exact: true }).click();
    const parsed = await parsePromise;
    const metadata = await parsed.json();
    report.parse = { status: parsed.status(), elapsed_ms: Date.now() - parseStarted,
      success: metadata.success, title: metadata.data?.title ?? metadata.title };
    assert.equal(parsed.status(), 200);
    assert.equal(metadata.success, true);
    const login = page.getByRole('heading', { name: '登录账号', exact: true });
    await login.waitFor({ state: 'visible', timeout: 10000 });
    await login.locator('..').getByRole('button').click();
    report.default_summary_login_dismissed = true;
    await page.getByRole('button', { name: 'AI 问答' }).click();
    page.on('request', r => {
      if (r.method() === 'POST' && r.url().endsWith('/api/chat')) report.requests.push(JSON.parse(r.postData()));
    });
    const questions = [
      '从用户输入到页面只显示模型答案，本节演示了哪些处理步骤？请包括带角色的消息、模板与编码、生成、解码和提取回答。',
      'tokenizer.encode 和 tokenizer.decode 分别转换什么？为什么本节演示中“大家好”先编码再解码可能多出 begin_of_text？',
    ];
    for (const question of questions) {
      const input = page.getByPlaceholder('输入你的问题...');
      await input.fill(question);
      const responsePromise = page.waitForResponse(r => r.url().endsWith('/api/chat'));
      const started = Date.now();
      await page.getByRole('button', { name: '发送', exact: true }).click();
      const response = await responsePromise;
      const raw = await response.text();
      const frames = events(raw);
      const sources = JSON.parse(frames.find(e => e.event === 'sources').data).sources;
      const answer = frames.filter(e => e.event === 'answer').map(e => JSON.parse(e.data)).join('');
      const task = { question, http_status: response.status(), elapsed_ms: Date.now() - started,
        done_event: frames.some(e => e.event === 'done'), error_event: frames.some(e => e.event === 'error'),
        source_count: sources.length, source_chars: sources.reduce((n, s) => n + s.text.length, 0),
        answer_events: frames.filter(e => e.event === 'answer').length, answer, sources };
      report.tasks.push(task);
      firstSources ??= sources;
      assert.equal(response.status(), 200);
      assert.equal(task.done_event, true);
      assert.equal(task.error_event, false);
      assert.ok(task.source_chars > 12000 && task.source_chars <= 48000);
      assert.equal(sources.length, firstSources.length);
      assert.ok(answer.length > 30);
      assert.doesNotMatch(answer, /\bas_special_tokens?\s*=/i);
      assert.ok(sources.every(s => new URL(s.url).searchParams.get('p') === '1'));
      await page.waitForFunction(() => !document.querySelector('input[placeholder="输入你的问题..."]').disabled);
      assert.equal(await page.locator('details[open]').count(), 0);
      console.log(JSON.stringify({ phase: 'question', number: report.tasks.length, elapsed_ms: task.elapsed_ms, sources: sources.length }));
    }
    assert.equal(report.requests[0].video_id, undefined);
    assert.match(report.requests[1].video_id, /^[a-f0-9]{16}$/);
    assert.ok(report.requests.every(r => !('subtitle_text' in r)));
    report.video_id_reused = true;
    report.input_recovered = true;
    const answers = await page.locator('.chat-prose').allTextContents();
    report.rendered_answers = answers;
    assert.equal(answers.length, 2);
    assert.ok(/提取|取出/.test(answers[0]));
    assert.ok(/begin.of.text/.test(answers[1]));
    await page.screenshot({ path: path.join(directory, `${stem}-chat.png`), fullPage: true });
    const evidence = page.locator('details').first();
    await evidence.locator('summary').click();
    assert.equal(await evidence.evaluate(e => e.open), true);
    const late = firstSources.find(s => s.start > 2267 && s.text.includes('模型输出的部分'));
    assert.ok(late, 'Actual source includes the later UI answer-extraction passage');
    const sourceLink = evidence.locator('a[target="_blank"]').filter({ hasText: `[${late.id}]` });
    await sourceLink.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(directory, `${stem}-evidence.png`), fullPage: false });
    const popupPromise = page.waitForEvent('popup');
    await sourceLink.click();
    const popup = await popupPromise;
    await popup.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => {});
    report.source_click = { id: late.id, expected: late.url, opened: popup.url(), timestamp: late.timestamp };
    assert.equal(new URL(popup.url()).searchParams.get('p'), '1');
    assert.equal(new URL(popup.url()).searchParams.get('t'), String(Math.floor(late.start)));
    await popup.close();
    assert.equal(report.page_errors.length, 0);
    report.status = 'passed';
  } catch (error) {
    report.status = 'failed';
    report.error = { name: error.name, message: error.message };
    await page.screenshot({ path: path.join(directory, `${stem}-failed.png`), fullPage: true }).catch(() => {});
    process.exitCode = 1;
  } finally {
    fs.writeFileSync(resultPath, JSON.stringify(report, null, 2), { flag: 'wx' });
    console.log(JSON.stringify({ phase: 'result', status: report.status, error: report.error, page_errors: report.page_errors.length }));
    await browser.close();
  }
})();
