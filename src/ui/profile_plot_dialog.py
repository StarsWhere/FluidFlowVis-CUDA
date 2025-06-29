#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一维剖面图对话框
"""
import logging
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any
from scipy.ndimage import map_coordinates

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
    QWidget, QLabel
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

class ProfilePlotDialog(QDialog):
    """显示一维剖面图的对话框。"""
    
    def __init__(self, start_point: Tuple, end_point: Tuple, interpolated_data: Dict, variable_name: str, parent=None):
        super().__init__(parent)
        self.start_point = start_point
        self.end_point = end_point
        self.interp_data = interpolated_data
        self.variable_name = variable_name
        self.profile_data = None

        self.setWindowTitle(f"剖面图: {variable_name or 'N/A'}")
        self.setMinimumSize(800, 600)

        main_layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout()
        title = f"从 ({start_point[0]:.2f}, {start_point[1]:.2f}) 到 ({end_point[0]:.2f}, {end_point[1]:.2f})"
        controls_layout.addWidget(QLabel(title))
        controls_layout.addStretch()
        self.export_button = QPushButton("导出数据...")
        self.export_button.clicked.connect(self.export_data)
        controls_layout.addWidget(self.export_button)
        main_layout.addLayout(controls_layout)

        self.figure = Figure(figsize=(8, 5), dpi=100, tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        main_layout.addWidget(self.canvas)
        
        self.plot_profile()

    def plot_profile(self):
        """计算并绘制剖面数据。"""
        self.ax.clear()
        
        try:
            gx, gy = self.interp_data.get('grid_x'), self.interp_data.get('grid_y')
            heatmap_data = self.interp_data.get('heatmap_data')
            
            if gx is None or gy is None or heatmap_data is None:
                raise ValueError("缺少用于剖面分析的有效插值数据。")

            # 将物理坐标转换为网格索引坐标
            x_coords, y_coords = gx[0, :], gy[:, 0]
            start_idx_x = np.interp(self.start_point[0], x_coords, np.arange(len(x_coords)))
            start_idx_y = np.interp(self.start_point[1], y_coords, np.arange(len(y_coords)))
            end_idx_x = np.interp(self.end_point[0], x_coords, np.arange(len(x_coords)))
            end_idx_y = np.interp(self.end_point[1], y_coords, np.arange(len(y_coords)))
            
            num_points = int(np.hypot(end_idx_x - start_idx_x, end_idx_y - start_idx_y)) * 2
            num_points = max(100, num_points) # 确保至少有100个采样点
            
            line_y_indices = np.linspace(start_idx_y, end_idx_y, num_points)
            line_x_indices = np.linspace(start_idx_x, end_idx_x, num_points)
            
            # 使用map_coordinates进行高效的沿线插值
            profile_values = map_coordinates(heatmap_data, np.vstack((line_y_indices, line_x_indices)), order=1, prefilter=False)
            
            distance = np.hypot(self.end_point[0] - self.start_point[0], self.end_point[1] - self.start_point[1])
            profile_distance = np.linspace(0, distance, num_points)
            
            self.profile_data = pd.DataFrame({
                'distance': profile_distance,
                'value': profile_values
            })

            self.ax.plot(self.profile_data['distance'], self.profile_data['value'])
            self.ax.set_title(f"变量 '{self.variable_name}' 的剖面图")
            self.ax.set_xlabel("沿线的距离")
            self.ax.set_ylabel(f"值 ({self.variable_name})")
            self.ax.grid(True, linestyle='--', alpha=0.6)
            
            formatter = ticker.ScalarFormatter(useMathText=True)
            formatter.set_scientific(True)
            formatter.set_powerlimits((-3, 3))
            self.ax.yaxis.set_major_formatter(formatter)

        except Exception as e:
            logger.error(f"绘制剖面图失败: {e}", exc_info=True)
            self.ax.text(0.5, 0.5, f"绘图失败:\n{e}", ha='center', va='center', transform=self.ax.transAxes, color='red')
            
        self.canvas.draw()

    def export_data(self):
        if self.profile_data is None or self.profile_data.empty:
            QMessageBox.warning(self, "无数据", "没有可导出的剖面数据。")
            return
            
        filepath, _ = QFileDialog.getSaveFileName(self, "保存剖面数据", "", "CSV 文件 (*.csv)")
        if not filepath:
            return
            
        try:
            self.profile_data.to_csv(filepath, index=False)
            QMessageBox.information(self, "成功", f"剖面数据已保存到:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存文件: {e}")