#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
派生变量计算处理器
"""
import logging
import re
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QEventLoop
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
        self.ui.compute_combined_btn.clicked.connect(self.start_combined_computation)

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
            
            # 允许覆盖现有变量，但需要用户确认
            if name in self.dm.get_variables():
                reply = QMessageBox.question(self.main_window, "变量已存在", f"变量 '{name}' 已存在于数据库中。您想覆盖它吗？\n\n覆盖将删除旧数据并用新计算的值替换。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
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
        self.compute_worker = DerivedVariableWorker(self.dm, self.formula_engine, definitions)
        
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
            for _, formula in definitions:
                if not re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula, re.DOTALL):
                    raise ValueError(f"公式格式无效: '{formula}'. 时间聚合公式必须是 '聚合函数(表达式)'，例如 'mean(u)'。")
        except (ValueError, InterruptedError) as e:
            QMessageBox.warning(self.main_window, "输入错误", str(e))
            return

        self.compute_progress_dialog = StatsProgressDialog(self.main_window, "正在计算时间聚合变量")
        self.compute_worker = TimeAggregatedVariableWorker(self.dm, self.formula_engine, definitions)
        
        self.compute_worker.progress.connect(self.on_progress_update)
        self.compute_worker.finished.connect(self.on_computation_finished)
        self.compute_worker.error.connect(self.on_computation_error)
        
        self.compute_worker.start()
        self.compute_progress_dialog.exec()
    
    def start_combined_computation(self):
        """解析并顺序执行组合计算任务。"""
        if self.dm.get_frame_count() == 0:
            QMessageBox.warning(self.main_window, "无数据", "请先加载数据。")
            return

        text = self.ui.combined_formula_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self.main_window, "输入错误", "请输入组合计算的定义。")
            return

        blocks = []
        current_type = None
        current_block_lines = []
        for line in text.split('\n'):
            line_strip = line.strip().lower()
            if line_strip == '#--- per-frame ---#':
                if current_type is not None and any(l.strip() for l in current_block_lines):
                    blocks.append((current_type, "\n".join(current_block_lines)))
                current_type = 'per-frame'
                current_block_lines = []
            elif line_strip == '#--- time-aggregated ---#':
                if current_type is not None and any(l.strip() for l in current_block_lines):
                    blocks.append((current_type, "\n".join(current_block_lines)))
                current_type = 'time-aggregated'
                current_block_lines = []
            elif current_type is not None and line.strip() and not line.strip().startswith('#'):
                current_block_lines.append(line)
        
        if current_type is not None and any(l.strip() for l in current_block_lines):
            blocks.append((current_type, "\n".join(current_block_lines)))

        if not blocks:
            QMessageBox.warning(self.main_window, "解析错误", "未找到任何有效的计算块。请使用 '#--- PER-FRAME ---#' 或 '#--- TIME-AGGREGATED ---#' 来定义块。")
            return
            
        self.compute_progress_dialog = StatsProgressDialog(self.main_window, "正在执行组合计算")
        
        for i, (block_type, defs_text) in enumerate(blocks):
            self.compute_progress_dialog.update_progress(i, len(blocks), f"执行块 {i+1}/{len(blocks)} ({block_type})...")
            
            try:
                definitions = self._parse_definitions(defs_text)
                if not definitions: continue
            except (ValueError, InterruptedError) as e:
                self.compute_progress_dialog.close()
                QMessageBox.warning(self.main_window, "解析错误", f"块 {i+1} 中存在错误: {e}")
                return

            worker = None
            if block_type == 'per-frame':
                worker = DerivedVariableWorker(self.dm, self.formula_engine, definitions)
            else:
                for _, formula in definitions:
                    if not re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula, re.DOTALL):
                        QMessageBox.warning(self.main_window, "输入错误", f"时间聚合公式格式无效: '{formula}'")
                        self.compute_progress_dialog.close()
                        return
                worker = TimeAggregatedVariableWorker(self.dm, self.formula_engine, definitions)

            event_loop = QEventLoop()
            error_message = []
            
            worker.finished.connect(event_loop.quit)
            worker.error.connect(error_message.append)
            worker.error.connect(event_loop.quit)
            
            # Connect progress to a lambda to add block info
            worker.progress.connect(lambda cur, tot, msg: self.compute_progress_dialog.update_progress(i, len(blocks), f"块 {i+1}: {msg}"))
            
            worker.start()
            self.compute_progress_dialog.show()
            event_loop.exec()

            if error_message:
                self.on_computation_error(f"块 {i+1} ({block_type}) 执行失败: \n{error_message[0]}")
                return

            logger.info(f"计算块 {i+1} ('{block_type}') 成功。正在刷新数据管理器状态...")
            self.dm.refresh_schema_info()
            self.formula_engine.update_allowed_variables(self.dm.get_variables())

        self.compute_progress_dialog.close()
        QMessageBox.information(self.main_window, "计算完成", "所有组合计算任务已成功完成。")
        self.main_window._load_project_data()
        self.ui.combined_formula_edit.clear()


    def on_progress_update(self, current, total, message):
        if self.compute_progress_dialog:
            self.compute_progress_dialog.update_progress(current, total, message)
            
    def on_computation_finished(self):
        if self.compute_progress_dialog:
            self.compute_progress_dialog.accept()

        QMessageBox.information(self.main_window, "计算完成", f"新变量已成功计算并添加到数据库。正在刷新应用程序状态...")
        self.main_window._load_project_data()
        self.ui.new_variable_formula_edit.clear()
        self.ui.new_time_agg_formula_edit.clear()

    def on_computation_error(self, error_msg: str):
        if self.compute_progress_dialog:
            self.compute_progress_dialog.close()
        QMessageBox.critical(self.main_window, "计算失败", f"计算新变量时发生错误: \n{error_msg}")