from PyQt6.QtGui import QIcon, QBrush, QColor
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
from typing import Optional, Tuple
import numpy as np
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QFileDialog, QLineEdit, QMenu, QInputDialog, QToolTip, QListWidgetItem, QTableWidgetItem, QApplication, QTreeWidgetItem
from PyQt6.QtCore import Qt, QSettings, QPoint, QTimer
from PyQt6.QtGui import QCursor
import pyarrow as pa

from src.core.data_manager import DataManager
from src.core.formula_engine import FormulaEngine
from src.core.constants import PickerMode
from src.utils.help_dialog import HelpDialog
from src.utils.gpu_utils import is_gpu_available
from src.utils.help_content import (
    get_formula_help_html, get_axis_title_help_html,
    get_data_processing_help_html, get_analysis_help_html,
    get_template_help_html, get_theme_help_html,
    get_data_management_help_html # NEW
)
from src.ui.ui_setup import UiMainWindow
from src.ui.dialogs import ImportDialog, StatsProgressDialog
from src.ui.timeseries_dialog import TimeSeriesDialog
from src.ui.profile_plot_dialog import ProfilePlotDialog
from src.ui.dialogs import FilterBuilderDialog
from src.core.workers import DatabaseImportWorker

from src.handlers.config_handler import ConfigHandler
from src.handlers.stats_handler import StatsHandler
from src.handlers.export_handler import ExportHandler
from src.handlers.playback_handler import PlaybackHandler
from src.handlers.template_handler import TemplateHandler
from src.handlers.theme_handler import ThemeHandler


try: import moviepy.editor; MOVIEPY_AVAILABLE = True
except ImportError: MOVIEPY_AVAILABLE = False
try: import imageio; IMAGEIO_AVAILABLE = True
except ImportError: IMAGEIO_AVAILABLE = False
VIDEO_EXPORT_AVAILABLE = MOVIEPY_AVAILABLE or IMAGEIO_AVAILABLE
logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """应用程序的主窗口类。"""
    
    def __init__(self):
        super().__init__(); self.setWindowIcon(QIcon("png/icon.png"))
        self.settings = QSettings("StarsWhere", "InterVis"); self.data_manager = DataManager(); self.formula_engine = FormulaEngine(); self.ui = UiMainWindow()
        self.current_frame_index: int = 0; self._should_reset_view_after_refresh: bool = False
        self.project_dir = self.settings.value("project_directory", os.path.join(os.getcwd(), "data")); self.output_dir = self.settings.value("output_directory", os.path.join(os.getcwd(), "output"))
        os.makedirs(self.project_dir, exist_ok=True); os.makedirs(self.output_dir, exist_ok=True)
        self.redraw_debounce_timer = QTimer(self); self.redraw_debounce_timer.setSingleShot(True); self.redraw_debounce_timer.setInterval(150)
        self.validation_timer = QTimer(self); self.validation_timer.setSingleShot(True); self.validation_timer.setInterval(500)
        self.import_worker: Optional[DatabaseImportWorker] = None; self.import_progress_dialog: Optional[ImportDialog] = None
        self.timeseries_dialog: Optional[TimeSeriesDialog] = None; self.profile_dialog: Optional[ProfilePlotDialog] = None
        self.config_handler = ConfigHandler(self, self.ui); self.stats_handler = StatsHandler(self, self.ui, self.data_manager, self.formula_engine); self.export_handler = ExportHandler(self, self.ui, self.data_manager, self.config_handler); self.playback_handler = PlaybackHandler(self, self.ui, self.data_manager); self.template_handler = TemplateHandler(self, self.ui, self.config_handler); self.theme_handler = ThemeHandler(self, self.ui)
        self._init_ui(); self._connect_signals(); self._load_settings(); self._initialize_project()

    def _init_ui(self):
        self.ui.setup_ui(self, self.formula_engine)
        self.ui.gpu_checkbox.setEnabled(is_gpu_available()); self.ui.data_dir_line_edit.setText(self.project_dir); self.export_handler.set_output_dir(self.output_dir)
        if not VIDEO_EXPORT_AVAILABLE:
            tooltip = "功能不可用：请安装 moviepy 或 imageio"
            self.ui.export_vid_btn.setEnabled(False); self.ui.export_vid_btn.setToolTip(tooltip)
            self.ui.batch_export_btn.setEnabled(False); self.ui.batch_export_btn.setToolTip(tooltip)
        
        # [MODIFIED] Re-enable Data Management
        self.ui.tab_widget.setTabEnabled(2, True); self.ui.tab_widget.setTabText(2, "数据处理")
        self.ui.tab_widget.setTabEnabled(3, True); self.ui.tab_widget.setTabText(3, "数据管理")
        
        # Still disable unimplemented sub-features
        self.ui.new_time_agg_formula_edit.setEnabled(False); self.ui.compute_and_add_time_agg_btn.setEnabled(False)
        self.ui.combined_formula_edit.setEnabled(False); self.ui.compute_combined_btn.setEnabled(False)
        self.ui.custom_stats_input.setEnabled(False); self.ui.save_and_calc_custom_stats_btn.setEnabled(False)
        self.ui.export_stats_btn.setEnabled(False)

        self._update_gpu_status_label(); self._on_vector_plot_type_changed(); self._on_time_analysis_mode_changed()

    def _connect_signals(self):
        self.data_manager.error_occurred.connect(self._on_error)
        self.redraw_debounce_timer.timeout.connect(self._apply_visualization_settings)
        self.validation_timer.timeout.connect(self._validate_all_formulas)
        self.ui.plot_widget.mouse_moved.connect(self._on_mouse_moved); self.ui.plot_widget.probe_data_ready.connect(self._on_probe_data); self.ui.plot_widget.value_picked.connect(self._on_value_picked); self.ui.plot_widget.timeseries_point_picked.connect(self._on_timeseries_point_picked); self.ui.plot_widget.profile_line_defined.connect(self._on_profile_line_defined); self.ui.plot_widget.plot_rendered.connect(self._on_plot_rendered); self.ui.plot_widget.interpolation_error.connect(self._on_interpolation_error); self.ui.plot_widget.mouse_left_plot.connect(lambda: QToolTip.hideText())
        self.ui.open_data_dir_action.triggered.connect(self._change_project_directory); self.ui.reload_action.triggered.connect(self._force_reload_data); self.ui.exit_action.triggered.connect(self.close); self.ui.reset_view_action.triggered.connect(self.ui.plot_widget.reset_view); self.ui.toggle_panel_action.triggered.connect(self._toggle_control_panel); self.ui.full_screen_action.triggered.connect(self._toggle_full_screen); self.ui.formula_help_action.triggered.connect(lambda: self._show_help("formula")); self.ui.analysis_help_action.triggered.connect(lambda: self._show_help("analysis")); self.ui.dp_help_action.triggered.connect(lambda: self._show_help("data_processing")); self.ui.template_help_action.triggered.connect(lambda: self._show_help("template")); self.ui.theme_help_action.triggered.connect(lambda: self._show_help("theme")); self.ui.about_action.triggered.connect(self._show_about)
        self.ui.change_data_dir_btn.clicked.connect(self._change_project_directory); self.ui.refresh_button.clicked.connect(lambda: self._force_refresh_plot(reset_view=True)); self.ui.apply_cache_btn.clicked.connect(self._apply_cache_settings); self.ui.gpu_checkbox.toggled.connect(self._on_gpu_toggle); self.ui.vector_plot_type.currentIndexChanged.connect(self._on_vector_plot_type_changed); self.ui.aspect_ratio_combo.currentIndexChanged.connect(self._on_aspect_ratio_mode_changed)
        self.ui.probe_by_coords_btn.clicked.connect(self._probe_by_coords)
        self.ui.apply_filter_btn.clicked.connect(self._apply_global_filter) # Re-enabled
        self.ui.build_filter_btn.clicked.connect(self._open_filter_builder) # Re-enabled
        self.ui.switch_dataset_btn.clicked.connect(self._switch_to_selected_dataset) # NEW
        self.ui.rename_dataset_btn.clicked.connect(self._rename_selected_dataset) # Replaces rename_variable
        self.ui.delete_dataset_btn.clicked.connect(self._delete_selected_dataset) # Replaces delete_variable
        self.ui.time_analysis_mode_combo.currentIndexChanged.connect(self._on_time_analysis_mode_changed)
        self.ui.pick_timeseries_btn.toggled.connect(self._on_pick_timeseries_toggled); self.ui.pick_by_coords_btn.clicked.connect(self._pick_timeseries_by_coords); self.ui.draw_profile_btn.toggled.connect(self._on_draw_profile_toggled); self.ui.draw_profile_by_coords_btn.clicked.connect(self._draw_profile_by_coords)
        self.ui.analysis_help_btn.clicked.connect(lambda: self._show_help("analysis"))
        self.ui.time_avg_start_slider.valueChanged.connect(self.ui.time_avg_start_spinbox.setValue); self.ui.time_avg_start_spinbox.valueChanged.connect(self.ui.time_avg_start_slider.setValue); self.ui.time_avg_end_slider.valueChanged.connect(self.ui.time_avg_end_spinbox.setValue); self.ui.time_avg_end_spinbox.valueChanged.connect(self.ui.time_avg_end_slider.setValue); self.ui.time_avg_start_spinbox.editingFinished.connect(self._trigger_auto_apply); self.ui.time_avg_end_spinbox.editingFinished.connect(self._trigger_auto_apply)
        self.config_handler.connect_signals(); self.stats_handler.connect_signals(); self.export_handler.connect_signals(); self.playback_handler.connect_signals(); self.template_handler.connect_signals(); self.theme_handler.connect_signals()
        self._connect_auto_apply_widgets()

    def _get_all_formula_editors(self) -> list:
        return [self.ui.x_axis_formula, self.ui.y_axis_formula, self.ui.chart_title_edit, self.ui.heatmap_formula, self.ui.contour_formula, self.ui.vector_u_formula, self.ui.vector_v_formula, self.ui.new_variable_formula_edit]

    def _connect_auto_apply_widgets(self):
        widgets = [self.ui.heatmap_enabled, self.ui.heatmap_colormap, self.ui.contour_enabled, self.ui.contour_labels, self.ui.contour_levels, self.ui.contour_linewidth, self.ui.contour_colors, self.ui.vector_enabled, self.ui.vector_plot_type, self.ui.quiver_density_spinbox, self.ui.quiver_scale_spinbox, self.ui.stream_density_spinbox, self.ui.stream_linewidth_spinbox, self.ui.stream_color_combo, self.ui.filter_enabled_checkbox, self.ui.aspect_ratio_spinbox]
        for editor in self._get_all_formula_editors():
            if isinstance(editor, QLineEdit): editor.textChanged.connect(self.validation_timer.start); editor.editingFinished.connect(self._trigger_auto_apply)
            else: editor.textChanged.connect(self.validation_timer.start)
        for w in widgets:
            if hasattr(w, 'toggled'): w.toggled.connect(self._trigger_auto_apply)
            elif hasattr(w, 'currentIndexChanged'): w.currentIndexChanged.connect(self._trigger_auto_apply)
            elif hasattr(w, 'valueChanged'): w.valueChanged.connect(self._trigger_auto_apply)
    
    def _trigger_auto_apply(self, *args):
        if self.config_handler._is_loading_config: return
        self.config_handler.mark_config_as_dirty()
        if self.data_manager.get_frame_count() > 0: self._should_reset_view_after_refresh = False; self.redraw_debounce_timer.start()

    def _validate_all_formulas(self):
        for editor in self._get_all_formula_editors():
            formula_text = editor.toPlainText() if hasattr(editor, 'toPlainText') else editor.text(); all_valid = True; errors = []
            if isinstance(editor, QLineEdit):
                 is_valid, error_msg = self.formula_engine.validate_syntax(formula_text)
                 if not is_valid: all_valid = False; errors.append(error_msg)
            else:
                for line in formula_text.split('\n'):
                    if line.strip() and not line.strip().startswith('#'):
                        temp_new_vars = {d.split('=')[0].strip() for d in editor.toPlainText().split('\n') if '=' in d}; original_allowed = self.formula_engine.allowed_variables; self.formula_engine.allowed_variables = original_allowed.union(temp_new_vars)
                        is_valid, error_msg = self.formula_engine.validate_syntax(line.split('=')[1].strip() if '=' in line else line)
                        self.formula_engine.allowed_variables = original_allowed
                        if not is_valid: all_valid = False; errors.append(f"Line '{line[:30]}...': {error_msg}")
            editor.setStyleSheet("" if all_valid else "background-color: #ffe0e0;"); editor.setToolTip("\n".join(errors))

    def _initialize_project(self):
        if not self.data_manager.setup_project_directory(self.project_dir): return
        if self.data_manager.is_project_ready():
            logger.info(f"在 {self.project_dir} 中找到现有项目，直接加载。")
            last_dataset_uri = self.settings.value("last_active_dataset", None)
            # 检查数据集URI是否存在，如果不存在，则清除设置
            if last_dataset_uri and not os.path.exists(last_dataset_uri):
                logger.warning(f"上次活动的数据集 '{last_dataset_uri}' 不存在，清除设置。")
                self.settings.remove("last_active_dataset")
                last_dataset_uri = None
            
            if last_dataset_uri:
                self.switch_to_dataset(uri=last_dataset_uri)
            else:
                # 如果没有上次活动的数据集或数据集不存在，则提示用户创建新数据集
                reply = QMessageBox.question(self, "未找到项目数据", f"在目录 '{self.project_dir}' 中未找到数据集。\n\n是否从此目录中的所有CSV文件创建新的数据集？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes: self._start_database_import()
                else: self.ui.status_bar.showMessage("操作已取消。请选择一个包含CSV文件的项目目录。", 5000)
        else: # 如果项目目录没有准备好，总是提示导入
            reply = QMessageBox.question(self, "未找到项目数据", f"在目录 '{self.project_dir}' 中未找到数据集。\n\n是否从此目录中的所有CSV文件创建新的数据集？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes: self._start_database_import()
            else: self.ui.status_bar.showMessage("操作已取消。请选择一个包含CSV文件的项目目录。", 5000)

    def _start_database_import(self):
        self.import_progress_dialog = ImportDialog(self, "正在创建Parquet数据集..."); self.import_worker = DatabaseImportWorker(self.data_manager)
        self.import_worker.progress.connect(self.import_progress_dialog.update_progress); self.import_worker.log_message.connect(self.import_progress_dialog.set_log_message); self.import_worker.finished.connect(self._on_import_finished); self.import_worker.error.connect(self._on_error)
        self.import_worker.start(); self.import_progress_dialog.exec()
        
    def _on_import_finished(self, new_dataset_uri):
        if self.import_progress_dialog: self.import_progress_dialog.accept()
        QMessageBox.information(self, "导入完成", f"Parquet数据集已成功创建在:\n{new_dataset_uri}")
        self.switch_to_dataset(uri=new_dataset_uri)
    
    def switch_to_dataset(self, uri: Optional[str]):
        try:
            self.data_manager.set_active_dataset(uri=uri); self._load_project_data()
        except Exception as e: self._on_error(f"切换数据集失败: {e}")

    def _load_project_data(self):
        if not self.data_manager.active_dataset_uri: self.ui.status_bar.showMessage("项目中无可用数据集。", 5000); self.ui.compute_and_add_btn.setEnabled(False); self._update_datasets_browser(); return
        
        self._update_db_info(); self._update_datasets_browser()
        frame_count = self.data_manager.get_frame_count()
        if frame_count > 0:
            all_vars = self.data_manager.get_variables()
            self.stats_handler.load_and_display_stats()
            self.playback_handler.update_time_axis_candidates()
            self.formula_engine.update_allowed_variables(all_vars)
            
            self.ui.floating_probe_vars_list.clear()
            for var in sorted(all_vars):
                item = QListWidgetItem(var); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Unchecked)
                self.ui.floating_probe_vars_list.addItem(item)

            self.ui.time_slider.setMaximum(frame_count - 1)
            self.ui.video_start_frame.setMaximum(frame_count - 1); self.ui.video_end_frame.setMaximum(frame_count - 1); self.ui.video_end_frame.setValue(frame_count - 1)
            for w in [self.ui.time_avg_start_slider, self.ui.time_avg_start_spinbox, self.ui.time_avg_end_slider, self.ui.time_avg_end_spinbox]: w.setMaximum(frame_count - 1)
            self.ui.time_avg_end_spinbox.setValue(frame_count - 1)
            
            self.config_handler.populate_config_combobox(); self.template_handler.populate_template_combobox(); self.theme_handler.populate_theme_combobox()
            self.ui.compute_and_add_btn.setEnabled(True)
            self._force_refresh_plot(reset_view=True)
            self.ui.status_bar.showMessage(f"项目加载成功，共 {frame_count} 帧数据。", 5000)
        else:
            self.ui.status_bar.showMessage("项目加载失败：数据集为空或无法读取。", 5000)
            self.ui.compute_and_add_btn.setEnabled(False)
    
    def _update_db_info(self):
        info = self.data_manager.get_database_info()
        db_path = info.get("db_path", "N/A"); db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if db_path != "N/A" and os.path.exists(db_path) else 0
        active_dataset_name = os.path.basename(info.get('active_dataset', '无')) if info.get('active_dataset') else '无'
        db_info_text = f"活动数据集: {active_dataset_name}"
        self.ui.db_info_label.setText(db_info_text); self.ui.db_info_label.setToolTip(info.get('active_dataset', '无'))

    def _apply_global_filter(self):
        try:
            filter_text = self.ui.filter_text_edit.text() if self.ui.filter_enabled_checkbox.isChecked() else ""
            self.data_manager.set_global_filter(filter_text)
            self._force_refresh_plot(reset_view=False)
            self.ui.status_bar.showMessage("全局过滤器已应用。", 3000)
        except ValueError as e: QMessageBox.critical(self, "过滤器错误", f"过滤器语法无效: {e}")

    def _open_filter_builder(self):
        if self.data_manager.get_frame_count() == 0: QMessageBox.warning(self, "无数据", "请先加载数据再构建过滤器。"); return
        dialog = FilterBuilderDialog(self.data_manager.get_variables(), self)
        if dialog.exec():
            self.ui.filter_text_edit.setText(dialog.get_filter_string())
            self._apply_global_filter()

    def _update_datasets_browser(self):
        self.ui.datasets_tree.clear()
        datasets = self.data_manager.get_all_datasets_info()
        
        # Build a dict of items and a parent-child relationship map
        items_by_id = {}
        children_map = {}
        
        for row in datasets:
            ds_id, name, uri, parent_id, created_at = row
            parent = self.ui.datasets_tree if parent_id is None else items_by_id.get(parent_id)
            if parent is None and parent_id is not None:
                if parent_id not in children_map: children_map[parent_id] = []
                children_map[parent_id].append(row)
                continue
            
            item = QTreeWidgetItem(parent, [name, created_at.split('.')[0], str(parent_id) if parent_id else "N/A", str(ds_id)])
            item.setData(0, Qt.ItemDataRole.UserRole, uri) # Store URI in user data
            items_by_id[ds_id] = item
            
            # If this item is the active one, select and highlight it
            if uri == self.data_manager.active_dataset_uri:
                item.setSelected(True)
                item.setBackground(0, QBrush(QColor("#d4edda"))) # Bootstrap 'success' green

            # Add any children that were waiting for this parent
            if ds_id in children_map:
                for child_row in children_map[ds_id]:
                    child_item = QTreeWidgetItem(item, [child_row[1], child_row[4].split('.')[0], str(child_row[3]), str(child_row[0])])
                    child_item.setData(0, Qt.ItemDataRole.UserRole, child_row[2])
                    items_by_id[child_row[0]] = child_item
        
        self.ui.datasets_tree.expandAll()

    def _switch_to_selected_dataset(self):
        selected = self.ui.datasets_tree.selectedItems()
        if not selected: QMessageBox.warning(self, "未选择", "请在浏览器中选择一个要切换的数据集。"); return
        uri = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if uri != self.data_manager.active_dataset_uri:
            self.switch_to_dataset(uri)

    def _delete_selected_dataset(self):
        selected = self.ui.datasets_tree.selectedItems()
        if not selected: QMessageBox.warning(self, "未选择", "请在浏览器中选择一个要删除的数据集。"); return
        
        item = selected[0]
        name = item.text(0); ds_id = int(item.text(3))
        
        reply = QMessageBox.question(self, "确认删除", f"您确定要永久删除数据集 <b>'{name}'</b> 吗？<br><br>此操作将从磁盘删除其所有Parquet文件，且<b>无法撤销</b>。其所有派生的子数据集也将被一并删除。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.data_manager.delete_dataset(ds_id)
                QMessageBox.information(self, "成功", f"数据集 '{name}' 已成功删除。")
                self._load_project_data() # Reload project state
            except Exception as e: self._on_error(f"删除数据集失败: {e}")

    def _rename_selected_dataset(self): QMessageBox.information(self, "功能待实现", "重命名数据集功能将在未来版本中提供。")

    # --- Omitted other unchanged methods for brevity ---
    def _apply_visualization_settings(self):
        if self.data_manager.get_frame_count() == 0: return
        config = self.config_handler.get_current_config(); self.ui.plot_widget.set_config(heatmap_config=config['heatmap'], contour_config=config['contour'], vector_config=config['vector'], analysis=config['analysis'], x_axis_formula=config['axes']['x_formula'], y_axis_formula=config['axes']['y_formula'], chart_title=config['axes']['title'], aspect_ratio_config=config['axes']['aspect_config'], grid_resolution=(config['export']['video_grid_w'], config['export']['video_grid_h']), use_gpu=config['performance']['gpu'])
        is_time_avg = config['analysis']['time_average']['enabled']
        if is_time_avg: start, end = config['analysis']['time_average']['start_frame'], config['analysis']['time_average']['end_frame']; data = self.data_manager.get_time_averaged_data(start, end); self.ui.plot_widget.update_data(data); self._update_frame_info(is_time_avg=True, start=start, end=end)
        else: self._load_frame(self.current_frame_index)
        self.ui.status_bar.showMessage("可视化设置已更新。", 2000)
    def _load_frame(self, frame_index: int):
        if not (0 <= frame_index < self.data_manager.get_frame_count()): return
        data = self.data_manager.get_frame_data(frame_index)
        if data is not None: self.current_frame_index = frame_index; self.ui.time_slider.blockSignals(True); self.ui.time_slider.setValue(frame_index); self.ui.time_slider.blockSignals(False); self.ui.plot_widget.update_data(data); self._update_frame_info();
        if self.ui.plot_widget.last_mouse_coords: self.ui.plot_widget.get_probe_data_at_coords(*self.ui.plot_widget.last_mouse_coords)
    def closeEvent(self, event):
        self.settings.setValue("last_active_dataset", self.data_manager.active_dataset_uri)
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
    # The rest of the methods are unchanged and thus omitted for brevity.
    # A full file would include them all.
    def _on_time_analysis_mode_changed(self):
        is_time_avg = self.ui.time_analysis_mode_combo.currentText() == "时间平均场"
        self.ui.playback_widget.setVisible(not is_time_avg); self.playback_handler.set_enabled(not is_time_avg)
        self.ui.time_average_range_widget.setVisible(is_time_avg)
        if VIDEO_EXPORT_AVAILABLE: self.ui.export_vid_btn.setEnabled(not is_time_avg); self.ui.batch_export_btn.setEnabled(True); self.ui.export_vid_btn.setToolTip("时间平均场模式下无法导出视频" if is_time_avg else "")
        self._trigger_auto_apply()
    def _on_aspect_ratio_mode_changed(self): is_custom = self.ui.aspect_ratio_combo.currentText() == "Custom"; self.ui.aspect_ratio_spinbox.setVisible(is_custom); self._trigger_auto_apply()
    def _on_pick_timeseries_toggled(self, checked):
        if checked: self.ui.draw_profile_btn.setChecked(False); self.ui.plot_widget.set_picker_mode(PickerMode.TIMESERIES); self.ui.status_bar.showMessage("时间序列模式: 在图表上单击一点以拾取 (右键取消)。", 0)
        elif self.ui.plot_widget.picker_mode == PickerMode.TIMESERIES: self.ui.plot_widget.set_picker_mode(None); self.ui.status_bar.clearMessage()
    def _on_draw_profile_toggled(self, checked):
        if checked: self.ui.pick_timeseries_btn.setChecked(False); self.ui.plot_widget.set_picker_mode(PickerMode.PROFILE_START); self.ui.status_bar.showMessage("剖面图模式: 点击定义剖面线起点 (右键取消)。", 0)
        elif self.ui.plot_widget.picker_mode in [PickerMode.PROFILE_START, PickerMode.PROFILE_END]: self.ui.plot_widget.set_picker_mode(None); self.ui.status_bar.clearMessage()
    def _pick_timeseries_by_coords(self):
        text, ok = QInputDialog.getText(self, "按坐标拾取时间序列点", "请输入坐标 (x, y):", QLineEdit.EchoMode.Normal, "0.0, 0.0")
        if ok and text:
            try: x_str, y_str = text.split(','); coords = (float(x_str.strip()), float(y_str.strip())); self._on_timeseries_point_picked(coords)
            except (ValueError, IndexError): QMessageBox.warning(self, "输入无效", "请输入格式为 'x, y' 的两个数值。")
    def _draw_profile_by_coords(self):
        start_text, ok1 = QInputDialog.getText(self, "绘制剖面图", "请输入起点坐标 (x1, y1):");
        if not (ok1 and start_text): return
        end_text, ok2 = QInputDialog.getText(self, "绘制剖面图", "请输入终点坐标 (x2, y2):");
        if not (ok2 and end_text): return
        try:
            x1_str, y1_str = start_text.split(','); start_coords = (float(x1_str.strip()), float(y1_str.strip()))
            x2_str, y2_str = end_text.split(','); end_coords = (float(x2_str.strip()), float(y2_str.strip()))
            self._on_profile_line_defined(start_coords, end_coords)
        except (ValueError, IndexError): QMessageBox.warning(self, "输入无效", "请输入格式为 'x, y' 的两个数值。")

    def _on_timeseries_point_picked(self, coords: Tuple[float, float]):
        self.ui.pick_timeseries_btn.setChecked(False)
        x, y = coords
        if not self.data_manager.active_dataset_uri: QMessageBox.warning(self, "无数据", "请先加载数据集。"); return
        
        try:
            # Get the raw data for the picked point across all frames
            timeseries_data = self.data_manager.get_timeseries_at_coords(x, y)
            if timeseries_data is None or timeseries_data.empty: QMessageBox.information(self, "无数据", f"在 ({x:.2f}, {y:.2f}) 处未找到时间序列数据。"); return
            
            # Get current config for formulas
            config = self.config_handler.get_current_config()
            
            # Pass data and formulas to the TimeSeriesDialog
            if self.timeseries_dialog and self.timeseries_dialog.isVisible(): self.timeseries_dialog.close()
            self.timeseries_dialog = TimeSeriesDialog(
                timeseries_data,
                self.data_manager.time_variable,
                self.formula_engine,
                self.output_dir,
                config['heatmap'].get('formula', ''), # Heatmap formula
                config['contour'].get('formula', ''), # Contour formula
                config['vector'].get('u_formula', ''), # Vector U formula
                config['vector'].get('v_formula', ''), # Vector V formula
                self # Parent
            )
            self.timeseries_dialog.show()

        except Exception as e: logger.error(f"无法获取时间序列数据: {e}", exc_info=True); QMessageBox.critical(self, "错误", f"无法获取时间序列数据: {e}")

    def _on_profile_line_defined(self, start_point, end_point):
        self.ui.draw_profile_btn.setChecked(False)
        if not self.ui.plot_widget.interpolated_results: QMessageBox.warning(self, "无数据", "无可用于剖面的插值数据。"); return
        if self.profile_dialog and self.profile_dialog.isVisible(): self.profile_dialog.close()
        available_data = {}
        config = self.config_handler.get_current_config()
        for key in ['heatmap', 'contour', 'vector_u', 'vector_v']:
            data_key = f'{key}_data'
            if data_key in self.ui.plot_widget.interpolated_results and self.ui.plot_widget.interpolated_results[data_key] is not None:
                formula = ""
                if key == 'heatmap' and config['heatmap'].get('enabled'): formula = config['heatmap'].get('formula', key)
                elif key == 'contour' and config['contour'].get('enabled'): formula = config['contour'].get('formula', key)
                elif key == 'vector_u' and config['vector'].get('enabled'): formula = config['vector'].get('u_formula', key)
                elif key == 'vector_v' and config['vector'].get('enabled'): formula = config['vector'].get('v_formula', key)
                if formula: available_data[key] = formula
        self.profile_dialog = ProfilePlotDialog(start_point, end_point, self.ui.plot_widget.interpolated_results, available_data, self.output_dir, self)
        self.profile_dialog.show()
    def _update_frame_info(self, is_time_avg: bool = False, start: int = 0, end: int = 0):
        if is_time_avg: self.ui.frame_info_label.setText(f"时间平均: 帧 {start}-{end}"); self.ui.timestamp_label.setText("")
        else:
            fc = self.data_manager.get_frame_count()
            self.ui.frame_info_label.setText(f"帧: {self.current_frame_index + 1}/{fc if fc > 0 else '?'}")
            info = self.data_manager.get_frame_info(self.current_frame_index)
            if info and 'timestamp' in info:
                ts_val = info.get('timestamp', 'N/A'); ts_str = f"{ts_val:.4f}" if isinstance(ts_val, (float, int)) else str(ts_val)
                self.ui.timestamp_label.setText(f"时间({self.data_manager.time_variable}): {ts_str}")
        self.ui.cache_label.setText(f"缓存: {self.data_manager.get_cache_info()['size']}/{self.data_manager.get_cache_info()['max_size']}")
    def _on_error(self, message: str):
        if self.import_progress_dialog and self.import_progress_dialog.isVisible(): self.import_progress_dialog.accept()
        self.ui.status_bar.showMessage(f"错误: {message}", 5000); QMessageBox.critical(self, "发生错误", message)
    def _on_mouse_moved(self, x, y): self.ui.probe_coord_label.setText(f"({x:.3e}, {y:.3e})")
    def _on_probe_data(self, data): self._update_main_probe_display(data); self._update_floating_probe_display(data)
    def _probe_by_coords(self):
        text, ok = QInputDialog.getText(self, "按坐标查询探针", "请输入坐标 (x, y):")
        if ok and text:
            try: x_str, y_str = text.split(','); x, y = float(x_str.strip()), float(y_str.strip()); self.ui.plot_widget.get_probe_data_at_coords(x, y); QMessageBox.information(self, "查询成功", f"数据探针已更新为坐标 ({x:.3e}, {y:.3e}) 的值。")
            except (ValueError, IndexError): QMessageBox.warning(self, "输入无效", "请输入格式为 'x, y' 的两个数值。")
    def _update_main_probe_display(self, data):
        scrollbar = self.ui.probe_text.verticalScrollBar(); scroll_position = scrollbar.value()
        lines = []
        if data.get('variables'): lines.extend([f"{'--- 最近原始数据点 ---':^40}"] + [f"{k:<18s} {v:12.6e}" if isinstance(v, (int, float)) else f"{k:<18s} {v}" for k, v in data['variables'].items()] + [""])
        if data.get('interpolated'):
            config = self.config_handler.get_current_config(); lines.append(f"{'--- 鼠标位置插值数据 ---':^40}")
            lines.append(f"{f'X坐标 ({config['axes'].get('x_formula', 'x')}):':<25s} {data.get('x'):12.6e}")
            lines.append(f"{f'Y坐标 ({config['axes'].get('y_formula', 'y')}):':<25s} {data.get('y'):12.6e}")
            probe_map = {'heatmap': f"热力图 ({config['heatmap'].get('formula', 'N/A')})", 'contour': f"等高线 ({config['contour'].get('formula', 'N/A')})", 'vector_u': f"U分量 ({config['vector'].get('u_formula', 'N/A')})", 'vector_v': f"V分量 ({config['vector'].get('v_formula', 'N/A')})"}
            for key, value in data['interpolated'].items():
                if key in probe_map:
                    val_str = f"{value:12.6e}" if isinstance(value, (int,float)) and not np.isnan(value) else 'N/A'
                    lines.append(f"{probe_map[key]:<25s} {val_str}")
        self.ui.probe_text.setPlainText("\n".join(lines)); scrollbar.setValue(scroll_position)
    def _update_floating_probe_display(self, data):
        checked_items = [self.ui.floating_probe_vars_list.item(i) for i in range(self.ui.floating_probe_vars_list.count()) if self.ui.floating_probe_vars_list.item(i).checkState() == Qt.CheckState.Checked]
        if not checked_items: QToolTip.hideText(); return
        probe_html_lines = ["<div style='background-color: #ffffdd; border: 1px solid black; padding: 4px; font-family: Monospace; font-size: 9pt;'>"]
        raw_vars = data.get('variables', {}); interp_vars = data.get('interpolated', {})
        for item in checked_items:
            var_name = item.text(); value = raw_vars.get(var_name, np.nan) 
            if np.isnan(value):
                 if var_name in interp_vars: value = interp_vars[var_name]
                 elif f"{var_name}_data" in self.ui.plot_widget.interpolated_results:
                     val = interp_vars.get(var_name)
                     if val is not None: value = val
            val_str = f"{value:.4e}" if isinstance(value, (int, float)) and not np.isnan(value) else 'N/A'
            probe_html_lines.append(f"<b>{var_name:<15}</b>: {val_str}")
        probe_html_lines.append("</div>")
        if len(probe_html_lines) > 2 and self.ui.plot_widget.canvas.underMouse(): QToolTip.showText(QCursor.pos() + QPoint(10, 10), "<br>".join(probe_html_lines), self.ui.plot_widget)
        else: QToolTip.hideText()
    def _on_value_picked(self, mode, value): target = self.ui.heatmap_vmin if mode == PickerMode.VMIN else self.ui.heatmap_vmax; target.setText(f"{value:.4e}"); self._trigger_auto_apply()
    def _on_plot_rendered(self):
        if self.playback_handler.is_playing: self.playback_handler.play_timer.start()
        if self._should_reset_view_after_refresh: self.ui.plot_widget.reset_view(); self._should_reset_view_after_refresh = False
        if self.ui.plot_widget.picker_mode == PickerMode.PROFILE_END: self.ui.status_bar.showMessage("剖面图模式: 点击定义剖面线终点 (右键取消)。", 0)
    def _on_interpolation_error(self, message: str): QMessageBox.critical(self, "可视化错误", f"无法渲染图形，公式可能存在问题。\n\n错误详情:\n{message}"); self.ui.status_bar.showMessage(f"渲染错误: {message}", 5000)
    def _on_gpu_toggle(self, is_on): self._trigger_auto_apply()
    def _on_vector_plot_type_changed(self): is_q = self.ui.vector_plot_type.currentData(Qt.ItemDataRole.UserRole) == self.config_handler.VectorPlotType.QUIVER; self.ui.quiver_options_group.setVisible(is_q); self.ui.streamline_options_group.setVisible(not is_q); self._trigger_auto_apply()
    def _force_refresh_plot(self, reset_view=False): self._should_reset_view_after_refresh = reset_view; self._apply_visualization_settings()
    def _show_help(self, help_type: str):
        content_map = {"formula": get_formula_help_html(self.data_manager.get_variables(), self.formula_engine.custom_global_variables, self.formula_engine.science_constants), "axis_title": get_axis_title_help_html(), "data_processing": get_data_processing_help_html(), "analysis": get_analysis_help_html(), "template": get_template_help_html(), "theme": get_theme_help_html(), "data_management": get_data_management_help_html()}
        content = content_map.get(help_type)
        if content: HelpDialog(content, self).exec()
    def _show_about(self): QMessageBox.about(self, "关于 InterVis", "<h2>InterVis v3.4-ProFinal</h2><p>作者: StarsWhere</p><p>一个使用PyQt6和Matplotlib构建的交互式数据可视化工具。</p><p><b>v3.4 功能重构:</b></p><ul><li><b>统一数据处理:</b> 将“逐帧计算”和“全局统计”合并为统一的“数据处理”选项卡，流程更清晰。</li><li><b>动态时间轴:</b> 不再依赖文件名排序，用户可从数据中任选数值列作为时间演化依据。</li><li><b>帮助系统完善:</b> 为所有计算功能提供了统一且详细的帮助文档。</li><li>保留并优化了原有功能，如一键导出、多变量剖面图、并行批量导出、可视化模板与主题等。</li></ul>")
    def _force_reload_data(self):
        """强制重新加载当前项目数据。"""
        self.data_manager.clear_all() # 清除所有缓存和当前数据集
        self._initialize_project() # 重新初始化项目，这将加载数据

    def _change_project_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择项目目录 (包含CSV文件)", self.project_dir)
        if new_dir and new_dir != self.project_dir: self.project_dir = new_dir; self.ui.data_dir_line_edit.setText(self.project_dir); self.playback_handler.stop_playback(); self.data_manager.clear_all(); self._initialize_project()
    def _toggle_control_panel(self, checked): self.ui.control_panel.setVisible(checked)
    def _toggle_full_screen(self, checked): self.showFullScreen() if checked else self.showNormal()
    def _apply_cache_settings(self): self.data_manager.set_cache_size(self.ui.cache_size_spinbox.value()); self._update_frame_info()
    def _load_settings(self):
        self.restoreGeometry(self.settings.value("geometry", self.saveGeometry())); self.restoreState(self.settings.value("windowState", self.saveState()))
        self.ui.control_panel.setVisible(self.settings.value("panel_visible", True, type=bool)); self.ui.toggle_panel_action.setChecked(self.ui.control_panel.isVisible())
        self.ui.output_dir_line_edit.setText(self.output_dir); self._update_gpu_status_label()
    def _save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry()); self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("project_directory", self.project_dir); self.settings.setValue("output_directory", self.output_dir)
        self.settings.setValue("panel_visible", self.ui.control_panel.isVisible())
        if self.config_handler.current_config_file: self.settings.setValue("last_config_file", self.config_handler.current_config_file)
        self.settings.setValue("last_time_variable", self.data_manager.time_variable)
        if self.data_manager.active_dataset_uri: self.settings.setValue("last_active_dataset", self.data_manager.active_dataset_uri)
    def _update_gpu_status_label(self):
        use_gpu = self.ui.gpu_checkbox.isChecked(); gpu_available = is_gpu_available()
        if use_gpu and gpu_available: status, color = ("GPU: 已启用", "green")
        elif not use_gpu and gpu_available: status, color = ("GPU: 可用 (未启用)", "orange")
        else: status, color = ("GPU: 不可用", "red")
        self.ui.gpu_status_label.setText(status); self.ui.gpu_status_label.setStyleSheet(f"color: {color};")
    def _show_variable_menu(self, line_edit: QLineEdit, position: QPoint):
        menu = QMenu(self); insert_text = lambda text: line_edit.insert(f" {text} ")
        var_menu = menu.addMenu("数据变量"); [var_menu.addAction(var).triggered.connect(lambda c, v=var: insert_text(v)) for var in sorted(self.data_manager.get_variables())]
        if self.formula_engine.custom_global_variables: global_menu = menu.addMenu("全局常量"); [global_menu.addAction(g).triggered.connect(lambda c, v=g: insert_text(v)) for g in sorted(self.formula_engine.custom_global_variables.keys())]
        if self.formula_engine.science_constants: const_menu = menu.addMenu("科学常数"); [const_menu.addAction(c).triggered.connect(lambda ch, v=c: insert_text(v)) for c in sorted(self.formula_engine.science_constants.keys())]
        if not menu.actions(): menu.addAction("无可用变量").setEnabled(False)
        menu.exec(position)