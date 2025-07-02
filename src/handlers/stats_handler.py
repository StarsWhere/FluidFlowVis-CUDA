#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局统计处理器 (Parquet Backend)
"""
import logging
import os
from PyQt6.QtWidgets import QMessageBox
from src.ui.dialogs import StatsProgressDialog
from src.core.workers import GlobalStatsWorker

logger = logging.getLogger(__name__)

class StatsHandler:
    """处理所有与全局统计计算、UI更新和导出相关的逻辑。"""

    def __init__(self, main_window, ui, data_manager, formula_engine):
        self.main_window = main_window
        self.ui = ui
        self.dm = data_manager
        self.formula_engine = formula_engine
        self.stats_progress_dialog = None
        self.stats_worker = None

    def connect_signals(self):
        """连接此处理器管理的UI组件的信号。"""
        self.ui.recalc_basic_stats_btn.clicked.connect(self.start_global_stats_calculation)
        # Other signals remain disconnected for now

    def reset_global_stats(self):
        """当数据重载时调用，重置统计信息和UI状态。"""
        self.dm.global_stats.clear()
        self.formula_engine.update_custom_global_variables({})
        self.ui.stats_results_text.setText("数据已重载。")
        self.ui.recalc_basic_stats_btn.setEnabled(False)

    def load_and_display_stats(self):
        """从DataManager加载统计信息并更新UI。"""
        self.dm.load_global_stats()
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.update_stats_display()
        self.ui.recalc_basic_stats_btn.setEnabled(self.dm.is_project_ready())

    def start_global_stats_calculation(self):
        """为当前活动的数据集强制重新计算基础统计数据。"""
        if not self.dm.active_dataset_uri:
            QMessageBox.warning(self.main_window, "无数据", "请先加载或创建一个数据集。")
            return
            
        reply = QMessageBox.question(self.main_window, "确认", "这将为当前活动数据集的所有数值变量重新计算基础统计数据(min, max, mean)并覆盖现有值。是否继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        self.stats_progress_dialog = StatsProgressDialog(self.main_window, "重新计算基础统计")
        self.stats_worker = GlobalStatsWorker(self.dm, self.dm.active_dataset_uri)
        self.stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.stats_worker.finished.connect(self.on_global_stats_finished)
        self.stats_worker.error.connect(self.on_stats_error)
        self.stats_worker.start()
        self.stats_progress_dialog.exec()

    def on_global_stats_finished(self):
        """在基础统计计算完成后调用。"""
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        self.load_and_display_stats() # Reload and update UI
        self.main_window._trigger_auto_apply()
        QMessageBox.information(self.main_window, "计算完成", "基础统计数据已更新。")

    def on_stats_error(self, error_msg: str):
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        QMessageBox.critical(self.main_window, "计算失败", f"计算时发生错误: \n{error_msg}")

    def update_stats_display(self):
        """更新统计显示区域。"""
        all_stats = self.dm.global_stats
        
        if not all_stats:
            self.ui.stats_results_text.setText("无统计结果。"); return
        
        display_parts = ["<b>--- 全局统计常量 ---</b>"]
        for k, v in sorted(all_stats.items()):
            display_parts.append(f"<code>{k}: {v:.6e}</code>")
        
        text = "<br>".join(display_parts)
        self.ui.stats_results_text.setHtml(f"<div style='font-family: Consolas, \"Courier New\", monospace; font-size: 9pt;'>{text}</div>")