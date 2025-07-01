
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
派生变量计算处理器
"""
import logging
import re
from PyQt6.QtWidgets import QMessageBox
from src.ui.dialogs import StatsProgressDialog
from src.core.workers import DerivedVariableWorker, TimeAggregatedVariableWorker

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
        self.ui.compute_and_add_btn.clicked.connect(self.start_derived_variable_computation)
        self.ui.compute_and_add_time_agg_btn.clicked.connect(self.start_time_aggregated_computation)

    def _parse_definitions(self, text_content: str):
        """从多行文本中解析定义。"""
        lines = [line.strip() for line in text_content.split('\n') if line.strip() and not line.strip().startswith('#')]
        definitions = []
        for line in lines:
            if '=' not in line:
                raise ValueError(f"定义无效 (缺少 '='): {line}")
            name, formula = line.split('=', 1)
            name, formula = name.strip(), formula.strip()

            if not name or not formula:
                raise ValueError(f"在 '{line}' 中，变量名和公式不能为空。")
            if not name.isidentifier():
                raise ValueError(f"变量名 '{name}' 无效。只能包含字母、数字和下划线，且不能以数字开头。")
            
            if name in self.dm.get_variables():
                reply = QMessageBox.question(self.main_window, "名称冲突", f"变量名 '{name}' 已存在。是否覆盖？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Cancel:
                    raise InterruptedError(f"用户取消了对 '{name}' 的覆盖。")
            
            definitions.append((name, formula))
        return definitions

    def start_derived_variable_computation(self):
        """启动后台任务以计算和添加新的逐帧变量列。"""
        if self.dm.get_frame_count() == 0:
            QMessageBox.warning(self.main_window, "无数据", "请先加载数据。")
            return
            
        definitions_text = self.ui.new_variable_formula_edit.toPlainText().strip()
        if not definitions_text:
            QMessageBox.warning(self.main_window, "输入错误", "请输入至少一个逐帧派生变量的定义。")
            return
        
        try:
            definitions = self._parse_definitions(definitions_text)
        except (ValueError, InterruptedError) as e:
            QMessageBox.warning(self.main_window, "输入错误", str(e))
            return
        
        self.compute_progress_dialog = StatsProgressDialog(self.main_window, "正在计算逐帧变量")
        self.compute_worker = DerivedVariableWorker(self.dm, definitions)
        
        self.compute_worker.progress.connect(self.on_progress_update)
        self.compute_worker.finished.connect(self.on_computation_finished)
        self.compute_worker.error.connect(self.on_computation_error)
        
        self.compute_worker.start()
        self.compute_progress_dialog.exec()
        
    def start_time_aggregated_computation(self):
        """启动后台任务以计算和添加新的时间聚合变量列。"""
        if self.dm.get_frame_count() == 0:
            QMessageBox.warning(self.main_window, "无数据", "请先加载数据。")
            return
            
        definitions_text = self.ui.new_time_agg_formula_edit.toPlainText().strip()
        if not definitions_text:
            QMessageBox.warning(self.main_window, "输入错误", "请输入至少一个时间聚合变量的定义。")
            return

        try:
            definitions = self._parse_definitions(definitions_text)
            # Additional validation for time-agg format
            for _, formula in definitions:
                if not re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula, re.DOTALL):
                    raise ValueError(f"公式格式无效: '{formula}'. 时间聚合公式必须是 '聚合函数(表达式)'，例如 'mean(u)'。")
        except (ValueError, InterruptedError) as e:
            QMessageBox.warning(self.main_window, "输入错误", str(e))
            return

        self.compute_progress_dialog = StatsProgressDialog(self.main_window, "正在计算时间聚合变量")
        self.compute_worker = TimeAggregatedVariableWorker(self.dm, definitions)
        
        self.compute_worker.progress.connect(self.on_progress_update)
        self.compute_worker.finished.connect(self.on_computation_finished)
        self.compute_worker.error.connect(self.on_computation_error)
        
        self.compute_worker.start()
        self.compute_progress_dialog.exec()

    def on_progress_update(self, current, total, message):
        if self.compute_progress_dialog:
            self.compute_progress_dialog.update_progress(current, total, message)
            
    def on_computation_finished(self):
        """当Worker成功完成时调用。"""
        if self.compute_progress_dialog:
            self.compute_progress_dialog.accept()

        QMessageBox.information(self.main_window, "计算完成", f"新变量已成功计算并添加到数据库。正在刷新应用程序状态...")
        
        # Perform a full "soft reload" to update all UI and data components
        self.main_window._load_project_data()
        
        # Clear the input fields for the next operation
        self.ui.new_variable_formula_edit.clear()
        self.ui.new_time_agg_formula_edit.clear()

    def on_computation_error(self, error_msg: str):
        """当Worker遇到错误时调用。"""
        if self.compute_progress_dialog:
            self.compute_progress_dialog.accept()
        QMessageBox.critical(self.main_window, "计算失败", f"计算新变量时发生错误: \n{error_msg}")