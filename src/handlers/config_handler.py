#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理处理器
"""
import os
import json
import logging
from typing import Dict, Any, Optional

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QInputDialog, QWidget
from PyQt6.QtCore import QTimer, Qt

from src.core.constants import VectorPlotType, StreamlineColor

logger = logging.getLogger(__name__)

class ConfigHandler:
    """处理所有与加载、保存和管理可视化设置文件相关的逻辑。"""
    
    def __init__(self, main_window, ui):
        self.main_window = main_window
        self.ui = ui
        self.settings = main_window.settings
        
        # Share enums for easier access in main_window
        self.VectorPlotType = VectorPlotType
        self.StreamlineColor = StreamlineColor
        
        self.settings_dir = os.path.join(os.getcwd(), "settings")
        os.makedirs(self.settings_dir, exist_ok=True)
        
        self.config_is_dirty: bool = False
        self._is_loading_config: bool = False
        self.current_config_file: Optional[str] = None
        self._loaded_config: Optional[Dict[str, Any]] = None

    def connect_signals(self):
        """连接此处理器管理的UI组件的信号。"""
        self.ui.config_combo.currentIndexChanged.connect(self.on_config_selected)
        self.ui.save_config_btn.clicked.connect(self.save_current_config)
        self.ui.save_config_as_btn.clicked.connect(self.save_config_as)
        self.ui.new_config_action.triggered.connect(self.create_new_config)
        self.ui.save_config_action.triggered.connect(self.save_current_config)
        self.ui.save_config_as_action.triggered.connect(self.save_config_as)

        # Let main_window handle connecting widgets for auto-apply and dirty marking
        # This simplifies the handler's responsibility.

    def mark_config_as_dirty(self, *args):
        if self._is_loading_config: return
        QTimer.singleShot(50, self._check_config_dirty_status)
    
    def _check_config_dirty_status(self):
        current_config = self.get_current_config()
        if self._loaded_config != current_config:
            self.config_is_dirty = True
            current_file = os.path.basename(self.current_config_file) if self.current_config_file else "新设置"
            self.ui.config_status_label.setText(f"{current_file} (未保存)")
            self.ui.config_status_label.setStyleSheet("color: orange;")
        else:
            self.config_is_dirty = False
            current_file = os.path.basename(self.current_config_file) if self.current_config_file else "新设置"
            self.ui.config_status_label.setText(f"{current_file}")
            self.ui.config_status_label.setStyleSheet("color: green;")

    def populate_config_combobox(self):
        self.ui.config_combo.blockSignals(True)
        current_selection = self.ui.config_combo.currentText()
        self.ui.config_combo.clear()
        
        default_config_path = os.path.join(self.settings_dir, "default.json")
        if not os.path.exists(default_config_path):
            with open(default_config_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_current_config(), f, indent=4)

        config_files = sorted([f for f in os.listdir(self.settings_dir) if f.endswith('.json')])
        self.ui.config_combo.addItems(config_files)
        
        last_config = os.path.basename(self.settings.value("last_config_file", default_config_path))
        if last_config in config_files:
            self.ui.config_combo.setCurrentText(last_config)
        elif current_selection in config_files:
            self.ui.config_combo.setCurrentText(current_selection)

        self.ui.config_combo.blockSignals(False)
        self.load_config_by_name(self.ui.config_combo.currentText())

    def on_config_selected(self, index: int):
        if index < 0: return
        if self.config_is_dirty:
            reply = QMessageBox.question(self.main_window, '未保存的修改', "切换前是否保存当前修改？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self.save_current_config()
            elif reply == QMessageBox.StandardButton.Cancel:
                self.ui.config_combo.blockSignals(True)
                if self.current_config_file: self.ui.config_combo.setCurrentText(os.path.basename(self.current_config_file))
                self.ui.config_combo.blockSignals(False)
                return
        self.load_config_by_name(self.ui.config_combo.currentText())

    def load_config_by_name(self, filename: str):
        if not filename: return
        filepath = os.path.join(self.settings_dir, filename)
        if not os.path.exists(filepath): return
        
        self._is_loading_config = True
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.apply_config(config)
            self.current_config_file = filepath
            self.settings.setValue("last_config_file", filepath)
            QTimer.singleShot(100, self._finalize_config_load)
        except Exception as e:
            QMessageBox.critical(self.main_window, "加载失败", f"无法加载或解析配置文件 '{filename}':\n{e}")
            self._is_loading_config = False

    def _finalize_config_load(self):
        self._loaded_config = self.get_current_config()
        self.config_is_dirty = False
        self._check_config_dirty_status()
        self.ui.status_bar.showMessage(f"已加载设置: {os.path.basename(self.current_config_file)}", 3000)
        self._is_loading_config = False
        self.main_window._trigger_auto_apply()

    def save_current_config(self):
        if not self.current_config_file: self.save_config_as(); return
        try:
            current_config = self.get_current_config()
            with open(self.current_config_file, 'w', encoding='utf-8') as f: json.dump(current_config, f, indent=4)
            self._loaded_config = current_config
            self.config_is_dirty = False
            self._check_config_dirty_status()
            self.ui.status_bar.showMessage(f"设置已保存到 {os.path.basename(self.current_config_file)}", 3000)
        except Exception as e: QMessageBox.critical(self.main_window, "保存失败", f"无法写入配置文件 '{self.current_config_file}':\n{e}")

    def save_config_as(self):
        current_name = os.path.splitext(os.path.basename(self.current_config_file or "untitled"))[0]
        text, ok = QInputDialog.getText(self.main_window, "设置另存为", "请输入新配置文件的名称:", text=f"{current_name}_copy")
        if not (ok and text): return

        filename = f"{text}.json" if not text.endswith('.json') else text
        filepath = os.path.join(self.settings_dir, filename)
        
        if os.path.exists(filepath):
            if QMessageBox.question(self.main_window, "确认覆盖", f"文件 '{filename}' 已存在。是否覆盖？") != QMessageBox.StandardButton.Yes: return

        self.current_config_file = filepath; self.save_current_config()
        
        self.ui.config_combo.blockSignals(True)
        if self.ui.config_combo.findText(filename) == -1: self.ui.config_combo.addItem(filename)
        self.ui.config_combo.setCurrentText(filename)
        self.ui.config_combo.blockSignals(False)
        self.settings.setValue("last_config_file", filepath)

    def create_new_config(self):
        text, ok = QInputDialog.getText(self.main_window, "新建设置", "请输入新配置文件的名称:")
        if ok and text:
            new_filename = f"{text}.json" if not text.endswith('.json') else text
            new_filepath = os.path.join(self.settings_dir, new_filename)
            if os.path.exists(new_filepath):
                if QMessageBox.question(self.main_window, "文件已存在", f"文件 '{new_filename}' 已存在。是否覆盖？") != QMessageBox.StandardButton.Yes: return

            self.current_config_file = new_filepath
            self.apply_config({}); self.save_current_config()
            self.populate_config_combobox(); self.ui.config_combo.setCurrentText(new_filename)

    def get_current_config(self) -> Dict[str, Any]:
        vt = self.ui.vector_plot_type.currentData(Qt.ItemDataRole.UserRole)
        sc = self.ui.stream_color_combo.currentData(Qt.ItemDataRole.UserRole)
        return {
            "version": "2.0.0",
            "axes": {"title": self.ui.chart_title_edit.text().strip(), "x_formula": self.ui.x_axis_formula.text().strip() or "x", "y_formula": self.ui.y_axis_formula.text().strip() or "y"},
            "heatmap": {'enabled': self.ui.heatmap_enabled.isChecked(), 'formula': self.ui.heatmap_formula.text().strip(), 'colormap': self.ui.heatmap_colormap.currentText(), 'vmin': self.ui.heatmap_vmin.text().strip() or None, 'vmax': self.ui.heatmap_vmax.text().strip() or None},
            "contour": {'enabled': self.ui.contour_enabled.isChecked(), 'formula': self.ui.contour_formula.text().strip(), 'levels': self.ui.contour_levels.value(), 'colors': self.ui.contour_colors.currentText(), 'linewidths': self.ui.contour_linewidth.value(), 'show_labels': self.ui.contour_labels.isChecked()},
            "vector": {'enabled': self.ui.vector_enabled.isChecked(), 'type': vt.name if vt else 'STREAMLINE', 'u_formula': self.ui.vector_u_formula.text().strip(), 'v_formula': self.ui.vector_v_formula.text().strip(), 'quiver_options': {'density': self.ui.quiver_density_spinbox.value(), 'scale': self.ui.quiver_scale_spinbox.value()}, 'streamline_options': {'density': self.ui.stream_density_spinbox.value(), 'linewidth': self.ui.stream_linewidth_spinbox.value(), 'color_by': sc.value if sc else 'Magnitude'}},
            "analysis": {
                "filter": {"enabled": self.ui.filter_enabled_checkbox.isChecked(), "text": self.ui.filter_text_edit.text().strip()},
                "time_average": {"enabled": self.ui.time_analysis_mode_combo.currentText() == "时间平均场", "start_frame": self.ui.time_avg_start_spinbox.value(), "end_frame": self.ui.time_avg_end_spinbox.value()}
            },
            "playback": {"frame_skip_step": self.ui.frame_skip_spinbox.value()},
            "export": {"dpi": self.ui.export_dpi.value(), "video_fps": self.ui.video_fps.value(), "video_start_frame": self.ui.video_start_frame.value(), "video_end_frame": self.ui.video_end_frame.value(), "video_grid_w": self.ui.video_grid_w.value(), "video_grid_h": self.ui.video_grid_h.value()},
            "performance": {"gpu": self.ui.gpu_checkbox.isChecked(), "cache": self.ui.cache_size_spinbox.value()}
        }

    def apply_config(self, config: Dict[str, Any]):
        all_widgets = self.ui.control_panel.findChildren(QWidget); [w.blockSignals(True) for w in all_widgets]
        try:
            axes, heatmap, contour, vector, playback, export, perf, analysis = (config.get(k, {}) for k in ["axes", "heatmap", "contour", "vector", "playback", "export", "performance", "analysis"])
            
            self.ui.chart_title_edit.setText(axes.get("title", "")); self.ui.x_axis_formula.setText(axes.get("x_formula", "x")); self.ui.y_axis_formula.setText(axes.get("y_formula", "y"))
            self.ui.heatmap_enabled.setChecked(heatmap.get("enabled", False)); self.ui.heatmap_formula.setText(heatmap.get("formula", "")); self.ui.heatmap_colormap.setCurrentText(heatmap.get("colormap", "viridis")); self.ui.heatmap_vmin.setText(str(heatmap.get("vmin") or "")); self.ui.heatmap_vmax.setText(str(heatmap.get("vmax") or ""))
            self.ui.contour_enabled.setChecked(contour.get("enabled", False)); self.ui.contour_formula.setText(contour.get("formula", "")); self.ui.contour_levels.setValue(contour.get("levels", 10)); self.ui.contour_colors.setCurrentText(contour.get("colors", "black")); self.ui.contour_linewidth.setValue(contour.get("linewidths", 1.0)); self.ui.contour_labels.setChecked(contour.get("show_labels", True))
            
            vt = self.VectorPlotType[vector.get("type", "STREAMLINE")]
            self.ui.vector_plot_type.setCurrentIndex(self.ui.vector_plot_type.findData(vt))
            so = vector.get('streamline_options', {}); sc = self.StreamlineColor.from_str(so.get("color_by"))
            self.ui.stream_color_combo.setCurrentIndex(self.ui.stream_color_combo.findData(sc))
            qo = vector.get('quiver_options', {})
            self.ui.vector_enabled.setChecked(vector.get("enabled", False)); self.ui.vector_u_formula.setText(vector.get("u_formula", "")); self.ui.vector_v_formula.setText(vector.get("v_formula", ""))
            self.ui.quiver_density_spinbox.setValue(qo.get("density", 10)); self.ui.quiver_scale_spinbox.setValue(qo.get("scale", 1.0)); self.ui.stream_density_spinbox.setValue(so.get("density", 1.5)); self.ui.stream_linewidth_spinbox.setValue(so.get("linewidth", 1.0))
            
            filt = analysis.get('filter', {}); self.ui.filter_enabled_checkbox.setChecked(filt.get("enabled", False)); self.ui.filter_text_edit.setText(filt.get("text", ""))
            ta = analysis.get('time_average', {}); self.ui.time_analysis_mode_combo.setCurrentIndex(1 if ta.get("enabled", False) else 0)
            self.ui.time_avg_start_spinbox.setValue(ta.get("start_frame", 0)); self.ui.time_avg_end_spinbox.setValue(ta.get("end_frame", 0))

            self.ui.frame_skip_spinbox.setValue(playback.get("frame_skip_step", 1))
            self.ui.export_dpi.setValue(export.get("dpi", 300)); self.ui.video_fps.setValue(export.get("video_fps", 15)); self.ui.video_start_frame.setValue(export.get("video_start_frame", 0)); self.ui.video_end_frame.setValue(export.get("video_end_frame", 0)); self.ui.video_grid_w.setValue(export.get("video_grid_w", 300)); self.ui.video_grid_h.setValue(export.get("video_grid_h", 300))
            if self.ui.gpu_checkbox.isEnabled(): self.ui.gpu_checkbox.setChecked(perf.get("gpu", False))
            self.ui.cache_size_spinbox.setValue(perf.get("cache", 100)); self.main_window.data_manager.set_cache_size(self.ui.cache_size_spinbox.value())
        finally:
            [w.blockSignals(False) for w in all_widgets]
            self.main_window._update_gpu_status_label(); self.main_window._on_vector_plot_type_changed(); self.main_window._on_time_analysis_mode_changed()
            self.main_window._apply_global_filter()