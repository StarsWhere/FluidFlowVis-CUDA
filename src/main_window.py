import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QMessageBox, QFileDialog, QInputDialog, QComboBox, 
    QCheckBox, QLineEdit, QMenu, QSpinBox, QDoubleSpinBox, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QPoint
from PyQt6.QtGui import QAction

from src.core.data_manager import DataManager
from src.core.formula_validator import FormulaValidator
from src.utils.help_dialog import HelpDialog
from src.utils.gpu_utils import is_gpu_available
from src.utils.help_content import get_formula_help_html, get_custom_stats_help_html, get_axis_title_help_html
from src.visualization.video_exporter import VideoExportDialog
from src.ui.ui_setup import UiMainWindow
from src.ui.dialogs import BatchExportDialog, StatsProgressDialog
from src.core.workers import BatchExportWorker, GlobalStatsWorker, CustomGlobalStatsWorker

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """
    应用程序的主窗口类，管理UI布局、用户交互和各个模块之间的协调。
    UI创建部分已移至 UiMainWindow 类。
    """
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("StarsWhere", "InterVis")
        self.data_manager = DataManager()
        self.formula_validator = FormulaValidator()
        self.ui = UiMainWindow()

        # --- 状态变量 ---
        self.current_frame_index: int = 0
        self.is_playing: bool = False
        self.frame_skip_step: int = 1 
        self.skipped_frames: int = 0
        self.config_is_dirty: bool = False
        self._is_loading_config: bool = False
        self.current_config_file: Optional[str] = None
        self._loaded_config: Optional[Dict[str, Any]] = None 
        self.batch_export_dialog: Optional[BatchExportDialog] = None
        self.batch_export_worker: Optional[BatchExportWorker] = None
        
        # --- 路径管理 ---
        self.data_dir = self.settings.value("data_directory", os.path.join(os.getcwd(), "data"))
        self.output_dir = self.settings.value("output_directory", os.path.join(os.getcwd(), "output"))
        self.settings_dir = os.path.join(os.getcwd(), "settings")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_timer)
        
        # --- 初始化 ---
        self._init_ui()
        self._connect_signals()
        self._load_settings()
        self._initialize_data()

    # region 初始化
    def _init_ui(self):
        self.ui.setup_ui(self, self.formula_validator)
        self.ui.gpu_checkbox.setEnabled(is_gpu_available())
        self.ui.data_dir_line_edit.setText(self.data_dir)
        self.ui.output_dir_line_edit.setText(self.output_dir)
        self._update_gpu_status_label()
        self._on_vector_plot_type_changed() # 初始化矢量图选项可见性

    def _connect_signals(self):
        # Data & Plot signals
        self.data_manager.loading_finished.connect(self._on_loading_finished)
        self.data_manager.error_occurred.connect(self._on_error)
        self.ui.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        self.ui.plot_widget.probe_data_ready.connect(self._on_probe_data)
        self.ui.plot_widget.value_picked.connect(self._on_value_picked)
        self.ui.plot_widget.plot_rendered.connect(self._on_plot_rendered)
        self.ui.plot_widget.interpolation_error.connect(self._on_interpolation_error)
        
        # Menu actions
        self.ui.open_data_dir_action.triggered.connect(self._change_data_directory)
        self.ui.set_output_dir_action.triggered.connect(self._change_output_directory)
        self.ui.reload_action.triggered.connect(self._reload_data)
        self.ui.save_config_action.triggered.connect(self._save_current_config)
        self.ui.save_config_as_action.triggered.connect(self._save_config_as)
        self.ui.exit_action.triggered.connect(self.close)
        
        self.ui.reset_view_action.triggered.connect(self.ui.plot_widget.reset_view)
        self.ui.toggle_panel_action.triggered.connect(self._toggle_control_panel)
        self.ui.full_screen_action.triggered.connect(self._toggle_full_screen)
        
        self.ui.formula_help_action.triggered.connect(self._show_formula_help)
        self.ui.custom_stats_help_action.triggered.connect(self._show_custom_stats_help)
        self.ui.about_action.triggered.connect(self._show_about)

        # Playback controls
        self.ui.play_button.clicked.connect(self._toggle_play)
        self.ui.prev_btn.clicked.connect(self._prev_frame)
        self.ui.next_btn.clicked.connect(self._next_frame)
        self.ui.time_slider.valueChanged.connect(self._on_slider_changed)
        self.ui.frame_skip_spinbox.valueChanged.connect(self._on_frame_skip_changed)

        # Path controls
        self.ui.change_data_dir_btn.clicked.connect(self._change_data_directory)
        self.ui.change_output_dir_btn.clicked.connect(self._change_output_directory)

        # --- 统一的可视化设置信号连接 ---
        # 凡是修改后需要自动重绘和标记为“脏”的控件
        widgets_to_connect = [
            # Heatmap
            self.ui.heatmap_enabled, self.ui.heatmap_colormap, self.ui.contour_labels,
            self.ui.contour_levels, self.ui.contour_linewidth, self.ui.contour_colors,
            # Vector/Streamline
            self.ui.vector_enabled, self.ui.vector_plot_type, self.ui.quiver_density_spinbox,
            self.ui.quiver_scale_spinbox, self.ui.stream_density_spinbox,
            self.ui.stream_linewidth_spinbox, self.ui.stream_color_combo,
            # Formula line edits (editingFinished triggers update)
            self.ui.chart_title_edit, self.ui.x_axis_formula, self.ui.y_axis_formula, 
            self.ui.heatmap_formula, self.ui.heatmap_vmin, self.ui.heatmap_vmax, 
            self.ui.contour_formula, self.ui.vector_u_formula, self.ui.vector_v_formula
        ]

        for widget in widgets_to_connect:
            if isinstance(widget, (QCheckBox, QGroupBox)):
                widget.toggled.connect(self._trigger_auto_apply)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._trigger_auto_apply)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.valueChanged.connect(self._trigger_auto_apply)
            elif isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self._trigger_auto_apply)
        
        self.ui.vector_plot_type.currentIndexChanged.connect(self._on_vector_plot_type_changed)
        
        # Statistics tab controls
        self.ui.calc_basic_stats_btn.clicked.connect(self._start_global_stats_calculation)
        self.ui.calc_custom_stats_btn.clicked.connect(self._start_custom_stats_calculation)
        self.ui.export_stats_btn.clicked.connect(self._export_global_stats)

        # Export & Performance tab controls
        self.ui.export_img_btn.clicked.connect(self._export_image)
        self.ui.export_vid_btn.clicked.connect(self._export_video)
        self.ui.batch_export_btn.clicked.connect(self._start_batch_export)
        self.ui.apply_cache_btn.clicked.connect(self._apply_cache_settings)
        self.ui.gpu_checkbox.toggled.connect(self._on_gpu_toggle)
        self.ui.refresh_button.clicked.connect(self._force_refresh_plot)
        self.ui.plot_widget.plot_rendered.connect(self._on_plot_rendered)
        
        # Config management
        self.ui.config_combo.currentIndexChanged.connect(self._on_config_selected)
        self.ui.save_config_btn.clicked.connect(self._save_current_config)
        self.ui.save_config_as_btn.clicked.connect(self._save_config_as)
        self.ui.new_config_action.triggered.connect(self._create_new_config)

        # Connect settings that mark config as dirty but don't require redraw
        other_dirty_widgets = [
            self.ui.export_dpi, self.ui.video_fps, self.ui.video_start_frame, 
            self.ui.video_end_frame, self.ui.video_grid_w, self.ui.video_grid_h
        ]
        for widget in other_dirty_widgets:
             widget.valueChanged.connect(self._mark_config_as_dirty)

    def _trigger_auto_apply(self, *args):
        if self._is_loading_config: return
        if self.data_manager.get_frame_count() > 0:
            self._apply_visualization_settings()
        self._mark_config_as_dirty()
    # endregion

    # region 信号槽实现
    def _on_loading_finished(self, success: bool, message: str):
        self.ui.status_bar.showMessage(message, 5000)
        if success:
            frame_count = self.data_manager.get_frame_count()
            if frame_count > 0:
                self.formula_validator.update_allowed_variables(self.data_manager.get_variables())
                self.ui.time_slider.setMaximum(frame_count - 1)
                self.ui.video_start_frame.setMaximum(frame_count - 1)
                self.ui.video_end_frame.setMaximum(frame_count - 1)
                self.ui.video_end_frame.setValue(frame_count - 1)
                self._populate_config_combobox()
                self.ui.calc_basic_stats_btn.setEnabled(True)
            else:
                QMessageBox.warning(self, "数据为空", "指定的数据目录中没有找到有效的CSV文件。")
                self.ui.calc_basic_stats_btn.setEnabled(False)
        else:
            QMessageBox.critical(self, "错误", f"无法初始化数据管理器: {message}")
            self.ui.calc_basic_stats_btn.setEnabled(False)

    def _on_interpolation_error(self, message: str):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("可视化错误")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(f"无法渲染图形，公式可能存在问题。<br><br><b>错误详情:</b><br>{message}")
        
        # 尝试智能地清除可能有问题的公式
        def clear_if_invalid(widget):
            if widget.text() and not self.formula_validator.validate(widget.text()):
                widget.clear()

        if "X轴" in message: clear_if_invalid(self.ui.x_axis_formula)
        if "Y轴" in message: clear_if_invalid(self.ui.y_axis_formula)
        clear_if_invalid(self.ui.heatmap_formula)
        clear_if_invalid(self.ui.contour_formula)
        clear_if_invalid(self.ui.vector_u_formula)
        clear_if_invalid(self.ui.vector_v_formula)
        msg_box.exec()

    def _on_error(self, message: str):
        self.ui.status_bar.showMessage(f"错误: {message}", 5000)
        QMessageBox.critical(self, "发生错误", message)

    def _on_mouse_moved(self, x: float, y: float):
        self.ui.probe_coord_label.setText(f"({x:.3e}, {y:.3e})")

    def _on_probe_data(self, probe_data: dict):
        try:
            lines = [f"{'变量名':<16s} {'数值'}", "---------------------------"]
            lines.extend([f"{k:<16s} {v:12.6e}" for k, v in probe_data['variables'].items()])
            self.ui.probe_text.setPlainText("\n".join(lines))
        except Exception as e:
            logger.debug(f"更新探针数据显示失败: {e}")

    def _on_value_picked(self, mode: str, value: float):
        target_widget = self.ui.heatmap_vmin if mode == 'vmin' else self.ui.heatmap_vmax
        target_widget.setText(f"{value:.4e}")
        self._trigger_auto_apply()

    def _on_plot_rendered(self):
        if self.is_playing:
            self.play_timer.start()

    def _toggle_play(self):
        self.is_playing = not self.is_playing
        self.ui.play_button.setText("暂停" if self.is_playing else "播放")
        if self.is_playing:
            self.play_timer.setSingleShot(True)
            self.play_timer.start(0)
            self.ui.status_bar.showMessage("播放中...")
            if self.ui.plot_widget.last_mouse_coords is None and self.ui.plot_widget.current_data is not None and not self.ui.plot_widget.current_data.empty:
                # 自动将探针定位到中心
                x_min, x_max = self.ui.plot_widget.ax.get_xlim()
                y_min, y_max = self.ui.plot_widget.ax.get_ylim()
                center_x, center_y = (x_min + x_max) / 2, (y_min + y_max) / 2
                self.ui.plot_widget.last_mouse_coords = (center_x, center_y)
                self.ui.plot_widget.get_probe_data_at_coords(center_x, center_y)
        else:
            self.play_timer.stop()
            self.ui.status_bar.showMessage("已暂停")

    def _on_play_timer(self):
        self.play_timer.stop()
        if self.ui.plot_widget.is_busy_interpolating:
            self.skipped_frames += 1
            self.ui.status_bar.showMessage(f"渲染延迟，跳过 {self.skipped_frames} 帧...", 1000)
            if self.is_playing: self.play_timer.start()
            return
        self.skipped_frames = 0
        next_frame = (self.current_frame_index + self.frame_skip_step) % self.data_manager.get_frame_count()
        self.ui.time_slider.setValue(next_frame)

    def _prev_frame(self):
        if self.current_frame_index > 0: self.ui.time_slider.setValue(self.current_frame_index - 1)
    
    def _next_frame(self):
        if self.data_manager.get_frame_count() > 0 and self.current_frame_index < self.data_manager.get_frame_count() - 1:
            self.ui.time_slider.setValue(self.current_frame_index + 1)
    
    def _on_slider_changed(self, value: int):
        if value != self.current_frame_index: self._load_frame(value)
    
    def _on_frame_skip_changed(self, value: int):
        self.frame_skip_step = value
        self.play_timer.setInterval(50)
        self._mark_config_as_dirty()

    def _on_gpu_toggle(self, is_on):
        self.ui.plot_widget.set_config(use_gpu=is_on)
        self._update_gpu_status_label()
        self._trigger_auto_apply()
        self._mark_config_as_dirty()

    def _on_plot_rendered(self):
        """图表渲染完成后调用，用于重置视图。"""
        # 仅在需要重置视图时执行，例如通过“立即刷新”按钮触发
        # 避免在每次渲染时都重置视图，影响用户操作
        if hasattr(self, '_should_reset_view_after_refresh') and self._should_reset_view_after_refresh:
            self.ui.plot_widget.reset_view()
            self._should_reset_view_after_refresh = False # 重置标志
            logger.info("图表视图已重置。")

    def _on_vector_plot_type_changed(self, *args):
        is_quiver = self.ui.vector_plot_type.currentText().startswith("矢量图")
        self.ui.quiver_options_group.setVisible(is_quiver)
        self.ui.streamline_options_group.setVisible(not is_quiver)
        self._trigger_auto_apply()
    # endregion
    
    # region 核心逻辑
    def _initialize_data(self):
        self.ui.status_bar.showMessage(f"扫描目录: {self.data_dir}...")
        self.data_manager.initialize(self.data_dir)

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
        if info: self.ui.timestamp_label.setText(f"时间戳: {info['timestamp']}")
        cache = self.data_manager.get_cache_info()
        self.ui.cache_label.setText(f"缓存: {cache['size']}/{cache['max_size']}")

    def _force_refresh_plot(self):
        """强制刷新当前图表，应用所有可视化设置。"""
        self._should_reset_view_after_refresh = True # 设置标志
        self._apply_visualization_settings()
        logger.info("图表已手动刷新。等待渲染完成后重置视图。")

    def _apply_visualization_settings(self):
        if self.data_manager.get_frame_count() == 0: return

        def check_formula(widget, name):
            formula = widget.text().strip()
            if formula and not self.formula_validator.validate(formula):
                widget.setStyleSheet("border: 1px solid red;")
                QMessageBox.warning(self, "公式错误", f"{name}公式无效: '{formula}'")
                return False, None
            widget.setStyleSheet("")
            return True, formula
        
        valid, chart_title = check_formula(self.ui.chart_title_edit, "图表标题")
        if not valid: return
        valid, x_formula = check_formula(self.ui.x_axis_formula, "X轴")
        if not valid: return
        valid, y_formula = check_formula(self.ui.y_axis_formula, "Y轴")
        if not valid: return
        valid, heat_formula = check_formula(self.ui.heatmap_formula, "热力图")
        if not valid: return
        valid, contour_formula = check_formula(self.ui.contour_formula, "等高线")
        if not valid: return
        valid, u_formula = check_formula(self.ui.vector_u_formula, "矢量U分量")
        if not valid: return
        valid, v_formula = check_formula(self.ui.vector_v_formula, "矢量V分量")
        if not valid: return
        
        try:
            vmin = float(self.ui.heatmap_vmin.text()) if self.ui.heatmap_vmin.text().strip() else None
            vmax = float(self.ui.heatmap_vmax.text()) if self.ui.heatmap_vmax.text().strip() else None
        except ValueError:
            vmin, vmax = None, None
            self.ui.heatmap_vmin.clear(); self.ui.heatmap_vmax.clear()

        heat_cfg = {'enabled': self.ui.heatmap_enabled.isChecked(), 'formula': heat_formula, 'colormap': self.ui.heatmap_colormap.currentText(), 'vmin': vmin, 'vmax': vmax}
            
        contour_cfg = {'enabled': self.ui.contour_enabled.isChecked(), 'formula': contour_formula, 'levels': self.ui.contour_levels.value(), 'colors': self.ui.contour_colors.currentText(), 'linewidths': self.ui.contour_linewidth.value(), 'show_labels': self.ui.contour_labels.isChecked()}

        vector_cfg = {
            'enabled': self.ui.vector_enabled.isChecked(),
            'type': "Quiver" if self.ui.vector_plot_type.currentText().startswith("矢量图") else "Streamline",
            'u_formula': u_formula,
            'v_formula': v_formula,
            'quiver_options': {'density': self.ui.quiver_density_spinbox.value(), 'scale': self.ui.quiver_scale_spinbox.value()},
            'streamline_options': {'density': self.ui.stream_density_spinbox.value(), 'linewidth': self.ui.stream_linewidth_spinbox.value(), 'color_by': self.ui.stream_color_combo.currentText()}
        }
        
        self.ui.plot_widget.set_config(
            heatmap_config=heat_cfg, contour_config=contour_cfg, vector_config=vector_cfg,
            x_axis_formula=x_formula or 'x', y_axis_formula=y_formula or 'y', # 默认值为'x'/'y'
            chart_title=chart_title
        )
        self._load_frame(self.current_frame_index)
        self.ui.status_bar.showMessage("可视化设置已更新", 2000)
        self._mark_config_as_dirty()
    # endregion

    # region 菜单与文件操作
    def _show_formula_help(self, help_type: str = "formula"):
        """显示公式或轴标题的帮助文档。"""
        if help_type == "axis_title":
            html_content = get_axis_title_help_html()
            title = "坐标轴与标题指南"
        else: # "formula"
            html_content = get_formula_help_html(
                base_variables=self.data_manager.get_variables(),
                custom_global_variables=self.formula_validator.custom_global_variables,
                science_constants=self.formula_validator.science_constants
            )
            title = "公式语法说明"
        HelpDialog(html_content, self).exec()

    def _show_custom_stats_help(self):
        HelpDialog(get_custom_stats_help_html(), self).exec()
        
    def _show_about(self): 
        QMessageBox.about(self, "关于 InterVis", 
                          "<h2>InterVis v1.6</h2>"
                          "<p>作者: StarsWhere</p>"
                          "<p>一个使用PyQt6和Matplotlib构建的交互式数据可视化工具。</p>"
                          "<p><b>v1.6 更新:</b></p>"
                          "<ul>"
                          "<li>统一的公式输入，简化操作</li>"
                          "<li>动态图表标题与自定义支持</li>"
                          "<li>增强的菜单栏与工具栏</li>"
                          "<li>完善的帮助系统 (公式与自定义统计)</li>"
                          "<li>多项UI/UX细节优化和Bug修复</li>"
                          "</ul>")
    
    def _reload_data(self):
        if self.is_playing: self._toggle_play()
        self._reset_global_stats()
        self.data_manager.clear_all()
        self._initialize_data()

    def _change_data_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择数据目录", self.data_dir)
        if new_dir and new_dir != self.data_dir:
            self.data_dir = new_dir
            self.ui.data_dir_line_edit.setText(self.data_dir)
            self._reload_data()
            
    def _change_output_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir)
        if new_dir and new_dir != self.output_dir:
            self.output_dir = new_dir
            self.ui.output_dir_line_edit.setText(self.output_dir)

    def _toggle_control_panel(self, checked):
        self.ui.control_panel.setVisible(checked)

    def _toggle_full_screen(self, checked):
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()
            
    def _apply_cache_settings(self): 
        self.data_manager.set_cache_size(self.ui.cache_size_spinbox.value())
        self._update_frame_info()
        self._mark_config_as_dirty()

    def _export_image(self):
        fname = os.path.join(self.output_dir, f"frame_{self.current_frame_index:05d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        if self.ui.plot_widget.save_figure(fname, self.ui.export_dpi.value()):
            QMessageBox.information(self, "成功", f"图片已保存到:\n{fname}")
        else: QMessageBox.warning(self, "失败", "图片保存失败。")

    def _export_video(self):
        s_f, e_f = self.ui.video_start_frame.value(), self.ui.video_end_frame.value()
        if s_f >= e_f: QMessageBox.warning(self, "参数错误", "起始帧必须小于结束帧"); return
        fname = os.path.join(self.output_dir, f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        
        current_config = self._get_current_config()
        
        p_conf = {
            'x_axis_formula': current_config['axes']['x_formula'], 
            'y_axis_formula': current_config['axes']['y_formula'],
            'chart_title': current_config['axes']['title'],
            'use_gpu': self.ui.gpu_checkbox.isChecked(), 
            'heatmap_config': current_config['heatmap'], 'contour_config': current_config['contour'],
            'vector_config': current_config.get('vector', {}),
            'export_dpi': self.ui.export_dpi.value(),
            'grid_resolution': (self.ui.video_grid_w.value(), self.ui.video_grid_h.value()),
            'global_scope': self.data_manager.global_stats
        }
        VideoExportDialog(self, self.data_manager, p_conf, fname, s_f, e_f, self.ui.video_fps.value()).exec()
    # endregion
    
    # region 批量导出逻辑
    def _start_batch_export(self):
        if self.data_manager.get_frame_count() == 0:
            QMessageBox.warning(self, "无数据", "请先加载数据再执行批量导出。"); return
            
        config_files, _ = QFileDialog.getOpenFileNames(self, "选择要批量导出的配置文件", self.settings_dir, "JSON files (*.json)")
        if not config_files: return

        self.batch_export_dialog = BatchExportDialog(self)
        self.batch_export_worker = BatchExportWorker(config_files, self.data_manager, self.output_dir)
        self.batch_export_worker.progress.connect(self.batch_export_dialog.update_progress)
        self.batch_export_worker.log_message.connect(self.batch_export_dialog.add_log)
        self.batch_export_worker.finished.connect(self.batch_export_dialog.on_finish)
        self.batch_export_worker.finished.connect(self._on_batch_export_finished)
        self.batch_export_dialog.show()
        self.batch_export_worker.start()

    def _on_batch_export_finished(self, summary_message: str):
        if self.batch_export_dialog and self.batch_export_dialog.isVisible():
             QMessageBox.information(self, "批量导出完成", summary_message)
        else:
             self.ui.status_bar.showMessage(summary_message, 10000)
        self.batch_export_worker = None; self.batch_export_dialog = None
    # endregion

    # region 全局统计逻辑
    def _reset_global_stats(self):
        self.data_manager.clear_global_stats()
        self.formula_validator.update_custom_global_variables({})
        self.ui.stats_results_text.setText("数据已重载，请重新计算。")
        self.ui.export_stats_btn.setEnabled(False)
        self.ui.calc_custom_stats_btn.setEnabled(False)

    def _start_global_stats_calculation(self):
        if self.data_manager.get_frame_count() == 0: return
        self.stats_progress_dialog = StatsProgressDialog(self, "正在计算基础统计")
        self.stats_worker = GlobalStatsWorker(self.data_manager)
        self.stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.stats_worker.finished.connect(self._on_global_stats_finished)
        self.stats_worker.error.connect(self._on_global_stats_error)
        self.stats_worker.start()
        self.stats_progress_dialog.exec()

    def _on_global_stats_finished(self, results: Dict[str, float]):
        self.stats_progress_dialog.accept()
        if not results:
            self.ui.stats_results_text.setText("计算完成，无结果。")
            return

        self._update_stats_display()
        self.ui.export_stats_btn.setEnabled(True)
        self.ui.calc_custom_stats_btn.setEnabled(True)
        self.formula_validator.update_custom_global_variables(self.data_manager.global_stats)
        self._trigger_auto_apply()
        QMessageBox.information(self, "计算完成", "基础统计数据已计算并可用于公式中。")

    def _on_global_stats_error(self, error_msg: str):
        self.stats_progress_dialog.accept()
        QMessageBox.critical(self, "计算失败", f"计算基础统计时发生错误: \n{error_msg}")

    def _start_custom_stats_calculation(self):
        definitions_text = self.ui.custom_stats_input.toPlainText().strip()
        if not definitions_text: return
        definitions = [line.strip() for line in definitions_text.split('\n') if line.strip()]
        
        self.stats_progress_dialog = StatsProgressDialog(self, "正在计算自定义常量")
        self.custom_stats_worker = CustomGlobalStatsWorker(self.data_manager, definitions)
        self.custom_stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.custom_stats_worker.finished.connect(self._on_custom_stats_finished)
        self.custom_stats_worker.error.connect(self._on_custom_stats_error)
        self.custom_stats_worker.start()
        self.stats_progress_dialog.exec()

    def _on_custom_stats_finished(self, new_stats: Dict[str, float]):
        self.stats_progress_dialog.accept()
        if not new_stats:
            QMessageBox.warning(self, "计算完成", "未计算出任何新的自定义常量。"); return
        
        self._update_stats_display()
        self.formula_validator.update_custom_global_variables(self.data_manager.global_stats)
        self._trigger_auto_apply()
        QMessageBox.information(self, "计算完成", f"成功计算了 {len(new_stats)} 个自定义常量。")

    def _on_custom_stats_error(self, error_msg: str):
        self.stats_progress_dialog.accept()
        QMessageBox.critical(self, "计算失败", f"计算自定义常量时发生错误: \n{error_msg}")

    def _update_stats_display(self):
        all_stats = self.data_manager.global_stats
        if not all_stats:
            self.ui.stats_results_text.setText("无统计结果。"); return
        
        text = "\n".join([f"{k}: {v:.6e}" for k, v in all_stats.items()])
        self.ui.stats_results_text.setText(text)

    def _export_global_stats(self):
        if not self.data_manager.global_stats: return
        filepath, _ = QFileDialog.getSaveFileName(self, "导出统计结果", self.output_dir, "Text Files (*.txt)")
        if not filepath: return

        try:
            with open(filepath, 'w', encoding='utf-8') as f: f.write(self.ui.stats_results_text.toPlainText())
            QMessageBox.information(self, "导出成功", f"统计结果已保存到:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"无法保存文件: {e}")
    # endregion

    # region 设置管理逻辑
    def _mark_config_as_dirty(self, *args):
        if self._is_loading_config: return
        # 使用QTimer延迟检查，确保所有事件都处理完毕
        QTimer.singleShot(50, self._check_config_dirty_status)
    
    def _check_config_dirty_status(self):
        current_config = self._get_current_config()
        if self._loaded_config != current_config:
            self.config_is_dirty = True
            current_file = os.path.basename(self.current_config_file) if self.current_config_file else "新设置"
            self.ui.config_status_label.setText(f"{current_file} (未保存)")
            self.ui.config_status_label.setStyleSheet("color: orange;")
        else:
            self.config_is_dirty = False
            current_file = os.path.basename(self.current_config_file) if self.current_config_file else "新设置"
            self.ui.config_status_label.setText(f"{current_file} (已保存)")
            self.ui.config_status_label.setStyleSheet("color: green;")

    def _populate_config_combobox(self):
        self.ui.config_combo.blockSignals(True)
        current_selection = self.ui.config_combo.currentText()
        self.ui.config_combo.clear()
        
        default_config_path = os.path.join(self.settings_dir, "default.json")
        if not os.path.exists(default_config_path):
            with open(default_config_path, 'w', encoding='utf-8') as f:
                json.dump(self._get_current_config(), f, indent=4)

        config_files = sorted([f for f in os.listdir(self.settings_dir) if f.endswith('.json')])
        self.ui.config_combo.addItems(config_files)
        
        last_config = os.path.basename(self.settings.value("last_config_file", default_config_path))
        if last_config in config_files:
            self.ui.config_combo.setCurrentText(last_config)
        elif current_selection in config_files:
            self.ui.config_combo.setCurrentText(current_selection)

        self.ui.config_combo.blockSignals(False)
        self._load_config_by_name(self.ui.config_combo.currentText())

    def _on_config_selected(self, index: int):
        if index < 0: return # Ignore clear() signal
        if self.config_is_dirty:
            reply = QMessageBox.question(self, '未保存的修改', "切换前是否保存当前修改？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self._save_current_config()
            elif reply == QMessageBox.StandardButton.Cancel:
                self.ui.config_combo.blockSignals(True)
                if self.current_config_file:
                    self.ui.config_combo.setCurrentText(os.path.basename(self.current_config_file))
                self.ui.config_combo.blockSignals(False)
                return
        self._load_config_by_name(self.ui.config_combo.currentText())

    def _load_config_by_name(self, filename: str):
        if not filename: return
        filepath = os.path.join(self.settings_dir, filename)
        if not os.path.exists(filepath): 
            logger.warning(f"尝试加载但配置文件不存在: {filepath}")
            return
        
        self._is_loading_config = True
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self._apply_config(config)
            self.current_config_file = filepath
            self.settings.setValue("last_config_file", filepath)
            QTimer.singleShot(100, self._finalize_config_load)
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载或解析配置文件 '{filename}':\n{e}")
            self._is_loading_config = False

    def _finalize_config_load(self):
        self._loaded_config = self._get_current_config()
        self.config_is_dirty = False
        self._check_config_dirty_status() # 更新状态标签
        self.ui.status_bar.showMessage(f"已加载设置: {os.path.basename(self.current_config_file)}", 3000)
        self._is_loading_config = False
        self._trigger_auto_apply()

    def _save_current_config(self):
        if not self.current_config_file: 
            self._save_config_as()
            return
        
        try:
            with open(self.current_config_file, 'w', encoding='utf-8') as f:
                current_config = self._get_current_config()
                json.dump(current_config, f, indent=4)
            self._loaded_config = current_config
            self.config_is_dirty = False
            self._check_config_dirty_status()
            self.ui.status_bar.showMessage(f"设置已保存到 {os.path.basename(self.current_config_file)}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法写入配置文件 '{self.current_config_file}':\n{e}")

    def _save_config_as(self):
        filename, _ = QFileDialog.getSaveFileName(self, "设置另存为", self.settings_dir, "JSON Files (*.json)")
        if not filename:
            return
        
        self.current_config_file = filename
        self._save_current_config()
        
        # 更新下拉列表
        self.ui.config_combo.blockSignals(True)
        config_name = os.path.basename(filename)
        if self.ui.config_combo.findText(config_name) == -1:
            self.ui.config_combo.addItem(config_name)
        self.ui.config_combo.setCurrentText(config_name)
        self.ui.config_combo.blockSignals(False)
        self.settings.setValue("last_config_file", filename)


    def _create_new_config(self):
        text, ok = QInputDialog.getText(self, "新建设置", "请输入新配置文件的名称:")
        if ok and text:
            new_filename = f"{text}.json" if not text.endswith('.json') else text
            new_filepath = os.path.join(self.settings_dir, new_filename)
            if os.path.exists(new_filepath):
                if QMessageBox.question(self, "文件已存在", f"文件 '{new_filename}' 已存在。是否覆盖？") != QMessageBox.StandardButton.Yes: return

            self.current_config_file = new_filepath
            self._save_current_config() # 这会保存当前UI状态为新文件
            self._populate_config_combobox() # 重新填充以保证顺序和选中
            self.ui.config_combo.setCurrentText(new_filename)


    def _get_current_config(self) -> Dict[str, Any]:
        return {
            "version": "1.6",
            "axes": {
                "title": self.ui.chart_title_edit.text(),
                "x_formula": self.ui.x_axis_formula.text(), 
                "y_formula": self.ui.y_axis_formula.text()
            },
            "heatmap": {
                'enabled': self.ui.heatmap_enabled.isChecked(), 
                'formula': self.ui.heatmap_formula.text(), 
                'colormap': self.ui.heatmap_colormap.currentText(), 
                'vmin': self.ui.heatmap_vmin.text().strip() or None, 
                'vmax': self.ui.heatmap_vmax.text().strip() or None
            },
            "contour": {
                'enabled': self.ui.contour_enabled.isChecked(), 
                'formula': self.ui.contour_formula.text(), 
                'levels': self.ui.contour_levels.value(), 
                'colors': self.ui.contour_colors.currentText(), 
                'linewidths': self.ui.contour_linewidth.value(), 
                'show_labels': self.ui.contour_labels.isChecked()
            },
            "vector": {
                'enabled': self.ui.vector_enabled.isChecked(),
                'type': "Quiver" if self.ui.vector_plot_type.currentText().startswith("矢量图") else "Streamline",
                'u_formula': self.ui.vector_u_formula.text(),
                'v_formula': self.ui.vector_v_formula.text(),
                'quiver_options': {'density': self.ui.quiver_density_spinbox.value(), 'scale': self.ui.quiver_scale_spinbox.value()},
                'streamline_options': {'density': self.ui.stream_density_spinbox.value(), 'linewidth': self.ui.stream_linewidth_spinbox.value(), 'color_by': self.ui.stream_color_combo.currentText()}
            },
            "playback": {"frame_skip_step": self.ui.frame_skip_spinbox.value()},
            "export": {"dpi": self.ui.export_dpi.value(), "video_fps": self.ui.video_fps.value(), "video_start_frame": self.ui.video_start_frame.value(), "video_end_frame": self.ui.video_end_frame.value(), "video_grid_w": self.ui.video_grid_w.value(), "video_grid_h": self.ui.video_grid_h.value()},
            "performance": {"gpu": self.ui.gpu_checkbox.isChecked(), "cache": self.ui.cache_size_spinbox.value()}
        }
    
    def _apply_config(self, config: Dict[str, Any]):
        # Block signals on all relevant widgets to prevent premature updates
        all_widgets = self.ui.control_panel.findChildren(QWidget)
        for widget in all_widgets: widget.blockSignals(True)
        
        try:
            # Get sections with defaults
            axes = config.get("axes", {})
            heatmap = config.get("heatmap", {})
            contour = config.get("contour", {})
            vector = config.get("vector", {})
            playback = config.get("playback", {})
            export = config.get("export", {})
            perf = config.get("performance", {})
            
            # Axes and Title
            self.ui.chart_title_edit.setText(axes.get("title", ""))
            self.ui.x_axis_formula.setText(axes.get("x_formula", "x"))
            self.ui.y_axis_formula.setText(axes.get("y_formula", "y"))

            # Heatmap
            self.ui.heatmap_enabled.setChecked(heatmap.get("enabled", True))
            self.ui.heatmap_formula.setText(heatmap.get("formula", ""))
            self.ui.heatmap_colormap.setCurrentText(heatmap.get("colormap", "viridis"))
            self.ui.heatmap_vmin.setText(str(heatmap.get("vmin") or ""))
            self.ui.heatmap_vmax.setText(str(heatmap.get("vmax") or ""))
            
            # Contour
            self.ui.contour_enabled.setChecked(contour.get("enabled", False))
            self.ui.contour_formula.setText(contour.get("formula", ""))
            self.ui.contour_levels.setValue(contour.get("levels", 10))
            self.ui.contour_colors.setCurrentText(contour.get("colors", "black"))
            self.ui.contour_linewidth.setValue(contour.get("linewidths", 1.0))
            self.ui.contour_labels.setChecked(contour.get("show_labels", True))
            
            # Vector
            q_opts = vector.get('quiver_options', {})
            s_opts = vector.get('streamline_options', {})
            self.ui.vector_enabled.setChecked(vector.get("enabled", False))
            self.ui.vector_plot_type.setCurrentText("矢量图 (Quiver)" if vector.get("type") == "Quiver" else "流线图 (Streamline)")
            self.ui.vector_u_formula.setText(vector.get("u_formula", ""))
            self.ui.vector_v_formula.setText(vector.get("v_formula", ""))
            self.ui.quiver_density_spinbox.setValue(q_opts.get("density", 10))
            self.ui.quiver_scale_spinbox.setValue(q_opts.get("scale", 1.0))
            self.ui.stream_density_spinbox.setValue(s_opts.get("density", 1.5))
            self.ui.stream_linewidth_spinbox.setValue(s_opts.get("linewidth", 1.0))
            self.ui.stream_color_combo.setCurrentText(s_opts.get("color_by", "速度大小"))

            # Playback, Export, Performance
            self.ui.frame_skip_spinbox.setValue(playback.get("frame_skip_step", 1))
            self.ui.export_dpi.setValue(export.get("dpi", 300))
            self.ui.video_fps.setValue(export.get("video_fps", 15))
            self.ui.video_start_frame.setValue(export.get("video_start_frame", 0))
            self.ui.video_end_frame.setValue(export.get("video_end_frame", 0))
            self.ui.video_grid_w.setValue(export.get("video_grid_w", 300))
            self.ui.video_grid_h.setValue(export.get("video_grid_h", 300))
            if self.ui.gpu_checkbox.isEnabled(): self.ui.gpu_checkbox.setChecked(perf.get("gpu", False))
            self.ui.cache_size_spinbox.setValue(perf.get("cache", 100))
            self.data_manager.set_cache_size(self.ui.cache_size_spinbox.value())

        finally:
            for widget in all_widgets: widget.blockSignals(False)
            # <-- FIX: The problematic call to self._connect_signals() is REMOVED from here.
            self._update_gpu_status_label()
            self._on_vector_plot_type_changed()

    # endregion
    
    # region 程序设置与关闭
    def _load_settings(self):
        self.restoreGeometry(self.settings.value("geometry", self.saveGeometry()))
        self.restoreState(self.settings.value("windowState", self.saveState()))
        panel_visible = self.settings.value("panel_visible", True, type=bool)
        self.ui.control_panel.setVisible(panel_visible)
        self.ui.toggle_panel_action.setChecked(panel_visible)
        self._update_gpu_status_label()

    def _save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("data_directory", self.data_dir)
        self.settings.setValue("output_directory", self.output_dir)
        self.settings.setValue("panel_visible", self.ui.control_panel.isVisible())
        if self.current_config_file:
            self.settings.setValue("last_config_file", self.current_config_file)

    def closeEvent(self, event):
        if self.batch_export_worker and self.batch_export_worker.isRunning():
            if QMessageBox.question(self, "确认", "批量导出正在进行，确定退出吗？") == QMessageBox.StandardButton.Yes:
                self.batch_export_worker.cancel()
                self.batch_export_worker.progress.disconnect()
                self.batch_export_worker.log_message.disconnect()
                self.batch_export_worker.finished.disconnect()
                self.batch_export_worker.wait()
                self.batch_export_worker.deleteLater() # 确保对象被正确删除
            else: event.ignore(); return

        if self.config_is_dirty:
            reply = QMessageBox.question(self, '未保存的修改', "退出前是否保存当前修改？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self._save_current_config()
            elif reply == QMessageBox.StandardButton.Cancel: event.ignore(); return

        self._save_settings()
        self.play_timer.stop()
        if self.ui.plot_widget.thread_pool:
            self.ui.plot_widget.thread_pool.clear()
            self.ui.plot_widget.thread_pool.waitForDone()
        logger.info("应用程序正常关闭")
        super().closeEvent(event)
    # endregion

    # region 辅助方法
    def _update_gpu_status_label(self):
        if is_gpu_available():
            status, color = ("GPU: 启用", "green") if self.ui.gpu_checkbox.isChecked() else ("GPU: 可用", "orange")
        else:
            status, color = ("GPU: 不可用", "red")
        self.ui.gpu_status_label.setText(status)
        self.ui.gpu_status_label.setStyleSheet(f"color: {color};")

    def _show_variable_menu(self, line_edit: QLineEdit, position: QPoint):
        """为指定的QLineEdit创建并显示一个包含变量和常量的菜单"""
        menu = QMenu(self)

        # 数据变量
        data_vars = self.data_manager.get_variables()
        if data_vars:
            var_menu = menu.addMenu("数据变量")
            for var in sorted(data_vars):
                action = var_menu.addAction(var)
                action.triggered.connect(lambda checked=False, v=var: line_edit.insert(f" {v} "))
        
        # 全局统计
        global_vars = self.formula_validator.custom_global_variables
        if global_vars:
            global_menu = menu.addMenu("全局常量")
            for g_var in sorted(global_vars.keys()):
                action = global_menu.addAction(g_var)
                action.triggered.connect(lambda checked=False, v=g_var: line_edit.insert(f" {v} "))

        # 科学常数
        consts = self.formula_validator.science_constants
        if consts:
            const_menu = menu.addMenu("科学常数")
            for const in sorted(consts.keys()):
                action = const_menu.addAction(const)
                action.triggered.connect(lambda checked=False, v=const: line_edit.insert(f" {v} "))
        
        if not menu.actions():
            menu.addAction("无可用变量").setEnabled(False)

        menu.exec(position)
    # endregion