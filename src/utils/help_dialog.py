#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt

class HelpDialog(QDialog):
    def __init__(self, help_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("公式使用指南")
        self.setMinimumSize(600, 500)
        layout = QVBoxLayout(self)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(help_text)
        layout.addWidget(text_edit)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        self.setLayout(layout)