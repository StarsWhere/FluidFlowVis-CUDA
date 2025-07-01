from PyQt6.QtGui import QIcon
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
from typing import Optional
import numpy as np
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QFileDialog, QLineEdit, QMenu, QInputDialog, QToolTip, QListWidgetItem
from PyQt6.QtCore import Qt, QSettings, QPoint, QTimer
from PyQt6.QtGui import QCursor

from src.core.data_manager import DataManager
from src.core.formula_engine import FormulaEngine
from src.core.constants import PickerMode
from src.utils.help_dialog import HelpDialog
from src.utils.gpu_utils import is_gpu_available
from src.utils.help_content import (
    get_formula_help_html, get_axis_title_help_html,
    get_data_processing_help_html, get_analysis_help_html,
    get_template_help_html, get_theme_help_html
)
from src.ui.ui_setup import UiMainWindow
from src.ui.dialogs import ImportDialog, StatsProgressDialog
from src.ui.timeseries_dialog import TimeSeriesDialog
from src.ui.profile_plot_dialog import ProfilePlotDialog
from src.core.workers import DatabaseImportWorker

from src.handlers.config_handler import ConfigHandler
from src.handlers.stats_handler import StatsHandler
from src.handlers.export_handler import ExportHandler
from src.handlers.playback_handler import PlaybackHandler
from src.handlers.compute_handler import ComputeHandler
from src.handlers.template_handler import TemplateHandler
from src.handlers.theme_handler import ThemeHandler


try:
    import moviepy.editor
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

try:
    import imageio
    IMAGEIO_AVAILABLE = True
except ImportError:
    IMAGEIO_AVAILABLE = False

VIDEO_EXPORT_AVAILABLE = MOVIEPY_AVAILABLE or IMAGEIO_AVAILABLE
logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """应用程序的主窗口类。"""
    
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("png/icon.png")) # 设置主窗口图标
        
        self.settings = QSettings("StarsWhere", "InterVis")
        self.data_manager = DataManager()
        self.formula_engine = FormulaEngine()
        self.ui = UiMainWindow()

        self.current_frame_index: int = 0
        self._should_reset_view_after_refresh: bool = False
        
        self.project_dir = self.settings.value("project_directory", os.path.join(os.getcwd(), "data"))
        self.output_dir = self.settings.value("output_directory", os.path.join(os.getcwd(), "output"))
        os.makedirs(self.project_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.redraw_debounce_timer = QTimer(self); self.redraw_debounce_timer.setSingleShot(True); self.redraw_debounce_timer.setInterval(150)
        self.validation_timer = QTimer(self); self.validation_timer.setSingleShot(True); self.validation_timer.setInterval(500)

        self.import_worker: Optional[DatabaseImportWorker] = None
        self.import_progress_dialog: Optional[ImportDialog] = None
        self.timeseries_dialog: Optional[TimeSeriesDialog] = None
        self.profile_dialog: Optional[ProfilePlotDialog] = None

        self.config_handler = ConfigHandler(self, self.ui)
        self.stats_handler = StatsHandler(self, self.ui, self.data_manager, self.formula_engine)
        self.export_handler = ExportHandler(self, self.ui, self.data_manager, self.config_handler)
        self.playback_handler = PlaybackHandler(self, self.ui, self.data_manager)
        self.compute_handler = ComputeHandler(self, self.ui, self.data_manager, self.formula_engine)
        self.template_handler = TemplateHandler(self, self.ui, self.config_handler)
        self.theme_handler = ThemeHandler(self, self.ui)
        
        self._init_ui()
        self._connect_signals()
        self._load_settings()
        self._initialize_project()

    def _init_ui(self):
        self.ui.setup_ui(self, self.formula_engine)
        self.ui.gpu_checkbox.setEnabled(is_gpu_available())
        self.ui.data_dir_line_edit.setText(self.project_dir)
        self.export_handler.set_output_dir(self.output_dir)
        
        if not VIDEO_EXPORT_AVAILABLE:
            tooltip = "功能不可用：请安装 moviepy 或 imageio"
            self.ui.export_vid_btn.setEnabled(False); self.ui.export_vid_btn.setToolTip(tooltip)
            self.ui.batch_export_btn.setEnabled(False); self.ui.batch_export_btn.setToolTip(tooltip)

        self._update_gpu_status_label()
        self._on_vector_plot_type_changed()
        self._on_time_analysis_mode_changed()

    def _connect_signals(self):
        self.data_manager.error_occurred.connect(self._on_error)
        self.redraw_debounce_timer.timeout.connect(self._apply_visualization_settings)
        self.validation_timer.timeout.connect(self._validate_all_formulas)
        
        # Plot Widget
        self.ui.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        self.ui.plot_widget.probe_data_ready.connect(self._on_probe_data)
        self.ui.plot_widget.value_picked.connect(self._on_value_picked)
        self.ui.plot_widget.timeseries_point_picked.connect(self._on_timeseries_point_picked)
        self.ui.plot_widget.profile_line_defined.connect(self._on_profile_line_defined)
        self.ui.plot_widget.plot_rendered.connect(self._on_plot_rendered)
        self.ui.plot_widget.interpolation_error.connect(self._on_interpolation_error)
        self.ui.plot_widget.mouse_left_plot.connect(QToolTip.hideText)
        
        # Menu & Toolbar
        self.ui.open_data_dir_action.triggered.connect(self._change_project_directory)
        self.ui.reload_action.triggered.connect(self._force_reload_data)
        self.ui.exit_action.triggered.connect(self.close)
        self.ui.reset_view_action.triggered.connect(self.ui.plot_widget.reset_view)
        self.ui.toggle_panel_action.triggered.connect(self._toggle_control_panel)
        self.ui.full_screen_action.triggered.connect(self._toggle_full_screen)
        self.ui.formula_help_action.triggered.connect(lambda: self._show_help("formula"))
        self.ui.analysis_help_action.triggered.connect(lambda: self._show_help("analysis"))
        self.ui.dp_help_action.triggered.connect(lambda: self._show_help("data_processing"))
        self.ui.template_help_action.triggered.connect(lambda: self._show_help("template"))
        self.ui.theme_help_action.triggered.connect(lambda: self._show_help("theme"))
        self.ui.about_action.triggered.connect(self._show_about)

        # General Controls
        self.ui.change_data_dir_btn.clicked.connect(self._change_project_directory)
        self.ui.refresh_button.clicked.connect(lambda: self._force_refresh_plot(reset_view=True))
        self.ui.apply_cache_btn.clicked.connect(self._apply_cache_settings)
        self.ui.gpu_checkbox.toggled.connect(self._on_gpu_toggle)
        self.ui.vector_plot_type.currentIndexChanged.connect(self._on_vector_plot_type_changed)
        self.ui.aspect_ratio_combo.currentIndexChanged.connect(self._on_aspect_ratio_mode_changed)
        
        # Analysis/Data Management Controls
        self.ui.apply_filter_btn.clicked.connect(self._apply_global_filter)
        self.ui.time_analysis_mode_combo.currentIndexChanged.connect(self._on_time_analysis_mode_changed)
        self.ui.pick_timeseries_btn.toggled.connect(self._on_pick_timeseries_toggled)
        self.ui.pick_by_coords_btn.clicked.connect(self._pick_timeseries_by_coords)
        self.ui.draw_profile_btn.toggled.connect(self._on_draw_profile_toggled)
        self.ui.draw_profile_by_coords_btn.clicked.connect(self._draw_profile_by_coords)
        self.ui.time_analysis_help_btn.clicked.connect(lambda: self._show_help("analysis"))
        self.ui.time_avg_start_slider.valueChanged.connect(self.ui.time_avg_start_spinbox.setValue)
        self.ui.time_avg_start_spinbox.valueChanged.connect(self.ui.time_avg_start_slider.setValue)
        self.ui.time_avg_end_slider.valueChanged.connect(self.ui.time_avg_end_spinbox.setValue)
        self.ui.time_avg_end_spinbox.valueChanged.connect(self.ui.time_avg_end_slider.setValue)
        self.ui.time_avg_start_spinbox.editingFinished.connect(self._trigger_auto_apply)
        self.ui.time_avg_end_spinbox.editingFinished.connect(self._trigger_auto_apply)

        # Connect all handlers
        self.config_handler.connect_signals()
        self.stats_handler.connect_signals()
        self.export_handler.connect_signals()
        self.playback_handler.connect_signals()
        self.compute_handler.connect_signals()
        self.template_handler.connect_signals()
        self.theme_handler.connect_signals()
        
        self._connect_auto_apply_widgets()

    def _get_all_formula_editors(self) -> list[QLineEdit]:
        return [
            self.ui.x_axis_formula, self.ui.y_axis_formula, self.ui.chart_title_edit,
            self.ui.heatmap_formula, self.ui.contour_formula,
            self.ui.vector_u_formula, self.ui.vector_v_formula,
            self.ui.new_variable_formula_edit, self.ui.filter_text_edit,
            self.ui.new_time_agg_formula_edit # Added for new feature
        ]

    def _connect_auto_apply_widgets(self):
        widgets = [
            self.ui.heatmap_enabled, self.ui.heatmap_colormap,
            self.ui.contour_enabled, self.ui.contour_labels, self.ui.contour_levels,
            self.ui.contour_linewidth, self.ui.contour_colors, self.ui.vector_enabled,
            self.ui.vector_plot_type, self.ui.quiver_density_spinbox, self.ui.quiver_scale_spinbox,
            self.ui.stream_density_spinbox, self.ui.stream_linewidth_spinbox, self.ui.stream_color_combo,
            self.ui.filter_enabled_checkbox, self.ui.aspect_ratio_spinbox
        ]
        
        for editor in self._get_all_formula_editors():
            editor.textChanged.connect(self.validation_timer.start)
            editor.editingFinished.connect(self._trigger_auto_apply)

        for w in widgets:
            if hasattr(w, 'toggled'): w.toggled.connect(self._trigger_auto_apply)
            elif hasattr(w, 'currentIndexChanged'): w.currentIndexChanged.connect(self._trigger_auto_apply)
            elif hasattr(w, 'valueChanged'): w.valueChanged.connect(self._trigger_auto_apply)
    
    def _trigger_auto_apply(self, *args):
        if self.config_handler._is_loading_config: return
        self.config_handler.mark_config_as_dirty()
        if self.data_manager.get_frame_count() > 0:
            self._should_reset_view_after_refresh = True
            self.redraw_debounce_timer.start()

    def _validate_all_formulas(self):
        for editor in self._get_all_formula_editors():
            is_valid, error_msg = self.formula_engine.validate_syntax(editor.text())
            editor.setStyleSheet("" if is_valid else "background-color: #ffe0e0;")
            editor.setToolTip(error_msg)

    def _initialize_project(self):
        if not self.data_manager.setup_project_directory(self.project_dir): return
        if self.data_manager.is_database_ready():
            logger.info(f"在 {self.project_dir} 中找到现有数据库，直接加载。")
            self._load_project_data()
        else:
            reply = QMessageBox.question(self, "未找到数据库", f"在目录 '{self.project_dir}' 中未找到数据库文件。\n\n是否从此目录中的所有CSV文件创建新的数据库？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes: self._start_database_import()
            else: self.ui.status_bar.showMessage("操作已取消。请选择一个包含CSV文件或数据库的项目目录。", 5000)

    def _start_database_import(self):
        self.import_progress_dialog = ImportDialog(self, "正在创建和分析数据库...")
        self.import_worker = DatabaseImportWorker(self.data_manager)
        self.import_worker.progress.connect(self.import_progress_dialog.update_progress)
        self.import_worker.log_message.connect(self.import_progress_dialog.set_log_message)
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.error.connect(self._on_error)
        self.import_worker.start()
        self.import_progress_dialog.exec()
        
    def _on_import_finished(self):
        if self.import_progress_dialog: self.import_progress_dialog.accept()
        QMessageBox.information(self, "导入完成", "数据库已成功创建，基础统计数据已计算完毕。")
        self._load_project_data()

    def _load_project_data(self):
        self.data_manager.post_import_setup()
        self._update_db_info()
        frame_count = self.data_manager.get_frame_count()
        if frame_count > 0:
            all_vars = self.data_manager.get_variables()
            self.stats_handler.load_definitions_and_stats()
            self.playback_handler.update_time_axis_candidates()
            self.formula_engine.update_allowed_variables(all_vars)
            
            # --- FIX: Populate floating probe list with checkable items ---
            self.ui.floating_probe_vars_list.clear()
            for var in sorted(all_vars):
                item = QListWidgetItem(var)
                item.setCheckState(Qt.CheckState.Unchecked) # Make item checkable
                self.ui.floating_probe_vars_list.addItem(item)
            # --- END FIX ---

            self.ui.time_slider.setMaximum(frame_count - 1)
            self.ui.video_start_frame.setMaximum(frame_count - 1); self.ui.video_end_frame.setMaximum(frame_count - 1); self.ui.video_end_frame.setValue(frame_count - 1)
            for w in [self.ui.time_avg_start_slider, self.ui.time_avg_start_spinbox, self.ui.time_avg_end_slider, self.ui.time_avg_end_spinbox]: w.setMaximum(frame_count - 1)
            self.ui.time_avg_end_spinbox.setValue(frame_count - 1)
            self.config_handler.populate_config_combobox()
            self.template_handler.populate_template_combobox()
            self.theme_handler.populate_theme_combobox()
            self.ui.compute_and_add_btn.setEnabled(True)
            self.ui.compute_and_add_time_agg_btn.setEnabled(True)
            self._force_refresh_plot(reset_view=True)
            self.ui.status_bar.showMessage(f"项目加载成功，共 {frame_count} 帧数据。", 5000)
        else:
            self.ui.status_bar.showMessage("项目加载失败：数据库为空或无法读取。", 5000); QMessageBox.warning(self, "数据为空", "项目加载失败：数据库为空或无法读取。")
            self.ui.compute_and_add_btn.setEnabled(False)
            self.ui.compute_and_add_time_agg_btn.setEnabled(False)
    
    def _update_db_info(self):
        info = self.data_manager.get_database_info()
        db_path = info.get("db_path", "N/A"); is_ready = info.get("is_ready", False)
        frame_count = info.get("frame_count", 0); variables = info.get("variables", [])
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if db_path != "N/A" and os.path.exists(db_path) else 0
        db_info_text = f"路径: {os.path.basename(db_path)} | 帧: {frame_count} | 变量: {len(variables)} | 大小: {db_size_mb:.2f} MB"
        self.ui.db_info_label.setText(db_info_text); self.ui.db_info_label.setToolTip(db_path)

    def _apply_global_filter(self):
        try:
            filter_text = self.ui.filter_text_edit.text() if self.ui.filter_enabled_checkbox.isChecked() else ""
            self.data_manager.set_global_filter(filter_text)
            self._force_refresh_plot(reset_view=True)
            self.ui.status_bar.showMessage("全局过滤器已应用。", 3000)
        except ValueError as e:
            QMessageBox.critical(self, "过滤器错误", f"过滤器语法无效: {e}")

    def _on_time_analysis_mode_changed(self):
        is_time_avg = self.ui.time_analysis_mode_combo.currentText() == "时间平均场"
        self.ui.playback_widget.setVisible(not is_time_avg)
        self.playback_handler.set_enabled(not is_time_avg)
        self.ui.time_average_range_widget.setVisible(is_time_avg)
        if VIDEO_EXPORT_AVAILABLE:
            self.ui.export_vid_btn.setEnabled(not is_time_avg)
            self.ui.batch_export_btn.setEnabled(True)
            self.ui.export_vid_btn.setToolTip("时间平均场模式下无法导出视频" if is_time_avg else "")
        self._trigger_auto_apply()

    def _on_aspect_ratio_mode_changed(self):
        is_custom = self.ui.aspect_ratio_combo.currentText() == "Custom"
        self.ui.aspect_ratio_spinbox.setVisible(is_custom); self._trigger_auto_apply()
        
    def _on_pick_timeseries_toggled(self, checked):
        if checked:
            self.ui.draw_profile_btn.setChecked(False)
            self.ui.plot_widget.set_picker_mode(PickerMode.TIMESERIES)
            self.ui.status_bar.showMessage("时间序列模式: 在图表上单击一点以拾取 (右键取消)。", 0)
        elif self.ui.plot_widget.picker_mode == PickerMode.TIMESERIES:
            self.ui.plot_widget.set_picker_mode(None); self.ui.status_bar.clearMessage()

    def _on_draw_profile_toggled(self, checked):
        if checked:
            self.ui.pick_timeseries_btn.setChecked(False)
            self.ui.plot_widget.set_picker_mode(PickerMode.PROFILE_START)
            self.ui.status_bar.showMessage("剖面图模式: 点击定义剖面线起点 (右键取消)。", 0)
        elif self.ui.plot_widget.picker_mode in [PickerMode.PROFILE_START, PickerMode.PROFILE_END]:
            self.ui.plot_widget.set_picker_mode(None); self.ui.status_bar.clearMessage()

    def _pick_timeseries_by_coords(self):
        text, ok = QInputDialog.getText(self, "按坐标拾取时间序列点", "请输入坐标 (x, y):", QLineEdit.EchoMode.Normal, "0.0, 0.0")
        if ok and text:
            try:
                x_str, y_str = text.split(','); coords = (float(x_str.strip()), float(y_str.strip()))
                self._on_timeseries_point_picked(coords)
            except (ValueError, IndexError): QMessageBox.warning(self, "输入无效", "请输入格式为 'x, y' 的两个数值。")

    def _draw_profile_by_coords(self):
        start_text, ok1 = QInputDialog.getText(self, "绘制剖面图", "请输入起点坐标 (x1, y1):")
        if not (ok1 and start_text): return
        end_text, ok2 = QInputDialog.getText(self, "绘制剖面图", "请输入终点坐标 (x2, y2):")
        if not (ok2 and end_text): return
        try:
            x1_str, y1_str = start_text.split(','); start_coords = (float(x1_str.strip()), float(y1_str.strip()))
            x2_str, y2_str = end_text.split(','); end_coords = (float(x2_str.strip()), float(y2_str.strip()))
            self._on_profile_line_defined(start_coords, end_coords)
        except (ValueError, IndexError): QMessageBox.warning(self, "输入无效", "请输入格式为 'x, y' 的两个数值。")

    def _on_timeseries_point_picked(self, coords):
        self.ui.pick_timeseries_btn.setChecked(False)
        if self.timeseries_dialog and self.timeseries_dialog.isVisible(): self.timeseries_dialog.close()
        filter_clause = self.data_manager.global_filter_clause if self.ui.filter_enabled_checkbox.isChecked() else ""
        self.timeseries_dialog = TimeSeriesDialog(coords, self.data_manager, filter_clause, self.output_dir, self)
        self.timeseries_dialog.show()

    def _on_profile_line_defined(self, start_point, end_point):
        self.ui.draw_profile_btn.setChecked(False)
        if not self.ui.plot_widget.interpolated_results: QMessageBox.warning(self, "无数据", "无可用于剖面的插值数据。"); return
        if self.profile_dialog and self.profile_dialog.isVisible(): self.profile_dialog.close()
        available_data = {
            key.replace('_data', ''): self.config_handler.get_current_config().get(key.replace('_data',''),{}).get('formula', key.replace('_data',''))
            for key, data in self.ui.plot_widget.interpolated_results.items() if 'data' in key and isinstance(data, np.ndarray)
        }
        self.profile_dialog = ProfilePlotDialog(start_point, end_point, self.ui.plot_widget.interpolated_results, available_data, self.output_dir, self)
        self.profile_dialog.show()

    def _apply_visualization_settings(self):
        if self.data_manager.get_frame_count() == 0: return
        config = self.config_handler.get_current_config()
        self.ui.plot_widget.set_config(
            heatmap_config=config['heatmap'], contour_config=config['contour'],
            vector_config=config['vector'], analysis=config['analysis'],
            x_axis_formula=config['axes']['x_formula'], y_axis_formula=config['axes']['y_formula'],
            chart_title=config['axes']['title'], aspect_ratio_config=config['axes']['aspect_config'],
            grid_resolution=(config['export']['video_grid_w'], config['export']['video_grid_h']), use_gpu=config['performance']['gpu']
        )
        is_time_avg = config['analysis']['time_average']['enabled']
        if is_time_avg:
            start, end = config['analysis']['time_average']['start_frame'], config['analysis']['time_average']['end_frame']
            if start >= end: self.ui.status_bar.showMessage("时间平均范围无效：起始帧必须小于结束帧。", 3000); return
            data = self.data_manager.get_time_averaged_data(start, end)
            self.ui.plot_widget.update_data(data); self._update_frame_info(is_time_avg=True, start=start, end=end)
        else:
            self._load_frame(self.current_frame_index)
        self.ui.status_bar.showMessage("可视化设置已更新。", 2000)

    def _load_frame(self, frame_index: int):
        if not (0 <= frame_index < self.data_manager.get_frame_count()): return
        data = self.data_manager.get_frame_data(frame_index)
        if data is not None:
            self.current_frame_index = frame_index
            self.ui.time_slider.blockSignals(True); self.ui.time_slider.setValue(frame_index); self.ui.time_slider.blockSignals(False)
            self.ui.plot_widget.update_data(data)
            self._update_frame_info()
            if self.ui.plot_widget.last_mouse_coords: self.ui.plot_widget.get_probe_data_at_coords(*self.ui.plot_widget.last_mouse_coords)

    def _update_frame_info(self, is_time_avg: bool = False, start: int = 0, end: int = 0):
        if is_time_avg:
            self.ui.frame_info_label.setText(f"时间平均: 帧 {start}-{end}"); self.ui.timestamp_label.setText("")
        else:
            fc = self.data_manager.get_frame_count()
            self.ui.frame_info_label.setText(f"帧: {self.current_frame_index + 1}/{fc if fc > 0 else '?'}")
            info = self.data_manager.get_frame_info(self.current_frame_index)
            if info and 'timestamp' in info:
                ts_val = info.get('timestamp', 'N/A')
                ts_str = f"{ts_val:.4f}" if isinstance(ts_val, (float, int)) else str(ts_val)
                self.ui.timestamp_label.setText(f"时间({self.data_manager.time_variable}): {ts_str}")
        self.ui.cache_label.setText(f"缓存: {self.data_manager.get_cache_info()['size']}/{self.data_manager.get_cache_info()['max_size']}")

    def _on_error(self, message: str):
        if self.import_progress_dialog and self.import_progress_dialog.isVisible(): self.import_progress_dialog.accept()
        self.ui.status_bar.showMessage(f"错误: {message}", 5000); QMessageBox.critical(self, "发生错误", message)

    def _on_mouse_moved(self, x, y): self.ui.probe_coord_label.setText(f"({x:.3e}, {y:.3e})")
    
    def _on_probe_data(self, data):
        self._update_main_probe_display(data)
        self._update_floating_probe_display(data)

    def _update_main_probe_display(self, data):
        # Preserve scroll position
        scrollbar = self.ui.probe_text.verticalScrollBar()
        scroll_position = scrollbar.value()

        lines = []
        if data.get('variables'):
            lines.extend([f"{'--- 最近原始数据点 ---':^40}"] + [f"{k:<18s} {v:12.6e}" if isinstance(v, (int, float)) else f"{k:<18s} {v}" for k, v in data['variables'].items()] + [""])
        if data.get('interpolated'):
            config = self.config_handler.get_current_config()
            lines.append(f"{'--- 鼠标位置插值数据 ---':^40}")
            lines.append(f"{f'X坐标 ({config['axes'].get('x_formula', 'x')}):':<25s} {data.get('x'):12.6e}")
            lines.append(f"{f'Y坐标 ({config['axes'].get('y_formula', 'y')}):':<25s} {data.get('y'):12.6e}")
            probe_map = {'heatmap': f"热力图 ({config['heatmap'].get('formula', 'N/A')})", 'contour': f"等高线 ({config['contour'].get('formula', 'N/A')})", 'vector_u': f"U分量 ({config['vector'].get('u_formula', 'N/A')})", 'vector_v': f"V分量 ({config['vector'].get('v_formula', 'N/A')})"}
            for key, value in data['interpolated'].items():
                if key in probe_map:
                    val_str = f"{value:12.6e}" if isinstance(value, (int,float)) and not np.isnan(value) else 'N/A'
                    lines.append(f"{probe_map[key]:<25s} {val_str}")
        self.ui.probe_text.setPlainText("\n".join(lines))
        scrollbar.setValue(scroll_position)

    def _update_floating_probe_display(self, data):
        checked_items = [self.ui.floating_probe_vars_list.item(i) for i in range(self.ui.floating_probe_vars_list.count()) if self.ui.floating_probe_vars_list.item(i).checkState() == Qt.CheckState.Checked]
        
        if not checked_items:
            QToolTip.hideText()
            return

        probe_html_lines = ["<div style='background-color: #ffffdd; border: 1px solid black; padding: 4px; font-family: Monospace; font-size: 9pt;'>"]
        
        raw_vars = data.get('variables', {})
        interp_vars = data.get('interpolated', {})

        for item in checked_items:
            var_name = item.text()
            value = raw_vars.get(var_name, 'N/A')
            
            # Special handling for interpolated fields if raw doesn't exist (e.g., curl, div)
            if value == 'N/A':
                 # Check common interpolated names
                 if var_name in interp_vars: value = interp_vars[var_name]
                 elif f"{var_name}_data" in self.ui.plot_widget.interpolated_results:
                     val = interp_vars.get(var_name)
                     if val is not None: value = val
            
            val_str = f"{value:.4e}" if isinstance(value, (int, float)) and not np.isnan(value) else str(value)
            probe_html_lines.append(f"<b>{var_name:<15}</b>: {val_str}")

        probe_html_lines.append("</div>")
        
        if len(probe_html_lines) > 2: # Has at least one variable
             QToolTip.showText(QCursor.pos(), "<br>".join(probe_html_lines), self.ui.plot_widget)
        else:
             QToolTip.hideText()


    def _on_value_picked(self, mode, value):
        target = self.ui.heatmap_vmin if mode == PickerMode.VMIN else self.ui.heatmap_vmax
        target.setText(f"{value:.4e}"); self._trigger_auto_apply()

    def _on_plot_rendered(self):
        if self.playback_handler.is_playing: self.playback_handler.play_timer.start()
        if self._should_reset_view_after_refresh: self.ui.plot_widget.reset_view(); self._should_reset_view_after_refresh = False
        if self.ui.plot_widget.picker_mode == PickerMode.PROFILE_END: self.ui.status_bar.showMessage("剖面图模式: 点击定义剖面线终点 (右键取消)。", 0)

    def _on_interpolation_error(self, message: str):
        QMessageBox.critical(self, "可视化错误", f"无法渲染图形，公式可能存在问题。\n\n错误详情:\n{message}"); self.ui.status_bar.showMessage(f"渲染错误: {message}", 5000)

    def _on_gpu_toggle(self, is_on): self.ui.plot_widget.set_config(use_gpu=is_on); self._update_gpu_status_label(); self._trigger_auto_apply()
    def _on_vector_plot_type_changed(self):
        is_q = self.ui.vector_plot_type.currentData(Qt.ItemDataRole.UserRole) == self.config_handler.VectorPlotType.QUIVER
        self.ui.quiver_options_group.setVisible(is_q); self.ui.streamline_options_group.setVisible(not is_q); self._trigger_auto_apply()

    def _force_refresh_plot(self, reset_view=False): self._should_reset_view_after_refresh = reset_view; self._apply_visualization_settings()
    
    def _show_help(self, help_type: str):
        content_map = {
            "formula": get_formula_help_html(self.data_manager.get_variables(), self.formula_engine.custom_global_variables, self.formula_engine.science_constants),
            "axis_title": get_axis_title_help_html(),
            "data_processing": get_data_processing_help_html(),
            "analysis": get_analysis_help_html(), "template": get_template_help_html(), "theme": get_theme_help_html(),
        }
        content = content_map.get(help_type)
        if content: HelpDialog(content, self).exec()

    def _show_about(self): QMessageBox.about(self, "关于 InterVis", "<h2>InterVis v3.3-ProFinal</h2><p>作者: StarsWhere</p><p>一个使用PyQt6和Matplotlib构建的交互式数据可视化工具。</p><p><b>v3.3 功能重构:</b></p><ul><li><b>统一数据处理:</b> 将“逐帧计算”和“全局统计”合并为统一的“数据处理”选项卡，流程更清晰。</li><li><b>动态时间轴:</b> 不再依赖文件名排序，用户可从数据中任选数值列作为时间演化依据。</li><li><b>帮助系统完善:</b> 为所有计算功能提供了统一且详细的帮助文档。</li><li>保留并优化了原有功能，如一键导出、多变量剖面图、并行批量导出、可视化模板与主题等。</li></ul>")
    def _force_reload_data(self):
        reply = QMessageBox.question(self, "确认重新导入", "这将删除现有数据库并从CSV文件重新导入所有数据。此操作不可撤销。\n\n是否继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Yes:
            self.playback_handler.stop_playback(); self.stats_handler.reset_global_stats()
            try: os.remove(self.data_manager.db_path)
            except Exception as e: self._on_error(f"删除旧数据库失败: {e}"); return
            self._initialize_project()

    def _change_project_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择项目目录 (包含CSV文件)", self.project_dir)
        if new_dir and new_dir != self.project_dir:
            self.project_dir = new_dir; self.ui.data_dir_line_edit.setText(self.project_dir)
            self.playback_handler.stop_playback()
            self.stats_handler.reset_global_stats(); self.data_manager.clear_all()
            self._initialize_project()
            
    def _toggle_control_panel(self, checked): self.ui.control_panel.setVisible(checked)
    def _toggle_full_screen(self, checked): self.showFullScreen() if checked else self.showNormal()
    def _apply_cache_settings(self): self.data_manager.set_cache_size(self.ui.cache_size_spinbox.value()); self._update_frame_info()

    def _load_settings(self):
        self.restoreGeometry(self.settings.value("geometry", self.saveGeometry()))
        self.restoreState(self.settings.value("windowState", self.saveState()))
        self.ui.control_panel.setVisible(self.settings.value("panel_visible", True, type=bool)); self.ui.toggle_panel_action.setChecked(self.ui.control_panel.isVisible())
        self.ui.output_dir_line_edit.setText(self.output_dir); self._update_gpu_status_label()

    def _save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry()); self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("project_directory", self.project_dir); self.settings.setValue("output_directory", self.output_dir)
        self.settings.setValue("panel_visible", self.ui.control_panel.isVisible())
        if self.config_handler.current_config_file: self.settings.setValue("last_config_file", self.config_handler.current_config_file)
        self.settings.setValue("last_time_variable", self.data_manager.time_variable)

    def closeEvent(self, event):
        if not self.export_handler.on_main_window_close(): event.ignore(); return
        if self.config_handler.config_is_dirty:
            reply = QMessageBox.question(self, '未保存的修改', "退出前是否保存当前修改？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self.config_handler.save_current_config()
            elif reply == QMessageBox.StandardButton.Cancel: event.ignore(); return
        self._save_settings(); self.playback_handler.stop_playback()
        if self.ui.plot_widget.thread_pool: self.ui.plot_widget.thread_pool.clear(); self.ui.plot_widget.thread_pool.waitForDone()
        if self.timeseries_dialog: self.timeseries_dialog.close()
        if self.profile_dialog: self.profile_dialog.close()
        super().closeEvent(event)

    def _update_gpu_status_label(self):
        status, color = ("GPU: 启用", "green") if self.ui.gpu_checkbox.isChecked() and is_gpu_available() else (("GPU: 可用", "orange") if is_gpu_available() else ("GPU: 不可用", "red"))
        self.ui.gpu_status_label.setText(status); self.ui.gpu_status_label.setStyleSheet(f"color: {color};")

    def _show_variable_menu(self, line_edit: QLineEdit, position: QPoint):
        menu = QMenu(self); insert_text = lambda text: line_edit.insert(f" {text} ")
        var_menu = menu.addMenu("数据变量"); [var_menu.addAction(var).triggered.connect(lambda c, v=var: insert_text(v)) for var in sorted(self.data_manager.get_variables())]
        if self.formula_engine.custom_global_variables:
            global_menu = menu.addMenu("全局常量"); [global_menu.addAction(g).triggered.connect(lambda c, v=g: insert_text(v)) for g in sorted(self.formula_engine.custom_global_variables.keys())]
        if self.formula_engine.science_constants:
            const_menu = menu.addMenu("科学常数"); [const_menu.addAction(c).triggered.connect(lambda ch, v=c: insert_text(v)) for c in sorted(self.formula_engine.science_constants.keys())]
        if not menu.actions(): menu.addAction("无可用变量").setEnabled(False)
        menu.exec(position)