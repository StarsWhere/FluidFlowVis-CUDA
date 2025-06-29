#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InterVis
主程序入口
"""

import sys
import os
from PyQt6.QtWidgets import QApplication, QMessageBox

# 确保导入路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main_window import MainWindow
from src.utils.logger import setup_logger

def main():
    """主函数"""
    logger = setup_logger()
    
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("InterVis")
        app.setApplicationVersion("3.3-ProFinal") # 版本号更新
        app.setOrganizationName("StarsWhere")
        
        main_window = MainWindow()
        main_window.show()
        
        logger.info("InterVis v3.3-ProFinal 启动成功")
        sys.exit(app.exec())
        
    except Exception as e:
        logger.error(f"程序启动失败: {str(e)}", exc_info=True)
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("启动错误")
        msg_box.setText(f"程序启动失败，请查看日志获取详细信息。\n\n错误: {str(e)}")
        msg_box.exec()
        sys.exit(1)

if __name__ == "__main__":
    main()