#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import numpy as np

logger = logging.getLogger(__name__)
CUPY_AVAILABLE = False
cp = None

try:
    import cupy as cp
    device_count = cp.cuda.runtime.getDeviceCount()
    if device_count > 0:
        CUPY_AVAILABLE = True
        logger.info(f"CuPy 已找到，检测到 {device_count} 个CUDA设备。GPU 加速可用。")
    else:
        CUPY_AVAILABLE = False
        logger.warning("CuPy 已加载，但未检测到可用的CUDA设备。GPU加速不可用。")
except ImportError:
    CUPY_AVAILABLE = False
    logger.warning("CuPy 未安装，GPU 加速不可用。请运行 'pip install cupy-cudaXXX' (XXX是您的CUDA版本)。")
except Exception as e:
    CUPY_AVAILABLE = False
    logger.warning(f"CuPy 初始化失败，GPU 加速不可用。错误: {e}")

def is_gpu_available():
    return CUPY_AVAILABLE

def evaluate_formula_gpu(formula: str, variable_data: dict):
    if not is_gpu_available(): raise RuntimeError("GPU (CuPy) 环境不可用。")
    try:
        safe_dict = {
            'sin': cp.sin, 'cos': cp.cos, 'tan': cp.tan, 'asin': cp.arcsin, 'acos': cp.arccos, 'atan': cp.arctan,
            'sinh': cp.sinh, 'cosh': cp.cosh, 'tanh': cp.tanh, 'exp': cp.exp, 'log': cp.log, 'log10': cp.log10,
            'sqrt': cp.sqrt, 'abs': cp.abs, 'floor': cp.floor, 'ceil': cp.ceil, 'round': cp.round,
            'min': cp.minimum, 'max': cp.maximum, 'pi': cp.pi, 'e': cp.e
        }
        for var_name, value in variable_data.items():
            safe_dict[var_name] = cp.asarray(value) if isinstance(value, np.ndarray) else value

        result_gpu = eval(formula, {"__builtins__": __builtins__}, safe_dict) # Allow access to __builtins__ for CuPy's internal eval
        
        if not isinstance(result_gpu, cp.ndarray):
            ref_shape = next(v.shape for v in safe_dict.values() if isinstance(v, cp.ndarray))
            result_gpu = cp.full(ref_shape, float(result_gpu), dtype=cp.float32)

        result_cpu = cp.asnumpy(result_gpu)
        mempool = cp.get_default_memory_pool()
        mempool.free_all_blocks()
        return result_cpu
    except Exception as e:
        logger.error(f"GPU 公式计算失败: {formula} - {e}")
        raise ValueError(f"GPU 公式计算错误: {e}")