#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心计算模块：提供共享的数据准备与插值功能，包括高级空间运算。
"""
import numpy as np
import logging
import re
import ast
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
        return np.full_like(grid_x, np.nan)
        
    # 如果values是标量，直接创建一个填充后的网格
    if np.isscalar(values):
        return np.full_like(grid_x, values)

    valid_indices = np.isfinite(points).all(axis=1) & np.isfinite(values)
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

    x_range = np.ptp(filtered_points[:, 0])
    y_range = np.ptp(filtered_points[:, 1])
    if x_range < 1e-9 or y_range < 1e-9:
        logger.warning("数据点在几何上是退化的 (共线或单点)，将强制使用最近邻插值。")
        try:
            return griddata(filtered_points, filtered_values, (grid_x, grid_y), method='nearest')
        except QhullError:
             raise ValueError("退化的数据导致插值失败。")

    try:
        grid = griddata(filtered_points, filtered_values, (grid_x, grid_y), method='linear')
        
        if np.isnan(grid).any():
            grid_nearest = griddata(filtered_points, filtered_values, (grid_x, grid_y), method='nearest')
            nan_indices = np.isnan(grid)
            grid[nan_indices] = grid_nearest[nan_indices]
            
        return grid

    except QhullError:
        logger.error("插值时发生QhullError，输入点可能共线。")
        raise ValueError("输入点共线或退化，无法生成2D插值网格。")

def _eval_node_to_grid(
    node: ast.AST,
    data: np.ndarray, 
    points: np.ndarray,
    grid_x: np.ndarray, 
    grid_y: np.ndarray, 
    formula_engine: FormulaEngine,
    use_gpu: bool
) -> np.ndarray:
    """
    [NEW] 递归地求值AST节点，将其转换为网格化数据。这是新的核心计算函数。
    """
    # Base Case: Constant (e.g., 5, -2.0)
    if isinstance(node, ast.Constant):
        return np.full_like(grid_x, node.value)

    # Base Case: Name (e.g., u, p, R11, rho_avg)
    if isinstance(node, ast.Name):
        var_name = node.id
        values = _get_values_from_simple_formula(data, var_name, formula_engine, use_gpu)
        return _interpolate_field(points, values, grid_x, grid_y)

    # Recursive Step: Binary Operation (e.g., a + b, c * d)
    if isinstance(node, ast.BinOp):
        left_grid = _eval_node_to_grid(node.left, data, points, grid_x, grid_y, formula_engine, use_gpu)
        right_grid = _eval_node_to_grid(node.right, data, points, grid_x, grid_y, formula_engine, use_gpu)
        
        op_map = {
            ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
            ast.Pow: lambda a, b: a ** b,
        }
        if type(node.op) in op_map:
            return op_map[type(node.op)](left_grid, right_grid)
        else:
            raise TypeError(f"Unsupported binary operator: {type(node.op)}")
    
    # Recursive Step: Unary Operation (e.g., -a)
    if isinstance(node, ast.UnaryOp):
        operand_grid = _eval_node_to_grid(node.operand, data, points, grid_x, grid_y, formula_engine, use_gpu)
        if isinstance(node.op, ast.USub): return -operand_grid
        if isinstance(node.op, ast.UAdd): return operand_grid
        else: raise TypeError(f"Unsupported unary operator: {type(node.op)}")

    # Recursive Step: Function Call (e.g., sqrt(a), grad_x(b))
    if isinstance(node, ast.Call):
        func_id = node.func.id
        arg_grids = [_eval_node_to_grid(arg, data, points, grid_x, grid_y, formula_engine, use_gpu) for arg in node.args]

        if func_id in formula_engine.spatial_functions:
            if use_gpu:
                grid_y_gpu = cp.asarray(grid_y[:, 0]); grid_x_gpu = cp.asarray(grid_x[0, :])
                arg_grids_gpu = [cp.asarray(grid) if grid is not None else None for grid in arg_grids]
                result_gpu = _perform_spatial_op_gpu(func_id, arg_grids_gpu, grid_y_gpu, grid_x_gpu)
                return cp.asnumpy(result_gpu) if result_gpu is not None else np.full_like(grid_x, np.nan)
            else:
                return _perform_spatial_op_cpu(func_id, arg_grids, grid_y[:, 0], grid_x[0, :])
        
        elif func_id in formula_engine.simple_math_functions:
            np_func_map = {'sqrt': np.sqrt, 'abs': np.abs, 'sin': np.sin, 'cos': np.cos, 'tan': np.tan, 'asin': np.arcsin, 'acos': np.arccos, 'atan': np.arctan, 'sinh': np.sinh, 'cosh': np.cosh, 'tanh': np.tanh, 'exp': np.exp, 'log': np.log, 'log10': np.log10, 'floor': np.floor, 'ceil': np.ceil, 'round': np.round, 'min': np.minimum, 'max': np.maximum, 'pow': np.power}
            if func_id in np_func_map:
                return np_func_map[func_id](*arg_grids)
            else:
                raise NameError(f"Function '{func_id}' not implemented in CPU simple math evaluation.")
        else:
            raise NameError(f"Unknown or unsupported function in spatial context: '{func_id}'")

    raise TypeError(f"Unsupported AST node type: {type(node)}")

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

    try:
        x_values = formula_engine.evaluate_formula(data, x_formula)
        y_values = formula_engine.evaluate_formula(data, y_formula)
    except Exception as e:
        raise ValueError(f"计算坐标轴失败: x='{x_formula}', y='{y_formula}'. Error: {e}")

    grid_x, grid_y = np.meshgrid(
        np.linspace(x_values.min(), x_values.max(), grid_resolution[0]),
        np.linspace(y_values.min(), y_values.max(), grid_resolution[1])
    )
    points = np.vstack([x_values, y_values]).T

    try:
        tree = ast.parse(formula, mode='eval')
        result_grid = _eval_node_to_grid(
            tree.body, data, points, grid_x, grid_y, formula_engine, use_gpu
        )
    except Exception as e:
        logger.error(f"AST evaluation for formula '{formula}' failed: {e}", exc_info=True)
        raise ValueError(f"Failed to evaluate formula '{formula}': {e}") from e

    return {
        'grid_x': grid_x,
        'grid_y': grid_y,
        'result_data': result_grid
    }

def _perform_spatial_op_cpu(op, arg_grids, grid_y_coords, grid_x_coords):
    """在CPU上使用NumPy执行空间运算。"""
    if op in ['grad_x', 'grad_y', 'laplacian']:
        if len(arg_grids) != 1: raise ValueError(f"{op}需要1个参数，但收到了{len(arg_grids)}")
        field = arg_grids[0]
        if field is None: return None
        grad_gy, grad_gx = np.gradient(field, grid_y_coords, grid_x_coords, axis=(0, 1))
        if op == 'grad_x': return grad_gx
        if op == 'grad_y': return grad_gy
        if op == 'laplacian':
            g_gx_y, g_gx_x = np.gradient(grad_gx, grid_y_coords, grid_x_coords, axis=(0, 1))
            g_gy_y, g_gy_x = np.gradient(grad_gy, grid_y_coords, grid_x_coords, axis=(0, 1))
            return g_gx_x + g_gy_y

    elif op in ['div', 'curl']:
        if len(arg_grids) != 2: raise ValueError(f"{op}需要2个参数，但收到了{len(arg_grids)}")
        u, v = arg_grids
        if u is None or v is None: return None
        grad_u_y, grad_u_x = np.gradient(u, grid_y_coords, grid_x_coords, axis=(0, 1))
        grad_v_y, grad_v_x = np.gradient(v, grid_y_coords, grid_x_coords, axis=(0, 1))
        if op == 'div': return grad_u_x + grad_v_y
        if op == 'curl': return grad_v_x - grad_u_y
    
    raise ValueError(f"未知的空间操作: {op}")


def _perform_spatial_op_gpu(op, arg_grids_gpu, grid_y_coords_gpu, grid_x_coords_gpu):
    """在GPU上使用CuPy执行空间运算。"""
    if op in ['grad_x', 'grad_y', 'laplacian']:
        if len(arg_grids_gpu) != 1: raise ValueError(f"{op}需要1个参数，但收到了{len(arg_grids_gpu)}")
        field = arg_grids_gpu[0]
        if field is None: return None
        grad_gy, grad_gx = cp.gradient(field, grid_y_coords_gpu, grid_x_coords_gpu, axis=(0, 1))
        if op == 'grad_x': return grad_gx
        if op == 'grad_y': return grad_gy
        if op == 'laplacian':
            g_gx_y, g_gx_x = cp.gradient(grad_gx, grid_y_coords_gpu, grid_x_coords_gpu, axis=(0, 1))
            g_gy_y, g_gy_x = cp.gradient(grad_gy, grid_y_coords_gpu, grid_x_coords_gpu, axis=(0, 1))
            return g_gx_x + g_gy_y

    elif op in ['div', 'curl']:
        if len(arg_grids_gpu) != 2: raise ValueError(f"{op}需要2个参数，但收到了{len(arg_grids_gpu)}")
        u, v = arg_grids_gpu
        if u is None or v is None: return None
        grad_u_y, grad_u_x = cp.gradient(u, grid_y_coords_gpu, grid_x_coords_gpu, axis=(0, 1))
        grad_v_y, grad_v_x = cp.gradient(v, grid_y_coords_gpu, grid_x_coords_gpu, axis=(0, 1))
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