#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无头渲染器，用于在非GUI线程中安全地生成Matplotlib图像。
"""
import numpy as np
import pandas as pd
import logging
import re
from typing import Dict, Any, List

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.ticker as ticker
from scipy.interpolate import griddata

logger = logging.getLogger(__name__)

class HeadlessPlotter:
    """
    一个纯粹的、非GUI的绘图类，用于在后台线程中生成图像。
    它不继承QWidget，因此是线程安全的。
    """
    def __init__(self, plot_config: Dict[str, Any], validator):
        self.config = plot_config
        self.validator = validator
        self.grid_resolution = (150, 150)  # 与交互式窗口保持一致

    def _evaluate_complex_formula(self, data: pd.DataFrame, formula: str, eval_globals: dict) -> np.ndarray:
        """
        正确评估包含单帧聚合函数的复杂公式。
        例如 'p - mean(p)'。
        """
        # 正则表达式，用于查找聚合函数调用，例如: mean(p), std(u*u)
        agg_pattern = re.compile(r'(\b(?:' + '|'.join(self.validator.allowed_aggregates) + r'))\s*\((.*?)\)')
        
        local_scope = eval_globals.copy()
        processed_formula = formula
        
        # 按从后往前的顺序查找所有聚合函数调用，以避免替换时破坏字符串索引
        matches = list(agg_pattern.finditer(formula))
        for i, match in enumerate(reversed(matches)):
            agg_func_name, inner_expr = match.groups()
            
            # 检查括号是否平衡，以初步处理嵌套情况
            if inner_expr.count('(') != inner_expr.count(')'):
                continue
            
            # 评估聚合函数内部的表达式，例如 'p' 或 'u*u'
            try:
                inner_values = data.eval(inner_expr, global_dict=eval_globals, local_dict={})
            except Exception as e:
                raise ValueError(f"评估聚合函数内部表达式 '{inner_expr}' (在 {agg_func_name} 中) 时出错: {e}")

            # 应用相应的聚合操作
            scalar_result = 0.0
            if agg_func_name == 'mean': scalar_result = inner_values.mean()
            elif agg_func_name == 'sum': scalar_result = inner_values.sum()
            elif agg_func_name == 'median': scalar_result = inner_values.median()
            elif agg_func_name == 'std': scalar_result = inner_values.std()
            elif agg_func_name == 'var': scalar_result = inner_values.var()
            elif agg_func_name == 'min_frame': scalar_result = inner_values.min()
            elif agg_func_name == 'max_frame': scalar_result = inner_values.max()

            # 创建一个唯一的临时变量名，并将计算出的标量结果存入局部作用域
            temp_var_name = f"__agg_result_{len(matches) - 1 - i}__"
            local_scope[temp_var_name] = scalar_result
            
            # 用 @temp_var_name 替换原始公式中的聚合函数调用
            start, end = match.span()
            processed_formula = processed_formula[:start] + f"@{temp_var_name}" + processed_formula[end:]

        # 现在，使用预先计算好的聚合结果来评估最终的处理后公式
        try:
            return data.eval(processed_formula, global_dict={}, local_dict=local_scope)
        except Exception as e:
            raise ValueError(f"评估最终公式 '{processed_formula}' 时失败: {e}")

    def render_frame(self, data: pd.DataFrame, all_vars: List[str]) -> np.ndarray:
        """
        接收单帧数据和配置，返回一个代表渲染图像的NumPy数组。
        """
        # --- 1. 数据准备与公式求值 ---
        self.validator.update_custom_global_variables(self.config.get('global_scope', {}))
        self.validator.update_allowed_variables(all_vars)

        eval_globals = self.validator.get_all_constants_and_globals()
        
        processed_data = data.copy()

        # 计算坐标轴公式
        x_axis_base = self.config.get('x_axis', 'x')
        y_axis_base = self.config.get('y_axis', 'y')
        x_formula = self.config.get('x_axis_formula', '')
        y_formula = self.config.get('y_axis_formula', '')

        x_axis_final = x_axis_base
        if x_formula:
            try:
                processed_data['__x_calculated__'] = self._evaluate_complex_formula(processed_data, x_formula, eval_globals)
                x_axis_final = '__x_calculated__'
            except Exception as e:
                raise ValueError(f"X轴公式求值失败: {e}")
        
        y_axis_final = y_axis_base
        if y_formula:
            try:
                processed_data['__y_calculated__'] = self._evaluate_complex_formula(processed_data, y_formula, eval_globals)
                y_axis_final = '__y_calculated__'
            except Exception as e:
                raise ValueError(f"Y轴公式求值失败: {e}")

        # --- 2. 网格生成与插值 ---
        gx, gy = np.meshgrid(
            np.linspace(processed_data[x_axis_final].min(), processed_data[x_axis_final].max(), self.grid_resolution[0]),
            np.linspace(processed_data[y_axis_final].min(), processed_data[y_axis_final].max(), self.grid_resolution[1])
        )
        points = processed_data[[x_axis_final, y_axis_final]].values

        # 辅助函数，用于获取热力图/等高线所需的Z轴数据
        def get_interpolated_z(cfg):
            if not cfg.get('enabled'): return None
            
            formula = cfg.get('formula', '').strip()
            variable = cfg.get('variable')

            z_values = None
            if formula:
                # 使用新的、功能更全的公式评估函数
                z_values = self._evaluate_complex_formula(data, formula, eval_globals)
            elif variable and variable in data.columns:
                z_values = data[variable].values
            else:
                return None
            
            # 将Z值插值到网格上
            return griddata(points, z_values, (gx, gy), method='linear', fill_value=np.nan)

        heatmap_cfg = self.config.get('heatmap_config', {})
        contour_cfg = self.config.get('contour_config', {})
        
        heatmap_data = get_interpolated_z(heatmap_cfg)
        contour_data = get_interpolated_z(contour_cfg)

        # --- 3. Matplotlib绘图 ---
        dpi = self.config.get('export_dpi', 150) # Use a more specific config key
        fig = Figure(figsize=(12, 8), dpi=dpi, tight_layout=True)
        ax = fig.add_subplot(111)

        # 绘制热力图
        if heatmap_data is not None and not np.all(np.isnan(heatmap_data)):
            vmin_str = heatmap_cfg.get('vmin')
            vmax_str = heatmap_cfg.get('vmax')
            vmin = float(vmin_str) if vmin_str is not None and str(vmin_str).strip() != '' else None
            vmax = float(vmax_str) if vmax_str is not None and str(vmax_str).strip() != '' else None
            
            valid_data = heatmap_data[~np.isnan(heatmap_data)]
            if valid_data.size > 0:
                if vmin is None: vmin = np.min(valid_data)
                if vmax is None: vmax = np.max(valid_data)

            pcm = ax.pcolormesh(gx, gy, heatmap_data, 
                                cmap=heatmap_cfg.get('colormap', 'viridis'), 
                                vmin=vmin, vmax=vmax, shading='gouraud')
            cbar = fig.colorbar(pcm, ax=ax, format=ticker.ScalarFormatter(useMathText=True))
            cbar.set_label(heatmap_cfg.get('formula') or heatmap_cfg.get('variable', ''))

        # 绘制等高线
        if contour_data is not None and not np.all(np.isnan(contour_data)):
            cont = ax.contour(gx, gy, contour_data, 
                               levels=contour_cfg.get('levels', 10), 
                               colors=contour_cfg.get('colors', 'black'), 
                               linewidths=contour_cfg.get('linewidths', 1.0))
            if contour_cfg.get('show_labels'):
                ax.clabel(cont, inline=True, fontsize=8, fmt='%.2e')
        
        # --- 4. 格式化并渲染到NumPy数组 ---
        ax.set_aspect('auto', adjustable='box')
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.set_xlabel(x_formula or x_axis_base)
        ax.set_ylabel(y_formula or y_axis_base)
        
        formatter = ticker.ScalarFormatter(useMathText=True)
        formatter.set_scientific(True)
        formatter.set_powerlimits((-3, 3))
        ax.xaxis.set_major_formatter(formatter)
        ax.yaxis.set_major_formatter(formatter)

        x_min, x_max = np.nanmin(gx), np.nanmax(gx)
        y_min, y_max = np.nanmin(gy), np.nanmax(gy)
        xr = x_max - x_min or 1; yr = y_max - y_min or 1; m = 0.05
        ax.set_xlim(x_min - m * xr, x_max + m * xr)
        ax.set_ylim(y_min - m * yr, y_max + m * yr)

        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        
        buf = canvas.buffer_rgba()
        image_array = np.asarray(buf)
        
        # 释放figure占用的内存
        fig.clear()
        
        return image_array