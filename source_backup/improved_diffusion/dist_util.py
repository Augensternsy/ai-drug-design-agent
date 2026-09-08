"""
Helpers for distributed training.
"""

import io
import os
import socket

import torch as th
import torch.distributed as dist

# Change this to reflect your cluster layout.
# The GPU for a given rank is (rank % GPUS_PER_NODE).
GPUS_PER_NODE = 1 #8

SETUP_RETRY_COUNT = 3

MPI_AVAILABLE = False

def setup_dist(rank,world_size,port='12145'):
    """
    Setup a distributed process group.
    """
    print("IN AUG DIST setup")
    if dist.is_initialized():
        return

    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = port

    # 检测是否有可用的GPU
    gpu_available = th.cuda.is_available()
    try:
        if gpu_available:
            # 尝试创建测试张量来验证GPU是否真正可用
            test_tensor = th.zeros(1).cuda()
            del test_tensor
            th.cuda.synchronize()
            backend = 'nccl'
        else:
            backend = 'gloo'
    except Exception as e:
        print(f"GPU检测失败: {e}, 使用gloo后端")
        backend = 'gloo'

    dist.init_process_group(backend=backend, rank=rank, world_size=world_size)

def dev():
    """
    Get the device to use for torch.distributed.
    """
    if th.cuda.is_available():
        return th.device("cuda:0")
    return th.device("cpu")


def load_state_dict(path, **kwargs):
    """
    Load a PyTorch file without redundant fetches across MPI ranks.
    """
    # 延迟导入 blobfile
    import blobfile as bf
    with bf.BlobFile(path, "rb") as f:
        data = f.read()
    return th.load(io.BytesIO(data), **kwargs)


def sync_params(params):
    """
    Synchronize a sequence of Tensors across ranks from rank 0.
    """
    if not dist.is_initialized():
        return
    for p in params:
        with th.no_grad():
            dist.broadcast(p, 0)


def _find_free_port():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]
    finally:
        s.close()
