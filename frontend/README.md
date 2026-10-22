# 课间前端

我使用 Vue 3、Vite 和 Tailwind CSS 搭建课程复习界面，围绕“打开课程—提问—查看引用—回到原文核对”组织交互。页面默认进入问答，完整字幕独立读取，摘要与思维导图按需生成。

## 本地运行

在本目录运行，Node.js 版本要求见[项目说明](../README.md)：

```bash
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`，开发代理将 `/api` 请求转发到 `http://localhost:8000`，后端与 Milvus 需按项目说明另行启动。

## 验证与展示

```bash
npm test
npm run build
```

我将引用筛选和接口事件解析放在 `tests/` 中验证，测试使用 Node.js 内置运行器。产品截图见[应用截图](../README.md#应用截图)，真实网页检查与 AI 协作分工见[测试记录](../docs/product/SELF_TEST_LOG.md)。
