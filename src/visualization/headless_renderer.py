#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无头渲染器，用于在非GUI线程中安全地生成Matplotlib图像。
"""
import numpy as np
import pandas as pd
import logging
import sys
from typing import Dict, Any, List

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.ticker as ticker
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from src.core.rendering_core import prepare_gridded_data
from src.core.formula_engine import FormulaEngine
from src.core.constants import VectorPlotType, StreamlineColor

logger = logging.getLogger(__name__)

def _setup_headless_fonts():
    """为无头渲染器配置跨平台字体。"""
    font_name = None
    if sys.platform == "win32":
        font_name = "Microsoft YaHei"
    elif sys.platform == "darwin": # macOS
        font_name = "PingFang SC"
    else: # Linux
        font_name = "WenQuanYi Zen Hei"
    
    prop = fm.FontProperties(family=font_name)
    if fm.findfont(prop, fallback_to_default=False):
        plt.rcParams['font.sans-serif'] = [font_name]
    else:
        # 如果找不到特定字体，尝试一个通用列表
        fallback_fonts = ['SimHei', 'Heiti TC', 'sans-serif']
        plt.rcParams['font.sans-serif'] = fallback_fonts
        logger.warning(f"无法找到 '{font_name}' 字体，将回退到 {fallback_fonts}。中文显示可能不正常。")
    
    plt.rcParams['axes.unicode_minus'] = False

class HeadlessPlotter:
    """
    一个纯粹的、非GUI的绘图类，用于在后台线程中生成图像。
    它不继承QWidget，因此是线程安全的。
    """
    def __init__(self, plot_config: Dict[str, Any]):
        self.config = plot_config
        self.formula_engine = FormulaEngine()
        self.grid_resolution = self.config.get('grid_resolution', (150, 150))
        self.formula_engine.update_custom_global_variables(self.config.get('global_scope', {}))
        _setup_headless_fonts()

    def render_frame(self, data: pd.DataFrame, all_vars: List[str]) -> np.ndarray:
        """
        接收单帧数据和配置，返回一个代表渲染图像的NumPy数组。
        """
        self.formula_engine.update_allowed_variables(all_vars)

        try:
            render_config = {
                'x_axis_formula': self.config.get('x_axis_formula') or 'x',
                'y_axis_formula': self.config.get('y_axis_formula') or 'y',
                'heatmap_config': self.config.get('heatmap_config', {}),
                'contour_config': self.config.get('contour_config', {}),
                'vector_config': self.config.get('vector_config', {}),
                'use_gpu': self.config.get('use_gpu', False),
                'grid_resolution': self.grid_resolution
            }
            interpolated_results = prepare_gridded_data(data, render_config, self.formula_engine)
        except Exception as e:
            logger.error(f"无头渲染器数据准备失败: {e}")
            raise

        gx = interpolated_results.get('grid_x')
        gy = interpolated_results.get('grid_y')
        if gx is None or gy is None:
            raise ValueError("网格坐标(gx, gy)未生成，无法绘图。")

        dpi = self.config.get('export_dpi', 300)
        fig = Figure(figsize=(12, 8), dpi=dpi, tight_layout=True)
        ax = fig.add_subplot(111)
        colorbar_obj = None
        
        heatmap_cfg = self.config.get('heatmap_config', {})
        contour_cfg = self.config.get('contour_config', {})
        vector_cfg = self.config.get('vector_config', {})

        heatmap_data = interpolated_results.get('heatmap_data')
        if heatmap_cfg.get('enabled') and heatmap_data is not None and not np.all(np.isnan(heatmap_data)):
            vmin_str, vmax_str = heatmap_cfg.get('vmin'), heatmap_cfg.get('vmax')
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
            colorbar_obj.set_label(heatmap_cfg.get('formula', ''))

        contour_data = interpolated_results.get('contour_data')
        if contour_cfg.get('enabled') and contour_data is not None and not np.all(np.isnan(contour_data)):
            cont = ax.contour(gx, gy, contour_data, 
                               levels=contour_cfg.get('levels', 10), 
                               colors=contour_cfg.get('colors', 'black'), 
                               linewidths=contour_cfg.get('linewidths', 1.0))
            if contour_cfg.get('show_labels'):
                ax.clabel(cont, inline=True, fontsize=8, fmt='%.2e')
        
        vector_u_data, vector_v_data = interpolated_results.get('vector_u_data'), interpolated_results.get('vector_v_data')
        if vector_cfg.get('enabled') and vector_u_data is not None and vector_v_data is not None:
            plot_type = VectorPlotType.from_str(vector_cfg.get('type', 'Quiver'))
            if plot_type == VectorPlotType.QUIVER:
                opts = vector_cfg.get('quiver_options', {}); density = opts.get('density', 10); scale = opts.get('scale', 1.0)
                sl = slice(None, None, density)
                ax.quiver(gx[sl, sl], gy[sl, sl], vector_u_data[sl, sl], vector_v_data[sl, sl], 
                          scale=scale, scale_units='xy', angles='xy', color='black')
            elif plot_type == VectorPlotType.STREAMLINE:
                opts = vector_cfg.get('streamline_options', {})
                density = opts.get('density', 1.0)
                linewidth = opts.get('linewidth', 1.0)
                color_by = StreamlineColor.from_str(opts.get('color_by', StreamlineColor.MAGNITUDE.value))
                
                color_data = 'black'
                if color_by == StreamlineColor.MAGNITUDE: color_data = np.sqrt(vector_u_data**2 + vector_v_data**2)
                elif color_by == StreamlineColor.U_COMPONENT: color_data = vector_u_data
                elif color_by == StreamlineColor.V_COMPONENT: color_data = vector_v_data
                
                stream_plot = ax.streamplot(gx, gy, vector_u_data, vector_v_data, density=density, linewidth=linewidth, color=color_data, cmap='viridis' if isinstance(color_data, np.ndarray) else None)
                if isinstance(color_data, np.ndarray) and not colorbar_obj:
                    fig.colorbar(stream_plot.lines, ax=ax).set_label(f"流线 ({color_by.value})")

        ax.set_aspect('auto', adjustable='box'); ax.grid(True, linestyle='--', alpha=0.5)
        ax.set_xlabel(self.config.get('x_axis_formula') or 'x'); ax.set_ylabel(self.config.get('y_axis_formula') or 'y')
        
        title = self.config.get('chart_title', '')
        if title: ax.set_title(title)

        formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
        ax.xaxis.set_major_formatter(formatter); ax.yaxis.set_major_formatter(formatter)

        x_min, x_max = np.nanmin(gx), np.nanmax(gx); y_min, y_max = np.nanmin(gy), np.nanmax(gy)
        xr = x_max - x_min or 1; yr = y_max - y_min or 1; m = 0.05
        ax.set_xlim(x_min - m * xr, x_max + m * xr); ax.set_ylim(y_min - m * yr, y_max + m * yr)

        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        
        buf = canvas.buffer_rgba()
        image_array = np.asarray(buf)
        fig.clear()
        
        return image_array