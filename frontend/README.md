# Vercel Frontend

React + TypeScript + Vite 单页前端，默认连接 RTX 3090 Tailscale Funnel FastAPI，轮询任务状态并展示 RDKit/Vina 候选结果。

页面启动时会对 `/api/health` 执行一次 5 秒超时检查。健康检查成功时显示 `Live GPU · RTX 3090`；失败或超时时进入 `Demo Mode`，只显示明确标注的既有真实模型 SMILES，不会提交生成或 Vina 请求。

## 本地运行

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

生产构建：

```powershell
npm run build
```

离线 mock 检查：

```powershell
npm run test:mock
```

所有 API 请求均通过 `VITE_API_BASE_URL` 配置，不在业务代码中硬编码服务地址，也不向浏览器注入 API Key、Token 或服务端 Secret。
