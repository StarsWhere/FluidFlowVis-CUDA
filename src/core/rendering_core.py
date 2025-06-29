#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心渲染模块：提供共享的数据准备与插值功能
"""
import numpy as np
import logging
from scipy.interpolate import griddata
from scipy.spatial.qhull import QhullError
from typing import Dict, Any

from src.core.formula_engine import FormulaEngine
from src.utils.gpu_utils import is_gpu_available, evaluate_formula_gpu

logger = logging.getLogger(__name__)

def prepare_gridded_data(data: np.ndarray, config: Dict[str, Any], formula_engine: FormulaEngine) -> Dict[str, Any]:
    """
    根据配置，处理原始数据，执行公式计算和插值，返回可用于绘图的网格化数据。
    这是一个核心的、可被多处调用的函数。
    """
    if data is None or data.empty:
        return {}
    
    # --- 1. 准备配置和数据 ---
    processed_data = data.copy()
    
    # 从配置中获取公式
    x_formula = config.get('x_axis_formula', 'x')
    y_formula = config.get('y_axis_formula', 'y')
    heatmap_cfg = config.get('heatmap_config', {})
    contour_cfg = config.get('contour_config', {})
    vector_cfg = config.get('vector_config', {})
    use_gpu = config.get('use_gpu', False) and is_gpu_available()

    # --- 2. 坐标轴求值 ---
    try:
        x_values = formula_engine.evaluate_formula(processed_data, x_formula)
        processed_data['__x_calculated__'] = x_values
    except Exception as e:
        raise ValueError(f"X轴公式求值失败: {e}")

    try:
        y_values = formula_engine.evaluate_formula(processed_data, y_formula)
        processed_data['__y_calculated__'] = y_values
    except Exception as e:
        raise ValueError(f"Y轴公式求值失败: {e}")
        
    # --- 3. 网格与插值点定义 ---
    grid_resolution = config.get('grid_resolution', (150, 150))
    gx, gy = np.meshgrid(
        np.linspace(processed_data['__x_calculated__'].min(), processed_data['__x_calculated__'].max(), grid_resolution[0]),
        np.linspace(processed_data['__y_calculated__'].min(), processed_data['__y_calculated__'].max(), grid_resolution[1])
    )
    points = processed_data[['__x_calculated__', '__y_calculated__']].values
    
    # --- 4. 绘图数据求值 (热力图、等高线、矢量场) ---
    def get_values_from_formula(cfg, formula_key='formula'):
        formula = cfg.get(formula_key, '').strip()
        if not cfg.get('enabled') or not formula: 
            return None
        
        # 聚合函数不能在GPU上按点计算
        uses_aggregates = any(agg_func in formula for agg_func in formula_engine.allowed_aggregates)
        
        if use_gpu and not uses_aggregates:
            try:
                req_vars = formula_engine.get_used_variables(formula)
                var_data = {var: data[var].values for var in req_vars}
                combined_vars = {**formula_engine.get_all_constants_and_globals(), **var_data}
                return evaluate_formula_gpu(formula, combined_vars)
            except Exception as e:
                logger.warning(f"GPU评估公式 '{formula}' 失败，回退到CPU。错误: {e}")
                return formula_engine.evaluate_formula(data, formula)
        else:
            return formula_engine.evaluate_formula(data, formula)

    heatmap_z = get_values_from_formula(heatmap_cfg)
    contour_z = get_values_from_formula(contour_cfg)
    vector_u = get_values_from_formula(vector_cfg, 'u_formula')
    vector_v = get_values_from_formula(vector_cfg, 'v_formula')
    
    # --- 5. 插值 ---
    try:
        heatmap_data = griddata(points, heatmap_z, (gx, gy), method='linear') if heatmap_z is not None else None
        contour_data = griddata(points, contour_z, (gx, gy), method='linear') if contour_z is not None else None
        vector_u_data = griddata(points, vector_u, (gx, gy), method='linear') if vector_u is not None else None
        vector_v_data = griddata(points, vector_v, (gx, gy), method='linear') if vector_v is not None else None
    except QhullError:
        raise ValueError(
            "输入点共线或退化，无法生成2D插值网格。\n\n"
            "这通常是因为X轴和Y轴的公式相同，或公式导致所有点都落在一条直线上。"
        )
    
    # --- 6. 返回结果 ---
    return {
        'grid_x': gx, 'grid_y': gy, 
        'heatmap_data': heatmap_data, 
        'contour_data': contour_data,
        'vector_u_data': vector_u_data,
        'vector_v_data': vector_v_data
    }