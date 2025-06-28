#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口界面 (已全面优化并补完所有代码)
"""
import os
import json
import logging
from typing import Dict, Any, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QComboBox, QLineEdit, QPushButton,
    QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit,
    QStatusBar, QMenuBar, QFileDialog, QMessageBox,
    QScrollArea, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings
from PyQt6.QtGui import QAction, QKeySequence, QFont, QIcon
from datetime import datetime

# 使用相对路径导入项目模块
from src.core.data_manager import DataManager
from src.visualization.plot_widget import PlotWidget
from src.core.formula_validator import FormulaValidator
from src.utils.help_dialog import HelpDialog
from src.utils.gpu_utils import is_gpu_available
from src.visualization.video_exporter import VideoExportDialog

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """
    应用程序的主窗口类，管理UI布局、用户交互和各个模块之间的协调。
    """
    
    def __init__(self):
        super().__init__()
        
        # --- 初始化核心组件 ---
        self.settings = QSettings("StarsWhere", "InteractiveFlowVis")
        self.data_manager = DataManager()
        self.formula_validator = FormulaValidator()
        
        # --- 初始化状态变量 ---
        self.current_frame_index: int = 0
        self.is_playing: bool = False
        self.frame_skip_step: int = 1 # Changed from play_fps to frame_skip_step
        self.skipped_frames: int = 0
        
        # --- 配置路径 ---
        self.data_dir = self.settings.value("data_directory", os.path.join(os.getcwd(), "data"))
        self.output_dir = self.settings.value("output_directory", os.path.join(os.getcwd(), "output"))
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # --- 配置定时器 ---
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_timer)
        
        # --- 构建界面并加载数据 ---
        self._init_ui()
        self._connect_signals()
        self._load_settings()
        self._initialize_data()

    # region UI 初始化
    def _init_ui(self):
        """初始化整体UI布局"""
        self.setWindowTitle("流场数据交互式分析平台 v1.3")
        self.setGeometry(100, 100, 1600, 950)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)
        
        self.plot_widget = PlotWidget(self.formula_validator)
        main_splitter.addWidget(self.plot_widget)
        
        control_panel = self._create_control_panel()
        main_splitter.addWidget(control_panel)
        
        main_splitter.setSizes([1200, 400])
        main_splitter.setStretchFactor(0, 1) # 让绘图区域随窗口拉伸
        main_splitter.setStretchFactor(1, 0) # 控制面板宽度固定
        
        self._create_menu_bar()
        self._create_status_bar()
        self._update_gpu_status_label() # Initialize GPU status label
    
    def _create_control_panel(self) -> QWidget:
        """创建右侧的控制面板"""
        panel = QWidget()
        panel.setMaximumWidth(400)
        
        main_layout = QVBoxLayout(panel)
        tab_widget = QTabWidget()
        
        tab_widget.addTab(self._create_visualization_tab(), "可视化")
        tab_widget.addTab(self._create_probe_tab(), "数据探针")
        tab_widget.addTab(self._create_export_tab(), "导出与性能")
        
        main_layout.addWidget(tab_widget)
        main_layout.addWidget(self._create_playback_group())
        main_layout.addWidget(self._create_path_group())

        return panel
    
    def _create_visualization_tab(self) -> QWidget:
        """创建“可视化”选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # 坐标轴设置
        axis_group = QGroupBox("坐标轴设置")
        axis_layout = QGridLayout(axis_group)
        axis_layout.addWidget(QLabel("X轴变量:"), 0, 0)
        self.x_axis_combo = QComboBox()
        axis_layout.addWidget(self.x_axis_combo, 0, 1)
        axis_layout.addWidget(QLabel("Y轴变量:"), 1, 0)
        self.y_axis_combo = QComboBox()
        axis_layout.addWidget(self.y_axis_combo, 1, 1)
        scroll_layout.addWidget(axis_group)

        # 热力图设置
        heatmap_group = QGroupBox("背景热力图")
        h_layout = QGridLayout(heatmap_group)
        self.heatmap_enabled = QCheckBox("启用"); self.heatmap_enabled.setChecked(True)
        h_layout.addWidget(self.heatmap_enabled, 0, 0, 1, 2)
        h_layout.addWidget(QLabel("变量:"), 1, 0)
        self.heatmap_variable = QComboBox(); h_layout.addWidget(self.heatmap_variable, 1, 1)
        
        h_formula_layout = QHBoxLayout()
        self.heatmap_formula = QLineEdit(); self.heatmap_formula.setPlaceholderText("例: rho * u**2")
        h_help_btn = QPushButton("?"); h_help_btn.setFixedSize(25,25); h_help_btn.setToolTip("打开公式帮助 (F1)"); h_help_btn.clicked.connect(self._show_formula_help)
        h_formula_layout.addWidget(self.heatmap_formula); h_formula_layout.addWidget(h_help_btn)
        h_layout.addWidget(QLabel("公式:"), 2, 0); h_layout.addLayout(h_formula_layout, 2, 1)

        h_layout.addWidget(QLabel("颜色映射:"), 3, 0)
        self.heatmap_colormap = QComboBox(); self.heatmap_colormap.addItems(['viridis', 'plasma', 'inferno', 'magma', 'jet', 'coolwarm'])
        h_layout.addWidget(self.heatmap_colormap, 3, 1)
        
        min_layout = QHBoxLayout(); self.heatmap_vmin = QLineEdit(); self.pick_vmin_btn = QPushButton("拾取"); self.pick_vmin_btn.clicked.connect(lambda: self.plot_widget.set_picker_mode('vmin')); min_layout.addWidget(self.heatmap_vmin); min_layout.addWidget(self.pick_vmin_btn)
        max_layout = QHBoxLayout(); self.heatmap_vmax = QLineEdit(); self.pick_vmax_btn = QPushButton("拾取"); self.pick_vmax_btn.clicked.connect(lambda: self.plot_widget.set_picker_mode('vmax')); max_layout.addWidget(self.heatmap_vmax); max_layout.addWidget(self.pick_vmax_btn)
        h_layout.addWidget(QLabel("最小值:"), 4, 0); h_layout.addLayout(min_layout, 4, 1)
        h_layout.addWidget(QLabel("最大值:"), 5, 0); h_layout.addLayout(max_layout, 5, 1)
        scroll_layout.addWidget(heatmap_group)
        
        # 等高线设置
        contour_group = QGroupBox("前景等高线")
        c_layout = QGridLayout(contour_group)
        self.contour_enabled = QCheckBox("启用"); c_layout.addWidget(self.contour_enabled, 0, 0, 1, 2)
        c_layout.addWidget(QLabel("变量:"), 1, 0); self.contour_variable = QComboBox(); c_layout.addWidget(self.contour_variable, 1, 1)
        c_layout.addWidget(QLabel("公式:"), 2, 0); self.contour_formula = QLineEdit(); self.contour_formula.setPlaceholderText("例: sqrt(u**2+v**2)"); c_layout.addWidget(self.contour_formula, 2, 1)
        c_layout.addWidget(QLabel("等高线数:"), 3, 0); self.contour_levels = QSpinBox(); self.contour_levels.setRange(2, 100); self.contour_levels.setValue(10); c_layout.addWidget(self.contour_levels, 3, 1)
        c_layout.addWidget(QLabel("线条颜色:"), 4, 0); self.contour_colors = QComboBox(); self.contour_colors.addItems(['black', 'white', 'red', 'blue', 'grey']); c_layout.addWidget(self.contour_colors, 4, 1)
        c_layout.addWidget(QLabel("线条宽度:"), 5, 0); self.contour_linewidth = QDoubleSpinBox(); self.contour_linewidth.setRange(0.1, 10.0); self.contour_linewidth.setValue(1.0); self.contour_linewidth.setSingleStep(0.1); c_layout.addWidget(self.contour_linewidth, 5, 1)
        self.contour_labels = QCheckBox("显示数值标签"); self.contour_labels.setChecked(True); c_layout.addWidget(self.contour_labels, 6, 0, 1, 2)
        scroll_layout.addWidget(contour_group)

        # 应用与重置按钮
        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("应用可视化设置"); apply_btn.clicked.connect(self._apply_visualization_settings)
        reset_btn = QPushButton("重置视图"); reset_btn.clicked.connect(self.plot_widget.reset_view)
        btn_layout.addWidget(apply_btn); btn_layout.addWidget(reset_btn)
        scroll_layout.addLayout(btn_layout)
        
        scroll_layout.addStretch()
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        return tab

    def _create_probe_tab(self) -> QWidget:
        """创建“数据探针”选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        probe_group = QGroupBox("探针信息")
        probe_layout = QVBoxLayout(probe_group)
        coord_layout = QHBoxLayout()
        coord_layout.addWidget(QLabel("鼠标坐标:"))
        self.probe_coord_label = QLabel("(0.00, 0.00)")
        self.probe_coord_label.setFont(QFont("monospace"))
        coord_layout.addWidget(self.probe_coord_label)
        coord_layout.addStretch()
        probe_layout.addLayout(coord_layout)
        self.probe_text = QTextEdit()
        self.probe_text.setReadOnly(True)
        self.probe_text.setFont(QFont("Courier New", 9))
        self.probe_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        probe_layout.addWidget(self.probe_text)
        layout.addWidget(probe_group)
        layout.addStretch()
        return tab

    def _create_export_tab(self) -> QWidget:
        """创建“导出与性能”选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 图片导出
        img_group = QGroupBox("图片导出")
        img_layout = QGridLayout(img_group)
        img_layout.addWidget(QLabel("分辨率(DPI):"), 0, 0)
        self.export_dpi = QSpinBox(); self.export_dpi.setRange(100, 1200); self.export_dpi.setValue(300); self.export_dpi.setSingleStep(50); img_layout.addWidget(self.export_dpi, 0, 1)
        export_img_btn = QPushButton("保存当前帧图片"); export_img_btn.clicked.connect(self._export_image)
        img_layout.addWidget(export_img_btn, 1, 0, 1, 2)
        layout.addWidget(img_group)
        
        # 视频导出
        vid_group = QGroupBox("视频导出")
        vid_layout = QGridLayout(vid_group)
        vid_layout.addWidget(QLabel("起始帧:"), 0, 0); self.video_start_frame = QSpinBox(); self.video_start_frame.setMinimum(0); vid_layout.addWidget(self.video_start_frame, 0, 1)
        vid_layout.addWidget(QLabel("结束帧:"), 1, 0); self.video_end_frame = QSpinBox(); self.video_end_frame.setMinimum(0); vid_layout.addWidget(self.video_end_frame, 1, 1)
        vid_layout.addWidget(QLabel("帧率(FPS):"), 2, 0); self.video_fps = QSpinBox(); self.video_fps.setRange(1, 60); self.video_fps.setValue(15); vid_layout.addWidget(self.video_fps, 2, 1)
        export_vid_btn = QPushButton("导出视频"); export_vid_btn.clicked.connect(self._export_video)
        vid_layout.addWidget(export_vid_btn, 3, 0, 1, 2)
        layout.addWidget(vid_group)
        
        # 性能设置
        perf_group = QGroupBox("性能设置")
        perf_layout = QVBoxLayout(perf_group)
        self.gpu_checkbox = QCheckBox("启用GPU加速 (需NVIDIA/CuPy)"); self.gpu_checkbox.setToolTip("使用CUDA加速公式计算和视频渲染"); self.gpu_checkbox.setEnabled(is_gpu_available()); self.gpu_checkbox.toggled.connect(lambda on: self.plot_widget.set_config(use_gpu=on))
        perf_layout.addWidget(self.gpu_checkbox)
        cache_layout = QHBoxLayout(); cache_layout.addWidget(QLabel("内存缓存:"))
        self.cache_size_spinbox = QSpinBox(); self.cache_size_spinbox.setRange(10, 2000); self.cache_size_spinbox.setValue(100); self.cache_size_spinbox.setSingleStep(10); self.cache_size_spinbox.setSuffix(" 帧")
        cache_layout.addWidget(self.cache_size_spinbox)
        apply_cache_btn = QPushButton("应用"); apply_cache_btn.clicked.connect(self._apply_cache_settings); cache_layout.addWidget(apply_cache_btn)
        perf_layout.addLayout(cache_layout)
        layout.addWidget(perf_group)

        # 配置管理
        cfg_group = QGroupBox("配置管理")
        cfg_layout = QHBoxLayout(cfg_group)
        save_btn = QPushButton("保存配置"); save_btn.clicked.connect(self._save_config)
        load_btn = QPushButton("加载配置"); load_btn.clicked.connect(self._load_config)
        cfg_layout.addWidget(save_btn); cfg_layout.addWidget(load_btn)
        layout.addWidget(cfg_group)
        
        layout.addStretch()
        return tab

    def _create_playback_group(self) -> QGroupBox:
        """创建播放控制面板"""
        group = QGroupBox("播放控制"); layout = QVBoxLayout(group)
        info_layout = QHBoxLayout(); self.frame_info_label = QLabel("帧: 0/0"); info_layout.addWidget(self.frame_info_label); info_layout.addStretch(); self.timestamp_label = QLabel("时间戳: 0.0"); info_layout.addWidget(self.timestamp_label); layout.addLayout(info_layout)
        self.time_slider = QSlider(Qt.Orientation.Horizontal); self.time_slider.setMinimum(0); layout.addWidget(self.time_slider)
        btns_layout = QHBoxLayout(); self.play_button = QPushButton("播放"); btns_layout.addWidget(self.play_button); prev_btn = QPushButton("<<"); btns_layout.addWidget(prev_btn); next_btn = QPushButton(">>"); btns_layout.addWidget(next_btn); btns_layout.addSpacing(20); btns_layout.addWidget(QLabel("跳帧:")); self.frame_skip_spinbox = QSpinBox(); self.frame_skip_spinbox.setRange(1, 100); self.frame_skip_spinbox.setValue(1); self.frame_skip_spinbox.setSuffix(" 帧"); btns_layout.addWidget(self.frame_skip_spinbox); layout.addLayout(btns_layout) # Changed label and suffix
        self.play_button.clicked.connect(self._toggle_play); prev_btn.clicked.connect(self._prev_frame); next_btn.clicked.connect(self._next_frame); self.time_slider.valueChanged.connect(self._on_slider_changed); self.frame_skip_spinbox.valueChanged.connect(self._on_frame_skip_changed) # Changed signal connection
        return group

    def _create_path_group(self) -> QGroupBox:
        """创建路径设置面板"""
        group = QGroupBox("路径设置"); layout = QGridLayout(group)
        layout.addWidget(QLabel("数据目录:"), 0, 0); self.data_dir_line_edit = QLineEdit(self.data_dir); self.data_dir_line_edit.setReadOnly(True); layout.addWidget(self.data_dir_line_edit, 0, 1); self.change_data_dir_btn = QPushButton("..."); self.change_data_dir_btn.setToolTip("选择数据文件夹"); self.change_data_dir_btn.clicked.connect(self._change_data_directory); layout.addWidget(self.change_data_dir_btn, 0, 2)
        layout.addWidget(QLabel("输出目录:"), 1, 0); self.output_dir_line_edit = QLineEdit(self.output_dir); self.output_dir_line_edit.setReadOnly(True); layout.addWidget(self.output_dir_line_edit, 1, 1); self.change_output_dir_btn = QPushButton("..."); self.change_output_dir_btn.setToolTip("选择输出文件夹"); self.change_output_dir_btn.clicked.connect(self._change_output_directory); layout.addWidget(self.change_output_dir_btn, 1, 2)
        return group
    
    def _create_menu_bar(self):
        """创建顶部菜单栏"""
        menubar = self.menuBar(); file_menu = menubar.addMenu('文件'); reload_action = QAction('重新加载数据', self); reload_action.setShortcut('Ctrl+R'); reload_action.triggered.connect(self._reload_data); file_menu.addAction(reload_action); file_menu.addSeparator(); exit_action = QAction('退出', self); exit_action.setShortcut('Ctrl+Q'); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        view_menu = menubar.addMenu('视图'); reset_view_action = QAction('重置视图', self); reset_view_action.setShortcut('Ctrl+0'); reset_view_action.triggered.connect(self.plot_widget.reset_view); view_menu.addAction(reset_view_action)
        help_menu = menubar.addMenu('帮助'); formula_help_action = QAction('公式指南', self); formula_help_action.setShortcut('F1'); formula_help_action.triggered.connect(self._show_formula_help); help_menu.addAction(formula_help_action); help_menu.addSeparator(); about_action = QAction('关于', self); about_action.triggered.connect(self._show_about); help_menu.addAction(about_action)

    def _create_status_bar(self):
        """创建底部状态栏"""
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.cache_label = QLabel("缓存: 0/100"); self.status_bar.addPermanentWidget(self.cache_label)
        self.gpu_status_label = QLabel("GPU: 检测中..."); self.status_bar.addPermanentWidget(self.gpu_status_label) # Add GPU status label
        self.status_bar.showMessage("准备就绪")
    # endregion

    # region 信号与槽
    def _connect_signals(self):
        """连接所有信号与槽"""
        self.data_manager.loading_finished.connect(self._on_loading_finished)
        self.data_manager.error_occurred.connect(self._on_error)
        self.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        self.plot_widget.probe_data_ready.connect(self._on_probe_data)
        self.plot_widget.value_picked.connect(self._on_value_picked)
        self.plot_widget.plot_rendered.connect(self._on_plot_rendered)

    def _on_loading_finished(self, success: bool, message: str):
        """数据加载完成后的回调"""
        self.status_bar.showMessage(message, 5000)
        if success:
            frame_count = self.data_manager.get_frame_count()
            if frame_count > 0:
                self.formula_validator.update_allowed_variables(self.data_manager.get_variables())
                self._populate_variable_combos()
                self.time_slider.setMaximum(frame_count - 1)
                self.video_start_frame.setMaximum(frame_count - 1)
                self.video_end_frame.setMaximum(frame_count - 1)
                self.video_end_frame.setValue(frame_count - 1)
                self._load_frame(0)
            else:
                QMessageBox.warning(self, "数据为空", "指定的数据目录中没有找到有效的CSV文件。")
        else:
            QMessageBox.critical(self, "错误", f"无法初始化数据管理器: {message}")

    def _on_error(self, message: str):
        """处理来自其他模块的错误信号"""
        self.status_bar.showMessage(f"错误: {message}", 5000)
        QMessageBox.critical(self, "发生错误", message)

    def _on_mouse_moved(self, x: float, y: float):
        """鼠标在绘图区移动时的回调"""
        self.probe_coord_label.setText(f"({x:.3e}, {y:.3e})")

    def _on_probe_data(self, probe_data: dict):
        """收到探针数据后的回调"""
        try:
            lines = [f"{'变量名':<16s} {'数值'}", "---------------------------"]
            lines.extend([f"{k:<16s} {v:12.6e}" for k, v in probe_data['variables'].items()])
            self.probe_text.setPlainText("\n".join(lines))
        except Exception as e:
            logger.debug(f"更新探针数据显示失败: {e}")

    def _on_value_picked(self, mode: str, value: float):
        """从图中拾取数值后的回调"""
        target_widget = self.heatmap_vmin if mode == 'vmin' else self.heatmap_vmax
        target_widget.setText(f"{value:.4e}")
        self.status_bar.showMessage(f"已拾取数值 {value:.4e} 到 {mode} 输入框", 3000)

    def _on_plot_rendered(self):
        """一帧渲染完成后的回调，用于播放优化"""
        if self.is_playing:
            self.play_timer.start()

    def _toggle_play(self):
        """切换播放/暂停状态"""
        self.is_playing = not self.is_playing
        self.play_button.setText("暂停" if self.is_playing else "播放")
        if self.is_playing:
            self.play_timer.setSingleShot(True)
            self.play_timer.start(0)
            self.status_bar.showMessage("播放中...")
            # If playing starts and no probe point is set, try to set one at the center
            if self.plot_widget.last_mouse_coords is None:
                # Get approximate center of the plot (assuming plot_widget has valid data and limits)
                # This is a heuristic; a more robust solution might involve getting the actual data range.
                if self.plot_widget.current_data is not None and not self.plot_widget.current_data.empty:
                    x_min, x_max = self.plot_widget.current_data[self.plot_widget.x_axis].min(), self.plot_widget.current_data[self.plot_widget.x_axis].max()
                    y_min, y_max = self.plot_widget.current_data[self.plot_widget.y_axis].min(), self.plot_widget.current_data[self.plot_widget.y_axis].max()
                    center_x = (x_min + x_max) / 2
                    center_y = (y_min + y_max) / 2
                    self.plot_widget.last_mouse_coords = (center_x, center_y)
                    self.plot_widget.get_probe_data_at_coords(center_x, center_y)
        else:
            self.play_timer.stop()
            self.status_bar.showMessage("已暂停")

    def _on_play_timer(self):
        """播放定时器的回调，实现智能跳帧"""
        self.play_timer.stop()
        if self.plot_widget.is_busy_interpolating:
            self.skipped_frames += 1
            self.status_bar.showMessage(f"渲染延迟，跳过 {self.skipped_frames} 帧...", 1000)
            if self.is_playing: self.play_timer.start()
            return
        
        self.skipped_frames = 0
        next_frame = (self.current_frame_index + self.frame_skip_step) % self.data_manager.get_frame_count() # Use frame_skip_step
        self.time_slider.setValue(next_frame)

    def _prev_frame(self):
        if self.current_frame_index > 0: self.time_slider.setValue(self.current_frame_index - 1)
    def _next_frame(self):
        if self.current_frame_index < self.data_manager.get_frame_count() - 1: self.time_slider.setValue(self.current_frame_index + 1)
    def _on_slider_changed(self, value: int):
        if value != self.current_frame_index: self._load_frame(value)
    def _on_frame_skip_changed(self, value: int): # Renamed and modified
        self.frame_skip_step = value
        # Set a fixed interval for the timer, independent of frame_skip_step
        # This allows for consistent animation speed while skipping frames
        self.play_timer.setInterval(50) # Example: 50ms interval (20 FPS)
    # endregion
    
    # region 核心逻辑
    def _initialize_data(self):
        """初始化数据管理器并加载数据"""
        self.status_bar.showMessage(f"扫描目录: {self.data_dir}...")
        self.data_manager.initialize(self.data_dir)

    def _populate_variable_combos(self):
        """用数据变量填充UI中的下拉框"""
        variables = self.data_manager.get_variables()
        if not variables: return
        
        combos = [self.x_axis_combo, self.y_axis_combo, self.heatmap_variable, self.contour_variable]
        for combo in combos:
            current_text = combo.currentText()
            combo.clear()
        
        self.heatmap_variable.addItem("无", None)
        self.contour_variable.addItem("无", None)
        
        for var in variables:
            for combo in combos: combo.addItem(var, var)
        
        # 尝试恢复或设置默认值
        for combo in combos:
            if combo.findText(current_text) != -1: combo.setCurrentText(current_text)
        
        if 'x' in variables: self.x_axis_combo.setCurrentText('x')
        if 'y' in variables: self.y_axis_combo.setCurrentText('y')
        if 'p' in variables: self.heatmap_variable.setCurrentText('p')

    def _load_frame(self, frame_index: int):
        """加载指定帧的数据并更新绘图"""
        if not (0 <= frame_index < self.data_manager.get_frame_count()): return
        data = self.data_manager.get_frame_data(frame_index)
        if data is not None:
            self.current_frame_index = frame_index
            self.plot_widget.update_data(data)
            self._update_frame_info()
            # After updating plot data, if a last mouse coordinate exists, update probe data
            if self.plot_widget.last_mouse_coords:
                x, y = self.plot_widget.last_mouse_coords
                self.plot_widget.get_probe_data_at_coords(x, y)

    def _update_frame_info(self):
        """更新状态栏和标签中的帧信息"""
        fc = self.data_manager.get_frame_count()
        self.frame_info_label.setText(f"帧: {self.current_frame_index + 1}/{fc}")
        info = self.data_manager.get_frame_info(self.current_frame_index)
        if info: self.timestamp_label.setText(f"时间戳: {info['timestamp']}")
        cache = self.data_manager.get_cache_info()
        self.cache_label.setText(f"缓存: {cache['size']}/{cache['max_size']}")

    def _apply_visualization_settings(self):
        """应用所有可视化设置并触发重绘"""
        try:
            vmin = float(self.heatmap_vmin.text()) if self.heatmap_vmin.text().strip() else None
            vmax = float(self.heatmap_vmax.text()) if self.heatmap_vmax.text().strip() else None
        except ValueError:
            QMessageBox.warning(self, "输入错误", "最小值/最大值必须是有效的数字。"); return

        heat_cfg = {'enabled': self.heatmap_enabled.isChecked(), 'variable': self.heatmap_variable.currentData(), 'formula': self.heatmap_formula.text().strip(), 'colormap': self.heatmap_colormap.currentText(), 'vmin': vmin, 'vmax': vmax}
        if heat_cfg['formula'] and not self.formula_validator.validate(heat_cfg['formula']):
            QMessageBox.warning(self, "公式错误", f"热力图公式无效"); return
            
        contour_cfg = {'enabled': self.contour_enabled.isChecked(), 'variable': self.contour_variable.currentData(), 'formula': self.contour_formula.text().strip(), 'levels': self.contour_levels.value(), 'colors': self.contour_colors.currentText(), 'linewidths': self.contour_linewidth.value(), 'show_labels': self.contour_labels.isChecked()}
        if contour_cfg['formula'] and not self.formula_validator.validate(contour_cfg['formula']):
            QMessageBox.warning(self, "公式错误", f"等高线公式无效"); return

        self.plot_widget.set_config(heatmap_config=heat_cfg, contour_config=contour_cfg, x_axis=self.x_axis_combo.currentText(), y_axis=self.y_axis_combo.currentText())
        self._load_frame(self.current_frame_index)
        self.status_bar.showMessage("正在应用可视化设置...", 3000)
    # endregion

    # region 菜单与文件操作
    def _show_formula_help(self): HelpDialog(self.formula_validator.get_formula_help_html(), self).exec()
    def _show_about(self): QMessageBox.about(self, "关于", "<h2>流场数据交互式分析平台 v1.3</h2><p>作者: StarsWhere</p><p>一个使用PyQt6和Matplotlib构建的数据可视化工具。</p>")
    def _reload_data(self):
        if self.is_playing: self._toggle_play()
        self.data_manager.clear_all(); self._initialize_data()
    def _change_data_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择数据目录", self.data_dir)
        if new_dir and new_dir != self.data_dir:
            self.data_dir = new_dir; self.data_dir_line_edit.setText(self.data_dir); self._reload_data()
    def _change_output_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir)
        if new_dir and new_dir != self.output_dir:
            self.output_dir = new_dir; self.output_dir_line_edit.setText(self.output_dir)
    def _apply_cache_settings(self): self.data_manager.set_cache_size(self.cache_size_spinbox.value()); self._update_frame_info()

    def _export_image(self):
        fname = os.path.join(self.output_dir, f"frame_{self.current_frame_index:05d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        if self.plot_widget.save_figure(fname, self.export_dpi.value()):
            QMessageBox.information(self, "成功", f"图片已保存到:\n{fname}")
        else: QMessageBox.warning(self, "失败", "图片保存失败。")

    def _export_video(self):
        s_f, e_f = self.video_start_frame.value(), self.video_end_frame.value()
        if s_f >= e_f: QMessageBox.warning(self, "参数错误", "起始帧必须小于结束帧"); return
        fname = os.path.join(self.output_dir, f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        p_conf = {'x_axis': self.x_axis_combo.currentText(), 'y_axis': self.y_axis_combo.currentText(), 'use_gpu': self.gpu_checkbox.isChecked(), 'heatmap_config': self._get_current_config()['heatmap'], 'contour_config': self._get_current_config()['contour']}
        VideoExportDialog(self, self.data_manager, p_conf, fname, s_f, e_f, self.video_fps.value()).exec()

    def _get_current_config(self) -> Dict[str, Any]:
        """获取当前所有UI配置，用于保存"""
        return {
            "version": "1.3", "axes": {"x": self.x_axis_combo.currentText(), "y": self.y_axis_combo.currentText()},
            "heatmap": {'enabled': self.heatmap_enabled.isChecked(), 'variable': self.heatmap_variable.currentData(), 'formula': self.heatmap_formula.text(), 'colormap': self.heatmap_colormap.currentText(), 'vmin': self.heatmap_vmin.text().strip() if self.heatmap_vmin.text().strip() else None, 'vmax': self.heatmap_vmax.text().strip() if self.heatmap_vmax.text().strip() else None},
            "contour": {'enabled': self.contour_enabled.isChecked(), 'variable': self.contour_variable.currentData(), 'formula': self.contour_formula.text(), 'levels': self.contour_levels.value(), 'colors': self.contour_colors.currentText(), 'linewidths': self.contour_linewidth.value(), 'show_labels': self.contour_labels.isChecked()},
            "playback": {"frame_skip_step": self.frame_skip_spinbox.value()}, "export": {"dpi": self.export_dpi.value(), "video_fps": self.video_fps.value()}, # Changed key
            "performance": {"gpu": self.gpu_checkbox.isChecked(), "cache": self.cache_size_spinbox.value()}
        }
    
    def _apply_config(self, config: Dict[str, Any]):
        """从字典加载配置到UI"""
        try:
            # 安全地获取各个配置节
            perf = config.get("performance", {}); axes = config.get("axes", {}); heatmap = config.get("heatmap", {}); contour = config.get("contour", {}); playback = config.get("playback", {}); export = config.get("export", {})
            
            # 应用配置
            if self.gpu_checkbox.isEnabled():
                self.gpu_checkbox.setChecked(perf.get("gpu", False))
                self._update_gpu_status_label() # Update GPU status after applying config
            self.cache_size_spinbox.setValue(perf.get("cache", 100)); self._apply_cache_settings()
            
            if axes.get("x"): self.x_axis_combo.setCurrentText(axes["x"])
            if axes.get("y"): self.y_axis_combo.setCurrentText(axes["y"])
            
            self.heatmap_enabled.setChecked(heatmap.get("enabled", False))
            self.heatmap_variable.setCurrentText(heatmap.get("variable") or "无")
            self.heatmap_formula.setText(heatmap.get("formula", ""))
            self.heatmap_colormap.setCurrentText(heatmap.get("colormap", "viridis"))
            self.heatmap_vmin.setText(str(heatmap.get("vmin", "")) if heatmap.get("vmin") is not None else "")
            self.heatmap_vmax.setText(str(heatmap.get("vmax", "")) if heatmap.get("vmax") is not None else "")
            
            self.contour_enabled.setChecked(contour.get("enabled", False))
            self.contour_variable.setCurrentText(contour.get("variable") or "无")
            self.contour_formula.setText(contour.get("formula", ""))
            self.contour_levels.setValue(contour.get("levels", 10))
            self.contour_colors.setCurrentText(contour.get("colors", "black"))
            self.contour_linewidth.setValue(contour.get("linewidths", 1.0))
            self.contour_labels.setChecked(contour.get("show_labels", True))
            
            self.frame_skip_spinbox.setValue(playback.get("frame_skip_step", 1)) # Changed key and default value
            self.export_dpi.setValue(export.get("dpi", 300))
            self.video_fps.setValue(export.get("video_fps", 15))
            
            # 应用设置以刷新视图
            self._apply_visualization_settings()
            self.status_bar.showMessage("配置已成功应用", 3000)
        except Exception as e:
            logger.error(f"应用配置失败: {e}", exc_info=True)
            QMessageBox.critical(self, "错误", f"应用配置失败，文件可能已损坏或版本不兼容。\n\n错误: {e}")

    def _save_config(self):
        fname, _ = QFileDialog.getSaveFileName(self, "保存配置", self.output_dir, "JSON files (*.json)")
        if fname:
            with open(fname, 'w', encoding='utf-8') as f: json.dump(self._get_current_config(), f, indent=4)
            self.status_bar.showMessage(f"配置已保存到 {os.path.basename(fname)}", 3000)

    def _load_config(self):
        fname, _ = QFileDialog.getOpenFileName(self, "加载配置", self.output_dir, "JSON files (*.json)")
        if fname:
            try:
                with open(fname, 'r', encoding='utf-8') as f: self._apply_config(json.load(f))
            except Exception as e:
                logger.error(f"加载配置文件 '{fname}' 失败: {e}", exc_info=True)
                QMessageBox.critical(self, "加载失败", f"无法加载或解析配置文件。\n\n错误: {e}")
    # endregion
    
    # region 程序设置与关闭
    def _load_settings(self):
        """加载持久化程序设置"""
        self.restoreGeometry(self.settings.value("geometry", self.saveGeometry()))
        self.restoreState(self.settings.value("windowState", self.saveState()))
        self.frame_skip_spinbox.setValue(self.settings.value("frame_skip_step", 1, type=int)) # Changed key and default value
        self.export_dpi.setValue(self.settings.value("export_dpi", 300, type=int))
        self.video_fps.setValue(self.settings.value("video_fps", 15, type=int))
        self.cache_size_spinbox.setValue(self.settings.value("cache_size", 100, type=int))
        if self.gpu_checkbox.isEnabled():
            self.gpu_checkbox.setChecked(self.settings.value("use_gpu", False, type=bool))
        self._update_gpu_status_label() # Update GPU status after loading settings

    def _save_settings(self):
        """保存持久化程序设置"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("data_directory", self.data_dir)
        self.settings.setValue("output_directory", self.output_dir)
        self.settings.setValue("frame_skip_step", self.frame_skip_spinbox.value()) # Changed key
        self.settings.setValue("export_dpi", self.export_dpi.value())
        self.settings.setValue("video_fps", self.video_fps.value())
        self.settings.setValue("cache_size", self.cache_size_spinbox.value())
        self.settings.setValue("use_gpu", self.gpu_checkbox.isChecked())

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        self._save_settings()
        self.play_timer.stop()
        self.plot_widget.thread_pool.clear()
        self.plot_widget.thread_pool.waitForDone()
        logger.info("应用程序正常关闭")
        super().closeEvent(event)
    # endregion

    # region 辅助方法
    def _update_gpu_status_label(self):
        """更新状态栏中的GPU加速状态显示"""
        if is_gpu_available():
            if self.gpu_checkbox.isChecked():
                self.gpu_status_label.setText("GPU: 启用")
                self.gpu_status_label.setStyleSheet("color: green;")
            else:
                self.gpu_status_label.setText("GPU: 可用 (未启用)")
                self.gpu_status_label.setStyleSheet("color: orange;")
        else:
            self.gpu_status_label.setText("GPU: 不可用")
            self.gpu_status_label.setStyleSheet("color: red;")
    # endregion