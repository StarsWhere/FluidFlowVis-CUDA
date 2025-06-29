#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间序列图表对话框
"""
import logging
import numpy as np
import os # Import os for path operations
from datetime import datetime # Import datetime for unique filenames
from typing import Tuple, Optional
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QWidget, QMessageBox, QFileDialog # Add QMessageBox, QFileDialog
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

class TimeSeriesDialog(QDialog):
    """一个显示时间序列及其FFT的对话框。"""
    
    def __init__(self, point_coords: Tuple[float, float], data_manager, filter_clause: str, parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self.point_coords = point_coords
        self.filter_clause = filter_clause
        self.current_df = None
        
        self.setWindowTitle(f"时间序列分析 @ ({point_coords[0]:.2f}, {point_coords[1]:.2f})")
        self.setMinimumSize(800, 700)

        main_layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("选择变量:"))
        self.variable_combo = QComboBox()
        self.variable_combo.addItems(self.dm.get_variables())
        self.variable_combo.currentIndexChanged.connect(self.plot_data)
        controls_layout.addWidget(self.variable_combo)
        controls_layout.addStretch()
        self.fft_button = QPushButton("计算 FFT")
        self.fft_button.clicked.connect(self.plot_fft)
        self.fft_button.setEnabled(False)
        controls_layout.addWidget(self.fft_button)

        self.export_fft_button = QPushButton("导出 FFT 结果")
        self.export_fft_button.clicked.connect(self.export_fft_results)
        self.export_fft_button.setEnabled(False)
        controls_layout.addWidget(self.export_fft_button)
        main_layout.addLayout(controls_layout)

        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        # 创建两个子图，一个用于时间序列，一个用于FFT
        self.ax_time = self.figure.add_subplot(2, 1, 1)
        self.ax_fft = self.figure.add_subplot(2, 1, 2)
        main_layout.addWidget(self.canvas)
        
        self.figure.tight_layout(pad=3.0)
        self.plot_data()

    def plot_data(self):
        selected_variable = self.variable_combo.currentText()
        if not selected_variable: return

        self.ax_time.clear(); self.ax_fft.clear()
        self.ax_fft.set_yticklabels([]); self.ax_fft.set_xticklabels([])
        self.ax_fft.set_title("快速傅里叶变换 (FFT)")
        self.ax_fft.set_xlabel("频率 (Hz)")
        self.ax_fft.set_ylabel("振幅")
        
        try:
            # Use a slightly larger tolerance for picking points
            x_range = self.dm.global_stats.get('x_global_max', 1) - self.dm.global_stats.get('x_global_min', 0)
            y_range = self.dm.global_stats.get('y_global_max', 1) - self.dm.global_stats.get('y_global_min', 0)
            tolerance = max(x_range * 0.01, y_range * 0.01, 1e-6)

            self.current_df = self.dm.get_timeseries_at_point(selected_variable, self.point_coords, tolerance)

            if self.current_df is None or self.current_df.empty:
                self.ax_time.text(0.5, 0.5, "在此位置找不到时间序列数据", ha='center', va='center', transform=self.ax_time.transAxes)
                self.fft_button.setEnabled(False)
                self.export_fft_button.setEnabled(False)
            else:
                self.ax_time.plot(self.current_df['timestamp'], self.current_df[selected_variable], marker='.', linestyle='-')
                self.ax_time.set_title(f"'{selected_variable}' 的时间演化")
                self.ax_time.set_xlabel("时间戳")
                self.ax_time.set_ylabel(f"值 ({selected_variable})")
                self.ax_time.grid(True, linestyle='--', alpha=0.6)
                
                formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
                self.ax_time.yaxis.set_major_formatter(formatter)
                
                is_valid_for_fft = len(self.current_df) > 1 and np.all(np.diff(self.current_df['timestamp']) > 0)
                self.fft_button.setEnabled(is_valid_for_fft)
                self.export_fft_button.setEnabled(False) # FFT not computed yet

        except Exception as e:
            logger.error(f"绘制时间序列图失败: {e}", exc_info=True)
            self.ax_time.text(0.5, 0.5, f"绘图失败:\n{e}", ha='center', va='center', color='red')
            self.fft_button.setEnabled(False)
            self.export_fft_button.setEnabled(False)
            
        self.canvas.draw()

    def plot_fft(self):
        if self.current_df is None or self.current_df.empty: return
        
        selected_variable = self.variable_combo.currentText()
        signal = self.current_df[selected_variable].values
        timestamps = self.current_df['timestamp'].values
        
        N = len(signal)
        if N < 2: return
        
        time_diffs = np.diff(timestamps)
        if np.any(time_diffs <= 0):
            self.ax_fft.clear()
            self.ax_fft.text(0.5, 0.5, "时间戳不均匀或无效，无法计算FFT", ha='center', color='red')
            self.canvas.draw()
            self.export_fft_button.setEnabled(False)
            return
            
        T = np.mean(time_diffs)

        self.yf = np.fft.fft(signal - np.mean(signal)) # 减去均值
        self.xf = np.fft.fftfreq(N, T)[:N//2]
        
        self.ax_fft.clear()
        self.ax_fft.plot(self.xf, 2.0/N * np.abs(self.yf[0:N//2]))
        self.ax_fft.set_title(f"'{selected_variable}' 的快速傅里叶变换 (FFT)")
        self.ax_fft.set_xlabel("频率 (Hz)")
        self.ax_fft.set_ylabel("振幅")
        self.ax_fft.grid(True, linestyle='--', alpha=0.6)
        self.canvas.draw()
        self.export_fft_button.setEnabled(True)

    def export_fft_results(self):
        if self.xf is None or self.yf is None:
            logger.warning("没有可导出的 FFT 结果。请先计算 FFT。")
            return

        import pandas as pd
        
        # 获取默认输出目录 (假设 DataManager 有一个 output_dir 属性)
        # 如果没有，可能需要从主窗口或其他地方获取
        output_dir = getattr(self.dm, 'output_dir', os.path.join(os.getcwd(), 'output'))
        os.makedirs(output_dir, exist_ok=True) # 确保目录存在

        # 生成默认文件名，包含时间戳以确保唯一性
        default_filename = f"fft_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_name = os.path.join(output_dir, default_filename)
        
        try:
            # 提取振幅部分
            amplitudes = 2.0/len(self.yf) * np.abs(self.yf[0:len(self.yf)//2])
            
            df_fft = pd.DataFrame({
                '频率 (Hz)': self.xf,
                '振幅': amplitudes
            })
            df_fft.to_csv(file_name, index=False)
            logger.info(f"FFT 结果已成功导出到 {file_name}")
            QMessageBox.information(self, "成功", f"FFT 结果已成功导出到:\n{file_name}")
        except Exception as e:
            logger.error(f"导出 FFT 结果失败: {e}", exc_info=True)
            QMessageBox.critical(self, "导出失败", f"导出 FFT 结果失败:\n{e}")