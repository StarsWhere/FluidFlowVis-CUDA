#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InterVis
主程序入口
"""

import sys
import os
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon

# 确保导入路径正确，这是良好的实践
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main_window import MainWindow
from src.utils.logger import setup_logger

def main():
    """主函数"""
    # 设置日志
    logger = setup_logger()
    
    try:
        # 创建QApplication实例
        app = QApplication(sys.argv)
        app.setApplicationName("InterVis")
        app.setApplicationVersion("1.7-Refactored") # 更新版本号
        app.setOrganizationName("StarsWhere")
        
        # Qt6 自动处理高DPI缩放
        
        # 创建主窗口
        main_window = MainWindow()
        main_window.show()
        
        logger.info("InterVis 启动成功")
        
        # 启动事件循环
        sys.exit(app.exec())
        
    except Exception as e:
        # 捕获任何未预料到的启动错误
        logger.error(f"程序启动失败: {str(e)}", exc_info=True)
        # 尝试以图形化方式显示错误
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("启动错误")
        msg_box.setText(f"程序启动失败，请查看日志获取详细信息。\n\n错误: {str(e)}")
        msg_box.exec()
        sys.exit(1)

if __name__ == "__main__":
    main()