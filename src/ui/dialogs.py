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
    QPushButton, QTextEdit, QListWidget, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class ConfigSelectionDialog(QDialog):
    """一个自定义对话框，用于从特定目录选择一个或多个配置文件。"""
    def __init__(self, settings_dir: str, parent=None):
        super().__init__(parent)
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