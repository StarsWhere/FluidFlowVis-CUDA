#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口UI创建与布局模块
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QComboBox, QLineEdit, QPushButton,
    QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit,
    QStatusBar, QFileDialog, QMessageBox,
    QScrollArea, QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont

from src.visualization.plot_widget import PlotWidget

class UiMainWindow:
    """
    此类负责创建和布局主窗口的所有UI组件。
    """
    def setup_ui(self, main_window: QMainWindow, formula_validator):
        main_window.setWindowTitle("InterVis v1.4")
        main_window.setGeometry(100, 100, 1600, 950)
        
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)
        
        self.plot_widget = PlotWidget(formula_validator)
        main_splitter.addWidget(self.plot_widget)
        
        control_panel = self._create_control_panel(main_window)
        main_splitter.addWidget(control_panel)
        
        main_splitter.setSizes([1200, 400])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        
        self._create_menu_bar(main_window)
        self._create_status_bar(main_window)

    def _create_control_panel(self, parent_window) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(450)
        
        main_layout = QVBoxLayout(panel)
        self.tab_widget = QTabWidget()
        
        self.tab_widget.addTab(self._create_visualization_tab(parent_window), "可视化")
        self.tab_widget.addTab(self._create_probe_tab(), "数据探针")
        self.tab_widget.addTab(self._create_statistics_tab(parent_window), "全局统计")
        self.tab_widget.addTab(self._create_export_tab(), "导出与性能")
        
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self._create_playback_group())
        main_layout.addWidget(self._create_path_group())

        return panel
    
    def _create_visualization_tab(self, parent_window) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        axis_group = QGroupBox("坐标轴设置")
        axis_layout = QGridLayout(axis_group)
        axis_layout.addWidget(QLabel("X轴变量:"), 0, 0)
        self.x_axis_combo = QComboBox()
        axis_layout.addWidget(self.x_axis_combo, 0, 1)
        axis_layout.addWidget(QLabel("X轴公式:"), 0, 2)
        self.x_axis_formula = QLineEdit(); self.x_axis_formula.setPlaceholderText("可选, 例: x / 1000")
        axis_layout.addWidget(self.x_axis_formula, 0, 3)
        
        axis_layout.addWidget(QLabel("Y轴变量:"), 1, 0)
        self.y_axis_combo = QComboBox()
        axis_layout.addWidget(self.y_axis_combo, 1, 1)
        axis_layout.addWidget(QLabel("Y轴公式:"), 1, 2)
        self.y_axis_formula = QLineEdit(); self.y_axis_formula.setPlaceholderText("可选, 例: y * rho_global_mean")
        axis_layout.addWidget(self.y_axis_formula, 1, 3)
        axis_layout.setColumnStretch(1, 1)
        axis_layout.setColumnStretch(3, 2)
        scroll_layout.addWidget(axis_group)

        heatmap_group = QGroupBox("背景热力图")
        h_layout = QGridLayout(heatmap_group)
        self.heatmap_enabled = QCheckBox("启用"); self.heatmap_enabled.setChecked(True)
        h_layout.addWidget(self.heatmap_enabled, 0, 0, 1, 2)
        h_layout.addWidget(QLabel("变量:"), 1, 0)
        self.heatmap_variable = QComboBox(); h_layout.addWidget(self.heatmap_variable, 1, 1)
        
        h_formula_layout = QHBoxLayout()
        self.heatmap_formula = QLineEdit(); self.heatmap_formula.setPlaceholderText("例: p - mean(p)")
        h_help_btn = QPushButton("?"); h_help_btn.setFixedSize(25,25); h_help_btn.setToolTip("打开公式说明 (F1)"); h_help_btn.clicked.connect(parent_window._show_formula_help)
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
        
        contour_group = QGroupBox("前景等高线")
        c_layout = QGridLayout(contour_group)
        self.contour_enabled = QCheckBox("启用"); c_layout.addWidget(self.contour_enabled, 0, 0, 1, 2)
        c_layout.addWidget(QLabel("变量:"), 1, 0); self.contour_variable = QComboBox(); c_layout.addWidget(self.contour_variable, 1, 1)
        c_layout.addWidget(QLabel("公式:"), 2, 0); self.contour_formula = QLineEdit(); self.contour_formula.setPlaceholderText("例: rho*(u-u_global_mean)"); c_layout.addWidget(self.contour_formula, 2, 1)
        c_layout.addWidget(QLabel("等高线数:"), 3, 0); self.contour_levels = QSpinBox(); self.contour_levels.setRange(2, 100); self.contour_levels.setValue(10); c_layout.addWidget(self.contour_levels, 3, 1)
        c_layout.addWidget(QLabel("线条颜色:"), 4, 0); self.contour_colors = QComboBox(); self.contour_colors.addItems(['black', 'white', 'red', 'blue', 'grey']); c_layout.addWidget(self.contour_colors, 4, 1)
        c_layout.addWidget(QLabel("线条宽度:"), 5, 0); self.contour_linewidth = QDoubleSpinBox(); self.contour_linewidth.setRange(0.1, 10.0); self.contour_linewidth.setValue(1.0); self.contour_linewidth.setSingleStep(0.1); c_layout.addWidget(self.contour_linewidth, 5, 1)
        self.contour_labels = QCheckBox("显示数值标签"); self.contour_labels.setChecked(True); c_layout.addWidget(self.contour_labels, 6, 0, 1, 2)
        scroll_layout.addWidget(contour_group)

        btn_layout = QHBoxLayout()
        reset_btn = QPushButton("重置视图"); reset_btn.clicked.connect(self.plot_widget.reset_view)
        btn_layout.addStretch()
        btn_layout.addWidget(reset_btn)
        scroll_layout.addLayout(btn_layout)
        
        scroll_layout.addStretch()
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        return tab

    def _create_probe_tab(self) -> QWidget:
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
        
    def _create_statistics_tab(self, parent_window) -> QWidget:
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        
        basic_group = QGroupBox("基础统计")
        basic_layout = QVBoxLayout(basic_group)
        
        info_label = QLabel("计算所有数据文件中每个原始变量的全局统计特征(均值、标准差等)。\n这些特征将作为常量在公式中使用。")
        info_label.setWordWrap(True)
        basic_layout.addWidget(info_label)

        action_layout = QHBoxLayout()
        self.calc_basic_stats_btn = QPushButton("开始计算基础统计")
        self.calc_basic_stats_btn.setToolTip("遍历所有CSV文件计算统计数据，过程可能较慢。")
        self.export_stats_btn = QPushButton("导出统计结果")
        self.export_stats_btn.setToolTip("将当前显示的统计结果直接保存到输出目录。")
        self.export_stats_btn.setEnabled(False)
        action_layout.addWidget(self.calc_basic_stats_btn)
        action_layout.addWidget(self.export_stats_btn)
        basic_layout.addLayout(action_layout)
        main_layout.addWidget(basic_group)
        
        custom_group = QGroupBox("自定义常量计算")
        custom_layout = QVBoxLayout(custom_group)
        
        custom_header_layout = QHBoxLayout()
        custom_info = QLabel("在此定义新的全局常量，每行一个。您可以使用基础统计的结果。<br>格式: <code>new_name = agg_func(expression)</code>")
        custom_info.setTextFormat(Qt.TextFormat.RichText)
        custom_info.setWordWrap(True)
        custom_header_layout.addWidget(custom_info, 1)

        custom_help_btn = QPushButton("?")
        custom_help_btn.setFixedSize(25, 25)
        custom_help_btn.setToolTip("查看自定义常量计算说明")
        custom_help_btn.clicked.connect(parent_window._show_custom_stats_help)
        custom_header_layout.addWidget(custom_help_btn)
        custom_layout.addLayout(custom_header_layout)
        
        self.custom_stats_input = QTextEdit()
        self.custom_stats_input.setFont(QFont("Courier New", 9))
        self.custom_stats_input.setPlaceholderText("示例:\nreynolds_stress_uv = mean((u - u_global_mean) * (v - v_global_mean))\ntke_global = mean(0.5 * (u**2 + v**2))")
        self.custom_stats_input.setFixedHeight(100)
        custom_layout.addWidget(self.custom_stats_input)

        self.calc_custom_stats_btn = QPushButton("计算自定义常量")
        self.calc_custom_stats_btn.setToolTip("基于基础统计和公式计算新的常量。")
        self.calc_custom_stats_btn.setEnabled(False)
        custom_btn_layout = QHBoxLayout()
        custom_btn_layout.addStretch()
        custom_btn_layout.addWidget(self.calc_custom_stats_btn)
        custom_layout.addLayout(custom_btn_layout)
        main_layout.addWidget(custom_group)

        results_group = QGroupBox("计算结果")
        results_layout = QVBoxLayout(results_group)
        self.stats_results_text = QTextEdit()
        self.stats_results_text.setReadOnly(True)
        self.stats_results_text.setFont(QFont("Courier New", 9))
        self.stats_results_text.setText("尚未计算。点击上方按钮开始。")
        results_layout.addWidget(self.stats_results_text)
        main_layout.addWidget(results_group)
        
        main_layout.addStretch()
        return tab

    def _create_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        img_group = QGroupBox("图片导出")
        img_layout = QGridLayout(img_group)
        img_layout.addWidget(QLabel("分辨率(DPI):"), 0, 0)
        self.export_dpi = QSpinBox(); self.export_dpi.setRange(100, 1200); self.export_dpi.setValue(300); self.export_dpi.setSingleStep(50); img_layout.addWidget(self.export_dpi, 0, 1)
        self.export_img_btn = QPushButton("保存当前帧图片")
        img_layout.addWidget(self.export_img_btn, 1, 0, 1, 2)
        layout.addWidget(img_group)
        
        vid_group = QGroupBox("视频导出")
        vid_layout = QGridLayout(vid_group)
        vid_layout.addWidget(QLabel("起始帧:"), 0, 0); self.video_start_frame = QSpinBox(); self.video_start_frame.setMinimum(0); vid_layout.addWidget(self.video_start_frame, 0, 1)
        vid_layout.addWidget(QLabel("结束帧:"), 1, 0); self.video_end_frame = QSpinBox(); self.video_end_frame.setMinimum(0); vid_layout.addWidget(self.video_end_frame, 1, 1)
        vid_layout.addWidget(QLabel("帧率(FPS):"), 2, 0); self.video_fps = QSpinBox(); self.video_fps.setRange(1, 60); self.video_fps.setValue(15); vid_layout.addWidget(self.video_fps, 2, 1)
        self.export_vid_btn = QPushButton("导出视频")
        vid_layout.addWidget(self.export_vid_btn, 3, 0, 1, 2)
        layout.addWidget(vid_group)
        
        batch_vid_group = QGroupBox("批量视频导出")
        batch_vid_layout = QVBoxLayout(batch_vid_group)
        self.batch_export_btn = QPushButton("选择设置并批量导出...")
        self.batch_export_btn.setToolTip("选择多个.json配置文件，为每个配置文件自动导出视频")
        batch_vid_layout.addWidget(self.batch_export_btn)
        layout.addWidget(batch_vid_group)
        
        perf_group = QGroupBox("性能设置")
        perf_layout = QVBoxLayout(perf_group)
        self.gpu_checkbox = QCheckBox("启用GPU加速 (需NVIDIA/CuPy)")
        self.gpu_checkbox.setToolTip("使用CUDA加速公式计算和视频渲染")
        perf_layout.addWidget(self.gpu_checkbox)
        cache_layout = QHBoxLayout(); cache_layout.addWidget(QLabel("内存缓存:"))
        self.cache_size_spinbox = QSpinBox(); self.cache_size_spinbox.setRange(10, 2000); self.cache_size_spinbox.setValue(100); self.cache_size_spinbox.setSingleStep(10); self.cache_size_spinbox.setSuffix(" 帧")
        cache_layout.addWidget(self.cache_size_spinbox)
        self.apply_cache_btn = QPushButton("应用")
        cache_layout.addWidget(self.apply_cache_btn)
        perf_layout.addLayout(cache_layout)
        layout.addWidget(perf_group)

        cfg_group = QGroupBox("设置管理")
        cfg_layout = QGridLayout(cfg_group)
        cfg_layout.addWidget(QLabel("配置文件:"), 0, 0)
        self.config_combo = QComboBox()
        cfg_layout.addWidget(self.config_combo, 0, 1, 1, 2)
        
        btn_layout = QHBoxLayout()
        self.save_config_btn = QPushButton("保存设置")
        self.new_config_btn = QPushButton("新建设置")
        btn_layout.addWidget(self.save_config_btn)
        btn_layout.addWidget(self.new_config_btn)
        cfg_layout.addLayout(btn_layout, 1, 1, 1, 2)

        self.config_status_label = QLabel("")
        self.config_status_label.setStyleSheet("color: orange;")
        cfg_layout.addWidget(self.config_status_label, 2, 0, 1, 3)

        layout.addWidget(cfg_group)
        
        layout.addStretch()
        return tab

    def _create_playback_group(self) -> QGroupBox:
        group = QGroupBox("播放控制")
        layout = QVBoxLayout(group)
        info_layout = QHBoxLayout()
        self.frame_info_label = QLabel("帧: 0/0")
        info_layout.addWidget(self.frame_info_label)
        info_layout.addStretch()
        self.timestamp_label = QLabel("时间戳: 0.0")
        info_layout.addWidget(self.timestamp_label)
        layout.addLayout(info_layout)
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setMinimum(0)
        layout.addWidget(self.time_slider)
        btns_layout = QHBoxLayout()
        self.play_button = QPushButton("播放")
        btns_layout.addWidget(self.play_button)
        self.prev_btn = QPushButton("<<")
        btns_layout.addWidget(self.prev_btn)
        self.next_btn = QPushButton(">>")
        btns_layout.addWidget(self.next_btn)
        btns_layout.addSpacing(20)
        btns_layout.addWidget(QLabel("跳帧:"))
        self.frame_skip_spinbox = QSpinBox()
        self.frame_skip_spinbox.setRange(1, 100)
        self.frame_skip_spinbox.setValue(1)
        self.frame_skip_spinbox.setSuffix(" 帧")
        btns_layout.addWidget(self.frame_skip_spinbox)
        layout.addLayout(btns_layout)
        return group

    def _create_path_group(self) -> QGroupBox:
        group = QGroupBox("路径设置")
        layout = QGridLayout(group)
        layout.addWidget(QLabel("数据目录:"), 0, 0)
        self.data_dir_line_edit = QLineEdit()
        self.data_dir_line_edit.setReadOnly(True)
        layout.addWidget(self.data_dir_line_edit, 0, 1)
        self.change_data_dir_btn = QPushButton("...")
        self.change_data_dir_btn.setToolTip("选择数据文件夹")
        layout.addWidget(self.change_data_dir_btn, 0, 2)
        layout.addWidget(QLabel("输出目录:"), 1, 0)
        self.output_dir_line_edit = QLineEdit()
        self.output_dir_line_edit.setReadOnly(True)
        layout.addWidget(self.output_dir_line_edit, 1, 1)
        self.change_output_dir_btn = QPushButton("...")
        self.change_output_dir_btn.setToolTip("选择输出文件夹")
        layout.addWidget(self.change_output_dir_btn, 1, 2)
        return group
    
    def _create_menu_bar(self, main_window: QMainWindow):
        menubar = main_window.menuBar()
        file_menu = menubar.addMenu('文件')
        self.reload_action = QAction('重新加载数据', main_window)
        self.reload_action.setShortcut('Ctrl+R')
        file_menu.addAction(self.reload_action)
        file_menu.addSeparator()
        self.exit_action = QAction('退出', main_window)
        self.exit_action.setShortcut('Ctrl+Q')
        file_menu.addAction(self.exit_action)
        
        view_menu = menubar.addMenu('视图')
        self.reset_view_action = QAction('重置视图', main_window)
        self.reset_view_action.setShortcut('Ctrl+0')
        view_menu.addAction(self.reset_view_action)
        
        help_menu = menubar.addMenu('帮助')
        self.formula_help_action = QAction('公式指南', main_window)
        self.formula_help_action.setShortcut('F1')
        help_menu.addAction(self.formula_help_action)
        help_menu.addSeparator()
        self.about_action = QAction('关于', main_window)
        help_menu.addAction(self.about_action)

    def _create_status_bar(self, main_window: QMainWindow):
        self.status_bar = QStatusBar()
        main_window.setStatusBar(self.status_bar)
        self.cache_label = QLabel("缓存: 0/100")
        self.status_bar.addPermanentWidget(self.cache_label)
        self.gpu_status_label = QLabel("GPU: 检测中...")
        self.status_bar.addPermanentWidget(self.gpu_status_label)
        self.status_bar.showMessage("准备就绪")