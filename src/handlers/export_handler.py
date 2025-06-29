#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出功能处理器
"""
import os
import logging
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import QMessageBox, QFileDialog

from src.visualization.video_exporter import VideoExportDialog
from src.ui.dialogs import BatchExportDialog
from src.core.workers import BatchExportWorker

logger = logging.getLogger(__name__)

class ExportHandler:
    """处理所有与导出图像、视频和批量任务相关的逻辑。"""

    def __init__(self, main_window, ui, data_manager, config_handler):
        self.main_window = main_window
        self.ui = ui
        self.dm = data_manager
        self.config_handler = config_handler

        self.output_dir = self.main_window.output_dir
        self.settings_dir = self.config_handler.settings_dir

        self.batch_export_dialog: Optional[BatchExportDialog] = None
        self.batch_export_worker: Optional[BatchExportWorker] = None

    def connect_signals(self):
        self.ui.export_img_btn.clicked.connect(self.export_image)
        self.ui.export_vid_btn.clicked.connect(self.export_video)
        self.ui.batch_export_btn.clicked.connect(self.start_batch_export)
        self.ui.set_output_dir_action.triggered.connect(self._change_output_directory)
        self.ui.change_output_dir_btn.clicked.connect(self._change_output_directory)

    def set_output_dir(self, directory: str):
        self.output_dir = directory
        self.ui.output_dir_line_edit.setText(self.output_dir)

    def _change_output_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self.main_window, "选择输出目录", self.output_dir)
        if new_dir and new_dir != self.output_dir:
            self.set_output_dir(new_dir)
            self.main_window.settings.setValue("output_directory", new_dir)

    def export_image(self):
        fname = os.path.join(self.output_dir, f"frame_{self.main_window.current_frame_index:05d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        if self.ui.plot_widget.save_figure(fname, self.ui.export_dpi.value()):
            QMessageBox.information(self.main_window, "成功", f"图片已保存到:\n{fname}")
        else:
            QMessageBox.warning(self.main_window, "失败", "图片保存失败。")

    def export_video(self):
        s_f, e_f = self.ui.video_start_frame.value(), self.ui.video_end_frame.value()
        if s_f >= e_f:
            QMessageBox.warning(self.main_window, "参数错误", "起始帧必须小于结束帧"); return
        
        fname = os.path.join(self.output_dir, f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        
        current_config = self.config_handler.get_current_config()
        
        p_conf = {
            'x_axis_formula': current_config['axes'].get('x_formula') or 'x',
            'y_axis_formula': current_config['axes'].get('y_formula') or 'y',
            'chart_title': current_config['axes'].get('title', ''),
            'use_gpu': self.ui.gpu_checkbox.isChecked(), 
            'heatmap_config': current_config['heatmap'], 
            'contour_config': current_config['contour'],
            'vector_config': current_config.get('vector', {}),
            'export_dpi': self.ui.export_dpi.value(),
            'grid_resolution': (self.ui.video_grid_w.value(), self.ui.video_grid_h.value()),
            'global_scope': self.dm.global_stats
        }
        VideoExportDialog(self.main_window, self.dm, p_conf, fname, s_f, e_f, self.ui.video_fps.value()).exec()

    def start_batch_export(self):
        if self.dm.get_frame_count() == 0:
            QMessageBox.warning(self.main_window, "无数据", "请先加载数据再执行批量导出。"); return
            
        config_files, _ = QFileDialog.getOpenFileNames(self.main_window, "选择要批量导出的配置文件", self.settings_dir, "JSON files (*.json)")
        if not config_files: return

        self.batch_export_dialog = BatchExportDialog(self.main_window)
        self.batch_export_worker = BatchExportWorker(config_files, self.dm, self.output_dir)
        self.batch_export_worker.progress.connect(self.batch_export_dialog.update_progress)
        self.batch_export_worker.log_message.connect(self.batch_export_dialog.add_log)
        self.batch_export_worker.finished.connect(self.batch_export_dialog.on_finish)
        self.batch_export_worker.finished.connect(self._on_batch_export_finished)
        self.batch_export_dialog.show()
        self.batch_export_worker.start()

    def _on_batch_export_finished(self, summary_message: str):
        if self.batch_export_dialog and self.batch_export_dialog.isVisible():
             QMessageBox.information(self.main_window, "批量导出完成", summary_message)
        else:
             self.ui.status_bar.showMessage(summary_message, 10000)
        self.batch_export_worker = None
        self.batch_export_dialog = None
    
    def on_main_window_close(self):
        """在主窗口关闭时由主窗口调用，用于安全地停止工作线程。"""
        if self.batch_export_worker and self.batch_export_worker.isRunning():
            if QMessageBox.question(self.main_window, "确认", "批量导出正在进行，确定退出吗？") == QMessageBox.StandardButton.Yes:
                self.batch_export_worker.cancel()
                # 尝试安全地断开信号连接
                try:
                    self.batch_export_worker.progress.disconnect()
                    self.batch_export_worker.log_message.disconnect()
                    self.batch_export_worker.finished.disconnect()
                except TypeError: # 如果信号未连接会引发TypeError
                    pass
                self.batch_export_worker.wait(30000) # 增加等待时间，例如30秒
                self.batch_export_worker.deleteLater()
                return True # 表示可以关闭
            else:
                return False # 表示取消关闭
        return True # 表示没有正在运行的worker，可以关闭