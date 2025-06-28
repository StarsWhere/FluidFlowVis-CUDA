#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
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
    def __init__(self, data, res, x_ax, y_ax, heat_cfg, contour_cfg, use_gpu, validator):
        super().__init__()
        self.data, self.res, self.x_ax, self.y_ax = data, res, x_ax, y_ax
        self.heat_cfg, self.contour_cfg, self.use_gpu = heat_cfg, contour_cfg, use_gpu and is_gpu_available()
        self.validator, self.signals = validator, WorkerSignals()

    def run(self):
        try: self.signals.result.emit(self._perform_interpolation())
        except Exception as e:
            error_msg = f"插值失败: {e}\n{traceback.format_exc()}"
            logger.error(error_msg); self.signals.error.emit(str(e))
        finally: self.signals.finished.emit()

    def _perform_interpolation(self):
        if self.data is None or self.x_ax not in self.data.columns or self.y_ax not in self.data.columns: return {}
        gx, gy = np.meshgrid(np.linspace(self.data[self.x_ax].min(), self.data[self.x_ax].max(), self.res[0]),
                             np.linspace(self.data[self.y_ax].min(), self.data[self.y_ax].max(), self.res[1]))
        points, cache = self.data[[self.x_ax, self.y_ax]].values, {}
        def _interp(var):
            if var not in cache: cache[var] = griddata(points, self.data[var].values, (gx, gy), method='linear', fill_value=np.nan)
            return cache[var]
        def _eval_cpu(formula, req_vars):
            var_data = {var: _interp(var) for var in req_vars}
            safe_dict = {'np': np, **var_data} # Use numpy directly
            safe_globals = {"__builtins__": None, "np": np}
            result = eval(formula, safe_globals, var_data)
            return result if isinstance(result, np.ndarray) else np.full_like(gx, float(result))
        def _eval_gpu(formula, req_vars):
            var_data = {var: self.data[var].values for var in req_vars}
            gpu_res = evaluate_formula_gpu(formula, var_data)
            return griddata(points, gpu_res, (gx, gy), method='linear', fill_value=np.nan)
        def _get_data(cfg):
            if not cfg.get('enabled'): return None
            formula, var = cfg.get('formula'), cfg.get('variable')
            if formula:
                req_vars = self.validator.get_used_variables(formula)
                return _eval_gpu(formula, req_vars) if self.use_gpu else _eval_cpu(formula, req_vars)
            elif var: return _interp(var)
            return None
        return {'grid_x': gx, 'grid_y': gy, 'heatmap_data': _get_data(self.heat_cfg), 'contour_data': _get_data(self.contour_cfg)}

class PlotWidget(QWidget):
    mouse_moved = pyqtSignal(float, float); probe_data_ready = pyqtSignal(dict)
    plot_rendered = pyqtSignal(); value_picked = pyqtSignal(str, float)

    def __init__(self, formula_validator, parent=None):
        super().__init__(parent)
        self.formula_validator = formula_validator
        self.figure = Figure(figsize=(12, 8), dpi=100, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.addWidget(self.canvas); self.setLayout(layout)
        self.current_data: Optional[pd.DataFrame] = None; self.interpolated_results: Dict[str, Any] = {}
        self.x_axis, self.y_axis = 'x', 'y'; self.use_gpu = False
        self.heatmap_config = {'enabled': False}; self.contour_config = {'enabled': False}
        self.heatmap_obj = self.contour_obj = self.colorbar_obj = None
        self.is_dragging = False; self.drag_start_pos = None; self.picker_mode: Optional[str] = None
        self.last_mouse_coords: Optional[tuple[float, float]] = None # Store last mouse coordinates for probe updates
        self.grid_resolution = (150, 150); self.thread_pool = QThreadPool(); self.is_busy_interpolating = False
        self._connect_signals(); self._setup_plot_style()

    def _connect_signals(self):
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.canvas.mpl_connect('button_press_event', self._on_button_press)
        self.canvas.mpl_connect('button_release_event', self._on_button_release)

    def _setup_plot_style(self):
        self.ax.set_aspect('auto', adjustable='box'); self.ax.grid(True, linestyle='--', alpha=0.5)
        self.ax.set_xlabel(self.x_axis); self.ax.set_ylabel(self.y_axis); self.ax.set_title('Flow Field Visualization')
        formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
        self.ax.xaxis.set_major_formatter(formatter); self.ax.yaxis.set_major_formatter(formatter)
    
    def update_data(self, data: pd.DataFrame):
        if self.is_busy_interpolating: return
        self.current_data = data.copy(); self.is_busy_interpolating = True
        worker = InterpolationWorker(self.current_data, self.grid_resolution, self.x_axis, self.y_axis,
            self.heatmap_config, self.contour_config, self.use_gpu, self.formula_validator)
        worker.signals.result.connect(self._on_interpolation_result)
        worker.signals.error.connect(lambda e: logger.error(f"插值线程错误: {e}"))
        worker.signals.finished.connect(lambda: setattr(self, 'is_busy_interpolating', False))
        self.thread_pool.start(worker)

    def _on_interpolation_result(self, result: dict):
        self.interpolated_results = result; self.redraw(); self.plot_rendered.emit()
        # After redrawing, if there's a last known mouse position, update probe data
        if self.last_mouse_coords:
            self.get_probe_data_at_coords(self.last_mouse_coords[0], self.last_mouse_coords[1])

    def set_config(self, **kwargs):
        self.x_axis = kwargs.get('x_axis', self.x_axis); self.y_axis = kwargs.get('y_axis', self.y_axis)
        self.use_gpu = kwargs.get('use_gpu', self.use_gpu)
        if 'heatmap_config' in kwargs: self.heatmap_config = kwargs['heatmap_config']
        if 'contour_config' in kwargs: self.contour_config = kwargs['contour_config']

    def redraw(self):
        if not self.ax: return
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim(); is_initial = (xlim == (0.0, 1.0))
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._setup_plot_style()
        if self.heatmap_config.get('enabled'): self._draw_heatmap()
        if self.contour_config.get('enabled'): self._draw_contour()
        if not is_initial: self.ax.set_xlim(xlim); self.ax.set_ylim(ylim)
        else: self.reset_view()
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
        self.last_mouse_coords = (event.xdata, event.ydata) # Update last mouse coordinates
        if not self.is_dragging: self.get_probe_data_at_coords(event.xdata, event.ydata)
        if self.is_dragging and self.drag_start_pos:
            dx, dy = event.xdata - self.drag_start_pos[0], event.ydata - self.drag_start_pos[1]
            xlim, ylim = self.drag_start_lims
            self.ax.set_xlim(xlim[0] - dx, xlim[1] - dx); self.ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
            self.canvas.draw_idle()
    
    def get_probe_data_at_coords(self, x: float, y: float):
        if self.current_data is None: return
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
        if event.button == 1 and self.is_dragging: self.is_dragging = False; self.drag_start_pos = None
    def set_picker_mode(self, mode: Optional[str]):
        self.picker_mode = mode; self.canvas.setCursor(QCursor(Qt.CursorShape.CrossCursor if mode else Qt.CursorShape.ArrowCursor))
    def get_figure_as_numpy(self, dpi=150):
        self.figure.set_dpi(dpi); self.canvas.draw(); return np.asarray(self.canvas.buffer_rgba())
    def save_figure(self, filename: str, dpi: int = 300):
        try: self.figure.savefig(filename, dpi=dpi, bbox_inches='tight'); return True
        except Exception as e: logger.error(f"保存图形失败: {e}"); return False
    def reset_view(self):
        if self.current_data is not None and not self.current_data.empty:
            x_min, x_max = self.current_data[self.x_axis].min(), self.current_data[self.x_axis].max()
            y_min, y_max = self.current_data[self.y_axis].min(), self.current_data[self.y_axis].max()
            xr = x_max - x_min or 1; yr = y_max - y_min or 1; m = 0.05
            self.ax.set_xlim(x_min - m * xr, x_max + m * xr); self.ax.set_ylim(y_min - m * yr, y_max + m * yr)
            self.canvas.draw_idle()