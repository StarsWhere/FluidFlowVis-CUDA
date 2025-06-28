#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台工作线程模块
"""
import os
import json
import logging
from typing import List, Dict
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop

from src.core.data_manager import DataManager
from src.visualization.video_exporter import VideoExportWorker

logger = logging.getLogger(__name__)

# --- 批量导出功能 ---

class BatchExportWorker(QThread):
    """在后台执行批量视频导出任务的工作线程。"""
    progress = pyqtSignal(int, int, str)  # current_index, total, filename
    log_message = pyqtSignal(str)
    finished = pyqtSignal(str)  # summary_message

    def __init__(self, config_files: List[str], data_manager: DataManager, output_dir: str, parent=None):
        super().__init__(parent)
        self.config_files = config_files
        self.data_manager = data_manager
        self.output_dir = output_dir
        self.is_cancelled = False

    def run(self):
        successful_exports = 0
        failed_exports = 0
        total_files = len(self.config_files)

        for i, filepath in enumerate(self.config_files):
            if self.is_cancelled:
                break
            
            filename = os.path.basename(filepath)
            self.progress.emit(i, total_files, filename)
            self.log_message.emit(f"正在读取配置文件: {filename}")

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 从配置文件中提取所有需要的参数
                axes_cfg = config.get('axes', {})
                export_cfg = config.get("export", {})
                
                p_conf = {
                    'x_axis': axes_cfg.get('x', 'x'),
                    'y_axis': axes_cfg.get('y', 'y'),
                    'x_axis_formula': axes_cfg.get('x_formula', ''),
                    'y_axis_formula': axes_cfg.get('y_formula', ''),
                    'use_gpu': config.get('performance', {}).get('gpu', False),
                    'heatmap_config': config.get('heatmap', {}),
                    'contour_config': config.get('contour', {}),
                    'global_scope': self.data_manager.global_stats
                }
                
                s_f = export_cfg.get("video_start_frame", 0)
                e_f = export_cfg.get("video_end_frame", self.data_manager.get_frame_count() - 1)
                fps = export_cfg.get("video_fps", 15)

                if s_f >= e_f:
                    raise ValueError("起始帧必须小于结束帧")

                config_name = os.path.splitext(filename)[0]
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                out_fname = os.path.join(self.output_dir, f"batch_{config_name}_{timestamp}.mp4")

                self.log_message.emit(f"准备导出视频: {os.path.basename(out_fname)}")
                
                video_worker = VideoExportWorker(self.data_manager, p_conf, out_fname, s_f, e_f, fps)
                
                loop = QEventLoop()
                export_success = False
                export_message = ""

                def on_video_finished(success, msg):
                    nonlocal export_success, export_message
                    export_success = success
                    export_message = msg
                    loop.quit()

                video_worker.export_finished.connect(on_video_finished)
                video_worker.progress_updated.connect(lambda cur, tot, msg: self.log_message.emit(f"  └ {msg}"))
                
                video_worker.start()
                loop.exec()

                if export_success:
                    self.log_message.emit(f"成功: {filename} -> {os.path.basename(out_fname)}")
                    successful_exports += 1
                else:
                    self.log_message.emit(f"失败: {filename}. 原因: {export_message}")
                    failed_exports += 1

            except Exception as e:
                self.log_message.emit(f"处理配置文件 '{filename}' 时发生严重错误: {e}")
                failed_exports += 1
        
        summary = f"成功导出 {successful_exports} 个视频，失败 {failed_exports} 个。"
        self.finished.emit(summary)

    def cancel(self):
        self.is_cancelled = True

# --- 全局统计功能 ---

class GlobalStatsWorker(QThread):
    """在后台计算全局统计数据"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager

    def run(self):
        try:
            results = self.data_manager.calculate_global_stats(
                lambda current, total: self.progress.emit(current, total)
            )
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"全局统计计算失败: {e}", exc_info=True)
            self.error.emit(str(e))

class CustomGlobalStatsWorker(QThread):
    """在后台计算自定义全局常量"""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, definitions: List[str], parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.definitions = definitions
    
    def run(self):
        try:
            results = self.data_manager.calculate_custom_global_stats(
                self.definitions,
                lambda current, total, msg: self.progress.emit(current, total, msg)
            )
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"自定义全局常量计算失败: {e}", exc_info=True)
            self.error.emit(str(e))