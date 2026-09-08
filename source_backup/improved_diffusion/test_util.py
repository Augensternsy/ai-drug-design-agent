import torch as th
import numpy as np

def compute_logp(args, model, x, input_ids):
    word_emb = model.weight
    sigma = 0.1
    if args.model_arch == '1d-unet':
        x = x.permute(0, 2, 1)

    bsz, seqlen, dim = x.shape

    x_flat = x.reshape(-1, x.size(-1)).unsqueeze(0)  # 1, bsz*sample*seqlen, dim
    word_emb_flat = word_emb.unsqueeze(1)  # vocab, 1,  dim
    diff = (x_flat - word_emb_flat) ** 2  # vocab, seqlen, dim

    logp_expanded = -diff.sum(dim=-1) / (2 * sigma ** 2)  # vocab, seqlen
    logp_expanded = logp_expanded.permute((1, 0))
    # print(th.topk(logp_expanded.view(bsz, seqlen, -1), k=5, dim=-1)[0])
    # print(input_ids[0])
    ce = th.nn.CrossEntropyLoss(reduction='none')
    loss = ce(logp_expanded, input_ids.view(-1)).view(bsz, seqlen)
    # print(loss[0])

    # print(loss.shape)
    return loss

def get_weights(model, args):
    if hasattr(model, 'transformer'):
        input_embs = model.transformer.wte  # input_embs
        down_proj = model.down_proj
        down_proj_emb = down_proj(input_embs.weight)
        print(down_proj_emb.shape)
        # model = th.nn.Embedding(down_proj_emb.shape[1], down_proj_emb.shape[0])
        model = th.nn.Embedding(down_proj_emb.size(0), down_proj_emb.size(1))
        print(args.emb_scale_factor)
        model.weight.data = down_proj_emb * args.emb_scale_factor

    elif hasattr(model, 'weight'):
        pass
    else:
        assert NotImplementedError
        
    model.weight.requires_grad = False
    return model

def denoised_fn_round(args, model, text_emb, t):
    thresh_t = getattr(args, 'clamp_thresh', 350)
    if thresh_t is not None and t[0] > thresh_t:
        return text_emb
    
    top_k = getattr(args, 'clamp_top_k', 5)
    temp = getattr(args, 'clamp_temp', 0.1)
    soft_clamp = getattr(args, 'clamp_soft', True)

    down_proj_emb = model
    old_shape = text_emb.shape
    old_device = text_emb.device

    # Flatten text_emb if it has batch dimension
    if len(text_emb.shape) > 2:
        flat_text_emb = text_emb.reshape(-1, text_emb.size(-1))
    else:
        flat_text_emb = text_emb

    flat_text_emb_dev = flat_text_emb.to(down_proj_emb.device)

    def get_efficient_knn_topk(down_proj_emb, text_emb, k=1, dist='l2'):
        if dist == 'l2':
            emb_norm = (down_proj_emb**2).sum(-1).view(-1, 1) # vocab, 1
            text_emb_t = th.transpose(text_emb, 0, 1) # d, bsz*seqlen
            arr_norm = (text_emb ** 2).sum(-1).view(-1, 1) # bsz*seqlen, 1
            dist_matrix = emb_norm + arr_norm.transpose(0, 1) - 2.0 * th.mm(down_proj_emb, text_emb_t)
            dist_matrix = th.clamp(dist_matrix, 0.0, np.inf)
        
        # negative distance for topk (smaller distance -> larger negative value)
        topk_out = th.topk(-dist_matrix, k=k, dim=0)
        return topk_out.values, topk_out.indices

    # Get top_k nearest neighbors
    neg_dists, indices = get_efficient_knn_topk(down_proj_emb, flat_text_emb_dev, k=top_k, dist='l2')

    if top_k > 1:
        # Compute weights based on softmax of negative distances over temp
        weights = th.softmax(neg_dists / temp, dim=0) # [top_k, bsz*seqlen]
        # Weighted sum of top_k embeddings
        clamped_embs = (down_proj_emb[indices] * weights.unsqueeze(-1)).sum(dim=0) # [bsz*seqlen, dim]
    else:
        rounded_tokens = indices[0]
        clamped_embs = down_proj_emb[rounded_tokens]

    if soft_clamp:
        # alpha goes from 0.0 (at t=thresh_t) to 1.0 (at t=0)
        alpha = (thresh_t - t[0].float()) / thresh_t
        alpha = th.clamp(alpha, 0.0, 1.0)
        new_embeds = alpha * clamped_embs + (1.0 - alpha) * flat_text_emb_dev
    else:
        new_embeds = clamped_embs

    new_embeds = new_embeds.view(old_shape).to(old_device)
    return new_embeds

def load_results(json_path, load_dict):
    import json
    with open(json_path, 'w') as f:
        json.dump(load_dict, f, indent=2)
