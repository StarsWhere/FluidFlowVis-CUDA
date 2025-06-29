#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import logging
import traceback
import sys
from typing import Optional, Dict, Any, Tuple

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.lines import Line2D
from scipy.interpolate import interpn, griddata

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QObject, QRunnable, QThreadPool, Qt
from PyQt6.QtGui import QCursor

from src.core.rendering_core import prepare_gridded_data
from src.core.constants import VectorPlotType, StreamlineColor, PickerMode

logger = logging.getLogger(__name__)

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(dict)

class InterpolationWorker(QRunnable):
    def __init__(self, data, config, formula_engine):
        super().__init__()
        self.data = data
        self.config = config
        self.formula_engine = formula_engine
        self.signals = WorkerSignals()
        
    def run(self):
        try:
            result = prepare_gridded_data(self.data, self.config, self.formula_engine)
            self.signals.result.emit(result)
        except Exception as e:
            error_msg = f"插值或公式计算失败: {e}\n{traceback.format_exc()}"
            logger.error(error_msg)
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

class PlotWidget(QWidget):
    mouse_moved = pyqtSignal(float, float)
    probe_data_ready = pyqtSignal(dict)
    plot_rendered = pyqtSignal()
    value_picked = pyqtSignal(PickerMode, float)
    timeseries_point_picked = pyqtSignal(tuple)
    profile_line_defined = pyqtSignal(tuple, tuple)
    interpolation_error = pyqtSignal(str)

    def __init__(self, formula_engine, parent=None):
        super().__init__(parent)
        self.formula_engine = formula_engine
        self.figure = Figure(figsize=(12, 8), dpi=100, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.addWidget(self.canvas)
        
        self.current_data: Optional[pd.DataFrame] = None
        self.interpolated_results: Dict[str, Any] = {}
        
        self.x_axis_formula, self.y_axis_formula, self.chart_title = 'x', 'y', ''
        self.use_gpu, self.heatmap_config, self.contour_config, self.vector_config = False, {}, {}, {}
        self.grid_resolution = (150, 150)
        self.analysis = {}
        
        self.heatmap_obj = self.contour_obj = self.colorbar_obj = self.vector_quiver_obj = self.vector_stream_obj = None
        
        self.is_dragging = False; self.drag_start_pos = None; self.picker_mode: Optional[PickerMode] = None
        self.profile_start_point: Optional[Tuple[float, float]] = None
        self.profile_preview_line: Optional[Line2D] = None
        self.last_mouse_coords: Optional[Tuple[float, float]] = None
        self.thread_pool = QThreadPool(); self.is_busy_interpolating = False
        
        self._connect_signals()
        self._setup_plot_style()

    def _connect_signals(self):
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.canvas.mpl_connect('button_press_event', self._on_button_press)
        self.canvas.mpl_connect('button_release_event', self._on_button_release)

    def _get_platform_font(self) -> str:
        if sys.platform == "win32": return "Microsoft YaHei"
        elif sys.platform == "darwin": return "PingFang SC"
        font_options = ["WenQuanYi Zen Hei", "Noto Sans CJK SC", "Source Han Sans SC"]
        for font in font_options:
            if fm.findfont(font, fallback_to_default=False): return font
        return "sans-serif"

    def _setup_plot_style(self):
        font_name = self._get_platform_font()
        plt.rcParams['font.sans-serif'] = [font_name]
        plt.rcParams['axes.unicode_minus'] = False
        logger.info(f"使用字体: {font_name}")
        self.ax.grid(True, linestyle='--', alpha=0.5)

    def _update_plot_decorations(self):
        self.ax.set_xlabel(self.x_axis_formula); self.ax.set_ylabel(self.y_axis_formula)
        
        title = self.chart_title
        if not title:
            is_avg = self.analysis.get('time_average', {}).get('enabled', False)
            if is_avg:
                start = self.analysis['time_average']['start_frame']
                end = self.analysis['time_average']['end_frame']
                title = f"时间平均场 (帧 {start}-{end})"
            else:
                parts = []
                if self.heatmap_config.get('enabled'): parts.append(f"热力图: {self.heatmap_config['formula']}")
                if self.contour_config.get('enabled'): parts.append(f"等高线: {self.contour_config['formula']}")
                title = " | ".join(parts) if parts else "InterVis Plot"
        self.ax.set_title(title)
        
        formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
        self.ax.xaxis.set_major_formatter(formatter); self.ax.yaxis.set_major_formatter(formatter)

    def update_data(self, data: Optional[pd.DataFrame]):
        if self.is_busy_interpolating: return
        if data is None or data.empty:
             self.ax.clear(); self._setup_plot_style(); self.ax.text(0.5, 0.5, "无有效数据点", ha='center', va='center', transform=self.ax.transAxes); self.canvas.draw_idle()
             return

        self.current_data = data.copy(); self.is_busy_interpolating = True
        
        worker_config = {
            'x_axis_formula': self.x_axis_formula, 'y_axis_formula': self.y_axis_formula,
            'heatmap_config': self.heatmap_config, 'contour_config': self.contour_config,
            'vector_config': self.vector_config, 'use_gpu': self.use_gpu, 'grid_resolution': self.grid_resolution
        }
        
        worker = InterpolationWorker(self.current_data, worker_config, self.formula_engine)
        worker.signals.result.connect(self._on_interpolation_result)
        worker.signals.error.connect(self._on_worker_error)
        worker.signals.finished.connect(lambda: setattr(self, 'is_busy_interpolating', False))
        self.thread_pool.start(worker)

    def _on_worker_error(self, error_message: str):
        self.is_busy_interpolating = False
        logger.error(f"插值线程错误: {error_message}")
        self.interpolation_error.emit(error_message)

    def _on_interpolation_result(self, result: dict):
        is_initial_plot = not self.interpolated_results
        self.interpolated_results = result
        self.redraw(is_initial_plot)
        self.plot_rendered.emit()
        if self.last_mouse_coords: self.get_probe_data_at_coords(*self.last_mouse_coords)

    def set_config(self, **kwargs):
        for key, value in kwargs.items(): setattr(self, key, value)
    
    def redraw(self, is_initial: bool = False):
        if not self.interpolated_results: return
        self._remove_profile_preview()
        self._update_plot_decorations()
        self._draw_heatmap(); self._draw_contour(); self._draw_vector_plot()
        if is_initial: self.reset_view()
        self.canvas.draw_idle()
    
    def _draw_heatmap(self):
        data, gx, gy = self.interpolated_results.get('heatmap_data'), self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        
        if self.colorbar_obj: self.colorbar_obj.remove(); self.colorbar_obj = None
        if self.heatmap_obj: self.heatmap_obj.remove(); self.heatmap_obj = None

        if not self.heatmap_config.get('enabled') or data is None or gx is None: return

        vmin_str, vmax_str = self.heatmap_config.get('vmin'), self.heatmap_config.get('vmax')
        
        vmin = float(vmin_str) if vmin_str is not None and str(vmin_str).strip() != '' else None
        vmax = float(vmax_str) if vmax_str is not None and str(vmax_str).strip() != '' else None

        valid = data[~np.isnan(data)]
        if valid.size > 0:
            if vmin is None: vmin = np.min(valid)
            if vmax is None: vmax = np.max(valid)

        self.heatmap_obj = self.ax.pcolormesh(gx, gy, data, cmap=self.heatmap_config.get('colormap', 'viridis'), vmin=vmin, vmax=vmax, shading='gouraud')
        self.colorbar_obj = self.figure.colorbar(self.heatmap_obj, ax=self.ax, format=ticker.ScalarFormatter(useMathText=True))
        self.colorbar_obj.set_label(self.heatmap_config.get('formula', ''))

    def _draw_contour(self):
        if self.contour_obj:
            for coll in self.contour_obj.collections: coll.remove()
            self.contour_obj = None

        data, gx, gy = self.interpolated_results.get('contour_data'), self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
        if not self.contour_config.get('enabled') or data is None or gx is None or np.all(np.isnan(data)): return

        self.contour_obj = self.ax.contour(gx, gy, data, levels=self.contour_config.get('levels', 10), colors=self.contour_config.get('colors', 'black'), linewidths=self.contour_config.get('linewidths', 1.0))
        if self.contour_config.get('show_labels'): self.ax.clabel(self.contour_obj, inline=True, fontsize=8, fmt='%.2e')

    def _draw_vector_plot(self):
        if self.vector_quiver_obj: self.vector_quiver_obj.remove(); self.vector_quiver_obj = None
        if self.vector_stream_obj: self.vector_stream_obj.lines.remove(); self.vector_stream_obj = None
        
        if not self.vector_config.get('enabled'): return
        plot_type = VectorPlotType.from_str(self.vector_config.get('type'))
        if plot_type == VectorPlotType.QUIVER: self._draw_quiver()
        else: self._draw_streamlines()

    def _draw_quiver(self):
        u, v, gx, gy = (self.interpolated_results.get(k) for k in ['vector_u_data', 'vector_v_data', 'grid_x', 'grid_y'])
        if u is None or v is None or gx is None: return
        opts = self.vector_config.get('quiver_options', {}); density = opts.get('density', 10); scale = opts.get('scale', 1.0)
        sl = slice(None, None, density)
        self.vector_quiver_obj = self.ax.quiver(gx[sl, sl], gy[sl, sl], u[sl, sl], v[sl, sl], scale=scale, scale_units='xy', angles='xy')

    def _draw_streamlines(self):
        u, v, gx, gy = (self.interpolated_results.get(k) for k in ['vector_u_data', 'vector_v_data', 'grid_x', 'grid_y'])
        if u is None or v is None or gx is None: return
        opts = self.vector_config.get('streamline_options', {}); density = opts.get('density', 1.5); lw = opts.get('linewidth', 1.0)
        color_by = StreamlineColor.from_str(opts.get('color_by'))
        
        color_data = 'black'
        if color_by == StreamlineColor.MAGNITUDE: color_data = np.sqrt(u**2 + v**2)
        elif color_by == StreamlineColor.U_COMPONENT: color_data = u
        elif color_by == StreamlineColor.V_COMPONENT: color_data = v
        
        self.vector_stream_obj = self.ax.streamplot(gx, gy, u, v, density=density, linewidth=lw, color=color_data, cmap='viridis' if isinstance(color_data, np.ndarray) else None)
        if isinstance(color_data, np.ndarray) and not self.colorbar_obj:
            self.colorbar_obj = self.figure.colorbar(self.vector_stream_obj.lines, ax=self.ax)
            self.colorbar_obj.set_label(f"流线 ({color_by.value})")

    def _on_mouse_move(self, event):
        if event.inaxes != self.ax or event.xdata is None: return
        self.mouse_moved.emit(event.xdata, event.ydata)
        self.last_mouse_coords = (event.xdata, event.ydata)
        if self.is_dragging:
            if self.drag_start_pos:
                dx, dy = event.xdata - self.drag_start_pos[0], event.ydata - self.drag_start_pos[1]
                xlim, ylim = self.drag_start_lims
                self.ax.set_xlim(xlim[0] - dx, xlim[1] - dx); self.ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
                self.canvas.draw_idle()
        elif self.picker_mode == PickerMode.PROFILE_END and self.profile_start_point:
            self._update_profile_preview((event.xdata, event.ydata))
        elif not self.picker_mode:
            self.get_probe_data_at_coords(event.xdata, event.ydata)
    
    def get_probe_data_at_coords(self, x: float, y: float):
        if self.current_data is None or self.current_data.empty: return
        results = {'x': x, 'y': y, 'variables': {}, 'interpolated': {}}
        try:
            # --- FIX: Handle complex axis formulas for probing raw data ---
            x_vals_formula = self.x_axis_formula or 'x'
            y_vals_formula = self.y_axis_formula or 'y'
            x_vals = self.current_data[x_vals_formula] if x_vals_formula in self.current_data.columns else self.formula_engine.evaluate_formula(self.current_data, x_vals_formula)
            y_vals = self.current_data[y_vals_formula] if y_vals_formula in self.current_data.columns else self.formula_engine.evaluate_formula(self.current_data, y_vals_formula)
            # --- END OF FIX ---
            dist_sq = (x_vals - x)**2 + (y_vals - y)**2
            if not dist_sq.empty:
                idx = dist_sq.idxmin()
                results['variables'] = self.current_data.loc[idx].to_dict()
        except Exception as e: logger.debug(f"获取原始探针数据时出错: {e}")

        try:
            gx, gy = self.interpolated_results.get('grid_x'), self.interpolated_results.get('grid_y')
            if gx is not None and gy is not None:
                point, grid_coords = (y, x), (gy[:, 0], gx[0, :])
                for key, data in self.interpolated_results.items():
                    if 'data' in key and isinstance(data, np.ndarray):
                        val = interpn(grid_coords, data, point, method='linear', bounds_error=False, fill_value=np.nan)[0]
                        results['interpolated'][key.replace('_data', '')] = val
        except Exception as e: logger.debug(f"获取插值探针数据时出错: {e}")
        self.probe_data_ready.emit(results)

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
        if event.button == 1:
            if self.picker_mode: self._handle_picker_click(event); return
            self.is_dragging, self.drag_start_pos = True, (event.xdata, event.ydata)
            self.drag_start_lims = self.ax.get_xlim(), self.ax.get_ylim()
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button == 3:
            if self.picker_mode: # 右键取消选择模式
                self.set_picker_mode(None)
            else:
                self.reset_view()

    def _handle_picker_click(self, event):
        coords = (event.xdata, event.ydata)
        if self.picker_mode == PickerMode.TIMESERIES:
            self.timeseries_point_picked.emit(coords)
            self.set_picker_mode(None)
        elif self.picker_mode == PickerMode.PROFILE_START:
            self.profile_start_point = coords
            self.set_picker_mode(PickerMode.PROFILE_END)
        elif self.picker_mode == PickerMode.PROFILE_END:
            if self.profile_start_point:
                self.profile_line_defined.emit(self.profile_start_point, coords)
            self.set_picker_mode(None)
        else: # VMIN/VMAX
            data = self.interpolated_results.get('heatmap_data')
            if data is not None:
                val = self._get_interpolated_value_at_coord('heatmap_data', *coords)
                if val is not None and not np.isnan(val): self.value_picked.emit(self.picker_mode, float(val))
            self.set_picker_mode(None)
    
    def _get_interpolated_value_at_coord(self, key, x, y) -> Optional[float]:
        data, gx, gy = (self.interpolated_results.get(k) for k in [key, 'grid_x', 'grid_y'])
        if data is None or gx is None: return None
        try: return interpn((gy[:, 0], gx[0, :]), data, (y, x), method='linear', bounds_error=False, fill_value=np.nan)[0]
        except Exception as e: logger.warning(f"拾取/插值数值失败: {e}"); return None

    def _on_button_release(self, event):
        if event.button == 1 and self.is_dragging: 
            self.is_dragging, self.drag_start_pos = False, None
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)

    def set_picker_mode(self, mode: Optional[PickerMode]):
        self.picker_mode = mode
        if mode:
            self.canvas.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
            self._remove_profile_preview()
            self.profile_start_point = None
            
    def _update_profile_preview(self, end_point):
        if not self.profile_start_point: return
        self._remove_profile_preview()
        self.profile_preview_line = Line2D(
            [self.profile_start_point[0], end_point[0]],
            [self.profile_start_point[1], end_point[1]],
            color='red', linestyle='--', marker='o'
        )
        self.ax.add_line(self.profile_preview_line)
        self.canvas.draw_idle()

    def _remove_profile_preview(self):
        if self.profile_preview_line:
            try:
                self.ax.lines.remove(self.profile_preview_line)
                self.profile_preview_line = None
            except ValueError:
                self.profile_preview_line = None
        self.canvas.draw_idle()

    def save_figure(self, filename: str, dpi: int = 300):
        try: self.figure.savefig(filename, dpi=dpi, bbox_inches='tight'); return True
        except Exception as e: logger.error(f"保存图形失败: {e}"); return False
        
    def reset_view(self):
        if self.interpolated_results and 'grid_x' in self.interpolated_results and self.interpolated_results['grid_x'] is not None:
            gx, gy = self.interpolated_results['grid_x'], self.interpolated_results['grid_y']
            if np.all(np.isnan(gx)) or np.all(np.isnan(gy)): return
            x_min, x_max, y_min, y_max = np.nanmin(gx), np.nanmax(gx), np.nanmin(gy), np.nanmax(gy)
            if any(np.isnan(v) for v in [x_min, x_max, y_min, y_max]): return
            
            xr = x_max - x_min or 1; yr = y_max - y_min or 1; m = 0.05
            self.ax.set_xlim(x_min - m * xr, x_max + m * xr); self.ax.set_ylim(y_min - m * yr, y_max + m * yr)
            self.ax.set_aspect('auto', adjustable='box')
            self.canvas.draw_idle()