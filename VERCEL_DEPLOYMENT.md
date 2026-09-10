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
Value: https://augensternsy--ai-drug-design-agent-fastapi-api.modal.run
Environment: Production, Preview, Development
```

变量值末尾可带或不带 `/`，前端会自动规范化。更新环境变量后需要重新部署。

## 4. 部署与验证

点击 **Deploy**。部署完成后打开 Vercel 公网地址，验证：

1. 可选择全部 12 个靶点。
2. 设置生成数量及 Vina 开关后能提交任务。
3. 页面能轮询并显示任务阶段和进度。
4. 完成后能展示 Rank、SMILES、QED、SA、MolWt、LogP、Lipinski 和 Vina score。

Modal 首次冷启动和分子生成可能需要数分钟。浏览器应保持页面打开，前端会持续轮询同一任务。
