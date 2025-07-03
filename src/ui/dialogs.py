# src/ui/dialogs.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义对话框模块
"""
import os
from typing import List
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextEdit, QListWidget, QDialogButtonBox, QMessageBox,
    QComboBox, QInputDialog, QLineEdit, QListWidgetItem
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

class ImportDialog(QDialog):
    """显示数据导入到数据库进度的对话框"""
    def __init__(self, parent=None, title="正在导入数据"):
        super().__init__(parent)
        self.setWindowIcon(QIcon("png/icon.png")) # 设置窗口图标
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(450, 150)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("正在初始化...")
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.log_label = QLabel("") # 用于显示额外信息，如写入数据库
        self.log_label.setStyleSheet("color: grey;")
        layout.addWidget(self.log_label)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, False)

    def update_progress(self, current: int, total: int, msg: str = ""):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        if msg:
            self.status_label.setText(msg)
        else:
            self.status_label.setText(f"正在处理第 {current}/{total} 个数据文件...")

    def set_log_message(self, msg: str):
        self.log_label.setText(msg)

class ConfigSelectionDialog(QDialog):
    """一个自定义对话框，用于从特定目录选择一个或多个配置文件。"""
    def __init__(self, settings_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon("png/icon.png")) # 设置窗口图标
        self.setWindowTitle("选择批量导出配置")
        self.setMinimumSize(450, 350)
        self.settings_dir = settings_dir

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("请选择要用于批量导出的一个或多个配置文件:"))

        self.list_widget = QListWidget()
        # 允许多选，支持Ctrl和Shift键
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_widget)

        self._populate_files()

        # 使用标准的OK/Cancel按钮框
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_files(self):
        """填充设置目录中的json文件列表。"""
        try:
            if not os.path.isdir(self.settings_dir):
                self.list_widget.addItem("错误: 找不到设置目录！")
                self.list_widget.setEnabled(False)
                return
            
            config_files = sorted([f for f in os.listdir(self.settings_dir) if f.endswith('.json')])
            if not config_files:
                self.list_widget.addItem("未找到任何配置文件 (.json)。")
                self.list_widget.setEnabled(False)
            else:
                self.list_widget.addItems(config_files)
        except Exception as e:
            self.list_widget.addItem(f"读取文件时出错: {e}")
            self.list_widget.setEnabled(False)

    def selected_files(self) -> List[str]:
        """返回所选文件的完整路径列表。"""
        selected_items = self.list_widget.selectedItems()
        return [os.path.join(self.settings_dir, item.text()) for item in selected_items]


class BatchExportDialog(QDialog):
    """用于显示批量导出进度的对话框。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon("png/icon.png")) # 设置窗口图标
        self.setWindowTitle("批量视频导出")
        self.setMinimumSize(500, 400)
        self.setModal(False) # 非模态，不阻塞主窗口

        layout = QVBoxLayout(self)

        # 整体进度
        overall_layout = QHBoxLayout()
        overall_layout.addWidget(QLabel("总进度:"))
        self.overall_progress_bar = QProgressBar()
        overall_layout.addWidget(self.overall_progress_bar)
        layout.addLayout(overall_layout)
        self.overall_status_label = QLabel("准备开始...")
        layout.addWidget(self.overall_status_label)
        
        # 日志输出
        layout.addWidget(QLabel("导出日志:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier New", 9))
        layout.addWidget(self.log_text)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setEnabled(False)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

    def update_progress(self, current: int, total: int, filename: str):
        self.overall_progress_bar.setMaximum(total)
        self.overall_progress_bar.setValue(current + 1)
        self.overall_status_label.setText(f"正在处理第 {current + 1}/{total} 个文件: {filename}")

    def add_log(self, message: str):
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def on_finish(self, summary_message: str):
        self.overall_status_label.setText("全部任务已完成！")
        self.add_log("-" * 20)
        self.add_log(f"批量导出完成。\n{summary_message}")
        self.close_button.setEnabled(True)
        self.overall_progress_bar.setValue(self.overall_progress_bar.maximum())


class StatsProgressDialog(QDialog):
    """显示全局统计计算进度的对话框"""
    def __init__(self, parent=None, title="正在计算统计数据"):
        super().__init__(parent)
        self.setWindowIcon(QIcon("png/icon.png")) # 设置窗口图标
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(450, 120)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("正在初始化...")
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowSystemMenuHint, False)

    def update_progress(self, current: int, total: int, msg: str = ""):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        if msg:
            self.status_label.setText(msg)
        else:
            self.status_label.setText(f"正在处理第 {current}/{total} 个数据文件...")

class FilterBuilderDialog(QDialog):
    """
    用于构建数据过滤表达式的对话框。
    允许用户选择变量、操作符和值来创建复杂的过滤条件。
    """
    OPERATORS = {
        '等于': '==',
        '不等于': '!=',
        '大于': '>',
        '小于': '<',
        '大于或等于': '>=',
        '小于或等于': '<=',
        '包含': 'LIKE',
        '不包含': 'NOT LIKE'
    }

    def __init__(self, available_variables: List[str], parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon("png/icon.png"))
        self.setWindowTitle("构建过滤器")
        self.setMinimumSize(600, 400)
        
        self.available_variables = sorted(available_variables)
        self.filter_parts = []  # 存储 (variable, sql_op, value, display_op) 元组

        self._init_ui()
        self._populate_variables()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        filter_label = QLabel("当前过滤器表达式:")
        main_layout.addWidget(filter_label)
        self.filter_display = QTextEdit()
        self.filter_display.setReadOnly(True)
        self.filter_display.setFont(QFont("Courier New", 10))
        main_layout.addWidget(self.filter_display)

        add_condition_group = QHBoxLayout()
        self.variable_combo = QComboBox()
        self.operator_combo = QComboBox()
        self.value_edit = QLineEdit()
        self.add_button = QPushButton("添加条件")
        self.add_button.clicked.connect(self._add_condition)

        add_condition_group.addWidget(QLabel("变量:"))
        add_condition_group.addWidget(self.variable_combo)
        add_condition_group.addWidget(QLabel("操作:"))
        add_condition_group.addWidget(self.operator_combo)
        add_condition_group.addWidget(QLabel("值:"))
        add_condition_group.addWidget(self.value_edit)
        add_condition_group.addWidget(self.add_button)
        main_layout.addLayout(add_condition_group)

        self.conditions_list = QListWidget()
        main_layout.addWidget(self.conditions_list)

        button_layout = QHBoxLayout()
        self.clear_button = QPushButton("清空所有")
        self.clear_button.clicked.connect(self._clear_conditions)
        self.remove_button = QPushButton("移除选中")
        self.remove_button.clicked.connect(self._remove_selected_condition)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        main_layout.addLayout(button_layout)

        self._populate_operators()
        self._update_filter_display()

    def _populate_variables(self):
        self.variable_combo.addItems(self.available_variables)

    def _populate_operators(self):
        self.operator_combo.addItems(self.OPERATORS.keys())

    def _add_condition(self):
        variable = self.variable_combo.currentText()
        display_op = self.operator_combo.currentText()
        sql_op = self.OPERATORS[display_op]
        value = self.value_edit.text().strip()

        if not variable or not value:
            QMessageBox.warning(self, "输入无效", "请选择变量并输入值。")
            return
        
        if sql_op in ['LIKE', 'NOT LIKE']:
            value = f"'%{value}%'"
        elif not self._is_numeric(value):
            value = f"'{value}'"

        self.filter_parts.append((variable, sql_op, value, display_op))
        self._update_conditions_list()
        self._update_filter_display()
        self.value_edit.clear()

    def _remove_selected_condition(self):
        selected_rows = [item.row() for item in self.conditions_list.selectedItems()]
        if not selected_rows:
            QMessageBox.warning(self, "未选择", "请选择要移除的条件。")
            return
        
        for row in sorted(selected_rows, reverse=True):
            del self.filter_parts[row]
        
        self._update_conditions_list()
        self._update_filter_display()

    def _clear_conditions(self):
        self.filter_parts.clear()
        self._update_conditions_list()
        self._update_filter_display()

    def _update_conditions_list(self):
        self.conditions_list.clear()
        for var, sql_op, val, display_op in self.filter_parts:
            # 清理显示的值
            display_val = val
            if sql_op in ['LIKE', 'NOT LIKE']:
                display_val = val.strip("'").strip('%')
            elif val.startswith("'") and val.endswith("'"):
                display_val = val[1:-1]
            
            display_text = f"'{var}' {display_op} '{display_val}'"
            self.conditions_list.addItem(display_text)

    def _update_filter_display(self):
        # 使用反引号 ` ` 包围变量名，以处理特殊字符
        filter_string = " AND ".join([f"`{var}` {op} {val}" for var, op, val, _ in self.filter_parts])
        self.filter_display.setPlainText(filter_string)

    def get_filter_string(self) -> str:
        return self.filter_display.toPlainText()

    def _is_numeric(self, value_str: str) -> bool:
        try:
            float(value_str)
            return True
        except ValueError:
            return False

class VariableSelectionDialog(QDialog):
    """
    [NEW] 一个用于让用户选择一个或多个变量（列）进行导出的对话框。
    """
    def __init__(self, all_variables: List[str], parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon("png/icon.png"))
        self.setWindowTitle("选择要导出的变量")
        self.setMinimumSize(400, 500)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("请选择要包含在导出文件中的变量列:"))
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.addItems(sorted(all_variables))
        layout.addWidget(self.list_widget)
        
        buttons_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.list_widget.selectAll)
        self.deselect_all_btn = QPushButton("全不选")
        self.deselect_all_btn.clicked.connect(self.list_widget.clearSelection)
        buttons_layout.addWidget(self.select_all_btn)
        buttons_layout.addWidget(self.deselect_all_btn)
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_selected_variables(self) -> List[str]:
        """返回用户选择的变量列表。"""
        return [item.text() for item in self.list_widget.selectedItems()]