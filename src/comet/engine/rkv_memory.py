"""Bounded-workspace evaluation of the pinned R-KV redundancy score."""


def redundancy_scores(
    k_by_head, *, redundancy_threshold, retain_ratio, retain_direction, max_similarity_bytes=1 << 30
):
    import torch

    heads, length, _ = k_by_head.shape
    if length <= 1:
        return torch.zeros((heads, length), dtype=torch.bfloat16, device=k_by_head.device)
    keys = k_by_head.to(dtype=torch.bfloat16)
    keys = keys / (keys.norm(dim=-1, keepdim=True) + 1e-8)
    # Include the integer selection temporaries, not just the similarity matrix.
    rows = max(1, min(length, min(max_similarity_bytes, 1 << 28) // (heads * length * 19)))
    indices = torch.arange(length, dtype=torch.long, device=keys.device)
    total = torch.zeros((heads, length), dtype=torch.float32, device=keys.device)
    for start in range(0, length, rows):
        end = min(start + rows, length)
        similarity = torch.bmm(keys[:, start:end], keys.transpose(1, 2))
        similarity[:, torch.arange(end - start, device=keys.device), indices[start:end]] = 0
        masked = torch.where(similarity > redundancy_threshold, indices[None, None], 0)
        if retain_direction == "last":
            retained = masked.max(dim=-1).values
        elif retain_direction == "first":
            retained = masked.min(dim=-1).values
        else:
            count = max(1, int(length * retain_ratio))
            if retain_direction == "last_percent":
                retained = masked.topk(count, dim=-1).values[:, :, 0]
            elif retain_direction == "first_percent":
                retained = masked.topk(count, dim=-1, largest=False).values[:, :, -1]
            else:
                raise ValueError(f"Unsupported R-KV retain direction: {retain_direction}")
        similarity.scatter_(2, retained.unsqueeze(-1), 0.0)
        total += similarity.float().sum(dim=1)
    return (total / length).to(torch.bfloat16).softmax(dim=-1)
