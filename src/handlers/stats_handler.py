
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
        # Connect to widgets in the new "Data Processing" tab
        self.ui.recalc_basic_stats_btn.clicked.connect(self.start_global_stats_calculation)
        self.ui.save_and_calc_custom_stats_btn.clicked.connect(self.start_custom_stats_calculation)
        self.ui.export_stats_btn.clicked.connect(self.export_global_stats)
        # REMOVED: self.ui.dp_help_btn.clicked.connect(...) to prevent double signal connection

    def reset_global_stats(self):
        """当数据重载时调用，重置统计信息和UI状态。"""
        self.dm.clear_global_stats()
        self.formula_engine.update_custom_global_variables({})
        self.ui.stats_results_text.setText("数据已重载。")
        self.ui.custom_stats_input.clear()
        self.ui.export_stats_btn.setEnabled(False)
        self.ui.save_and_calc_custom_stats_btn.setEnabled(False)
        self.ui.recalc_basic_stats_btn.setEnabled(False)

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
        self.ui.recalc_basic_stats_btn.setEnabled(True)
    
    def start_global_stats_calculation(self):
        """强制重新计算所有变量的基础统计数据。"""
        if self.dm.get_frame_count() == 0: return
        reply = QMessageBox.question(self.main_window, "确认", "这将重新计算所有<b>原始数值变量</b>的基础统计数据(mean, min, max等)并覆盖现有值。是否继续？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return
        
        self.stats_progress_dialog = StatsProgressDialog(self.main_window, "重新计算基础统计")
        vars_to_calc = self.dm.get_time_candidates() # Use this to get all numeric vars
        self.stats_worker = GlobalStatsWorker(self.dm, self.formula_engine, vars_to_calc) # Pass formula_engine
        self.stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.stats_worker.finished.connect(self.on_global_stats_finished)
        self.stats_worker.error.connect(self.on_stats_error)
        self.stats_worker.start()
        self.stats_progress_dialog.exec()

    def on_global_stats_finished(self):
        """在基础统计计算完成后调用。"""
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        self.dm.load_global_stats()
        self.update_stats_display()
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.main_window._trigger_auto_apply()
        QMessageBox.information(self.main_window, "计算完成", "基础统计数据已更新。")

    def start_custom_stats_calculation(self):
        """
        处理自定义全局常量的计算，包括删除不再存在的定义。
        """
        definitions_text = self.ui.custom_stats_input.toPlainText().strip()
        new_definitions = [line.strip() for line in definitions_text.split('\n') if line.strip() and not line.strip().startswith('#')]

        try:
            # 1. 找出需要删除的旧常量
            old_definitions = self.dm.load_custom_definitions()
            old_names = {self.main_window.compute_handler.compute_worker.calculator.parse_definition(d)[0] for d in old_definitions}
            new_names = {self.main_window.compute_handler.compute_worker.calculator.parse_definition(d)[0] for d in new_definitions}
            
            names_to_delete = list(old_names - new_names)
            if names_to_delete:
                logger.info(f"正在删除不再定义的全局常量: {names_to_delete}")
                self.dm.delete_global_stats(names_to_delete)

            # 2. 保存新的定义列表（这将覆盖旧的）
            self.dm.save_custom_definitions(new_definitions)
            logger.info("新的自定义常量定义已保存。")

            # 3. 如果有新的定义需要计算，则启动worker
            if new_definitions:
                self.stats_progress_dialog = StatsProgressDialog(self.main_window, "正在计算自定义常量")
                self.custom_stats_worker = CustomGlobalStatsWorker(self.dm, self.formula_engine, new_definitions)
                self.custom_stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
                self.custom_stats_worker.finished.connect(self.on_custom_stats_finished)
                self.custom_stats_worker.error.connect(self.on_stats_error)
                self.custom_stats_worker.start()
                self.stats_progress_dialog.exec()
            else:
                # 如果没有新定义，只需刷新UI
                self.on_custom_stats_finished()
                QMessageBox.information(self.main_window, "操作完成", "所有自定义常量均已移除。")

        except Exception as e:
            self.on_stats_error(f"处理自定义常量时出错: {e}")
            return

    def on_custom_stats_finished(self):
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        self.dm.load_global_stats() 
        self.update_stats_display()
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.main_window._trigger_auto_apply()
        if self.custom_stats_worker: # Only show message if a calculation was run
             QMessageBox.information(self.main_window, "计算完成", "自定义常量已计算并更新。")
        self.custom_stats_worker = None


    def on_stats_error(self, error_msg: str):
        if self.stats_progress_dialog: self.stats_progress_dialog.accept()
        QMessageBox.critical(self.main_window, "计算失败", f"计算时发生错误: \n{error_msg}")

    def update_stats_display(self):
        """更新统计显示区域，现在包括派生变量的定义。"""
        all_stats = self.dm.global_stats
        var_defs = self.dm.load_variable_definitions()
        
        if not all_stats and not var_defs:
            self.ui.stats_results_text.setText("无统计结果或已定义的变量。"); return
        
        display_parts = []

        # 1. Display variable definitions
        if var_defs:
            display_parts.append("<b>--- 已定义的派生/聚合变量 ---</b>")
            for name, info in sorted(var_defs.items()):
                type_map = {"per-frame": "逐帧", "time-aggregated": "时间聚合"}
                type_str = type_map.get(info['type'], info['type'])
                display_parts.append(f"<b>{name}</b> ({type_str}):<br>&nbsp;&nbsp;<code>{info['formula']}</code>")
            display_parts.append("<hr>")

        # 2. Display global stats
        if all_stats:
            display_parts.append("<b>--- 全局统计常量 ---</b>")
            for k, v in sorted(all_stats.items()):
                display_parts.append(f"<code>{k}: {v:.6e}</code>")
        
        text = "<br>".join(display_parts)
        self.ui.stats_results_text.setHtml(f"<div style='font-family: Courier New; font-size: 9pt;'>{text}</div>")
        self.ui.export_stats_btn.setEnabled(bool(all_stats))


    def export_global_stats(self):
        if not self.dm.global_stats:
            QMessageBox.warning(self.main_window, "导出失败", "没有可导出的统计结果。"); return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"global_stats_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                import csv
                writer = csv.writer(f)
                writer.writerow(["Name", "Value", "Definition/Source"])

                all_stats = self.dm.global_stats
                custom_defs_list = self.dm.load_custom_definitions()
                # 重新使用 StatisticsCalculator 的解析逻辑
                calculator = self.main_window.compute_handler.compute_worker.calculator
                custom_formulas = {calculator.parse_definition(d)[0]: calculator.parse_definition(d)[1] for d in custom_defs_list}
                
                for name, value in sorted(all_stats.items()):
                    formula = ""
                    if name in custom_formulas:
                        formula = custom_formulas[name]
                    else:
                        # 尝试从名称推断公式
                        parts = name.split('_global_')
                        if len(parts) == 2:
                            var, stat = parts
                            stat_func_map = {
                                "mean": "mean", "sum": "sum", "min": "min",
                                "max": "max", "var": "var", "std": "std"
                            }
                            if stat in stat_func_map:
                                formula = f"{stat_func_map[stat]}({var})"
                            else:
                                formula = f"基础统计 ({stat})"
                        else:
                            formula = "基础统计"

                    writer.writerow([name, f"{value:.6e}", formula])
            
            QMessageBox.information(self.main_window, "导出成功", f"统计结果已保存到:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self.main_window, "导出失败", f"无法保存文件: {e}")