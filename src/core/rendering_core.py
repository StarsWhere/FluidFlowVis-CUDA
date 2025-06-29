#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心渲染模块：提供共享的数据准备与插值功能
"""
import numpy as np
import logging
from typing import Dict, Any

from src.core.formula_engine import FormulaEngine
from src.core.computation_core import compute_gridded_field

logger = logging.getLogger(__name__)

def prepare_gridded_data(data: np.ndarray, config: Dict[str, Any], formula_engine: FormulaEngine) -> Dict[str, Any]:
    """
    根据配置，处理原始数据，执行公式计算和插值，返回可用于绘图的网格化数据。
    这个函数现在是 compute_gridded_field 的一个包装器，用于处理多个字段。
    """
    if data is None or data.empty:
        return {}
    
    # --- 1. 准备配置 ---
    x_formula = config.get('x_axis_formula', 'x')
    y_formula = config.get('y_axis_formula', 'y')
    heatmap_cfg = config.get('heatmap_config', {})
    contour_cfg = config.get('contour_config', {})
    vector_cfg = config.get('vector_config', {})
    use_gpu = config.get('use_gpu', False)
    grid_resolution = config.get('grid_resolution', (150, 150))
    
    results = {}
    
    # --- 2. 统一计算所有需要的场 ---
    formulas_to_compute = {
        'heatmap': heatmap_cfg.get('formula') if heatmap_cfg.get('enabled') else None,
        'contour': contour_cfg.get('formula') if contour_cfg.get('enabled') else None,
        'vector_u': vector_cfg.get('u_formula') if vector_cfg.get('enabled') else None,
        'vector_v': vector_cfg.get('v_formula') if vector_cfg.get('enabled') else None,
    }

    # 使用一个共享的网格来提高效率
    shared_grid_x, shared_grid_y = None, None

    for name, formula in formulas_to_compute.items():
        if not formula:
            results[f'{name}_data'] = None
            continue
        
        try:
            computation_result = compute_gridded_field(
                data, formula, x_formula, y_formula, formula_engine, grid_resolution, use_gpu
            )
            
            if computation_result:
                # 存储第一个计算出的网格
                if shared_grid_x is None:
                    shared_grid_x = computation_result.get('grid_x')
                    shared_grid_y = computation_result.get('grid_y')
                
                results[f'{name}_data'] = computation_result.get('result_data')
            else:
                results[f'{name}_data'] = None

        except ValueError as e:
            logger.error(f"计算字段 '{name}' (公式: {formula}) 失败: {e}")
            raise e # 将错误向上抛出，由调用者处理

    # --- 3. 返回结果 ---
    results['grid_x'] = shared_grid_x
    results['grid_y'] = shared_grid_y
    
    return results