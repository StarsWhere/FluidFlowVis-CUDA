#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心计算模块：提供共享的数据准备与插值功能，包括高级空间运算。
"""
import numpy as np
import logging
import re
from scipy.interpolate import griddata
from scipy.spatial.qhull import QhullError
from typing import Dict, Any

from src.core.formula_engine import FormulaEngine
from src.utils.gpu_utils import is_gpu_available, evaluate_formula_gpu, cp

logger = logging.getLogger(__name__)

def _interpolate_field(points, values, grid_x, grid_y):
    """
    辅助函数，执行一次插值，并使用最近邻方法填充边界外的NaN值。
    """
    if values is None:
        return None
    valid_indices = ~np.isnan(points).any(axis=1) & ~np.isnan(values)
    filtered_points = points[valid_indices]
    filtered_values = values[valid_indices]
    
    if filtered_points.shape[0] < 3:
        logger.warning("有效插值点少于3个，无法进行线性插值，将回退到最近邻插值。")
        if filtered_points.size == 0 or filtered_values.size == 0:
            return np.full_like(grid_x, np.nan)
        try:
            return griddata(filtered_points, filtered_values, (grid_x, grid_y), method='nearest')
        except QhullError:
             raise ValueError("输入点共线或退化，无法生成插值网格。")

    try:
        # 1. 执行主要的线性插值
        grid = griddata(filtered_points, filtered_values, (grid_x, grid_y), method='linear')
        
        # 2. (关键优化) 检查并填充边界外的NaN值
        if np.isnan(grid).any():
            # 使用最近邻插值来填充线性插值无法覆盖的区域 (即凸包外的区域)
            grid_nearest = griddata(filtered_points, filtered_values, (grid_x, grid_y), method='nearest')
            nan_indices = np.isnan(grid)
            grid[nan_indices] = grid_nearest[nan_indices]
            
        return grid

    except QhullError:
        logger.error("插值时发生QhullError，输入点可能共线。")
        raise ValueError("输入点共线或退化，无法生成2D插值网格。")

def compute_gridded_field(
    data: np.ndarray, 
    formula: str, 
    x_formula: str,
    y_formula: str,
    formula_engine: FormulaEngine, 
    grid_resolution: tuple,
    use_gpu: bool = False
) -> Dict[str, np.ndarray]:
    """
    计算单个公式的网格化场，支持简单插值和高级空间运算。
    返回一个包含网格坐标和计算结果的字典。
    """
    if data is None or data.empty or not formula:
        return {}
    
    use_gpu = use_gpu and is_gpu_available()

    # 1. 计算坐标轴
    try:
        x_values = formula_engine.evaluate_formula(data, x_formula)
        y_values = formula_engine.evaluate_formula(data, y_formula)
    except Exception as e:
        raise ValueError(f"计算坐标轴失败: x='{x_formula}', y='{y_formula}'. Error: {e}")

    # 2. 定义网格
    grid_x, grid_y = np.meshgrid(
        np.linspace(x_values.min(), x_values.max(), grid_resolution[0]),
        np.linspace(y_values.min(), y_values.max(), grid_resolution[1])
    )
    points = np.vstack([x_values, y_values]).T

    # 3. 递归或直接计算公式
    result_grid = _evaluate_spatial_formula_recursively(
        formula, data, points, grid_x, grid_y, formula_engine, use_gpu
    )

    return {
        'grid_x': grid_x,
        'grid_y': grid_y,
        'result_data': result_grid
    }

def _evaluate_spatial_formula_recursively(
    formula: str,
    data: np.ndarray, 
    points: np.ndarray,
    grid_x: np.ndarray, 
    grid_y: np.ndarray, 
    formula_engine: FormulaEngine,
    use_gpu: bool
) -> np.ndarray:
    """
    [OPTIMIZED] 递归地解析和计算公式，处理空间操作，并利用GPU进行梯度计算。
    """
    formula = formula.strip()
    
    # 查找最外层的空间函数调用
    match = re.match(r'^\s*(grad_x|grad_y|div|curl|laplacian)\s*\((.*)\)\s*$', formula, re.DOTALL)
    
    if not match:
        # 基本情况：没有空间函数，直接求值和插值
        values = _get_values_from_simple_formula(data, formula, formula_engine, use_gpu)
        return _interpolate_field(points, values, grid_x, grid_y)

    # 递归情况：处理空间函数
    op, args_str = match.groups()
    
    # 解析逗号分隔的参数，同时处理嵌套括号
    args = []
    balance = 0
    last_cut = 0
    for i, char in enumerate(args_str):
        if char == '(': balance += 1
        elif char == ')': balance -= 1
        elif char == ',' and balance == 0:
            args.append(args_str[last_cut:i].strip())
            last_cut = i + 1
    args.append(args_str[last_cut:].strip())

    # 递归计算每个参数的网格化场
    arg_grids = [_evaluate_spatial_formula_recursively(arg, data, points, grid_x, grid_y, formula_engine, use_gpu) for arg in args]

    # --- 执行空间运算 (CPU 或 GPU) ---
    if use_gpu:
        # 转移到GPU
        grid_y_gpu = cp.asarray(grid_y[:, 0])
        grid_x_gpu = cp.asarray(grid_x[0, :])
        arg_grids_gpu = [cp.asarray(grid) if grid is not None else None for grid in arg_grids]
        
        result_gpu = _perform_spatial_op_gpu(op, arg_grids_gpu, grid_y_gpu, grid_x_gpu)
        
        # 将结果转回CPU
        return cp.asnumpy(result_gpu) if result_gpu is not None else None
    else:
        # 在CPU上执行
        return _perform_spatial_op_cpu(op, arg_grids, grid_y[:, 0], grid_x[0, :])


def _perform_spatial_op_cpu(op, arg_grids, grid_y_coords, grid_x_coords):
    """在CPU上使用NumPy执行空间运算。"""
    if op in ['grad_x', 'grad_y', 'laplacian']:
        if len(arg_grids) != 1: raise ValueError(f"{op}需要1个参数，但收到了{len(arg_grids)}")
        field = arg_grids[0]
        if field is None: return None
        grad_gy, grad_gx = np.gradient(field, grid_y_coords, grid_x_coords)
        if op == 'grad_x': return grad_gx
        if op == 'grad_y': return grad_gy
        if op == 'laplacian':
            g_gx_y, g_gx_x = np.gradient(grad_gx, grid_y_coords, grid_x_coords)
            g_gy_y, g_gy_x = np.gradient(grad_gy, grid_y_coords, grid_x_coords)
            return g_gx_x + g_gy_y

    elif op in ['div', 'curl']:
        if len(arg_grids) != 2: raise ValueError(f"{op}需要2个参数，但收到了{len(arg_grids)}")
        u, v = arg_grids
        if u is None or v is None: return None
        grad_u_y, grad_u_x = np.gradient(u, grid_y_coords, grid_x_coords)
        grad_v_y, grad_v_x = np.gradient(v, grid_y_coords, grid_x_coords)
        if op == 'div': return grad_u_x + grad_v_y
        if op == 'curl': return grad_v_x - grad_u_y
    
    raise ValueError(f"未知的空间操作: {op}")


def _perform_spatial_op_gpu(op, arg_grids_gpu, grid_y_coords_gpu, grid_x_coords_gpu):
    """在GPU上使用CuPy执行空间运算。"""
    if op in ['grad_x', 'grad_y', 'laplacian']:
        if len(arg_grids_gpu) != 1: raise ValueError(f"{op}需要1个参数，但收到了{len(arg_grids_gpu)}")
        field = arg_grids_gpu[0]
        if field is None: return None
        grad_gy, grad_gx = cp.gradient(field, grid_y_coords_gpu, grid_x_coords_gpu)
        if op == 'grad_x': return grad_gx
        if op == 'grad_y': return grad_gy
        if op == 'laplacian':
            g_gx_y, g_gx_x = cp.gradient(grad_gx, grid_y_coords_gpu, grid_x_coords_gpu)
            g_gy_y, g_gy_x = cp.gradient(grad_gy, grid_y_coords_gpu, grid_x_coords_gpu)
            return g_gx_x + g_gy_y

    elif op in ['div', 'curl']:
        if len(arg_grids_gpu) != 2: raise ValueError(f"{op}需要2个参数，但收到了{len(arg_grids_gpu)}")
        u, v = arg_grids_gpu
        if u is None or v is None: return None
        grad_u_y, grad_u_x = cp.gradient(u, grid_y_coords_gpu, grid_x_coords_gpu)
        grad_v_y, grad_v_x = cp.gradient(v, grid_y_coords_gpu, grid_x_coords_gpu)
        if op == 'div': return grad_u_x + grad_v_y
        if op == 'curl': return grad_v_x - grad_u_y
    
    raise ValueError(f"未知的空间操作: {op}")


def _get_values_from_simple_formula(data, formula, formula_engine, use_gpu):
    """
    为没有空间操作的简单公式计算逐点值。
    """
    if not formula:
        return None

    uses_aggregates = any(agg_func in formula for agg_func in formula_engine.allowed_aggregates)

    if use_gpu and is_gpu_available() and not uses_aggregates:
        try:
            return evaluate_formula_gpu(formula, data, formula_engine)
        except Exception as e:
            logger.warning(f"GPU评估公式 '{formula}' 失败，回退到CPU。错误: {e}")
            return formula_engine.evaluate_formula(data, formula)
    else:
        return formula_engine.evaluate_formula(data, formula)