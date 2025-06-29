#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一维剖面图对话框
"""
import logging
import os
from datetime import datetime
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any
from scipy.ndimage import map_coordinates

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox,
    QLabel, QComboBox
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

class ProfilePlotDialog(QDialog):
    """显示一维剖面图的对话框，支持多变量选择。"""
    
    def __init__(self, start_point: Tuple, end_point: Tuple, interpolated_data: Dict, 
                 available_variables: Dict[str, str], output_dir: str, parent=None):
        super().__init__(parent)
        self.start_point = start_point
        self.end_point = end_point
        self.interp_data = interpolated_data
        self.available_variables = available_variables
        self.output_dir = output_dir
        self.profile_data_cache = {}

        self.setWindowTitle("一维剖面图分析")
        self.setMinimumSize(800, 600)

        main_layout = QVBoxLayout(self)

        # --- Controls Layout ---
        controls_layout = QHBoxLayout()
        # 使用科学计数法格式化坐标
        title = f"从 (X: {start_point[0]:.2e}, Y: {start_point[1]:.2e}) 到 (X: {end_point[0]:.2e}, Y: {end_point[1]:.2e})"
        controls_layout.addWidget(QLabel(title))
        controls_layout.addStretch()
        
        controls_layout.addWidget(QLabel("变量:"))
        self.variable_combo = QComboBox()
        self.populate_variables()
        self.variable_combo.currentIndexChanged.connect(self._update_plot)
        controls_layout.addWidget(self.variable_combo)

        self.export_button = QPushButton("一键导出数据")
        self.export_button.setToolTip(f"将当前剖面数据导出到项目输出目录")
        self.export_button.clicked.connect(self.export_data)
        controls_layout.addWidget(self.export_button)
        main_layout.addLayout(controls_layout)

        # --- Matplotlib Canvas ---
        self.figure = Figure(figsize=(8, 5), dpi=100, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        main_layout.addWidget(self.canvas)
        
        # --- Initial Plot ---
        self._update_plot()

    def populate_variables(self):
        """用可用变量填充下拉菜单。"""
        for key, formula in sorted(self.available_variables.items()):
            display_text = f"{key} ({formula})" if formula else key
            self.variable_combo.addItem(display_text, key)
        
        if 'heatmap' in self.available_variables:
             self.variable_combo.setCurrentText(f"heatmap ({self.available_variables['heatmap']})")

    def _calculate_profile(self, variable_key: str) -> pd.DataFrame:
        """为单个变量计算剖面数据，并缓存结果。"""
        if variable_key in self.profile_data_cache:
            return self.profile_data_cache[variable_key]

        gx, gy = self.interp_data.get('grid_x'), self.interp_data.get('grid_y')
        target_data = self.interp_data.get(f'{variable_key}_data')

        if gx is None or gy is None or target_data is None:
            raise ValueError(f"缺少变量 '{variable_key}' 的有效插值数据。")

        x_coords, y_coords = gx[0, :], gy[:, 0]
        start_idx_x = np.interp(self.start_point[0], x_coords, np.arange(len(x_coords)))
        start_idx_y = np.interp(self.start_point[1], y_coords, np.arange(len(y_coords)))
        end_idx_x = np.interp(self.end_point[0], x_coords, np.arange(len(x_coords)))
        end_idx_y = np.interp(self.end_point[1], y_coords, np.arange(len(y_coords)))
        
        num_points = int(np.hypot(end_idx_x - start_idx_x, end_idx_y - start_idx_y)) * 2
        num_points = max(100, num_points)
        
        line_y_indices = np.linspace(start_idx_y, end_idx_y, num_points)
        line_x_indices = np.linspace(start_idx_x, end_idx_x, num_points)
        
        profile_values = map_coordinates(target_data, np.vstack((line_y_indices, line_x_indices)), order=1, prefilter=False)
        
        distance = np.hypot(self.end_point[0] - self.start_point[0], self.end_point[1] - self.start_point[1])
        profile_distance = np.linspace(0, distance, num_points)
        
        df = pd.DataFrame({'distance': profile_distance, 'value': profile_values})
        self.profile_data_cache[variable_key] = df
        return df

    def _update_plot(self):
        """根据下拉菜单的选择，计算并绘制剖面数据。"""
        self.ax.clear()
        selected_key = self.variable_combo.currentData()
        if not selected_key:
            self.ax.text(0.5, 0.5, "请选择一个变量进行分析", ha='center'); self.canvas.draw(); return

        try:
            df = self._calculate_profile(selected_key)
            self.ax.plot(df['distance'], df['value'])
            
            display_text = self.variable_combo.currentText()
            self.ax.set_title(f"变量剖面图: {display_text}")
            self.ax.set_xlabel("沿线的距离")
            self.ax.set_ylabel(f"值")
            self.ax.grid(True, linestyle='--', alpha=0.6)
            
            formatter = ticker.ScalarFormatter(useMathText=True)
            formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
            self.ax.yaxis.set_major_formatter(formatter)

        except Exception as e:
            logger.error(f"绘制剖面图失败: {e}", exc_info=True)
            self.ax.text(0.5, 0.5, f"绘图失败:\n{e}", ha='center', color='red')
            
        self.canvas.draw()

    def export_data(self):
        selected_key = self.variable_combo.currentData()
        if not selected_key or selected_key not in self.profile_data_cache:
            QMessageBox.warning(self, "无数据", "没有可导出的剖面数据。"); return
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 将坐标添加到文件名中，使用科学计数法
        start_x, start_y = self.start_point
        end_x, end_y = self.end_point
        filename = f"profile_{selected_key}_from_x{start_x:.2e}_y{start_y:.2e}_to_x{end_x:.2e}_y{end_y:.2e}_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)
            
        try:
            df_to_export = self.profile_data_cache[selected_key].copy()
            # 更改列头为英文
            df_to_export.rename(columns={'distance': 'Distance', 'value': 'Value'}, inplace=True)
            df_to_export.to_csv(filepath, index=False)
            QMessageBox.information(self, "成功", f"剖面数据已保存到:\n{filepath}")
        except Exception as e:
            logger.error(f"保存剖面数据失败: {e}", exc_info=True)
            QMessageBox.critical(self, "保存失败", f"无法保存文件: {e}")