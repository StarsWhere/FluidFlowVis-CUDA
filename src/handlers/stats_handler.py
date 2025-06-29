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
        self.ui.calc_basic_stats_btn.clicked.connect(self.start_global_stats_calculation)
        self.ui.calc_custom_stats_btn.clicked.connect(self.start_custom_stats_calculation)
        self.ui.export_stats_btn.clicked.connect(self.export_global_stats)
        self.ui.custom_stats_help_action.triggered.connect(self.show_custom_stats_help)

    def reset_global_stats(self):
        """当数据重载时调用，重置统计信息和UI状态。"""
        self.dm.clear_global_stats()
        self.formula_engine.update_custom_global_variables({})
        self.ui.stats_results_text.setText("数据已重载，请重新计算。")
        self.ui.export_stats_btn.setEnabled(False)
        self.ui.calc_custom_stats_btn.setEnabled(False)

    def start_global_stats_calculation(self):
        if self.dm.get_frame_count() == 0: return
        self.stats_progress_dialog = StatsProgressDialog(self.main_window, "正在计算基础统计")
        self.stats_worker = GlobalStatsWorker(self.dm)
        self.stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.stats_worker.finished.connect(self.on_global_stats_finished)
        self.stats_worker.error.connect(self.on_global_stats_error)
        self.stats_worker.start()
        self.stats_progress_dialog.exec()

    def on_global_stats_finished(self, results: Dict[str, float]):
        self.stats_progress_dialog.accept()
        if not results:
            self.ui.stats_results_text.setText("计算完成，无结果。")
            return

        self.dm.global_stats = results
        self.update_stats_display()
        self.ui.export_stats_btn.setEnabled(True)
        self.ui.calc_custom_stats_btn.setEnabled(True)
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.main_window._trigger_auto_apply() # 触发重绘以应用新变量
        QMessageBox.information(self.main_window, "计算完成", "基础统计数据已计算并可用于公式中。")

    def on_global_stats_error(self, error_msg: str):
        self.stats_progress_dialog.accept()
        QMessageBox.critical(self.main_window, "计算失败", f"计算基础统计时发生错误: \n{error_msg}")

    def start_custom_stats_calculation(self):
        definitions_text = self.ui.custom_stats_input.toPlainText().strip()
        if not definitions_text: return
        definitions = [line.strip() for line in definitions_text.split('\n') if line.strip()]
        
        self.stats_progress_dialog = StatsProgressDialog(self.main_window, "正在计算自定义常量")
        self.custom_stats_worker = CustomGlobalStatsWorker(self.dm, definitions)
        self.custom_stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.custom_stats_worker.finished.connect(self.on_custom_stats_finished)
        self.custom_stats_worker.error.connect(self.on_custom_stats_error)
        self.custom_stats_worker.start()
        self.stats_progress_dialog.exec()

    def on_custom_stats_finished(self, new_stats: Dict[str, float]): # new_stats 现在只包含名称和数值
        self.stats_progress_dialog.accept()
        if not new_stats:
            QMessageBox.warning(self.main_window, "计算完成", "未计算出任何新的自定义常量。"); return
        
        self.dm.global_stats.update(new_stats)
        # custom_global_formulas 已经在 CustomGlobalStatsWorker 中更新，这里无需再次更新
        self.update_stats_display()
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.main_window._trigger_auto_apply()
        QMessageBox.information(self.main_window, "计算完成", f"成功计算了 {len(new_stats)} 个自定义常量。")

    def on_custom_stats_error(self, error_msg: str):
        self.stats_progress_dialog.accept()
        QMessageBox.critical(self.main_window, "计算失败", f"计算自定义常量时发生错误: \n{error_msg}")

    def update_stats_display(self):
        all_stats = self.dm.global_stats
        if not all_stats:
            self.ui.stats_results_text.setText("无统计结果。"); return
        
        text = "\n".join([f"{k}: {v:.6e}" for k, v in all_stats.items()])
        self.ui.stats_results_text.setText(text)

    def export_global_stats(self):
        if not self.dm.global_stats:
            QMessageBox.warning(self.main_window, "导出失败", "没有可导出的统计结果。"); return

        # 构造文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"global_stats_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("Name,Value,Formula\n") # CSV 头部
                
                # 遍历所有统计结果
                for name, value in self.dm.global_stats.items():
                    formula = self.dm.custom_global_formulas.get(name, "") # 获取自定义公式，如果没有则为空
                    f.write(f"{name},{value:.6e},{formula}\n")
            
            QMessageBox.information(self.main_window, "导出成功", f"统计结果已保存到:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self.main_window, "导出失败", f"无法保存文件: {e}")

    def show_custom_stats_help(self):
        from src.utils.help_dialog import HelpDialog
        from src.utils.help_content import get_custom_stats_help_html
        HelpDialog(get_custom_stats_help_html(), self.main_window).exec()