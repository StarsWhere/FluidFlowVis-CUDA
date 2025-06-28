#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无头渲染器，用于在非GUI线程中安全地生成Matplotlib图像。
"""
import numpy as np
import pandas as pd
import logging
from typing import Dict, Any, List

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.ticker as ticker
from scipy.interpolate import griddata
from scipy.spatial.qhull import QhullError # 导入Qhull错误类型

logger = logging.getLogger(__name__)

class HeadlessPlotter:
    """
    一个纯粹的、非GUI的绘图类，用于在后台线程中生成图像。
    它不继承QWidget，因此是线程安全的。
    """
    def __init__(self, plot_config: Dict[str, Any], validator):
        self.config = plot_config
        self.validator = validator
        # 使用配置中的分辨率，如果未提供则使用默认值
        self.grid_resolution = self.config.get('grid_resolution', (150, 150))

    def render_frame(self, data: pd.DataFrame, all_vars: List[str]) -> np.ndarray:
        """
        接收单帧数据和配置，返回一个代表渲染图像的NumPy数组。
        """
        # --- 1. 数据准备与公式求值 ---
        self.validator.update_custom_global_variables(self.config.get('global_scope', {}))
        self.validator.update_allowed_variables(all_vars)

        processed_data = data.copy()

        # 计算坐标轴公式
        x_axis_base = self.config.get('x_axis', 'x')
        y_axis_base = self.config.get('y_axis', 'y')
        x_formula = self.config.get('x_axis_formula', '')
        y_formula = self.config.get('y_axis_formula', '')

        x_axis_final = x_axis_base
        if x_formula:
            try:
                x_values = self.validator.evaluate_formula(processed_data, x_formula)
                x_axis_final = '__x_calculated__'
                processed_data[x_axis_final] = x_values
            except Exception as e:
                raise ValueError(f"X轴公式求值失败: {e}")
        
        y_axis_final = y_axis_base
        if y_formula:
            try:
                y_values = self.validator.evaluate_formula(processed_data, y_formula)
                y_axis_final = '__y_calculated__'
                processed_data[y_axis_final] = y_values
            except Exception as e:
                raise ValueError(f"Y轴公式求值失败: {e}")

        # --- 2. 网格生成与插值 ---
        gx, gy = np.meshgrid(
            np.linspace(processed_data[x_axis_final].min(), processed_data[x_axis_final].max(), self.grid_resolution[0]),
            np.linspace(processed_data[y_axis_final].min(), processed_data[y_axis_final].max(), self.grid_resolution[1])
        )
        points = processed_data[[x_axis_final, y_axis_final]].values

        # 辅助函数，用于获取热力图/等高线/矢量场所需的Z/U/V数据
        def get_values(cfg, var_key='variable', formula_key='formula'):
            if not cfg.get('enabled'): return None
            
            formula = cfg.get(formula_key, '').strip()
            variable = cfg.get(var_key)

            z_values_series = None
            if formula:
                z_values_series = self.validator.evaluate_formula(data, formula)
            elif variable and variable in data.columns:
                z_values_series = data[variable]
            
            return z_values_series.values if z_values_series is not None else None
        
        heatmap_cfg = self.config.get('heatmap_config', {})
        contour_cfg = self.config.get('contour_config', {})
        vector_cfg = self.config.get('vector_config', {})
        
        heatmap_z_values = get_values(heatmap_cfg)
        contour_z_values = get_values(contour_cfg)
        vector_u_values = get_values(vector_cfg, 'u_variable', 'u_formula')
        vector_v_values = get_values(vector_cfg, 'v_variable', 'v_formula')


        try:
            heatmap_data = griddata(points, heatmap_z_values, (gx, gy), method='linear') if heatmap_z_values is not None else None
            contour_data = griddata(points, contour_z_values, (gx, gy), method='linear') if contour_z_values is not None else None
            vector_u_data = griddata(points, vector_u_values, (gx, gy), method='linear') if vector_u_values is not None else None
            vector_v_data = griddata(points, vector_v_values, (gx, gy), method='linear') if vector_v_values is not None else None
        except QhullError:
            raise ValueError(
                "输入点共线或退化，无法生成2D插值网格。"
                "这通常是因为X轴和Y轴的公式相同或导致所有点都落在一条直线上。"
            )

        # --- 3. Matplotlib绘图 ---
        dpi = self.config.get('export_dpi', 300)
        fig = Figure(figsize=(12, 8), dpi=dpi, tight_layout=True)
        ax = fig.add_subplot(111)
        colorbar_obj = None

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
            colorbar_obj = fig.colorbar(pcm, ax=ax, format=ticker.ScalarFormatter(useMathText=True))
            colorbar_obj.set_label(heatmap_cfg.get('formula') or heatmap_cfg.get('variable', ''))

        # 绘制等高线
        if contour_data is not None and not np.all(np.isnan(contour_data)):
            cont = ax.contour(gx, gy, contour_data, 
                               levels=contour_cfg.get('levels', 10), 
                               colors=contour_cfg.get('colors', 'black'), 
                               linewidths=contour_cfg.get('linewidths', 1.0))
            if contour_cfg.get('show_labels'):
                ax.clabel(cont, inline=True, fontsize=8, fmt='%.2e')
        
        # 绘制矢量/流线图
        if vector_cfg.get('enabled') and vector_u_data is not None and vector_v_data is not None:
            plot_type = vector_cfg.get('type', 'Quiver')
            if plot_type == 'Quiver':
                opts = vector_cfg.get('quiver_options', {})
                density = opts.get('density', 10)
                scale = opts.get('scale', 1.0)
                sl = slice(None, None, density)
                ax.quiver(gx[sl, sl], gy[sl, sl], vector_u_data[sl, sl], vector_v_data[sl, sl], 
                          scale=scale, scale_units='xy', angles='xy', color='black')
            elif plot_type == 'Streamline':
                opts = vector_cfg.get('streamline_options', {})
                density = opts.get('density', 1.0)
                linewidth = opts.get('linewidth', 1.0)
                color_by = opts.get('color_by', '速度大小')
                
                color_data = 'black'
                if color_by == '速度大小':
                    color_data = np.sqrt(vector_u_data**2 + vector_v_data**2)
                elif color_by == 'U分量':
                    color_data = vector_u_data
                elif color_by == 'V分量':
                    color_data = vector_v_data
                
                stream_plot = ax.streamplot(gx, gy, vector_u_data, vector_v_data, 
                                            density=density, linewidth=linewidth, color=color_data, 
                                            cmap='viridis' if isinstance(color_data, np.ndarray) else None)
                if isinstance(color_data, np.ndarray) and not colorbar_obj:
                    cbar = fig.colorbar(stream_plot.lines, ax=ax)
                    cbar.set_label(f"流线 ({color_by})")

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

        if gx is not None and gy is not None:
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