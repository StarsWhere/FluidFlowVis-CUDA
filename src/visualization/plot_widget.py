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
    def __init__(self, data, res, x_ax, y_ax, x_formula, y_formula, heat_cfg, contour_cfg, use_gpu, validator):
        super().__init__()
        self.data, self.res = data, res
        self.x_ax, self.y_ax = x_ax, y_ax
        self.x_formula, self.y_formula = x_formula, y_formula
        self.heat_cfg, self.contour_cfg = heat_cfg, contour_cfg
        self.use_gpu = use_gpu and is_gpu_available()
        self.validator, self.signals = validator, WorkerSignals()
        
    def run(self):
        try: self.signals.result.emit(self._perform_interpolation())
        except Exception as e:
            error_msg = f"插值或公式计算失败: {e}\n{traceback.format_exc()}"
            logger.error(error_msg); self.signals.error.emit(str(e))
        finally: self.signals.finished.emit()

    def _perform_interpolation(self):
        if self.data is None: return {}
        
        # --- NEW: Axis Formula Evaluation ---
        data = self.data.copy() # Work on a copy
        x_axis_to_use = self.x_ax
        y_axis_to_use = self.y_ax
        eval_globals = self.validator.get_all_constants_and_globals()

        if self.x_formula:
            try:
                x_values = data.eval(self.x_formula, global_dict=eval_globals, local_dict={})
                x_axis_to_use = '__x_calculated__'
                data[x_axis_to_use] = x_values
            except Exception as e:
                raise ValueError(f"X轴公式求值失败: {e}")

        if self.y_formula:
            try:
                y_values = data.eval(self.y_formula, global_dict=eval_globals, local_dict={})
                y_axis_to_use = '__y_calculated__'
                data[y_axis_to_use] = y_values
            except Exception as e:
                raise ValueError(f"Y轴公式求值失败: {e}")

        if x_axis_to_use not in data.columns or y_axis_to_use not in data.columns:
            raise ValueError("一个或多个坐标轴变量在数据中不存在。")

        # --- Grid and Point Definition ---
        gx, gy = np.meshgrid(np.linspace(data[x_axis_to_use].min(), data[x_axis_to_use].max(), self.res[0]),
                             np.linspace(data[y_axis_to_use].min(), data[y_axis_to_use].max(), self.res[1]))
        
        # Points for interpolation are based on the (potentially calculated) axes
        points = data[[x_axis_to_use, y_axis_to_use]].values
        cache = {}
        
        # Heatmap/Contour evaluation
        def _interp(var):
            if var not in cache: 
                # Values for Z-data come from the original dataframe columns
                cache[var] = griddata(points, self.data[var].values, (gx, gy), method='linear', fill_value=np.nan)
            return cache[var]

        def _eval_cpu(formula, req_vars):
            def frame_mean(expr_str: str): return self.data.eval(expr_str, global_dict={}, local_dict=eval_globals).mean()
            def frame_sum(expr_str: str): return self.data.eval(expr_str, global_dict={}, local_dict=eval_globals).sum()
            def frame_median(expr_str: str): return self.data.eval(expr_str, global_dict={}, local_dict=eval_globals).median()
            def frame_std(expr_str: str): return self.data.eval(expr_str, global_dict={}, local_dict=eval_globals).std()
            def frame_var(expr_str: str): return self.data.eval(expr_str, global_dict={}, local_dict=eval_globals).var()
            def frame_min(expr_str: str): return self.data.eval(expr_str, global_dict={}, local_dict=eval_globals).min()
            def frame_max(expr_str: str): return self.data.eval(expr_str, global_dict={}, local_dict=eval_globals).max()

            var_data = {var: _interp(var) for var in req_vars}
            local_scope = {
                **eval_globals, **var_data, 'mean': frame_mean, 'sum': frame_sum, 'median': frame_median, 
                'std': frame_std, 'var': frame_var, 'min_frame': frame_min, 'max_frame': frame_max
            }
            
            processed_formula = formula
            pattern = re.compile(r'(\b(?:' + '|'.join(self.validator.allowed_aggregates) + r'))\s*\((.*?)\)')
            for match in reversed(list(pattern.finditer(formula))):
                func_name, inner_expr = match.groups()
                start, end = match.span()
                if inner_expr.count('(') != inner_expr.count(')'): continue
                quoted_inner_expr = f'"{inner_expr}"'
                new_call = f'{func_name}({quoted_inner_expr})'
                processed_formula = processed_formula[:start] + new_call + processed_formula[end:]
            
            logger.debug(f"Original formula: '{formula}', Processed for eval: '{processed_formula}'")
            
            safe_globals = {"__builtins__": None, "np": np}
            result = eval(processed_formula, safe_globals, local_scope)
            
            if not isinstance(result, np.ndarray):
                if gx is not None:
                    return np.full_like(gx, float(result))
                else:
                    raise ValueError("公式必须至少包含一个逐点数据变量 (如 u, v, x 等) 才能进行空间可视化。")
            return result
            
        def _eval_gpu(formula, req_vars):
            var_data = {var: self.data[var].values for var in req_vars}
            combined_vars = {**eval_globals, **var_data}
            gpu_res = evaluate_formula_gpu(formula, combined_vars)
            return griddata(points, gpu_res, (gx, gy), method='linear', fill_value=np.nan)
            
        def _get_data(cfg):
            if not cfg.get('enabled'): return None
            formula, var = cfg.get('formula'), cfg.get('variable')
            if formula:
                req_vars = self.validator.get_used_variables(formula)
                uses_aggregates = any(agg_func in formula for agg_func in self.validator.allowed_aggregates)
                
                if self.use_gpu and not uses_aggregates:
                    return _eval_gpu(formula, req_vars)
                else:
                    return _eval_cpu(formula, req_vars)
            elif var: return _interp(var)
            return None
            
        return {'grid_x': gx, 'grid_y': gy, 'heatmap_data': _get_data(self.heat_cfg), 'contour_data': _get_data(self.contour_cfg)}


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
        
        self.x_axis, self.y_axis = 'x', 'y'
        self.x_axis_formula, self.y_axis_formula = '', ''
        self.use_gpu = False
        self.heatmap_config = {'enabled': False}; self.contour_config = {'enabled': False}
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
        self.ax.set_xlabel(self.x_axis_formula or self.x_axis)
        self.ax.set_ylabel(self.y_axis_formula or self.y_axis)
        self.ax.set_title('InterVis')
        formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
        self.ax.xaxis.set_major_formatter(formatter); self.ax.yaxis.set_major_formatter(formatter)
    
    def update_data(self, data: pd.DataFrame):
        if self.is_busy_interpolating: return
        self.current_data = data.copy(); self.is_busy_interpolating = True
        worker = InterpolationWorker(
            self.current_data, self.grid_resolution, 
            self.x_axis, self.y_axis,
            self.x_axis_formula, self.y_axis_formula,
            self.heatmap_config, self.contour_config, 
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
        self.x_axis = kwargs.get('x_axis', self.x_axis)
        self.y_axis = kwargs.get('y_axis', self.y_axis)
        self.x_axis_formula = kwargs.get('x_axis_formula', self.x_axis_formula)
        self.y_axis_formula = kwargs.get('y_axis_formula', self.y_axis_formula)
        self.use_gpu = kwargs.get('use_gpu', self.use_gpu)
        if 'heatmap_config' in kwargs: self.heatmap_config = kwargs['heatmap_config']
        if 'contour_config' in kwargs: self.contour_config = kwargs['contour_config']

    def redraw(self):
        if not self.ax: return
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim(); is_initial = (xlim == (0.0, 1.0) and ylim == (0.0, 1.0))
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._setup_plot_style()
        if self.heatmap_config.get('enabled'): self._draw_heatmap()
        if self.contour_config.get('enabled'): self._draw_contour()
        
        if not is_initial: 
            self.ax.set_xlim(xlim); self.ax.set_ylim(ylim)
        else: 
            self.reset_view()
            
        self.canvas.draw()
    
    def _draw_heatmap(self):
        data, gx, gy = self.interpolated_results.get('heatmap_data'), self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if data is None or gx is None: return
        vmin, vmax = self.heatmap_config.get('vmin'), self.heatmap_config.get('vmax')
        valid = data[~np.isnan(data)]; vmin = np.min(valid) if vmin is None and valid.size > 0 else vmin
        vmax = np.max(valid) if vmax is None and valid.size > 0 else vmax
        self.heatmap_obj = self.ax.pcolormesh(gx, gy, data, cmap=self.heatmap_config.get('colormap', 'viridis'), vmin=vmin, vmax=vmax, shading='gouraud')
        self.colorbar_obj = self.figure.colorbar(self.heatmap_obj, ax=self.ax, format=ticker.ScalarFormatter(useMathText=True))
        self.colorbar_obj.set_label(self.heatmap_config.get('formula') or self.heatmap_config.get('variable', ''))

    def _draw_contour(self):
        data, gx, gy = self.interpolated_results.get('contour_data'), self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if data is None or gx is None or np.all(np.isnan(data)): return
        self.contour_obj = self.ax.contour(gx, gy, data, levels=self.contour_config.get('levels', 10), colors=self.contour_config.get('colors', 'black'), linewidths=self.contour_config.get('linewidths', 1.0))
        if self.contour_config.get('show_labels'): self.ax.clabel(self.contour_obj, inline=True, fontsize=8, fmt='%.2e')
    
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
        # Probing should work on the original coordinate system, as the calculated
        # coordinates may not exist as columns for the user to see.
        if self.current_data is None: return
        
        # We find the nearest point in the *original* data space
        # as the calculated space may be non-monotonic or complex.
        dist_sq = (self.current_data[self.x_axis] - x)**2 + (self.current_data[self.y_axis] - y)**2
        idx = dist_sq.idxmin()
        self.probe_data_ready.emit({'x': x, 'y': y, 'nearest_point': {'x': self.current_data.loc[idx, self.x_axis], 'y': self.current_data.loc[idx, self.y_axis]}, 'variables': self.current_data.loc[idx].to_dict()})

    def _on_scroll(self, event):
        if event.inaxes != self.ax: return
        sf = 1.1 if event.step < 0 else 1/1.1
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim(); xd, yd = event.xdata, event.ydata
        nw, nh = (xlim[1] - xlim[0]) * sf, (ylim[1] - ylim[0]) * sf
        rx, ry = (xd - xlim[0]) / (xlim[1] - xlim[0]), (yd - ylim[0]) / (ylim[1] - ylim[0])
        self.ax.set_xlim([xd - nw * rx, xd + nw * (1 - rx)]); self.ax.set_ylim([yd - nh * ry, yd + nh * (1 - ry)])
        self.canvas.draw_idle()
    
    def _on_button_press(self, event):
        if event.inaxes != self.ax or event.button != 1: return
        if self.picker_mode: self._handle_picker_click(event); return
        self.is_dragging = True; self.drag_start_pos = (event.xdata, event.ydata); self.drag_start_lims = self.ax.get_xlim(), self.ax.get_ylim()
        self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

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
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)

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
        elif self.current_data is not None and not self.current_data.empty:
            # Fallback to original data if no interpolation results available
            x_min, x_max = self.current_data[self.x_axis].min(), self.current_data[self.x_axis].max()
            y_min, y_max = self.current_data[self.y_axis].min(), self.current_data[self.y_axis].max()
            xr = x_max - x_min or 1; yr = y_max - y_min or 1; m = 0.05
            self.ax.set_xlim(x_min - m * xr, x_max + m * xr); self.ax.set_ylim(y_min - m * yr, y_max + m * yr)
            self.canvas.draw_idle()