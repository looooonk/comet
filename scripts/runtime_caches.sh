#!/usr/bin/env bash
# Source before importing GPU libraries, including in standalone preflight jobs.
: "${COMET_STORAGE:?Set COMET_STORAGE to persistent project storage}"

export XDG_CACHE_HOME="$COMET_STORAGE/cache"
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export UV_CACHE_DIR="$XDG_CACHE_HOME/uv"
export TRITON_CACHE_DIR="$XDG_CACHE_HOME/triton"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export TORCHINDUCTOR_CACHE_DIR="$XDG_CACHE_HOME/torchinductor"
export TORCH_EXTENSIONS_DIR="$XDG_CACHE_HOME/torch-extensions"
export PYTORCH_KERNEL_CACHE_PATH="$XDG_CACHE_HOME/torch-kernels"
export CUDA_CACHE_PATH="$XDG_CACHE_HOME/cuda"
export FLASHINFER_WORKSPACE_BASE="$XDG_CACHE_HOME/flashinfer"
export TVM_FFI_CACHE_DIR="$XDG_CACHE_HOME/tvm-ffi"

mkdir -p "$HF_HOME" "$UV_CACHE_DIR" "$TRITON_CACHE_DIR" \
    "$TORCH_HOME" "$TORCHINDUCTOR_CACHE_DIR" "$TORCH_EXTENSIONS_DIR" \
    "$PYTORCH_KERNEL_CACHE_PATH" "$CUDA_CACHE_PATH" \
    "$FLASHINFER_WORKSPACE_BASE" "$TVM_FFI_CACHE_DIR"
