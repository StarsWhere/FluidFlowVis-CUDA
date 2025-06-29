#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台工作线程模块
"""
import os
import json
import logging
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop

from src.core.data_manager import DataManager
from src.core.statistics_calculator import StatisticsCalculator
from src.visualization.video_exporter import VideoExportWorker

logger = logging.getLogger(__name__)

# --- 新增：数据扫描功能 ---

class DataScanWorker(QThread):
    """在后台线程中扫描数据目录，避免UI阻塞。"""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list, list) # 返回 file_index 和 variables
    error = pyqtSignal(str)

    def __init__(self, directory: str, parent=None):
        super().__init__(parent)
        self.directory = directory
    
    def run(self):
        try:
            logger.info(f"后台扫描开始: {self.directory}")
            csv_files = sorted([f for f in os.listdir(self.directory) if f.lower().endswith('.csv')])
            
            if not csv_files:
                self.finished.emit([], [])
                return
            
            self.progress.emit(0, len(csv_files), f"正在分析 {csv_files[0]}...")
            
            # 从第一个文件中读取数值列作为基准变量列表
            first_file_path = os.path.join(self.directory, csv_files[0])
            df_sample = pd.read_csv(first_file_path, nrows=10)
            base_variables = {col for col in df_sample.columns if pd.api.types.is_numeric_dtype(df_sample[col])}

            if not base_variables:
                raise ValueError("第一个CSV文件中未找到任何数值类型的列。")

            file_index = []
            for i, filename in enumerate(csv_files):
                self.progress.emit(i, len(csv_files), f"正在索引 {filename}...")
                file_index.append({'path': os.path.join(self.directory, filename), 'timestamp': i})
            
            self.finished.emit(file_index, sorted(list(base_variables)))
        except Exception as e:
            logger.error(f"扫描数据目录失败: {e}", exc_info=True)
            self.error.emit(str(e))

# --- 批量导出功能 ---

class BatchExportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, config_files: List[str], data_manager: DataManager, output_dir: str, parent=None):
        super().__init__(parent)
        self.config_files = config_files
        self.data_manager = data_manager
        self.output_dir = output_dir
        self.is_cancelled = False

    def run(self):
        successful, failed = 0, 0
        total = len(self.config_files)

        current_video_worker = None

        for i, filepath in enumerate(self.config_files):
            if self.is_cancelled:
                if current_video_worker and current_video_worker.isRunning():
                    current_video_worker.cancel()
                    current_video_worker.wait()
                break
            
            filename = os.path.basename(filepath)
            self.progress.emit(i, total, filename)
            self.log_message.emit(f"正在读取配置文件: {filename}")

            try:
                with open(filepath, 'r', encoding='utf-8') as f: config = json.load(f)
                
                axes_cfg, export_cfg = config.get('axes', {}), config.get("export", {})
                
                p_conf = {
                    'x_axis_formula': axes_cfg.get('x_formula', 'x'), 'y_axis_formula': axes_cfg.get('y_formula', 'y'),
                    'chart_title': axes_cfg.get('title', ''), 'use_gpu': config.get('performance', {}).get('gpu', False),
                    'heatmap_config': config.get('heatmap', {}), 'contour_config': config.get('contour', {}),
                    'vector_config': config.get('vector', {}),
                    'grid_resolution': (export_cfg.get("video_grid_w", 300), export_cfg.get("video_grid_h", 300)),
                    'export_dpi': export_cfg.get("dpi", 300), 'global_scope': self.data_manager.global_stats
                }
                
                s_f = export_cfg.get("video_start_frame", 0)
                e_f = export_cfg.get("video_end_frame", self.data_manager.get_frame_count() - 1)
                fps = export_cfg.get("video_fps", 15)

                if s_f >= e_f: raise ValueError("起始帧必须小于结束帧")

                config_name = os.path.splitext(filename)[0]
                out_fname = os.path.join(self.output_dir, f"batch_{config_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
                self.log_message.emit(f"准备导出视频: {os.path.basename(out_fname)}")
                
                current_video_worker = VideoExportWorker(self.data_manager, p_conf, out_fname, s_f, e_f, fps)
                loop = QEventLoop()
                export_success, export_message = False, ""

                def on_video_finished(success, msg):
                    nonlocal export_success, export_message
                    export_success, export_message = success, msg
                    loop.quit()

                current_video_worker.export_finished.connect(on_video_finished)
                current_video_worker.progress_updated.connect(lambda cur, tot, msg: self.log_message.emit(f"  └ {msg}"))
                current_video_worker.start(); loop.exec(); current_video_worker.deleteLater()

                if export_success: self.log_message.emit(f"成功: {filename}"); successful += 1
                else: self.log_message.emit(f"失败: {filename}. 原因: {export_message}"); failed += 1

            except Exception as e:
                self.log_message.emit(f"处理 '{filename}' 时发生严重错误: {e}"); failed += 1
        
        if current_video_worker and current_video_worker.isRunning():
            logger.warning("BatchExportWorker 结束时发现 video_worker 仍在运行，尝试取消并等待。")
            current_video_worker.cancel()
            current_video_worker.wait(30000)
            current_video_worker.deleteLater()

        self.finished.emit(f"成功导出 {successful} 个视频，失败 {failed} 个。")

    def cancel(self): self.is_cancelled = True

# --- 全局统计功能 ---

class GlobalStatsWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.calculator = StatisticsCalculator(data_manager)

    def run(self):
        try:
            calculated_data = self.calculator.calculate_global_stats(lambda c, t: self.progress.emit(c, t))
            stats_results = calculated_data.get("stats", {})
            formula_descriptions = calculated_data.get("formulas", {})
            self.data_manager.custom_global_formulas.update(formula_descriptions)
            self.finished.emit(stats_results)
        except Exception as e:
            logger.error(f"全局统计计算失败: {e}", exc_info=True)
            self.error.emit(str(e))

class CustomGlobalStatsWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, definitions: List[str], parent=None):
        super().__init__(parent)
        self.calculator = StatisticsCalculator(data_manager)
        self.definitions = definitions
        self.data_manager = data_manager

    def run(self):
        try:
            base_stats = self.data_manager.global_stats
            if not base_stats:
                raise RuntimeError("计算自定义常量前，必须先计算基础统计数据。")
            
            calculated_data = self.calculator.calculate_custom_global_stats(
                self.definitions, base_stats, lambda c, t, m: self.progress.emit(c, t, m)
            )
            
            new_stats = calculated_data.get("stats", {})
            new_formulas = calculated_data.get("formulas", {})
            self.data_manager.custom_global_formulas.update(new_formulas)
            self.finished.emit(new_stats)
        except Exception as e:
            logger.error(f"自定义全局常量计算失败: {e}", exc_info=True)
            self.error.emit(str(e))