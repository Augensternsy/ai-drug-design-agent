# Vercel 前端部署

## 1. 导入 GitHub 仓库

在 Vercel Dashboard 选择 **Add New → Project**，导入：

```text
https://github.com/Augensternsy/ai-drug-design-agent.git
```

## 2. 配置构建

设置以下项目参数：

```text
Framework Preset: Vite
Root Directory: frontend
Build Command: npm run build
Output Directory: dist
Install Command: npm install
```

## 3. 配置环境变量

在 **Settings → Environment Variables** 添加：

```text
Name: VITE_API_BASE_URL
Value: https://bianjilong.tailb99a04.ts.net
Environment: Production, Preview, Development
```

变量值末尾可带或不带 `/`，前端会自动规范化。更新环境变量后需要重新部署。

## 4. 部署与验证

点击 **Deploy**。部署完成后打开 Vercel 公网地址，验证：

1. 页面启动后向 `${VITE_API_BASE_URL}/api/health` 发起一次健康检查，超时为 5 秒。
2. 健康检查成功时显示 `Live GPU · RTX 3090`。
3. 失败或超时时显示 `Demo Mode` 和 `Demo / Precomputed Result`，不向后端提交生成或 Vina 请求。
4. Live 模式可选择全部 12 个靶点、提交任务并轮询任务状态。
5. 完成后能展示 Rank、SMILES、QED、SA、MolWt、LogP、Lipinski 和 Vina score。

RTX 3090 FastAPI 必须允许 Vercel 站点来源的 CORS 请求，并保持以下接口兼容：`/api/health`、`/api/targets`、`/api/generate`、`/api/agent/generate`、`/api/tasks/{task_id}`。Tailscale Funnel 或主机暂时不可达时，前端会安全降级，不会白屏。

Modal、RunPod 与 Hugging Face ZeroGPU 配置继续保留为独立部署选项，不受此次生产前端切换影响。
