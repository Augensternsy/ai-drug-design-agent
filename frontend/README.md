# Vercel Frontend

React + TypeScript + Vite 单页前端，用于提交 Modal GPU 分子生成任务、轮询任务状态并展示 RDKit/Vina 候选结果。

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

所有 API 请求均通过 `VITE_API_BASE_URL` 配置，不在源代码中硬编码服务地址。
