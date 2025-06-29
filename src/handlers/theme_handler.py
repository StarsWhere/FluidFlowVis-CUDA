#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
绘图主题处理器
"""
import os
import json
import logging
from typing import Dict, Any

from PyQt6.QtWidgets import QMessageBox, QInputDialog
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

class ThemeHandler:
    """处理与加载、保存和应用绘图主题相关的逻辑。"""
    
    def __init__(self, main_window, ui):
        self.main_window = main_window
        self.ui = ui
        
        self.themes_dir = os.path.join(os.getcwd(), "settings", "themes")
        os.makedirs(self.themes_dir, exist_ok=True)
        
        # 定义了哪些rcPrams可以被主题保存
        self.savable_params = [
            'figure.facecolor', 'axes.facecolor', 'axes.edgecolor',
            'axes.labelcolor', 'xtick.color', 'ytick.color', 'grid.color',
            'text.color', 'font.family', 'font.size', 'lines.linewidth',
            'lines.markersize', 'grid.linestyle', 'grid.linewidth', 'axes.grid'
        ]

    def connect_signals(self):
        """连接此处理器管理的UI组件的信号。"""
        self.ui.load_theme_btn.clicked.connect(self.apply_selected_theme)
        self.ui.save_theme_btn.clicked.connect(self.save_current_as_theme)

    def populate_theme_combobox(self):
        """填充主题下拉列表。"""
        self.ui.theme_combo.blockSignals(True)
        self.ui.theme_combo.clear()
        
        # 创建默认和暗色主题
        self._create_default_themes_if_not_exist()

        try:
            theme_files = sorted([f for f in os.listdir(self.themes_dir) if f.endswith('.json')])
            self.ui.theme_combo.addItems(theme_files)
        except Exception as e:
            logger.error(f"读取主题目录失败: {e}")
            
        self.ui.theme_combo.blockSignals(False)

    def _create_default_themes_if_not_exist(self):
        """如果默认主题文件不存在，则创建它们。"""
        default_theme_path = os.path.join(self.themes_dir, "default.json")
        if not os.path.exists(default_theme_path):
            with plt.style.context('default'):
                theme_data = self._get_savable_rcparams()
            with open(default_theme_path, 'w', encoding='utf-8') as f:
                json.dump(theme_data, f, indent=4)

        dark_theme_path = os.path.join(self.themes_dir, "dark_mode.json")
        if not os.path.exists(dark_theme_path):
            dark_theme = {
                "figure.facecolor": "#1e1e1e", "axes.facecolor": "#2c2c2c",
                "axes.edgecolor": "#bbbbbb", "axes.labelcolor": "#cccccc",
                "xtick.color": "#cccccc", "ytick.color": "#cccccc",
                "grid.color": "#555555", "text.color": "#dddddd",
                "font.family": "sans-serif", "font.size": 10.0,
                "lines.linewidth": 1.5, "lines.markersize": 6.0,
                "grid.linestyle": "--", "grid.linewidth": 0.8, "axes.grid": True
            }
            with open(dark_theme_path, 'w', encoding='utf-8') as f:
                json.dump(dark_theme, f, indent=4)
    
    def apply_selected_theme(self):
        """应用下拉列表中选定的主题。"""
        theme_name = self.ui.theme_combo.currentText()
        if not theme_name: return

        filepath = os.path.join(self.themes_dir, theme_name)
        if not os.path.exists(filepath):
            QMessageBox.critical(self.main_window, "文件不存在", f"主题文件 '{theme_name}' 已不存在。")
            self.populate_theme_combobox()
            return
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                theme_data = json.load(f)
            
            # 应用主题
            plt.style.use('default') # First reset to default to clear old settings
            plt.rcParams.update(theme_data)

            # 强制刷新UI
            self.main_window.ui.plot_widget._setup_plot_style()
            self.main_window._force_refresh_plot(reset_view=False)
            
            self.main_window.ui.status_bar.showMessage(f"已应用主题: {theme_name}", 3000)
            
        except Exception as e:
            QMessageBox.critical(self.main_window, "应用失败", f"无法应用主题 '{theme_name}':\n{e}")

    def _get_savable_rcparams(self) -> Dict[str, Any]:
        """获取当前Matplotlib配置中可保存的参数。"""
        current_theme = {}
        for key in self.savable_params:
            try:
                current_theme[key] = plt.rcParams[key]
            except KeyError:
                logger.warning(f"无法找到主题参数 '{key}'，将跳过。")
        return current_theme

    def save_current_as_theme(self):
        """将当前的绘图风格保存为一个新的主题文件。"""
        text, ok = QInputDialog.getText(self.main_window, "另存为主题", "请输入新主题的名称:")
        if not (ok and text): return

        filename = f"{text}.json" if not text.endswith('.json') else text
        filepath = os.path.join(self.themes_dir, filename)
        
        if os.path.exists(filepath):
            reply = QMessageBox.question(self.main_window, "确认覆盖", f"主题文件 '{filename}' 已存在。是否覆盖？")
            if reply != QMessageBox.StandardButton.Yes: return
        
        try:
            current_theme_data = self._get_savable_rcparams()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(current_theme_data, f, indent=4)
                
            self.main_window.ui.status_bar.showMessage(f"主题已保存到 {filename}", 3000)
            self.populate_theme_combobox()
            self.ui.theme_combo.setCurrentText(filename)
        except Exception as e:
            QMessageBox.critical(self.main_window, "保存失败", f"无法写入主题文件 '{filename}':\n{e}")