import copy
import functools
import os
import re

import blobfile as bf
import numpy as np
import torch as th
import torch.distributed as dist
from torch.nn.parallel.distributed import DistributedDataParallel as DDP
from torch.optim import AdamW

from . import dist_util, logger
from .fp16_util import (
    make_master_params,
    master_params_to_model_params,
    model_grads_to_master_grads,
    unflatten_master_params,
    zero_grad,
)
from .nn import update_ema
from .resample import LossAwareSampler, UniformSampler
# For ImageNet experiments, this was a good default value.
# We found that the lg_loss_scale quickly climbed to
# 20-21 within the first ~1K steps of training.
INITIAL_LOG_LOSS_SCALE = 20.0
import swanlab

def check_gpu_available():
    """可靠地检测GPU是否真正可用"""
    if not th.cuda.is_available():
        return False
    try:
        test_tensor = th.zeros(1).cuda()
        del test_tensor
        th.cuda.synchronize()
        return True
    except Exception:
        return False

def parse_resume_step_from_filename(filename):
    """
    Parse filename of the form path/to/modelNNNNNN.pt, where NNNNNN is the
    checkpoint's number of steps.
    """
    if not filename:
        return 0
    split = os.path.basename(filename).split("model")
    if len(split) < 2:
        match = re.findall(r'\d+', os.path.basename(filename))
        if match:
            return int(match[-1])
        return 0
    split1 = split[-1].split(".")[0]
    try:
        return int(split1)
    except ValueError:
        return 0

def find_ema_checkpoint(main_checkpoint, step, rate):
    """
    根据主模型的文件名，自动推导并寻找对应的 EMA 权重文件名。
    例如把 PLAIN_model200000.pt 转换为 PLAIN_ema_0.9999_200000.pt
    """
    if not main_checkpoint:
        return None
    
    dirname = os.path.dirname(main_checkpoint)
    basename = os.path.basename(main_checkpoint)
    
    # 替换文件名中的 "model" 为 "ema_{rate}_"
    ema_basename = basename.replace("model", f"ema_{rate}_")
    ema_path = os.path.join(dirname, ema_basename)
    
    if os.path.exists(ema_path):
        return ema_path
    
    # 如果没找到，返回 None，这样底层的防丢机制会兜底
    return None


def find_resume_checkpoint():
    return None




class TrainLoop:
    def __init__(
        self,
        *,
        model,
        diffusion,
        data,
        batch_size,
        microbatch,
        lr,
        ema_rate,
        log_interval,
        save_interval,
        resume_checkpoint,
        use_fp16=False,
        fp16_scale_growth=1e-3,
        schedule_sampler=None,
        weight_decay=0.0,
        lr_anneal_steps=0,
        checkpoint_path='',
        gradient_clipping=-1.,
        eval_data=None,
        eval_interval=-1,
        use_ddp=True,  # 添加这个参数来控制是否使用DDP
    ):
        print("IN AUG trainutil")
        rank = dist.get_rank() if dist.is_initialized() else 0
        world_size = dist.get_world_size() if dist.is_initialized() else 1
        print("initialing Trainer for",rank,'/',world_size)
        self.rank = rank
        self.world_size = world_size
        self.diffusion = diffusion
        self.data = data
        self.eval_data = eval_data
        self.batch_size = batch_size
        self.microbatch = microbatch if microbatch > 0 else batch_size
        self.lr = lr*world_size
        print("ori lr:",lr,"new lr:",self.lr)
        self.ema_rate = (
            [ema_rate]
            if isinstance(ema_rate, float)
            else [float(x) for x in ema_rate.split(",")]
        )
        self.log_interval = log_interval
        self.eval_interval = eval_interval
        self.save_interval = save_interval
        self.resume_checkpoint = resume_checkpoint
        self.use_fp16 = use_fp16
        self.fp16_scale_growth = fp16_scale_growth
        self.schedule_sampler = schedule_sampler or UniformSampler(diffusion)
        self.weight_decay = weight_decay
        self.lr_anneal_steps = lr_anneal_steps
        self.gradient_clipping = gradient_clipping

        self.step = 0
        self.resume_step = 0
        self.global_batch = self.batch_size * (dist.get_world_size() if dist.is_initialized() else 1)


        self.lg_loss_scale = INITIAL_LOG_LOSS_SCALE
        self.sync_cuda = check_gpu_available()
        print('checkpoint_path:{}'.format(checkpoint_path))
        self.checkpoint_path = checkpoint_path # DEBUG **

        # 根据是否有GPU选择设备
        gpu_available = check_gpu_available()
        if gpu_available:
            self.model = model.to(rank)
        else:
            self.model = model.to(th.device("cpu"))

        self._load_and_sync_parameters()
        if gpu_available:
            self.use_ddp = True
            try:
                self.ddp_model = DDP(
                    self.model,
                    device_ids=[self.rank],
                    find_unused_parameters=True,
                )
            except Exception as e:
                print(f"DDP初始化失败: {e}，回退到非DDP模式")
                self.use_ddp = False
                self.ddp_model = self.model
        else:
            # CPU模式下不使用DDP，需要创建一个包装对象提供.module接口
            self.use_ddp = False
            self.ddp_model = self.model
            # 创建一个包装类，提供 .module 属性访问（模拟DDP的接口）
            class ModelWrapper:
                def __init__(self, model):
                    self.model = model
                    self.module = model  # .module 指向前面的 model

                def __call__(self, *args, **kwargs):
                    # 使其可调用
                    return self.model(*args, **kwargs)

                def __getattr__(self, name):
                    # 委托给内部 model
                    return getattr(self.model, name)
            self.ddp_model = ModelWrapper(self.model)

        self.model_params = list(self.ddp_model.parameters())
        self.master_params = self.model_params

        if self.use_fp16:
            self._setup_fp16()

        self.opt = AdamW(self.master_params, lr=self.lr, weight_decay=self.weight_decay)
        if self.resume_step:
            # Model was resumed, either due to a restart or a checkpoint
            # being specified at the command line.
            self.ema_params = [
                self._load_ema_parameters(rate) for rate in self.ema_rate
            ]
        else:
            self.ema_params = [
                copy.deepcopy(self.master_params) for _ in range(len(self.ema_rate))
            ]
    def _load_and_sync_parameters(self):
        resume_checkpoint = self.resume_checkpoint

        if resume_checkpoint:
            self.resume_step = parse_resume_step_from_filename(resume_checkpoint)
            if not dist.is_initialized() or dist.get_rank() == 0:
                # logger.log(f"loading model from checkpoint: {resume_checkpoint}...")
                print(f"loading model from checkpoint: {resume_checkpoint}...")
                self.model.load_state_dict(
                    dist_util.load_state_dict(
                        resume_checkpoint, map_location=dist_util.dev()
                    )
                )

        dist_util.sync_params(self.model.parameters())

    def _load_ema_parameters(self, rate):
        ema_checkpoint = find_ema_checkpoint(self.resume_checkpoint, self.resume_step, rate)
        if ema_checkpoint:
            logger.log(f"loading EMA from checkpoint: {ema_checkpoint}...")
            try:
                device = dist_util.dev()
            except Exception:
                device = th.device("cuda:0" if th.cuda.is_available() else "cpu")
            
            try:
                # 1. 保存当前的主模型权重备份
                backup_state_dict = copy.deepcopy(self.model.state_dict())
                
                # 2. 尝试将 EMA 权重直接加载进模型本体中
                self.model.load_state_dict(th.load(ema_checkpoint, map_location=device))
                
                # 3. 此时模型里的参数就是纯正的、维度绝对正确的 EMA 参数
                ema_params = [
                    p.clone().detach().to(device).float()
                    for p in self.model.parameters()
                ]
                
                # 4. 把模型恢复回主模型权重
                self.model.load_state_dict(backup_state_dict)
                
                if self.use_fp16:
                    return make_master_params(ema_params)
                return ema_params
            except Exception as e:
                logger.log(f"Warning: Failed to load EMA checkpoint {ema_checkpoint}: {e}")
                logger.log("Falling back to using master parameters as EMA parameters")
                # 如果加载失败，直接使用主模型的副本作为 EMA 参数
                return [p.clone().detach().to(device) for p in self.master_params]
            
        return None

    def _load_optimizer_state(self):
        main_checkpoint = find_resume_checkpoint() or self.resume_checkpoint
        opt_checkpoint = bf.join(
            bf.dirname(main_checkpoint), f"opt{self.resume_step:06}.pt"
        )
        if bf.exists(opt_checkpoint):
            logger.log(f"loading optimizer state from checkpoint: {opt_checkpoint}")
            state_dict = dist_util.load_state_dict(
                opt_checkpoint, map_location=dist_util.dev()
            )
            self.opt.load_state_dict(state_dict)

    def _setup_fp16(self):
        self.master_params = make_master_params(self.model_params)
        # Update all LayerNorm layers to use eps >= 1e-5 to prevent float16 underflow
        for module in self.model.modules():
            if isinstance(module, th.nn.LayerNorm):
                module.eps = max(module.eps, 1e-5)
        self.model.convert_to_fp16()

    def run_loop(self):
        print('START LOOP FLAG')
        while (
            not self.lr_anneal_steps
            or self.step + self.resume_step < self.lr_anneal_steps//self.world_size
        ):
            batch = next(self.data)
            cond = None
            # if self.step<3:
            #     print("RANK:",self.rank,"STEP:",self.step,"BATCH:",batch)
            self.run_step(batch, cond)
            if self.step % self.log_interval == 0:
                # dist.barrier()
                pass
                # print('loggggg')
                #logger.dumpkvs()
            if self.eval_data is not None and self.step % self.eval_interval == 0:
                # batch_eval, cond_eval = next(self.eval_data)
                # self.forward_only(batch, cond)
                print('eval on validation set')
                pass# logger.dumpkvs()
            if self.step % self.save_interval == 0 and self.step!=0:
                self.save()
                # Run for a finite amount of time in integration tests.
                if os.environ.get("DIFFUSION_TRAINING_TEST", "") and self.step > 0:
                    return
            self.step += 1
        # Save the last checkpoint if it wasn't already saved.
        if (self.step - 1) % self.save_interval != 0:
            self.save()

    def run_step(self, batch, cond):
        self.forward_backward(batch, cond)
        if self.use_fp16:
            self.optimize_fp16()
        else:
            self.optimize_normal()
        self.log_step()

    def forward_only(self, batch, cond):
        with th.no_grad():
            zero_grad(self.model_params)
            for i in range(0, batch.shape[0], self.microbatch):
                micro = batch[i: i + self.microbatch].to(dist_util.dev())
                micro_cond = {
                    k: v[i: i + self.microbatch].to(dist_util.dev())
                    for k, v in cond.items()
                }
                last_batch = (i + self.microbatch) >= batch.shape[0]
                t, weights = self.schedule_sampler.sample(micro.shape[0], dist_util.dev())
                # print(micro_cond.keys())
                compute_losses = functools.partial(
                    self.diffusion.training_losses,
                    self.ddp_model,
                    micro,
                    t,
                    model_kwargs=micro_cond,
                )

                if last_batch or not self.use_ddp:
                    losses = compute_losses()
                else:
                    with self.ddp_model.no_sync():
                        losses = compute_losses()

                log_loss_dict(
                    self.diffusion, t, {f"eval_{k}": v * weights for k, v in losses.items()}
                )


    def forward_backward(self, batch, cond):
        # zero_grad(self.model_params)
        self.opt.zero_grad()
        for i in range(0, batch[0].shape[0], self.microbatch):
            # 根据是否有GPU选择设备并对批次做切片 (microbatch)
            gpu_available = check_gpu_available()
            if gpu_available:
                micro = (
                    batch[0][i : i + self.microbatch].to(self.rank),
                    batch[1][i : i + self.microbatch].to(self.rank),
                    batch[2][i : i + self.microbatch].to(self.rank),
                    batch[3][i : i + self.microbatch].to(self.rank),
                )
            else:
                micro = (
                    batch[0][i : i + self.microbatch],
                    batch[1][i : i + self.microbatch],
                    batch[2][i : i + self.microbatch],
                    batch[3][i : i + self.microbatch],
                )
            last_batch = (i + self.microbatch) >= batch[0].shape[0]
            t, weights = self.schedule_sampler.sample(micro[0].shape[0], self.rank)

            compute_losses = functools.partial(
                self.diffusion.training_losses,
                self.ddp_model,
                micro,
                t,
                model_kwargs=None,
            )

            if last_batch or not self.use_ddp:
                losses = compute_losses()
            else:
                with self.ddp_model.no_sync():
                    losses = compute_losses()

            if isinstance(self.schedule_sampler, LossAwareSampler):
                self.schedule_sampler.update_with_local_losses(
                    t, losses["loss"].detach()
                )

            loss = (losses["loss"] * weights).mean()
            # print('----DEBUG-----',self.step,self.log_interval)
            if self.step % self.log_interval == 0 and self.rank==0:
                print("rank0: ",self.step,loss.item())
                swanlab.log({'loss':loss.item()})
            # log_loss_dict(
            #     self.diffusion, t, {k: v * weights for k, v in losses.items()}
            # )
            if self.use_fp16:
                loss_scale = 2 ** self.lg_loss_scale
                (loss * loss_scale).backward()
            else:
                loss.backward()

    def optimize_fp16(self):
        if any(not th.isfinite(p.grad).all() for p in self.model_params if p.grad is not None):
            self.lg_loss_scale -= 1
            # logger.log(f"Found NaN, decreased lg_loss_scale to {self.lg_loss_scale}")
            return

        model_grads_to_master_grads(self.model_params, self.master_params)
        self.master_params[0].grad.mul_(1.0 / (2 ** self.lg_loss_scale))
        self._log_grad_norm()
        self._anneal_lr()
        self.opt.step()
        for rate, params in zip(self.ema_rate, self.ema_params):
            update_ema(params, self.master_params, rate=rate)
        master_params_to_model_params(self.model_params, self.master_params)
        self.lg_loss_scale += self.fp16_scale_growth

    def grad_clip(self):
        # print('doing gradient clipping')
        max_grad_norm=self.gradient_clipping #3.0
        if hasattr(self.opt, "clip_grad_norm"):
            # Some optimizers (like the sharded optimizer) have a specific way to do gradient clipping
            self.opt.clip_grad_norm(max_grad_norm)
        # else:
        #     assert False
        # elif hasattr(self.model, "clip_grad_norm_"):
        #     # Some models (like FullyShardedDDP) have a specific way to do gradient clipping
        #     self.model.clip_grad_norm_(args.max_grad_norm)
        else:
            # Revert to normal clipping otherwise, handling Apex or full precision
            th.nn.utils.clip_grad_norm_(
                self.model.parameters(), #amp.master_params(self.opt) if self.use_apex else
                max_grad_norm,
            )

    def optimize_normal(self):
        if self.gradient_clipping > 0:
            self.grad_clip()
        # self._log_grad_norm()
        self._anneal_lr()
        self.opt.step()
        
        # === 新增：EMA 权重防丢失保护 ===
        if not hasattr(self, 'ema_params'):
            import copy
            self.ema_params = [
                copy.deepcopy(self.master_params)
                for _ in range(len(self.ema_rate))
            ]
        # ==============================
        
        for rate, params in zip(self.ema_rate, self.ema_params):
            update_ema(params, self.master_params, rate=rate)

    def _log_grad_norm(self):
        sqsum = 0.0
        for p in self.master_params:
            sqsum += (p.grad ** 2).sum().item()
        # logger.logkv_mean("grad_norm", np.sqrt(sqsum))

    def _anneal_lr(self):
        if not self.lr_anneal_steps:
            return
        frac_done = (self.step + self.resume_step) / self.lr_anneal_steps
        lr = self.lr * (1 - frac_done)
        for param_group in self.opt.param_groups:
            param_group["lr"] = lr

    def log_step(self):
        logger.logkv("step", self.step + self.resume_step)
        logger.logkv("samples", (self.step + self.resume_step + 1) * self.global_batch)
        if self.use_fp16:
            logger.logkv("lg_loss_scale", self.lg_loss_scale)

    def _master_params_to_state_dict(self, master_params):
        if self.use_fp16:
            master_params = unflatten_master_params(
                self.model_params, master_params
            )
        state_dict = self.model.state_dict()
        for i, (name, _value) in enumerate(self.model.named_parameters()):
            assert name in state_dict
            state_dict[name] = master_params[i]
        return state_dict

    def save(self):
        def save_checkpoint(rate, params):
            state_dict = self._master_params_to_state_dict(params)
            # Convert all parameters to float32 before saving
            state_dict = {k: v.float() for k, v in state_dict.items()}
            if not dist.is_initialized() or dist.get_rank() == 0:
                # logger.log(f"saving model {rate}...")
                print(f"saving model {rate}...")
                if not rate:
                    filename = f"PLAIN_model{((self.step+self.resume_step)*self.world_size):06d}.pt"
                else:
                    filename = f"PLAIN_ema_{rate}_{((self.step+self.resume_step)*self.world_size):06d}.pt"
                # print('writing to', bf.join(get_blob_logdir(), filename))
                # print('writing to', bf.join(self.checkpoint_path, filename))
                print('writing to', bf.join(self.checkpoint_path, filename))
                if not os.path.exists(self.checkpoint_path):
                    os.makedirs(self.checkpoint_path)
                with bf.BlobFile(bf.join(self.checkpoint_path, filename), "wb") as f:
                    th.save(state_dict, f)
        save_checkpoint(0, self.master_params)
        for rate, params in zip(self.ema_rate, self.ema_params):
            save_checkpoint(rate, params)

        # del state_dict
        # torch.save(self.opt.state_dict(), bf.join(self.checkpoint_path, f"opt{(self.step+self.resume_step)*self.world_size:06}.pt"))
