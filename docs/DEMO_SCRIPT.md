# 2–3 分钟 Demo 演示脚本

## 演示前准备

- 等待 Modal Academic Credits 审核通过，并确认只执行一次受控任务。
- 推荐使用 ESR1、`num_samples=1`；讲解 Vina 时只对单个候选执行一次。
- 提前打开个人网站、Vercel Demo 和 GitHub README，避免现场等待无关页面加载。
- 不展示 Modal Secret、LLM Key、Token、`.env` 或私有 Volume 文件。

## 0:00–0:20｜从个人网站进入项目

“这是我的 AI 药物分子设计与筛选 Agent。我从个人网站的项目卡片进入在线 Demo，前端部署在 Vercel，后端是 FastAPI + Modal Serverless GPU。”

操作：打开个人网站，点击“AI 药物分子设计 Agent”的“在线体验”。

## 0:20–0:45｜介绍两种输入方式

“系统支持表单和自然语言两种入口。论文实验正式验证的是 12 个测试靶点，这里选择 ESR1。公开 Demo 单次最多 5 个候选，Vina 默认关闭。”

操作：展示靶点下拉、生成数量、QED/SA 和 Vina 开关；不要立即提交。

## 0:45–1:10｜自然语言与 Agent Plan

“也可以直接输入：帮我针对 ESR1 生成 1 个候选分子，QED 优先，不进行 Vina 对接。LLM 只解析任务并输出 Agent Plan，不替代专业模型；如果 LLM 失败会自动使用规则解析器。”

操作：切换 Agent 输入区，展示解析后的 target、num_samples、约束、`run_docking` 和 `parser`。

## 1:10–1:35｜Tool Calling 与异步状态

“FastAPI 创建异步任务，前端通过 task_id 轮询状态。Tool trace 会依次展示 resolve_target、generate_molecules、evaluate_properties、可选 molecular_docking、rank_candidates 和结果总结。这样 GPU 冷启动或某一步失败都不会表现成页面卡死。”

操作：展示 queued、generating、evaluating、docking（如适用）、completed 状态和 Agent Tools 区域。

## 1:35–2:05｜真实候选与 RDKit 指标

“ESM-2 提供蛋白表征，DLPS-E2PO 执行条件分子生成。候选先通过 RDKit Valid 检查，再显示 QED、SA、MolWt、LogP 和 Lipinski。这里的计算指标用于筛选，不等同于实验活性或临床有效性。”

操作：展开真实结果卡片，指向 SMILES、Rank、RDKit Valid 和各项指标。

## 2:05–2:25｜Vina 与 2D/3D

“AutoDock Vina 是可选工具，因为它更耗时，也依赖受体结构和口袋设置。此前工程链路已完成真实 Vina 验证；演示时展示单分子的真实 score。2D 由 RDKit 生成，3D 使用 SDF 和 3Dmol.js 在浏览器中查看。”

操作：展示已有真实 Vina 截图或一次受控任务结果，再切换 2D/3D。没有真实截图时明确说明，不用 mock 分数替代。

## 2:25–2:45｜导出与历史

“单个候选可以复制 SMILES、下载 SDF；任务可以导出 CSV、JSON 和全部候选。本地历史保存在 localStorage，不增加数据库和隐私数据依赖。”

操作：指向 Copy SMILES、SDF、CSV、JSON 和历史任务入口，不必实际下载所有文件。

## 2:45–3:00｜架构与边界总结

“整个项目形成 Vercel 前端、FastAPI Agent、Modal GPU、模型 Volume 和 Secret 隔离的完整工程。成本保护包括最大 5 个候选、Vina 默认关闭、cooldown、后端校验和空闲缩容到 0。科研结论严格限定为 12 个正式测试靶点。”

操作：切到 GitHub README 的 Mermaid 架构图结束演示。
