#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局统计处理器
"""
import logging
import os
from typing import Dict
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from datetime import datetime
from src.ui.dialogs import StatsProgressDialog
from src.core.workers import GlobalStatsWorker, CustomGlobalStatsWorker

logger = logging.getLogger(__name__)

class StatsHandler:
    """处理所有与全局统计计算、UI更新和导出相关的逻辑。"""

    def __init__(self, main_window, ui, data_manager, formula_engine):
        self.main_window = main_window
        self.ui = ui
        self.dm = data_manager
        self.formula_engine = formula_engine
        
        self.output_dir = main_window.output_dir
        self.stats_progress_dialog = None
        self.stats_worker = None
        self.custom_stats_worker = None

    def connect_signals(self):
        self.ui.recalc_basic_stats_btn.clicked.connect(self.start_global_stats_calculation)
        self.ui.save_and_calc_custom_stats_btn.clicked.connect(self.start_custom_stats_calculation)
        self.ui.export_stats_btn.clicked.connect(self.export_global_stats)
        self.ui.custom_stats_help_action.triggered.connect(self.show_custom_stats_help)

    def reset_global_stats(self):
        """当数据重载时调用，重置统计信息和UI状态。"""
        self.dm.clear_global_stats()
        self.formula_engine.update_custom_global_variables({})
        self.ui.stats_results_text.setText("数据已重载。")
        self.ui.custom_stats_input.clear()
        self.ui.export_stats_btn.setEnabled(False)
        self.ui.save_and_calc_custom_stats_btn.setEnabled(False)

    def load_definitions_and_stats(self):
        """从数据库加载统计和定义，并更新UI。"""
        self.dm.load_global_stats()
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        
        definitions = self.dm.load_custom_definitions()
        self.ui.custom_stats_input.setPlainText("\n".join(definitions))
        
        self.update_stats_display()
        
        has_stats = bool(self.dm.global_stats)
        self.ui.export_stats_btn.setEnabled(has_stats)
        self.ui.save_and_calc_custom_stats_btn.setEnabled(True)
    
    def start_global_stats_calculation(self):
        """强制重新计算所有变量的基础统计数据。"""
        if self.dm.get_frame_count() == 0: return
        reply = QMessageBox.question(self.main_window, "确认", "这将重新计算所有变量的基础统计数据并覆盖现有值。是否继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        self.stats_progress_dialog = StatsProgressDialog(self.main_window, "重新计算基础统计")
        all_vars = self.dm.get_variables()
        self.stats_worker = GlobalStatsWorker(self.dm, all_vars)
        self.stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.stats_worker.finished.connect(self.on_global_stats_finished)
        self.stats_worker.error.connect(self.on_stats_error)
        self.stats_worker.start()
        self.stats_progress_dialog.exec()

    def on_global_stats_finished(self):
        """在基础统计计算完成后调用。"""
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        self.dm.load_global_stats() # 从数据库重新加载以获取最新值
        self.update_stats_display()
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.main_window._trigger_auto_apply()
        QMessageBox.information(self.main_window, "计算完成", "基础统计数据已更新。")

    def start_custom_stats_calculation(self):
        definitions_text = self.ui.custom_stats_input.toPlainText().strip()
        definitions = [line.strip() for line in definitions_text.split('\n') if line.strip() and not line.strip().startswith('#')]
        
        try:
            self.dm.save_custom_definitions(definitions)
            logger.info("自定义常量定义已保存。")
        except Exception as e:
            self.on_stats_error(f"保存定义失败: {e}")
            return
            
        self.stats_progress_dialog = StatsProgressDialog(self.main_window, "正在计算自定义常量")
        self.custom_stats_worker = CustomGlobalStatsWorker(self.dm, definitions)
        self.custom_stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.custom_stats_worker.finished.connect(self.on_custom_stats_finished)
        self.custom_stats_worker.error.connect(self.on_stats_error)
        self.custom_stats_worker.start()
        self.stats_progress_dialog.exec()

    def on_custom_stats_finished(self):
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        self.dm.load_global_stats() # 重新加载以包含新计算的常量
        self.update_stats_display()
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.main_window._trigger_auto_apply()
        QMessageBox.information(self.main_window, "计算完成", "自定义常量已计算并更新。")

    def on_stats_error(self, error_msg: str):
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        QMessageBox.critical(self.main_window, "计算失败", f"计算时发生错误: \n{error_msg}")

    def update_stats_display(self):
        all_stats = self.dm.global_stats
        if not all_stats:
            self.ui.stats_results_text.setText("无统计结果。"); return
        
        text = "\n".join([f"{k}: {v:.6e}" for k, v in sorted(all_stats.items())])
        self.ui.stats_results_text.setText(text)
        self.ui.export_stats_btn.setEnabled(True)

    def export_global_stats(self):
        if not self.dm.global_stats:
            QMessageBox.warning(self.main_window, "导出失败", "没有可导出的统计结果。"); return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"global_stats_{timestamp}.csv"
        filepath, _ = QFileDialog.getSaveFileName(self.main_window, "保存统计结果", os.path.join(self.output_dir, filename), "CSV 文件 (*.csv)")
        if not filepath: return

        try:
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                import csv
                writer = csv.writer(f)
                writer.writerow(["Name", "Value", "Definition (if custom)"])
                
                # 获取自定义公式的名称
                custom_names = self.dm.custom_global_formulas.keys()
                
                for name, value in sorted(self.dm.global_stats.items()):
                    formula = self.dm.custom_global_formulas.get(name, "")
                    writer.writerow([name, f"{value:.6e}", formula])
            
            QMessageBox.information(self.main_window, "导出成功", f"统计结果已保存到:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self.main_window, "导出失败", f"无法保存文件: {e}")

    def show_custom_stats_help(self):
        from src.utils.help_dialog import HelpDialog
        from src.utils.help_content import get_custom_stats_help_html
        HelpDialog(get_custom_stats_help_html(), self.main_window).exec()