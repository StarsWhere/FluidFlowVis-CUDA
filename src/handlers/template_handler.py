#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可视化模板处理器
"""
import os
import json
import logging
from typing import Dict, Any, Optional

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QInputDialog

logger = logging.getLogger(__name__)

class TemplateHandler:
    """处理与加载、保存和管理可视化模板文件相关的逻辑。"""
    
    def __init__(self, main_window, ui, config_handler):
        self.main_window = main_window
        self.ui = ui
        self.config_handler = config_handler # 需要用它来获取和应用配置
        
        self.templates_dir = os.path.join(os.getcwd(), "settings", "templates")
        os.makedirs(self.templates_dir, exist_ok=True)

    def connect_signals(self):
        """连接此处理器管理的UI组件的信号。"""
        self.ui.load_template_btn.clicked.connect(self.load_selected_template)
        self.ui.save_template_btn.clicked.connect(self.save_current_as_template)

    def populate_template_combobox(self):
        """填充模板下拉列表。"""
        self.ui.template_combo.blockSignals(True)
        self.ui.template_combo.clear()
        
        default_template_path = os.path.join(self.templates_dir, "default.json")
        if not os.path.exists(default_template_path):
            try:
                # 创建一个基础的默认模板
                default_content = self.config_handler.get_current_config()
                with open(default_template_path, 'w', encoding='utf-8') as f:
                    json.dump(default_content, f, indent=4)
            except Exception as e:
                logger.error(f"创建默认模板失败: {e}")

        try:
            template_files = sorted([f for f in os.listdir(self.templates_dir) if f.endswith('.json')])
            self.ui.template_combo.addItems(template_files)
        except Exception as e:
            logger.error(f"读取模板目录失败: {e}")
            
        self.ui.template_combo.blockSignals(False)

    def load_selected_template(self):
        """加载下拉列表中选定的模板。"""
        template_name = self.ui.template_combo.currentText()
        if not template_name:
            QMessageBox.warning(self.main_window, "无选择", "请先从下拉列表中选择一个模板。")
            return
            
        filepath = os.path.join(self.templates_dir, template_name)
        if not os.path.exists(filepath):
            QMessageBox.critical(self.main_window, "文件不存在", f"模板文件 '{template_name}' 已不存在。")
            self.populate_template_combobox()
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 使用 ConfigHandler 的 apply_config 方法来应用设置
            self.config_handler.apply_config(config_data)
            self.main_window.ui.status_bar.showMessage(f"已加载模板: {template_name}", 3000)
            
            # 加载模板后，主配置状态变为“未保存”
            self.config_handler.mark_config_as_dirty()

        except Exception as e:
            QMessageBox.critical(self.main_window, "加载失败", f"无法加载或解析模板 '{template_name}':\n{e}")

    def save_current_as_template(self):
        """将当前的可视化设置保存为一个新的模板文件。"""
        text, ok = QInputDialog.getText(self.main_window, "另存为模板", "请输入新模板的名称:")
        if not (ok and text): return

        filename = f"{text}.json" if not text.endswith('.json') else text
        filepath = os.path.join(self.templates_dir, filename)
        
        if os.path.exists(filepath):
            reply = QMessageBox.question(self.main_window, "确认覆盖", f"模板文件 '{filename}' 已存在。是否覆盖？")
            if reply != QMessageBox.StandardButton.Yes: return
        
        try:
            # 从 ConfigHandler 获取当前所有设置
            current_config = self.config_handler.get_current_config()
            
            # 将配置写入模板文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=4)
                
            self.main_window.ui.status_bar.showMessage(f"模板已保存到 {filename}", 3000)
            # 刷新模板列表
            self.populate_template_combobox()
            self.ui.template_combo.setCurrentText(filename)

        except Exception as e:
            QMessageBox.critical(self.main_window, "保存失败", f"无法写入模板文件 '{filename}':\n{e}")