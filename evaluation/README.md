# Drug Design Agent Evaluation Benchmark

本目录包含针对 AI 药物分子设计 Agent 的基准测试评估模块（Agent Evaluation Framework），用于评估 Agent 的**任务理解、意图识别、参数解析、工具调用链与端到端任务执行能力**。

---

## 📁 目录结构

```text
evaluation/
 ├── test_cases.json       # 药物设计测试集（包含 156 条多样式自然语言 Query）
 ├── evaluate_agent.py     # 自动化基准评估主程序
 ├── evaluation_report.json# 评估结果 JSON 报告
 ├── evaluation_report.md  # 评估结果 Markdown 报告
 └── README.md             # 本说明文档
```

---

## 🧪 评估指标体系 (Evaluation Metrics)

1. **Intent Accuracy (意图与靶点识别准确率)**
   - 验证 Agent 是否准确识别用户输入的蛋白质靶点名称（支持 `ESR1`, `JAK1`, `FTO`, `IDH1` 等 12 种靶点及其中英文别名）。

2. **Parameter Accuracy (参数解析准确率)**
   - 验证 Agent 是否准确解析生成数量 (`num_samples`, 1~5) 以及分子对接开关 (`run_docking`, `true`/`false`)。

3. **Tool Calling Accuracy (工具调用成功率)**
   - 验证 Agent 计算流水线中的 5 个核心 Tool 节点是否全流程正确调用并完成：
     - `ESM-2 Protein Encoding`
     - `DLPS-E2PO Generation`
     - `RDKit Validation`
     - `Property Evaluation`
     - `AutoDock Vina Docking`

4. **Task Success Rate (端到端任务成功率)**
   - 验证任务是否最终生成合法的候选分子，且每个候选分子包含有效的 SMILES、QED、SA、2D SVG 矢量图与 3D MolBlock/SDF 构象。

---

## 🚀 运行评估

在项目根目录下运行评估脚本：

```bash
/home/zmx/wsy/env/tgm-dlm/bin/python evaluation/evaluate_agent.py
```

运行完成后会自动在 `evaluation/` 目录下生成 `evaluation_report.json` 与 `evaluation_report.md` 详细评估报告。
