# Agent Evaluation Benchmark Report

## 📊 Summary Metrics

| Metric | Value | Percentage |
| :--- | :--- | :--- |
| **Total Test Cases** | 156 | 100% |
| **Correct Intent (Target Recognition)** | 156 / 156 | **100.00%** |
| **Parameter Accuracy (Samples & Docking)** | 148 / 156 | **94.87%** |
| **Executed E2E Sample Tasks** | 5 | 100% |
| **Tool Success Rate (All Tools Completed)** | 5 / 5 | **100.00%** |
| **Task Success Rate (Valid Candidates Returned)** | 5 / 5 | **100.00%** |

---

## 🛠 Tool Calling Workflow Evaluation

The following 5 agent tools are verified for execution integrity during evaluation:
1. **ESM-2 Protein Encoding** — Contextual residue embedding
2. **DLPS-E2PO Generation** — Discrete token diffusion sampling
3. **RDKit Validation** — Molecular topology & kekulization verification
4. **Property Evaluation** — QED, SA score, Lipinski, 2D SVG, 3D MolBlock computation
5. **AutoDock Vina Docking** — 3D binding affinity calculation

---

## 📝 Test Cases Sample Results

| Case ID | Input Prompt | Expected Target | Parsed Target | Intent Match | Param Match | E2E Status |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| `tc_001` | 请寻找针对esr1的1条活性配体，with docking | ESR1 | ESR1 | ✅ | ✅ | `completed` |
| `tc_002` | 为Esr1蛋白设计1条药物分子无需对接 | ESR1 | ESR1 | ✅ | ✅ | `N/A` |
| `tc_003` | 针对ESR1生成2条分子，with docking | ESR1 | ESR1 | ✅ | ✅ | `completed` |
| `tc_004` | 为esr1蛋白设计2个药物分子仅评估理化性质 | ESR1 | ESR1 | ✅ | ✅ | `N/A` |
| `tc_005` | 生成针对Esr1的3候选分子候选分子包含3D对接 | ESR1 | ESR1 | ✅ | ✅ | `N/A` |
| `tc_006` | 请寻找针对雌激素受体ESR1的三个活性配体，无需对接 | ESR1 | ESR1 | ✅ | ✅ | `completed` |
| `tc_007` | 生成针对Esr1的四个候选分子with docking | ESR1 | ESR1 | ✅ | ✅ | `N/A` |
| `tc_008` | 针对Esr1生成四个分子，不跑对接 | ESR1 | ESR1 | ✅ | ✅ | `N/A` |
| `tc_009` | 生成针对雌激素受体ESR1的五个候选分子with docking | ESR1 | ESR1 | ✅ | ✅ | `N/A` |
| `tc_010` | 请寻找针对ESR1的5个活性配体，不需要分子对接 | ESR1 | ESR1 | ✅ | ✅ | `N/A` |
| `tc_011` | 生成针对Hcrtr1的一个候选分子with docking | HCRTR1 | HCRTR1 | ✅ | ✅ | `completed` |
| `tc_012` | 为HCRTR1蛋白设计一个药物分子跳过Vina | HCRTR1 | HCRTR1 | ✅ | ✅ | `N/A` |
| `tc_013` | 请寻找针对Hcrtr1的两个活性配体，with docking | HCRTR1 | HCRTR1 | ✅ | ✅ | `N/A` |
| `tc_014` | 帮我设计hcrtr1靶点2条小分子without docking | HCRTR1 | HCRTR1 | ✅ | ✅ | `N/A` |
| `tc_015` | 为Hcrtr1蛋白设计3候选分子药物分子包含3D对接 | HCRTR1 | HCRTR1 | ✅ | ✅ | `N/A` |
