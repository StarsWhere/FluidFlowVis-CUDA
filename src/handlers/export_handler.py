# src/handlers/export_handler.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出功能处理器
"""
import os
import logging
from datetime import datetime
from typing import Optional, List

from PyQt6.QtWidgets import QMessageBox, QFileDialog
from src.visualization.video_exporter import VideoExportDialog
from src.ui.dialogs import BatchExportDialog, ConfigSelectionDialog, VariableSelectionDialog, ImportDialog as ProgressDialog
from src.core.workers import BatchExportWorker, DataExportWorker
from src.core.formula_engine import FormulaEngine # 引入FormulaEngine

logger = logging.getLogger(__name__)

class ExportHandler:
    """处理所有与导出图像、视频和数据相关的逻辑。"""

    def __init__(self, main_window, ui, data_manager, config_handler):
        self.main_window = main_window
        self.ui = ui
        self.dm = data_manager
        self.config_handler = config_handler
        self.formula_engine = main_window.formula_engine # 获取公式引擎实例

        self.output_dir = self.main_window.output_dir
        self.settings_dir = self.config_handler.settings_dir

        self.batch_export_dialog: Optional[BatchExportDialog] = None
        self.batch_export_worker: Optional[BatchExportWorker] = None
        self.data_export_worker: Optional[DataExportWorker] = None

    def connect_signals(self):
        self.ui.export_img_btn.clicked.connect(self.export_image)
        self.ui.export_vid_btn.clicked.connect(self.export_video)
        self.ui.batch_export_btn.clicked.connect(self.start_batch_export)
        self.ui.set_output_dir_action.triggered.connect(self._change_output_directory)
        self.ui.change_output_dir_btn.clicked.connect(self._change_output_directory)
        self.ui.export_data_csv_btn.clicked.connect(self.export_data) # MODIFIED

    def set_output_dir(self, directory: str):
        self.output_dir = directory
        os.makedirs(self.output_dir, exist_ok=True)
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
        """
        [OPTIMIZED] 导出视频。
        现在会分析配置，只将必需的变量列表传递给导出工作线程。
        """
        s_f, e_f = self.ui.video_start_frame.value(), self.ui.video_end_frame.value()
        if s_f >= e_f:
            QMessageBox.warning(self.main_window, "参数错误", "起始帧必须小于结束帧"); return
        
        config_name = os.path.splitext(os.path.basename(self.config_handler.current_config_file or "default"))[0]
        fname = os.path.join(self.output_dir, f"video_{config_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        
        current_config = self.config_handler.get_current_config()
        
        # [OPTIMIZED] 分析可视化配置，找出所有必需的变量
        required_vars = set()
        formulas = [
            current_config['axes'].get('x_formula', 'x'),
            current_config['axes'].get('y_formula', 'y')
        ]
        if current_config['heatmap'].get('enabled'):
            formulas.append(current_config['heatmap'].get('formula'))
        if current_config['contour'].get('enabled'):
            formulas.append(current_config['contour'].get('formula'))
        if current_config['vector'].get('enabled'):
            formulas.append(current_config['vector'].get('u_formula'))
            formulas.append(current_config['vector'].get('v_formula'))

        for f in filter(None, formulas):
            required_vars.update(self.formula_engine.get_used_variables(f))
        
        logger.info(f"视频导出任务启动，按需加载变量: {required_vars}")

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
            'global_scope': self.dm.global_stats,
            'required_variables': list(required_vars)  # [OPTIMIZED] 传递必需变量列表
        }
        VideoExportDialog(self.main_window, self.dm, p_conf, fname, s_f, e_f, self.ui.video_fps.value()).exec()

    def start_batch_export(self):
        if self.dm.get_frame_count() == 0:
            QMessageBox.warning(self.main_window, "无数据", "请先加载数据再执行批量导出。"); return
            
        dialog = ConfigSelectionDialog(self.settings_dir, self.main_window)
        if not dialog.exec(): return

        config_files = dialog.selected_files()
        if not config_files:
            QMessageBox.information(self.main_window, "无选择", "您没有选择任何配置文件。")
            return

        self.batch_export_dialog = BatchExportDialog(self.main_window)
        # 传递 FormulaEngine 实例给批量导出工作线程
        self.batch_export_worker = BatchExportWorker(config_files, self.dm, self.output_dir, self.formula_engine)
        
        self.batch_export_worker.progress.connect(self.batch_export_dialog.update_progress)
        self.batch_export_worker.log_message.connect(self.batch_export_dialog.add_log)
        self.batch_export_worker.summary_ready.connect(self.batch_export_dialog.on_finish)
        self.batch_export_worker.summary_ready.connect(self._on_batch_export_summary_ready)
        self.batch_export_worker.finished.connect(self._on_batch_export_thread_finished)

        self.batch_export_dialog.show()
        self.batch_export_worker.start()

    def export_data(self):
        """
        [MODIFIED] 导出数据，支持选择变量和文件格式。
        """
        if self.dm.get_frame_count() == 0:
            QMessageBox.warning(self.main_window, "无数据", "请先加载数据再导出。")
            return

        # 1. 弹出对话框让用户选择变量
        all_vars = self.dm.get_variables(include_id=True)
        var_dialog = VariableSelectionDialog(all_vars, self.main_window)
        if not var_dialog.exec():
            return  # 用户取消

        selected_vars = var_dialog.get_selected_variables()
        if not selected_vars:
            QMessageBox.information(self.main_window, "无选择", "您没有选择任何要导出的变量。")
            return

        # 2. 弹出文件保存对话框，让用户选择格式
        default_name = f"exported_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        file_filter = "Parquet 文件 (*.parquet);;CSV 文件 (*.csv)"
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self.main_window,
            "导出数据到文件",
            os.path.join(self.output_dir, default_name),
            file_filter
        )

        if not filepath:
            return # 用户取消

        # 3. 准备并启动工作线程
        progress = ProgressDialog(self.main_window, "正在导出数据...")
        filter_clause = self.dm.global_filter_clause if self.ui.filter_enabled_checkbox.isChecked() else ""
        
        self.data_export_worker = DataExportWorker(self.dm, filepath, filter_clause, selected_vars)
        self.data_export_worker.progress.connect(progress.update_progress)
        self.data_export_worker.finished.connect(lambda f=filepath: QMessageBox.information(self.main_window, "成功", f"数据已成功导出到:\n{f}"))
        self.data_export_worker.finished.connect(progress.accept)
        self.data_export_worker.error.connect(lambda msg: QMessageBox.critical(self.main_window, "导出失败", msg))
        self.data_export_worker.error.connect(progress.accept)
        
        self.data_export_worker.start()
        progress.exec()

    def _on_batch_export_summary_ready(self, summary_message: str):
        if self.batch_export_dialog and self.batch_export_dialog.isVisible():
             QMessageBox.information(self.main_window, "批量导出完成", summary_message)
        else:
             self.ui.status_bar.showMessage(summary_message, 10000)

    def _on_batch_export_thread_finished(self):
        logger.info("BatchExportWorker thread has finished. Cleaning up references.")
        self.batch_export_worker = None
        self.batch_export_dialog = None
    
    def on_main_window_close(self):
        if self.batch_export_worker and self.batch_export_worker.isRunning():
            if QMessageBox.question(self.main_window, "确认", "批量导出正在进行，确定退出吗？") == QMessageBox.StandardButton.Yes:
                self.batch_export_worker.cancel()
                try:
                    self.batch_export_worker.progress.disconnect()
                    self.batch_export_worker.log_message.disconnect()
                    self.batch_export_worker.summary_ready.disconnect()
                    self.batch_export_worker.finished.disconnect()
                except TypeError:
                    pass
                self.batch_export_worker.wait(30000)
                # self.batch_export_worker.deleteLater() # This can be problematic
                return True
            else:
                return False
        return True