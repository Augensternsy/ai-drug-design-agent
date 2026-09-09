# RunPod 执行清单

## 1. 创建 RunPod 资源

在 RunPod 控制台创建并选择：

```text
Network Volume: 20 GB
GPU Pod: 24 GB NVIDIA GPU（优先 RTX 3090 / RTX 4090 / RTX A5000）
Volume mount path: /workspace
Expose HTTP Ports: 8000
```

进入 Pod Terminal 后确认：

```bash
nvidia-smi
df -h /workspace
mkdir -p /workspace/models /workspace/data
```

## 2. 上传并校验资产包

将 `runpod-assets.tar.gz` 上传到 `/workspace/runpod-assets.tar.gz`，然后执行：

```bash
cd /workspace
echo "31c926aa70e03dfac4939ba1e349f14fa6cabea8ee553c00577b775f2b83d199  runpod-assets.tar.gz" | sha256sum -c -
```

## 3. 解压资产

```bash
cd /workspace
tar -xzf runpod-assets.tar.gz -C /workspace
test -f /workspace/models/e2po/direct_ki_e2po_15k.pt
test -f /workspace/models/esm2/pytorch_model.bin
test -f /workspace/data/targets/targets.json
```

## 4. 克隆项目并配置环境

```bash
cd /workspace
git clone https://github.com/Augensternsy/ai-drug-design-agent.git
cd /workspace/ai-drug-design-agent
git switch main
cp .env.runpod.example .env
```

## 5. 启动 FastAPI

```bash
cd /workspace/ai-drug-design-agent
bash scripts/runpod_bootstrap.sh
```

## 6. 测试 API

在另一个 Pod Terminal 中执行：

```bash
cd /workspace/ai-drug-design-agent
bash scripts/runpod_smoke_test.sh http://127.0.0.1:8000
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
```

## 7. 记录公网地址

把 `<POD_ID>` 替换为 RunPod 控制台显示的 Pod ID：

```bash
export POD_ID="<POD_ID>"
export PUBLIC_URL="https://${POD_ID}-8000.proxy.runpod.net"
printf '%s\n' "${PUBLIC_URL}" | tee /workspace/RUNPOD_PUBLIC_URL.txt
curl --fail --silent --show-error "${PUBLIC_URL}/api/health"
```
