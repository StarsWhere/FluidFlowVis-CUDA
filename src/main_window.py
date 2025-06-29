#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
from typing import Dict, Any, Optional, List
import numpy as np
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QFileDialog, QLineEdit, QMenu
from PyQt6.QtCore import Qt, QSettings, QPoint, QTimer
from PyQt6.QtGui import QAction

from src.core.data_manager import DataManager
from src.core.formula_engine import FormulaEngine
from src.core.constants import VectorPlotType, PickerMode
from src.utils.help_dialog import HelpDialog
from src.utils.gpu_utils import is_gpu_available
from src.utils.help_content import get_formula_help_html, get_axis_title_help_html
from src.ui.ui_setup import UiMainWindow
from src.ui.dialogs import StatsProgressDialog
from src.core.workers import DataScanWorker

from src.handlers.config_handler import ConfigHandler
from src.handlers.stats_handler import StatsHandler
from src.handlers.export_handler import ExportHandler
from src.handlers.playback_handler import PlaybackHandler

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
        
        self.settings = QSettings("StarsWhere", "InterVis")
        self.data_manager = DataManager()
        self.formula_engine = FormulaEngine()
        self.ui = UiMainWindow()

        self.current_frame_index: int = 0
        self._should_reset_view_after_refresh: bool = False
        
        self.data_dir = self.settings.value("data_directory", os.path.join(os.getcwd(), "data"))
        self.output_dir = self.settings.value("output_directory", os.path.join(os.getcwd(), "output"))
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.redraw_debounce_timer = QTimer(self)
        self.redraw_debounce_timer.setSingleShot(True)
        self.redraw_debounce_timer.setInterval(150)
        
        self.scan_worker: Optional[DataScanWorker] = None
        self.scan_progress_dialog: Optional[StatsProgressDialog] = None

        self.config_handler = ConfigHandler(self, self.ui, self.data_manager)
        self.stats_handler = StatsHandler(self, self.ui, self.data_manager, self.formula_engine)
        self.export_handler = ExportHandler(self, self.ui, self.data_manager, self.config_handler)
        self.playback_handler = PlaybackHandler(self, self.ui, self.data_manager)
        
        self._init_ui()
        self._connect_signals()
        self._load_settings()
        self._initialize_data()

    def _init_ui(self):
        self.ui.setup_ui(self, self.formula_engine)
        self.ui.gpu_checkbox.setEnabled(is_gpu_available())
        self.ui.data_dir_line_edit.setText(self.data_dir)
        self.ui.output_dir_line_edit.setText(self.output_dir)
        
        if not VIDEO_EXPORT_AVAILABLE:
            tooltip_msg = "功能不可用：请安装 moviepy 或 imageio (e.g., pip install moviepy)"
            self.ui.export_vid_btn.setEnabled(False)
            self.ui.export_vid_btn.setToolTip(tooltip_msg)
            self.ui.batch_export_btn.setEnabled(False)
            self.ui.batch_export_btn.setToolTip(tooltip_msg)
            logger.warning("视频导出功能不可用，因为 moviepy 和 imageio 均未安装。")

        self._update_gpu_status_label()
        self._on_vector_plot_type_changed()

    def _connect_signals(self):
        self.data_manager.error_occurred.connect(self._on_error)
        self.redraw_debounce_timer.timeout.connect(self._apply_visualization_settings)
        
        self.ui.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        self.ui.plot_widget.probe_data_ready.connect(self._on_probe_data)
        self.ui.plot_widget.value_picked.connect(self._on_value_picked)
        self.ui.plot_widget.plot_rendered.connect(self._on_plot_rendered)
        self.ui.plot_widget.interpolation_error.connect(self._on_interpolation_error)
        
        self.ui.open_data_dir_action.triggered.connect(self._change_data_directory)
        self.ui.reload_action.triggered.connect(self._reload_data)
        self.ui.exit_action.triggered.connect(self.close)
        self.ui.reset_view_action.triggered.connect(self.ui.plot_widget.reset_view)
        self.ui.toggle_panel_action.triggered.connect(self._toggle_control_panel)
        self.ui.full_screen_action.triggered.connect(self._toggle_full_screen)
        self.ui.formula_help_action.triggered.connect(self._show_formula_help)
        self.ui.about_action.triggered.connect(self._show_about)

        self.ui.change_data_dir_btn.clicked.connect(self._change_data_directory)
        self.ui.refresh_button.clicked.connect(self._force_refresh_plot)
        self.ui.apply_cache_btn.clicked.connect(self._apply_cache_settings)
        self.ui.gpu_checkbox.toggled.connect(self._on_gpu_toggle)
        self.ui.vector_plot_type.currentIndexChanged.connect(self._on_vector_plot_type_changed)

        self.config_handler.connect_signals()
        self.stats_handler.connect_signals()
        self.export_handler.connect_signals()
        self.playback_handler.connect_signals()

        widgets_to_connect_for_redraw = [
            self.ui.heatmap_enabled, self.ui.heatmap_colormap, self.ui.contour_labels,
            self.ui.contour_levels, self.ui.contour_linewidth, self.ui.contour_colors,
            self.ui.vector_enabled, self.ui.vector_plot_type, self.ui.quiver_density_spinbox,
            self.ui.quiver_scale_spinbox, self.ui.stream_density_spinbox,
            self.ui.stream_linewidth_spinbox, self.ui.stream_color_combo,
            self.ui.chart_title_edit, self.ui.x_axis_formula, self.ui.y_axis_formula, 
            self.ui.heatmap_formula, self.ui.heatmap_vmin, self.ui.heatmap_vmax, 
            self.ui.contour_formula, self.ui.vector_u_formula, self.ui.vector_v_formula
        ]
        for widget in widgets_to_connect_for_redraw:
            if hasattr(widget, 'toggled'): widget.toggled.connect(self._trigger_auto_apply)
            elif hasattr(widget, 'currentIndexChanged'): widget.currentIndexChanged.connect(self._trigger_auto_apply)
            elif hasattr(widget, 'valueChanged'): widget.valueChanged.connect(self._trigger_auto_apply)
            elif hasattr(widget, 'editingFinished'): widget.editingFinished.connect(self._trigger_auto_apply)

    def _trigger_auto_apply(self, *args):
        if self.config_handler._is_loading_config: return
        if self.data_manager.get_frame_count() > 0:
            self._should_reset_view_after_refresh = False
            self.redraw_debounce_timer.start()
        self.config_handler.mark_config_as_dirty()

    def _on_scan_finished(self, file_index: List[Dict], variables: List[str]):
        if self.scan_progress_dialog: self.scan_progress_dialog.accept()
        
        self.data_manager.post_scan_setup(file_index, variables)
        
        frame_count = self.data_manager.get_frame_count()
        if frame_count > 0:
            msg = f"成功索引 {frame_count} 帧数据"
            self.ui.status_bar.showMessage(msg, 5000)
            
            self.formula_engine.update_allowed_variables(self.data_manager.get_variables())
            self.ui.time_slider.setMaximum(frame_count - 1)
            self.ui.video_start_frame.setMaximum(frame_count - 1)
            self.ui.video_end_frame.setMaximum(frame_count - 1)
            self.ui.video_end_frame.setValue(frame_count - 1)
            self.config_handler.populate_config_combobox()
            self.ui.calc_basic_stats_btn.setEnabled(True)
            self._force_refresh_plot(reset_view=True)
        else:
            msg = "数据初始化失败：目录中未找到有效的CSV文件。"
            self.ui.status_bar.showMessage(msg, 5000)
            QMessageBox.warning(self, "数据为空", msg)
            self.ui.calc_basic_stats_btn.setEnabled(False)

    def _on_interpolation_error(self, message: str):
        QMessageBox.critical(self, "可视化错误", f"无法渲染图形，公式可能存在问题。\n\n错误详情:\n{message}")

    def _on_error(self, message: str):
        if self.scan_progress_dialog and self.scan_progress_dialog.isVisible(): self.scan_progress_dialog.accept()
        self.ui.status_bar.showMessage(f"错误: {message}", 5000)
        QMessageBox.critical(self, "发生错误", message)

    def _on_mouse_moved(self, x: float, y: float):
        self.ui.probe_coord_label.setText(f"({x:.3e}, {y:.3e})")

    def _on_probe_data(self, probe_data: dict):
        try:
            lines = []
            
            if probe_data.get('variables'):
                lines.append(f"{'--- 最近原始数据点 ---':^30}")
                lines.extend([f"{k:<16s} {v:12.6e}" for k, v in probe_data['variables'].items()])
                lines.append("")

            if probe_data.get('interpolated'):
                lines.append(f"{'--- 鼠标位置插值数据 ---':^30}")
                lines.extend([f"{k:<16s} {v:12.6e}" if isinstance(v, (int,float)) and not np.isnan(v) else f"{k:<16s} {'N/A'}" for k, v in probe_data['interpolated'].items()])
                lines.append("")

            if probe_data.get('evaluated_formulas'):
                lines.append(f"{'--- 公式求值 (在最近点) ---':^30}")
                for name, value in probe_data['evaluated_formulas'].items():
                    line = f"{name:<16s} {value:12.6e}" if isinstance(value, (int, float)) and not np.isnan(value) else f"{name:<16s} {value}"
                    lines.append(line)

            self.ui.probe_text.setPlainText("\n".join(lines))
        except Exception as e:
            logger.debug(f"更新探针数据显示失败: {e}")

    def _on_value_picked(self, mode: PickerMode, value: float):
        target_widget = self.ui.heatmap_vmin if mode == PickerMode.VMIN else self.ui.heatmap_vmax
        target_widget.setText(f"{value:.4e}")
        self._trigger_auto_apply()

    def _on_plot_rendered(self):
        if self.playback_handler.is_playing:
            self.playback_handler.play_timer.start()
        
        if self._should_reset_view_after_refresh:
            self.ui.plot_widget.reset_view()
            self._should_reset_view_after_refresh = False
            logger.info("图表视图已重置。")

    def _on_gpu_toggle(self, is_on):
        self.ui.plot_widget.set_config(use_gpu=is_on)
        self._update_gpu_status_label()
        self._trigger_auto_apply()

    def _on_vector_plot_type_changed(self, *args):
        selected_enum = self.ui.vector_plot_type.currentData(Qt.ItemDataRole.UserRole)
        is_quiver = selected_enum == VectorPlotType.QUIVER
        self.ui.quiver_options_group.setVisible(is_quiver)
        self.ui.streamline_options_group.setVisible(not is_quiver)
        self._trigger_auto_apply()
    
    def _initialize_data(self):
        if not self.data_manager.setup_directory(self.data_dir): return
        
        self.scan_progress_dialog = StatsProgressDialog(self, "正在扫描数据文件...")
        self.scan_worker = DataScanWorker(self.data_dir)
        self.scan_worker.progress.connect(self.scan_progress_dialog.update_progress)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_error)
        self.scan_worker.start()
        self.scan_progress_dialog.exec()

    def _load_frame(self, frame_index: int):
        if not (0 <= frame_index < self.data_manager.get_frame_count()): return
        data = self.data_manager.get_frame_data(frame_index)
        if data is not None:
            self.current_frame_index = frame_index
            self.ui.plot_widget.update_data(data)
            self._update_frame_info()
            if self.ui.plot_widget.last_mouse_coords:
                x, y = self.ui.plot_widget.last_mouse_coords
                self.ui.plot_widget.get_probe_data_at_coords(x, y)

    def _update_frame_info(self):
        fc = self.data_manager.get_frame_count()
        self.ui.frame_info_label.setText(f"帧: {self.current_frame_index + 1}/{fc}")
        info = self.data_manager.get_frame_info(self.current_frame_index)
        if info: self.ui.timestamp_label.setText(f"时间戳: {info.get('timestamp', 'N/A')}")
        cache = self.data_manager.get_cache_info()
        self.ui.cache_label.setText(f"缓存: {cache['size']}/{cache['max_size']}")

    def _force_refresh_plot(self, reset_view=False):
        self._should_reset_view_after_refresh = reset_view
        self._apply_visualization_settings()
        logger.info("图表已手动刷新。")

    def _apply_visualization_settings(self):
        if self.data_manager.get_frame_count() == 0: return

        # 定义检查函数
        def check_formula(widget: QLineEdit, name: str) -> bool:
            formula = widget.text().strip()
            # 对于可选的公式（热力图、等高线、矢量），只有在启用时才强制要求非空
            is_enabled = True
            if widget in [self.ui.heatmap_formula, self.ui.contour_formula, self.ui.vector_u_formula, self.ui.vector_v_formula]:
                group_box = widget.parent().parent() # 获取对应的 GroupBox
                if hasattr(group_box, 'isChecked'):
                    is_enabled = group_box.isChecked()

            if is_enabled and formula and not self.formula_engine.validate(formula):
                widget.clear() # 清除错误内容
                QMessageBox.warning(self, "公式错误", f"{name}公式无效: '{formula}'\n\n该公式已被清除，请重新输入。")
                return False
            return True

        # 按顺序验证所有公式
        if not all([
            check_formula(self.ui.x_axis_formula, "X轴"),
            check_formula(self.ui.y_axis_formula, "Y轴"),
            check_formula(self.ui.heatmap_formula, "热力图"),
            check_formula(self.ui.contour_formula, "等高线"),
            check_formula(self.ui.vector_u_formula, "矢量U"),
            check_formula(self.ui.vector_v_formula, "矢量V"),
        ]):
            return # 如果任何验证失败，则停止应用

        # 所有验证通过后，获取配置并应用
        config = self.config_handler.get_current_config()
        
        config_changed = self.ui.plot_widget.set_config(
            heatmap_config=config['heatmap'], contour_config=config['contour'],
            vector_config=config['vector'], x_axis_formula=config['axes']['x_formula'] or 'x',
            y_axis_formula=config['axes']['y_formula'] or 'y', chart_title=config['axes']['title']
        )
        
        self._load_frame(self.current_frame_index)
        self.ui.status_bar.showMessage("可视化设置已更新", 2000)

    def _show_formula_help(self, help_type: str = "formula"):
        if help_type == "axis_title":
            html_content = get_axis_title_help_html()
            title = "坐标轴与标题指南"
        else:
            html_content = get_formula_help_html(
                base_variables=self.data_manager.get_variables(),
                custom_global_variables=self.formula_engine.custom_global_variables,
                science_constants=self.formula_engine.science_constants
            )
            title = "公式语法说明"
        HelpDialog(html_content, self, window_title=title).exec()
        
    def _show_about(self): 
        QMessageBox.about(self, "关于 InterVis", 
                          "<h2>InterVis v1.7.3 (UX Refined)</h2>"
                          "<p>作者: StarsWhere</p>"
                          "<p>一个使用PyQt6和Matplotlib构建的交互式数据可视化工具。</p>"
                          "<p><b>v1.7.3 优化更新:</b></p>"
                          "<ul>"
                          "<li><b>UI/UX:</b> 简化'另存为'操作，优化变量插入和错误反馈逻辑。</li>"
                          "<li><b>鲁棒导出:</b> 视频导出功能现在会自动在 moviepy 和 imageio 之间降级。</li>"
                          "<li><b>性能:</b> 实现绘图增量更新与UI防抖，交互更流畅。</li>"
                          "<li><b>体验:</b> 异步加载数据，避免启动卡顿。</li>"
                          "</ul>")
    
    def _reload_data(self):
        if self.playback_handler.is_playing: self.playback_handler.toggle_play()
        self.stats_handler.reset_global_stats()
        self.data_manager.clear_all()
        self._initialize_data()

    def _change_data_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择数据目录", self.data_dir)
        if new_dir and new_dir != self.data_dir:
            self.data_dir = new_dir
            self.ui.data_dir_line_edit.setText(self.data_dir)
            self._reload_data()
            
    def _toggle_control_panel(self, checked):
        self.ui.control_panel.setVisible(checked)

    def _toggle_full_screen(self, checked):
        if checked: self.showFullScreen()
        else: self.showNormal()
            
    def _apply_cache_settings(self): 
        self.data_manager.set_cache_size(self.ui.cache_size_spinbox.value())
        self._update_frame_info()

    def _load_settings(self):
        self.restoreGeometry(self.settings.value("geometry", self.saveGeometry()))
        self.restoreState(self.settings.value("windowState", self.saveState()))
        panel_visible = self.settings.value("panel_visible", True, type=bool)
        self.ui.control_panel.setVisible(panel_visible)
        self.ui.toggle_panel_action.setChecked(panel_visible)
        self.export_handler.set_output_dir(self.output_dir)
        self._update_gpu_status_label()

    def _save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("data_directory", self.data_dir)
        self.settings.setValue("output_directory", self.export_handler.output_dir)
        self.settings.setValue("panel_visible", self.ui.control_panel.isVisible())
        if self.config_handler.current_config_file:
            self.settings.setValue("last_config_file", self.config_handler.current_config_file)

    def closeEvent(self, event):
        if not self.export_handler.on_main_window_close():
            event.ignore()
            return

        if self.config_handler.config_is_dirty:
            reply = QMessageBox.question(self, '未保存的修改', "退出前是否保存当前修改？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self.config_handler.save_current_config()
            elif reply == QMessageBox.StandardButton.Cancel: event.ignore(); return

        self._save_settings()
        self.playback_handler.stop_playback()
        if self.ui.plot_widget.thread_pool:
            self.ui.plot_widget.thread_pool.clear()
            self.ui.plot_widget.thread_pool.waitForDone()
        logger.info("应用程序正常关闭")
        super().closeEvent(event)

    def _update_gpu_status_label(self):
        if is_gpu_available():
            status, color = ("GPU: 启用", "green") if self.ui.gpu_checkbox.isChecked() else ("GPU: 可用", "orange")
        else:
            status, color = ("GPU: 不可用", "red")
        self.ui.gpu_status_label.setText(status)
        self.ui.gpu_status_label.setStyleSheet(f"color: {color};")

    def _show_variable_menu(self, line_edit: QLineEdit, position: QPoint):
        menu = QMenu(self)
        
        def insert_text(text_to_insert):
            # 改进的插入逻辑：如果输入框为空，直接设置文本；否则在光标处插入
            if not line_edit.text().strip():
                line_edit.setText(text_to_insert)
            else:
                line_edit.insert(f" {text_to_insert} ") # 在已有文本中插入时保留空格

        var_menu = menu.addMenu("数据变量")
        for var in sorted(self.data_manager.get_variables()):
            var_menu.addAction(var).triggered.connect(lambda checked=False, v=var: insert_text(v))
        
        if self.formula_engine.custom_global_variables:
            global_menu = menu.addMenu("全局常量")
            for g_var in sorted(self.formula_engine.custom_global_variables.keys()):
                global_menu.addAction(g_var).triggered.connect(lambda checked=False, v=g_var: insert_text(v))

        if self.formula_engine.science_constants:
            const_menu = menu.addMenu("科学常数")
            for const in sorted(self.formula_engine.science_constants.keys()):
                const_menu.addAction(const).triggered.connect(lambda checked=False, v=const: insert_text(v))
        
        if not menu.actions(): menu.addAction("无可用变量").setEnabled(False)
        menu.exec(position)