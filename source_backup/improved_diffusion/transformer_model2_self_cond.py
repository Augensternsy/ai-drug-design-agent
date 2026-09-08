# ====================================================================================
# 文件作用:
#   实现支持自条件化 (Self-Conditioning) 机制的 TransformerNetModel2 模型架构。
#
# 参照原文件:
#   improved_diffusion/transformer_model2.py
#
# 所做的修改与目的:
#   1. 在 __init__ 构造函数中新增 self_cond 门控参数，默认值为 False。
#   2. 扩维输入映射层 input_up_proj：
#      - 当 self_cond=True 时，输入特征维度由 in_channels 翻倍为 in_channels * 2，
#        以便同时接收当前噪声状态 x_t 与前一步预测的去噪状态 x_0_prev 的拼接输入。
#      - 当 self_cond=False 时，保持原始 in_channels 输入维度，向前完全兼容。
# ====================================================================================

from .transformer_utils import BertAttention, trans_nd, layer_norm
from transformers import AutoConfig
# from transformers import BertEncoder
from transformers.models.bert.modeling_bert import BertEncoder
import torch
from abc import abstractmethod

import math

import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F

from .fp16_util import convert_module_to_f16, convert_module_to_f32
from .nn import (
    SiLU,
    conv_nd,
    linear,
    avg_pool_nd,
    zero_module,
    timestep_embedding,
    checkpoint,
)

print('checkpoint 0810 in model.py (Self-Conditioning Version)')
class TransformerNetModel2(nn.Module):
    def __init__(
        self,
        in_channels,
        model_channels,
        dropout=0.1,
        num_classes=None,
        use_checkpoint=False,
        config=None,
        config_name='bert-base-uncased',
        training_mode='emb', # e2e
        vocab_size=None, #821
        experiment_mode='lm', #lm
        init_pretrained=False,
        logits_mode=1,
        hidden_size=768,
        # hidden_size=640,  # 修改
        num_attention_heads = 12,
        num_hidden_layers=12,
        mask = False,
        self_cond=False  # 新增自条件化门控参数
    ):
        super().__init__()
        import os
        from pathlib import Path
        _default_bert_dir = Path(__file__).resolve().parents[2] / "models" / "bert-base-uncased"
        bert_config_path = os.getenv("BERT_CONFIG_PATH", str(_default_bert_dir))
        config = AutoConfig.from_pretrained(bert_config_path)
        config._attn_implementation = "eager" # 修改
        config.is_decoder=True
        config.add_cross_attention=True
        config.hidden_dropout_prob = 0.1
        config.hidden_size = hidden_size
        config.num_attention_heads = num_attention_heads
        config.num_hidden_layers = num_hidden_layers
            # config.hidden_size = 512
        self.mask = mask
        self.in_channels = in_channels # 16
        self.model_channels = model_channels # 128
        self.dropout =dropout
        self.num_classes = None # None
        self.use_checkpoint = False # False
        self.num_heads_upsample = 4
        self.logits_mode = 1
        self.self_cond = self_cond  # 存储自条件化参数
        vocab_size = 312 # 修改
        # self.deep_channels = deep_channels
        self.word_embedding = nn.Embedding(vocab_size, self.in_channels)
        # deepmax = 28
        # self.deep_embedding = nn.Embedding(deepmax,self.deep_channels)
        self.lm_head = nn.Linear(self.in_channels, vocab_size)
        self.lm_head.weight = self.word_embedding.weight
        # self.deep_head = nn.Linear(self.deep_channels, deepmax)
        # self.deep_head.weight = self.deep_embedding.weight
        self.conditional_gen = False

        # 新增：维度适配层（将1024维的蛋白质嵌入转为config.hidden_size维）
        self.desc_dim_adapter = nn.Linear(1024, config.hidden_size)  # in_features=1024（蛋白质嵌入维度），out_features=config.hidden_size（目标输出维度）

        # self.desc_down_proj = nn.Linear(config.hidden_size,config.hidden_size)

        self.desc_down_proj = nn.Sequential(
            # linear(config.hidden_size,config.hidden_size),
            linear(config.hidden_size,config.hidden_size),
            SiLU(),
            linear(config.hidden_size, config.hidden_size),
        )

        time_embed_dim = model_channels * 4 # 512
        self.time_embed = nn.Sequential(
            linear(model_channels, time_embed_dim),
            SiLU(),
            linear(time_embed_dim, config.hidden_size),
        )

        # 修改：自条件化支持下的输入维度变换
        # 如果启用自条件化，由于输入是 x_t 和 x_0_prev 的拼接，通道数翻倍
        in_features = in_channels * 2 if self_cond else in_channels
        self.input_up_proj = nn.Sequential(
            nn.Linear(in_features, config.hidden_size),
            nn.Tanh(), nn.Linear(config.hidden_size, config.hidden_size))
        
        self.input_transformers = BertEncoder(config)

        self.register_buffer("position_ids", torch.arange(config.max_position_embeddings).expand((1, -1)))
        self.position_embeddings = nn.Embedding(config.max_position_embeddings, config.hidden_size)
        # self.token_type_embeddings = nn.Embedding(config.type_vocab_size, config.hidden_size)
        self.LayerNorm = nn.LayerNorm(config.hidden_size, eps=config.layer_norm_eps)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.output_down_proj = nn.Sequential(nn.Linear(config.hidden_size, config.hidden_size),
                                              nn.Tanh(), nn.Linear(config.hidden_size, in_channels))

    def get_embeds(self, input_ids):
        return self.word_embedding(input_ids)

    def get_embeds_with_deep(self, input_ids):
        atom , deep = input_ids
        # th.tensor([0]).to('cuda')
        # print(atom,deep)
        # print(deep[0])
        atom = self.word_embedding(atom)
        # th.tensor([0]).to('cuda')
        deep = self.deep_embedding(deep)
        # th.tensor([0]).to('cuda')
        return torch.concat([atom,deep],dim=-1)

    def get_logits_deep(self,hidden_repr):
        hidden_repr = hidden_repr.float()
        if hasattr(self, 'deep_head'):
            weight = self.deep_head.weight.float()
            bias = self.deep_head.bias.float() if self.deep_head.bias is not None else None
            return F.linear(hidden_repr, weight, bias)
        return hidden_repr

    def get_logits(self, hidden_repr):
        # Always compute logits in float32 to prevent overflow in softmax/CrossEntropyLoss under FP16
        hidden_repr = hidden_repr.float()
        weight = self.lm_head.weight.float()
        bias = self.lm_head.bias.float() if self.lm_head.bias is not None else None
        
        if self.logits_mode == 1:
            return F.linear(hidden_repr, weight, bias)
        elif self.logits_mode == 2:
            text_emb = hidden_repr
            emb_norm = (weight ** 2).sum(-1).view(-1, 1)  # vocab
            text_emb_t = th.transpose(text_emb.view(-1, text_emb.size(-1)), 0, 1)  # d, bsz*seqlen
            arr_norm = (text_emb ** 2).sum(-1).view(-1, 1)  # bsz*seqlen, 1
            dist = emb_norm + arr_norm.transpose(0, 1) - 2.0 * th.mm(weight,
                                                                     text_emb_t)  # (vocab, d) x (d, bsz*seqlen)
            scores = th.sqrt(th.clamp(dist, 0.0, np.inf)).view(emb_norm.size(0), hidden_repr.size(0),
                                                               hidden_repr.size(1)) # vocab, bsz*seqlen
            scores = -scores.permute(1, 2, 0).contiguous()

            return scores
        else:
            raise NotImplementedError

    def forward(self, x, timesteps, desc_state, desc_mask ,y=None, src_ids=None, src_mask=None):
        """
        Apply the model to an input batch.

        :param x: an [N x C x ...] Tensor of inputs.
        :param timesteps: a 1-D batch of timesteps.
        :param y: an [N] Tensor of labels, if class-conditional.
        :return: an [N x C x ...] Tensor of outputs.
        """
        # print(f'real model inputs: {timesteps}')
        assert (y is not None) == (
            self.num_classes is not None
        ), "must specify y if and only if the model is class-conditional"

        # Cast inputs to the inner dtype (float16 if running in FP16 mode)
        x = x.type(self.inner_dtype)
        desc_state = desc_state.type(self.inner_dtype)

        # hs = []
        emb = self.time_embed(timestep_embedding(timesteps, self.model_channels).type(self.inner_dtype))

        # 处理 desc_state：[batch, 1, seq_len, dim] 或 [batch, seq_len, dim]
        if desc_state.dim() == 4:
            # [batch, 1, seq_len, dim] -> [batch, seq_len, dim]
            desc_state = desc_state.squeeze(1)
        
        # 将 1024 维蛋白质嵌入映射到 768 维
        desc_state = self.desc_dim_adapter(desc_state)
        
        # 核心修复：将 desc_mask 从二进制掩码 (1=保留, 0=掩蔽) 转换为加性掩码 (0.0=保留, -10000.0=掩蔽)
        desc_mask = (1.0 - desc_mask.to(desc_state.dtype)) * -10000.0
        
        # 处理 desc_mask
        # 确保是 4D：[batch, 1, 1, seq_len] 用于 cross-attention
        while desc_mask.dim() < 4:
            desc_mask = desc_mask.unsqueeze(1)
        
        emb_x = self.input_up_proj(x)
        # x 的形状是 [batch_size, something, seq_length, channels]
        seq_length = x.size(-2)
        position_ids = self.position_ids[:, : seq_length ]

        # 处理 4D 输入的情况 [batch, extra_dim, seq_len, hidden]
        if x.dim() == 4:
            # 将 4D 转换为 3D 以便正确广播
            batch_size, extra_dim, seq_len, channels = emb_x.shape
            # emb_x: [batch, extra_dim, seq_len, hidden] -> [batch*extra_dim, seq_len, hidden]
            emb_x_flat = emb_x.view(batch_size * extra_dim, seq_len, channels)
            # position_embeddings: [1, seq_len, hidden] -> [batch*extra_dim, seq_len, hidden]
            pos_emb_flat = self.position_embeddings(position_ids).expand(batch_size * extra_dim, -1, -1)
            # emb: [batch*hidden] -> [batch*extra_dim, hidden] -> [batch*extra_dim, seq_len, hidden]
            emb_expanded = emb.unsqueeze(1).expand(-1, extra_dim, -1).reshape(batch_size * extra_dim, -1)
            emb_expanded = emb_expanded.unsqueeze(1).expand(-1, seq_len, -1)
            # 相加得到 3D emb_inputs
            emb_inputs = pos_emb_flat + emb_x_flat + emb_expanded
            emb_inputs = self.dropout(self.LayerNorm(emb_inputs))
            # desc_state 也需要复制 extra_dim 次
            desc_state = desc_state.repeat(extra_dim, 1, 1)
            desc_mask = desc_mask.repeat(extra_dim, 1, 1, 1)
        else:
            # 3D 输入保持原逻辑
            emb_inputs = self.position_embeddings(position_ids) + emb_x + emb.unsqueeze(1).expand(-1, seq_length, -1)
            emb_inputs = self.dropout(self.LayerNorm(emb_inputs))
        
        input_trans_hidden_states = self.input_transformers(emb_inputs,encoder_hidden_states=desc_state,encoder_attention_mask=desc_mask).last_hidden_state
        h = self.output_down_proj(input_trans_hidden_states)
        
        # 如果我们之前展平了维度，现在需要将输出形状转换回原始形状
        if emb_inputs.dim() == 3 and x.dim() == 4:
            # 将形状从 [batch*extra_dim, seq_len, channels] 转换回 [batch, extra_dim, seq_len, channels]
            batch_size = x.size(0)
            extra_dim = x.size(1)
            seq_len = x.size(2)
            channels = h.size(-1)
            # 确保形状匹配
            expected_size = batch_size * extra_dim * seq_len * channels
            if h.numel() == expected_size:
                h = h.view(batch_size, extra_dim, seq_len, channels)
        
        h = h.type(x.dtype)
        return h

    def get_feature_vectors(self, x, timesteps, y=None):
        hs = []
        emb = self.time_embed(timestep_embedding(timesteps, self.model_channels))
        if self.num_classes is not None:
            assert y.shape == (x.shape[0],)
            emb = emb + self.label_emb(y)
        result = dict(down=[], up=[])
        h = x.type(self.inner_dtype)
        for module in self.input_blocks:
            h = module(h, emb)
            hs.append(h)
            result["down"].append(h.type(x.dtype))
        h = self.middle_block(h, emb)
        result["middle"] = h.type(x.dtype)
        for module in self.output_blocks:
            cat_in = th.cat([h, hs.pop()], dim=-1)
            h = module(cat_in, emb)
            result["up"].append(h.type(x.dtype))
        return result

    @property
    def inner_dtype(self):
        return next(self.input_transformers.parameters()).dtype

    def convert_to_fp16(self):
        self.to(th.float16)

    def convert_to_fp32(self):
        self.to(th.float32)
