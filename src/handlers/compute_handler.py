
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
派生变量计算处理器
"""
import logging
from PyQt6.QtWidgets import QMessageBox
from src.ui.dialogs import StatsProgressDialog
from src.core.workers import DerivedVariableWorker

logger = logging.getLogger(__name__)

class ComputeHandler:
    """处理与动态计算新变量并将其添加到数据库相关的逻辑。"""

    def __init__(self, main_window, ui, data_manager, formula_engine):
        self.main_window = main_window
        self.ui = ui
        self.dm = data_manager
        self.formula_engine = formula_engine
        
        self.compute_progress_dialog = None
        self.compute_worker = None

    def connect_signals(self):
        """连接此处理器管理的UI组件的信号。"""
        # Connects to the button in the "Data Processing" tab
        self.ui.compute_and_add_btn.clicked.connect(self.start_derived_variable_computation)

    def start_derived_variable_computation(self):
        """启动后台任务以计算和添加新的变量列。"""
        if self.dm.get_frame_count() == 0:
            QMessageBox.warning(self.main_window, "无数据", "请先加载数据。")
            return
            
        new_name = self.ui.new_variable_name_edit.text().strip()
        formula = self.ui.new_variable_formula_edit.text().strip()

        if not new_name or not formula:
            QMessageBox.warning(self.main_window, "输入错误", "新变量名和计算公式均不能为空。")
            return
        
        if not new_name.isidentifier():
            QMessageBox.warning(self.main_window, "名称无效", f"变量名 '{new_name}' 无效。只能包含字母、数字和下划线，且不能以数字开头。")
            return

        if new_name in self.dm.get_variables():
            reply = QMessageBox.question(self.main_window, "名称冲突", f"变量名 '{new_name}' 已存在。是否覆盖？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                return

        self.compute_progress_dialog = StatsProgressDialog(self.main_window, "正在计算新变量")
        self.compute_worker = DerivedVariableWorker(self.dm, new_name, formula)
        
        self.compute_worker.progress.connect(self.compute_progress_dialog.update_progress)
        self.compute_worker.finished.connect(self.on_computation_finished)
        self.compute_worker.error.connect(self.on_computation_error)
        
        self.compute_worker.start()
        self.compute_progress_dialog.exec()

    def on_computation_finished(self):
        """当Worker成功完成时调用。"""
        if self.compute_progress_dialog:
            self.compute_progress_dialog.accept()

        self.dm.refresh_schema_info()
        self.dm.load_global_stats() # Reload to get new stats
        self.formula_engine.update_allowed_variables(self.dm.get_variables())
        self.formula_engine.update_custom_global_variables(self.dm.global_stats)
        self.main_window.stats_handler.update_stats_display() 
        self.main_window.playback_handler.update_time_axis_candidates() # Update time axis combo
        
        new_name = self.ui.new_variable_name_edit.text().strip()
        QMessageBox.information(self.main_window, "计算完成", f"新变量 '{new_name}' 已成功计算并添加到数据库，其基础统计数据也已更新。")
        
        self.ui.new_variable_name_edit.clear(); self.ui.new_variable_formula_edit.clear()
        self.main_window._trigger_auto_apply()

    def on_computation_error(self, error_msg: str):
        """当Worker遇到错误时调用。"""
        if self.compute_progress_dialog:
            self.compute_progress_dialog.accept()
        QMessageBox.critical(self.main_window, "计算失败", f"计算新变量时发生错误: \n{error_msg}")