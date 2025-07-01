#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import numpy as np
import pandas as pd

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

def evaluate_formula_gpu(formula: str, data: pd.DataFrame, formula_engine) -> np.ndarray:
    """
    [OPTIMIZED] 在GPU上评估公式。
    它现在直接接收DataFrame和FormulaEngine，以简化变量管理。
    """
    if not is_gpu_available():
        raise RuntimeError("GPU (CuPy) 环境不可用。")

    try:
        # 构建GPU上的执行上下文
        safe_dict = {
            'sin': cp.sin, 'cos': cp.cos, 'tan': cp.tan, 'asin': cp.arcsin, 'acos': cp.arccos, 'atan': cp.arctan,
            'sinh': cp.sinh, 'cosh': cp.cosh, 'tanh': cp.tanh, 'exp': cp.exp, 'log': cp.log, 'log10': cp.log10,
            'sqrt': cp.sqrt, 'abs': cp.abs, 'floor': cp.floor, 'ceil': cp.ceil, 'round': cp.round,
            'min': cp.minimum, 'max': cp.maximum, 'pi': cp.pi, 'e': cp.e
        }
        
        # 添加全局和科学常量
        for const_name, value in formula_engine.get_all_constants_and_globals().items():
            safe_dict[const_name] = value

        # 找到公式中用到的变量，并转移到GPU
        req_vars = formula_engine.get_used_variables(formula)
        for var_name in req_vars:
            if var_name in data.columns:
                safe_dict[var_name] = cp.asarray(data[var_name].values)

        # 执行计算
        result_gpu = eval(formula, {"__builtins__": {}}, safe_dict)
        
        # [FIX] 处理结果是标量的情况 (例如公式是 'p_global_mean' 或 '2*pi')
        if not isinstance(result_gpu, cp.ndarray):
            # 结果是一个标量。我们需要将其广播为一个数组。
            # 为此，我们需要从输入变量中获取一个参考数组形状。
            try:
                # 找到第一个数组变量以获取形状
                ref_shape = next(v.shape for v in safe_dict.values() if isinstance(v, cp.ndarray))
                # 创建一个与输入数据相同大小的常量数组
                result_gpu = cp.full(ref_shape, float(result_gpu), dtype=cp.float32)
            except StopIteration:
                # 如果公式中没有任何逐点变量（如 'u', 'v', 'x'），则会发生此错误。
                # 这样的公式不能作为热力图/等高线图进行可视化。
                raise ValueError("公式必须至少包含一个逐点数据变量 (如 u, v, x 等) 才能进行空间可视化。")

        # 将结果从GPU内存转移回CPU内存
        result_cpu = cp.asnumpy(result_gpu)
        
        # 清理GPU内存池
        mempool = cp.get_default_memory_pool()
        mempool.free_all_blocks()
        
        return result_cpu
        
    except Exception as e:
        logger.error(f"GPU 公式计算失败: {formula} - {e}", exc_info=True)
        # 重新抛出更通用的消息，但包含原始错误
        raise ValueError(f"GPU 公式计算错误: {e}")