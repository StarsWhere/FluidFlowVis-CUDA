#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import re
import ast
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker
from scipy.interpolate import griddata
from scipy.spatial.qhull import QhullError # 导入Qhull错误类型
from typing import Optional, Dict, Any
import logging
import traceback
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QObject, QRunnable, QThreadPool, Qt
from PyQt6.QtGui import QCursor
from src.utils.gpu_utils import is_gpu_available, evaluate_formula_gpu

logger = logging.getLogger(__name__)

class WorkerSignals(QObject):
    finished = pyqtSignal(); error = pyqtSignal(str); result = pyqtSignal(dict)

class InterpolationWorker(QRunnable):
    def __init__(self, data, res, x_formula, y_formula, heat_cfg, contour_cfg, vector_cfg, use_gpu, validator):
        super().__init__()
        self.data, self.res = data, res
        self.x_formula, self.y_formula = x_formula, y_formula
        self.heat_cfg, self.contour_cfg, self.vector_cfg = heat_cfg, contour_cfg, vector_cfg
        self.use_gpu = use_gpu and is_gpu_available()
        self.validator, self.signals = validator, WorkerSignals()
        
    def run(self):
        try:
            self.signals.result.emit(self._perform_interpolation())
        except Exception as e:
            error_msg = f"插值或公式计算失败: {e}\n{traceback.format_exc()}"
            logger.error(error_msg)
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

    def _perform_interpolation(self):
        if self.data is None: return {}
        
        # --- 坐标轴公式求值 ---
        processed_data = self.data.copy()
        
        try:
            x_values = self.validator.evaluate_formula(processed_data, self.x_formula)
            processed_data['__x_calculated__'] = x_values
        except Exception as e:
            raise ValueError(f"X轴公式求值失败: {e}")

        try:
            y_values = self.validator.evaluate_formula(processed_data, self.y_formula)
            processed_data['__y_calculated__'] = y_values
        except Exception as e:
            raise ValueError(f"Y轴公式求值失败: {e}")

        # --- 网格与插值点定义 ---
        gx, gy = np.meshgrid(
            np.linspace(processed_data['__x_calculated__'].min(), processed_data['__x_calculated__'].max(), self.res[0]),
            np.linspace(processed_data['__y_calculated__'].min(), processed_data['__y_calculated__'].max(), self.res[1])
        )
        points = processed_data[['__x_calculated__', '__y_calculated__']].values

        # --- 热力图、等高线、矢量场Z/U/V值求值 ---
        def get_values_from_formula(cfg, formula_key='formula'):
            formula = cfg.get(formula_key, '').strip()
            if not cfg.get('enabled') or not formula: 
                return None
            
            uses_aggregates = any(agg_func in formula for agg_func in self.validator.allowed_aggregates)
            if self.use_gpu and not uses_aggregates:
                req_vars = self.validator.get_used_variables(formula)
                var_data = {var: self.data[var].values for var in req_vars}
                combined_vars = {**self.validator.get_all_constants_and_globals(), **var_data}
                return evaluate_formula_gpu(formula, combined_vars)
            else:
                return self.validator.evaluate_formula(self.data, formula)

        heatmap_z = get_values_from_formula(self.heat_cfg)
        contour_z = get_values_from_formula(self.contour_cfg)
        vector_u = get_values_from_formula(self.vector_cfg, 'u_formula')
        vector_v = get_values_from_formula(self.vector_cfg, 'v_formula')
        
        # --- 插值 (添加错误处理) ---
        try:
            heatmap_data = griddata(points, heatmap_z, (gx, gy), method='linear') if heatmap_z is not None else None
            contour_data = griddata(points, contour_z, (gx, gy), method='linear') if contour_z is not None else None
            vector_u_data = griddata(points, vector_u, (gx, gy), method='linear') if vector_u is not None else None
            vector_v_data = griddata(points, vector_v, (gx, gy), method='linear') if vector_v is not None else None
        except QhullError:
            raise ValueError(
                "输入点共线或退化，无法生成2D插值网格。\n\n"
                "这通常是因为X轴和Y轴的公式相同，或公式导致所有点都落在一条直线上。"
                "请为X轴和Y轴使用不同的公式。"
            )
            
        return {
            'grid_x': gx, 'grid_y': gy, 
            'heatmap_data': heatmap_data, 
            'contour_data': contour_data,
            'vector_u_data': vector_u_data,
            'vector_v_data': vector_v_data
        }


class PlotWidget(QWidget):
    mouse_moved = pyqtSignal(float, float)
    probe_data_ready = pyqtSignal(dict)
    plot_rendered = pyqtSignal()
    value_picked = pyqtSignal(str, float)
    interpolation_error = pyqtSignal(str)

    def __init__(self, formula_validator, parent=None):
        super().__init__(parent)
        self.formula_validator = formula_validator
        self.figure = Figure(figsize=(12, 8), dpi=100, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.addWidget(self.canvas); self.setLayout(layout)
        self.current_data: Optional[pd.DataFrame] = None; self.interpolated_results: Dict[str, Any] = {}
        
        self.x_axis_formula, self.y_axis_formula = 'x', 'y'
        self.chart_title = ""
        self.use_gpu = False
        self.heatmap_config = {'enabled': False}; self.contour_config = {'enabled': False}; self.vector_config = {'enabled': False}
        self.heatmap_obj = self.contour_obj = self.colorbar_obj = None
        self.is_dragging = False; self.drag_start_pos = None; self.picker_mode: Optional[str] = None
        self.last_mouse_coords: Optional[tuple[float, float]] = None
        self.grid_resolution = (150, 150); self.thread_pool = QThreadPool(); self.is_busy_interpolating = False
        self._connect_signals(); self._setup_plot_style()

    def _connect_signals(self):
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.canvas.mpl_connect('button_press_event', self._on_button_press)
        self.canvas.mpl_connect('button_release_event', self._on_button_release)

    def _setup_plot_style(self):
        self.ax.set_aspect('auto', adjustable='box'); self.ax.grid(True, linestyle='--', alpha=0.5)
        self.ax.set_xlabel(self.x_axis_formula)
        self.ax.set_ylabel(self.y_axis_formula)
        
        # 动态标题逻辑
        final_title = self.chart_title
        if not final_title:
            parts = []
            if self.heatmap_config.get('enabled') and self.heatmap_config.get('formula'):
                parts.append(f"Heatmap of '{self.heatmap_config['formula']}'")
            if self.contour_config.get('enabled') and self.contour_config.get('formula'):
                parts.append(f"Contours of '{self.contour_config['formula']}'")
            if self.vector_config.get('enabled'):
                plot_type = self.vector_config.get('type', "Vector")
                parts.append(f"{plot_type} Plot")
            final_title = " and ".join(parts) if parts else "InterVis Plot"
        self.ax.set_title(final_title)

        formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
        self.ax.xaxis.set_major_formatter(formatter); self.ax.yaxis.set_major_formatter(formatter)
    
    def update_data(self, data: pd.DataFrame):
        if self.is_busy_interpolating: return
        self.current_data = data.copy(); self.is_busy_interpolating = True
        worker = InterpolationWorker(
            self.current_data, self.grid_resolution, 
            self.x_axis_formula, self.y_axis_formula,
            self.heatmap_config, self.contour_config, self.vector_config,
            self.use_gpu, self.formula_validator
        )
        worker.signals.result.connect(self._on_interpolation_result)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.finished.connect(lambda: setattr(self, 'is_busy_interpolating', False))
        self.thread_pool.start(worker)

    def _on_worker_error(self, error_message: str):
        """Handles errors from the interpolation worker thread."""
        logger.error(f"插值线程错误: {error_message}")
        self.interpolation_error.emit(error_message)

    def _on_interpolation_result(self, result: dict):
        self.interpolated_results = result; self.redraw(); self.plot_rendered.emit()
        if self.last_mouse_coords:
            self.get_probe_data_at_coords(self.last_mouse_coords[0], self.last_mouse_coords[1])

    def set_config(self, **kwargs):
        self.x_axis_formula = kwargs.get('x_axis_formula', self.x_axis_formula)
        self.y_axis_formula = kwargs.get('y_axis_formula', self.y_axis_formula)
        self.chart_title = kwargs.get('chart_title', self.chart_title)
        self.use_gpu = kwargs.get('use_gpu', self.use_gpu)
        if 'heatmap_config' in kwargs: self.heatmap_config = kwargs['heatmap_config']
        if 'contour_config' in kwargs: self.contour_config = kwargs['contour_config']
        if 'vector_config' in kwargs: self.vector_config = kwargs['vector_config']

    def redraw(self):
        if not self.ax: return
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim(); is_initial = (xlim == (0.0, 1.0) and ylim == (0.0, 1.0))
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._setup_plot_style() # Style (incl. title) is set here
        if self.heatmap_config.get('enabled'): self._draw_heatmap()
        if self.contour_config.get('enabled'): self._draw_contour()
        if self.vector_config.get('enabled'): self._draw_vector_plot()
        
        if not is_initial: 
            self.ax.set_xlim(xlim); self.ax.set_ylim(ylim)
        else: 
            self.reset_view()
            
        self.canvas.draw()
    
    def _draw_heatmap(self):
        data, gx, gy = self.interpolated_results.get('heatmap_data'), self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if data is None or gx is None: return
        vmin_str = self.heatmap_config.get('vmin')
        vmax_str = self.heatmap_config.get('vmax')
        vmin = float(vmin_str) if vmin_str is not None and str(vmin_str).strip() != '' else None
        vmax = float(vmax_str) if vmax_str is not None and str(vmax_str).strip() != '' else None
            
        valid = data[~np.isnan(data)]; 
        if valid.size > 0:
            if vmin is None: vmin = np.min(valid)
            if vmax is None: vmax = np.max(valid)

        self.heatmap_obj = self.ax.pcolormesh(gx, gy, data, cmap=self.heatmap_config.get('colormap', 'viridis'), vmin=vmin, vmax=vmax, shading='gouraud')
        self.colorbar_obj = self.figure.colorbar(self.heatmap_obj, ax=self.ax, format=ticker.ScalarFormatter(useMathText=True))
        self.colorbar_obj.set_label(self.heatmap_config.get('formula', ''))

    def _draw_contour(self):
        data, gx, gy = self.interpolated_results.get('contour_data'), self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if data is None or gx is None or np.all(np.isnan(data)): return
        self.contour_obj = self.ax.contour(gx, gy, data, levels=self.contour_config.get('levels', 10), colors=self.contour_config.get('colors', 'black'), linewidths=self.contour_config.get('linewidths', 1.0))
        if self.contour_config.get('show_labels'): self.ax.clabel(self.contour_obj, inline=True, fontsize=8, fmt='%.2e')

    def _draw_vector_plot(self):
        plot_type = self.vector_config.get('type', 'Quiver')
        if plot_type == 'Quiver':
            self._draw_quiver()
        elif plot_type == 'Streamline':
            self._draw_streamlines()

    def _draw_quiver(self):
        u, v = self.interpolated_results.get('vector_u_data'), self.interpolated_results.get('vector_v_data')
        gx, gy = self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if u is None or v is None or gx is None: return

        opts = self.vector_config.get('quiver_options', {})
        density = opts.get('density', 10)
        scale = opts.get('scale', 1.0)
        
        sl = slice(None, None, density)
        self.ax.quiver(gx[sl, sl], gy[sl, sl], u[sl, sl], v[sl, sl], scale=scale, scale_units='xy', angles='xy')

    def _draw_streamlines(self):
        u, v = self.interpolated_results.get('vector_u_data'), self.interpolated_results.get('vector_v_data')
        gx, gy = self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if u is None or v is None or gx is None: return

        opts = self.vector_config.get('streamline_options', {})
        density = opts.get('density', 1.5)
        linewidth = opts.get('linewidth', 1.0)
        color_by = opts.get('color_by', '速度大小')
        
        color_data = 'black'
        if color_by == '速度大小':
            color_data = np.sqrt(u**2 + v**2)
        elif color_by == 'U分量':
            color_data = u
        elif color_by == 'V分量':
            color_data = v
        
        stream_plot = self.ax.streamplot(gx, gy, u, v, density=density, linewidth=linewidth, color=color_data, cmap='viridis' if isinstance(color_data, np.ndarray) else None)
        # Add colorbar for streamlines if colored by magnitude and no other colorbar exists
        if isinstance(color_data, np.ndarray) and not self.colorbar_obj:
            cbar = self.figure.colorbar(stream_plot.lines, ax=self.ax)
            cbar.set_label(f"流线 ({color_by})")

    def _on_mouse_move(self, event):
        if event.inaxes != self.ax or event.xdata is None: return
        self.mouse_moved.emit(event.xdata, event.ydata)
        self.last_mouse_coords = (event.xdata, event.ydata)
        if not self.is_dragging: self.get_probe_data_at_coords(event.xdata, event.ydata)
        if self.is_dragging and self.drag_start_pos:
            dx, dy = event.xdata - self.drag_start_pos[0], event.ydata - self.drag_start_pos[1]
            xlim, ylim = self.drag_start_lims
            self.ax.set_xlim(xlim[0] - dx, xlim[1] - dx); self.ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
            self.canvas.draw_idle()
    
    def get_probe_data_at_coords(self, x: float, y: float):
        if self.current_data is None: return
        
        processed_data = self.current_data.copy()

        try:
            x_probe_values = self.formula_validator.evaluate_formula(processed_data, self.x_axis_formula)
            y_probe_values = self.formula_validator.evaluate_formula(processed_data, self.y_axis_formula)
        except Exception: 
            return # If formula fails for probe, just stop.

        dist_sq = (x_probe_values - x)**2 + (y_probe_values - y)**2
        idx = dist_sq.idxmin()
        original_x = self.current_data.get('x', [0])[idx]
        original_y = self.current_data.get('y', [0])[idx]
        self.probe_data_ready.emit({'x': x, 'y': y, 'nearest_point': {'x': original_x, 'y': original_y}, 'variables': self.current_data.loc[idx].to_dict()})

    def _on_scroll(self, event):
        if event.inaxes != self.ax: return
        sf = 1.1 if event.step < 0 else 1/1.1
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim(); xd, yd = event.xdata, event.ydata
        nw, nh = (xlim[1] - xlim[0]) * sf, (ylim[1] - ylim[0]) * sf
        rx, ry = (xd - xlim[0]) / (xlim[1] - xlim[0]), (yd - ylim[0]) / (ylim[1] - ylim[0])
        self.ax.set_xlim([xd - nw * rx, xd + nw * (1 - rx)]); self.ax.set_ylim([yd - nh * ry, yd + nh * (1 - ry)])
        self.canvas.draw_idle()
    
    def _on_button_press(self, event):
        if event.inaxes != self.ax: return
        if event.button == 1: # Left click
            if self.picker_mode: 
                self._handle_picker_click(event)
                return
            self.is_dragging = True
            self.drag_start_pos = (event.xdata, event.ydata)
            self.drag_start_lims = self.ax.get_xlim(), self.ax.get_ylim()
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button == 3: # Right click
            self.reset_view()

    def _handle_picker_click(self, event):
        data, gx, gy = self.interpolated_results.get('heatmap_data'), self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if data is not None and gx is not None:
            try:
                from scipy.interpolate import interpn
                val = interpn((gy[:, 0], gx[0, :]), data, (event.ydata, event.xdata), method='linear', bounds_error=False, fill_value=np.nan)
                if not np.isnan(val): self.value_picked.emit(self.picker_mode, float(val))
            except Exception as e: logger.warning(f"拾取数值失败: {e}")
        self.set_picker_mode(None)

    def _on_button_release(self, event):
        if event.button == 1 and self.is_dragging: 
            self.is_dragging = False; self.drag_start_pos = None
            self.canvas.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def set_picker_mode(self, mode: Optional[str]):
        self.picker_mode = mode
        if mode:
            self.canvas.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self.canvas.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def get_figure_as_numpy(self, dpi=150):
        self.figure.set_dpi(dpi); self.canvas.draw(); return np.asarray(self.canvas.buffer_rgba())
        
    def save_figure(self, filename: str, dpi: int = 300):
        try: self.figure.savefig(filename, dpi=dpi, bbox_inches='tight'); return True
        except Exception as e: logger.error(f"保存图形失败: {e}"); return False
        
    def reset_view(self):
        if self.interpolated_results and 'grid_x' in self.interpolated_results and self.interpolated_results['grid_x'] is not None:
            gx, gy = self.interpolated_results['grid_x'], self.interpolated_results['grid_y']
            x_min, x_max = np.nanmin(gx), np.nanmax(gx)
            y_min, y_max = np.nanmin(gy), np.nanmax(gy)
            xr = x_max - x_min or 1; yr = y_max - y_min or 1; m = 0.05
            self.ax.set_xlim(x_min - m * xr, x_max + m * xr); self.ax.set_ylim(y_min - m * yr, y_max + m * yr)
            self.canvas.draw_idle()