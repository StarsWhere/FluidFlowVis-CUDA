
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口UI创建与布局模块
"""
import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QComboBox, QLineEdit, QPushButton,
    QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit,
    QStatusBar, QToolBar, QScrollArea, QTabWidget, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QListWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont, QIcon

from src.visualization.plot_widget import PlotWidget
from src.core.constants import VectorPlotType, StreamlineColor, PickerMode

class UiMainWindow:
    """此类负责创建和布局主窗口的所有UI组件。"""
    def setup_ui(self, main_window: QMainWindow, formula_engine):
        main_window.setWindowTitle("InterVis v3.5-ProFinal")
        main_window.setGeometry(100, 100, 1600, 950)
        
        central_widget = QWidget()
        main_window.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        self.plot_widget = PlotWidget(formula_engine)
        self.main_splitter.addWidget(self.plot_widget)
        
        self.control_panel = self._create_control_panel(main_window)
        self.main_splitter.addWidget(self.control_panel)
        
        self.main_splitter.setSizes([1200, 450])
        self.main_splitter.setStretchFactor(0, 1)
        
        self._create_menu_bar(main_window)
        self._create_tool_bar(main_window)
        self._create_status_bar(main_window)

    def _create_control_panel(self, parent_window) -> QWidget:
        panel = QWidget(); panel.setMaximumWidth(450); panel.setMinimumWidth(400)
        main_layout = QVBoxLayout(panel)
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self._create_visualization_tab(parent_window), "可视化")
        self.tab_widget.addTab(self._create_analysis_tab(parent_window), "分析")
        self.tab_widget.addTab(self._create_data_processing_tab(parent_window), "数据处理")
        self.tab_widget.addTab(self._create_datamanagement_tab(parent_window), "数据管理")
        self.tab_widget.addTab(self._create_export_tab(parent_window), "导出与性能")
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self._create_playback_group())
        main_layout.addWidget(self._create_path_group())
        return panel

    def _create_formula_input(self, label_text, placeholder, parent_window, help_method):
        layout = QHBoxLayout(); line_edit = QLineEdit(); line_edit.setPlaceholderText(placeholder)
        vars_btn = QPushButton("变量"); vars_btn.setToolTip("插入可用变量或常量")
        vars_btn.clicked.connect(lambda: parent_window._show_variable_menu(line_edit, vars_btn.mapToGlobal(vars_btn.rect().bottomLeft())))
        help_btn = QPushButton("?"); help_btn.setFixedSize(25, 25); help_btn.setToolTip("打开相关帮助 (F1/F2)"); help_btn.clicked.connect(help_method)
        layout.addWidget(line_edit); layout.addWidget(vars_btn); layout.addWidget(help_btn)
        return QLabel(label_text), layout, line_edit
    
    def _create_visualization_tab(self, parent_window) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab); scroll_area = QScrollArea(); scroll_widget = QWidget(); scroll_layout = QVBoxLayout(scroll_widget)
        
        template_theme_group = QGroupBox("预设与风格")
        tt_layout = QGridLayout(template_theme_group)
        
        tt_layout.addWidget(QLabel("可视化模板:"), 0, 0)
        self.template_combo = QComboBox(); tt_layout.addWidget(self.template_combo, 0, 1)
        template_btn_layout = QHBoxLayout()
        self.load_template_btn = QPushButton("加载"); template_btn_layout.addWidget(self.load_template_btn)
        self.save_template_btn = QPushButton("另存为..."); template_btn_layout.addWidget(self.save_template_btn)
        tt_layout.addLayout(template_btn_layout, 0, 2)
        self.template_help_btn = QPushButton("?"); self.template_help_btn.setFixedSize(25, 25); self.template_help_btn.setToolTip("打开可视化模板帮助")
        self.template_help_btn.clicked.connect(lambda: parent_window._show_help("template"))
        tt_layout.addWidget(self.template_help_btn, 0, 3)

        tt_layout.addWidget(QLabel("绘图主题:"), 1, 0)
        self.theme_combo = QComboBox(); tt_layout.addWidget(self.theme_combo, 1, 1)
        theme_btn_layout = QHBoxLayout()
        self.load_theme_btn = QPushButton("应用"); theme_btn_layout.addWidget(self.load_theme_btn)
        self.save_theme_btn = QPushButton("另存为..."); theme_btn_layout.addWidget(self.save_theme_btn)
        tt_layout.addLayout(theme_btn_layout, 1, 2)
        self.theme_help_btn = QPushButton("?"); self.theme_help_btn.setFixedSize(25, 25); self.theme_help_btn.setToolTip("打开绘图主题帮助")
        self.theme_help_btn.clicked.connect(lambda: parent_window._show_help("theme"))
        tt_layout.addWidget(self.theme_help_btn, 1, 3)
        scroll_layout.addWidget(template_theme_group)

        time_group = QGroupBox("时间分析")
        time_layout = QGridLayout(time_group)
        time_layout.addWidget(QLabel("分析模式:"), 0, 0)
        self.time_analysis_mode_combo = QComboBox(); self.time_analysis_mode_combo.addItems(["瞬时场", "时间平均场"])
        time_layout.addWidget(self.time_analysis_mode_combo, 0, 1)
        self.time_analysis_help_btn = QPushButton("?"); self.time_analysis_help_btn.setFixedSize(25, 25)
        self.time_analysis_help_btn.setToolTip("打开时间分析功能帮助")
        self.time_analysis_help_btn.clicked.connect(lambda: parent_window._show_help("analysis"))
        time_layout.addWidget(self.time_analysis_help_btn, 0, 2)

        self.time_average_range_widget = QWidget()
        range_layout = QGridLayout(self.time_average_range_widget)
        range_layout.setContentsMargins(0, 5, 0, 0)
        self.time_avg_start_slider = QSlider(Qt.Orientation.Horizontal); self.time_avg_start_spinbox = QSpinBox()
        self.time_avg_end_slider = QSlider(Qt.Orientation.Horizontal); self.time_avg_end_spinbox = QSpinBox()
        self.time_avg_start_spinbox.setMinimumWidth(60); self.time_avg_end_spinbox.setMinimumWidth(60)
        range_layout.addWidget(QLabel("起始帧:"), 0, 0); range_layout.addWidget(self.time_avg_start_slider, 0, 1); range_layout.addWidget(self.time_avg_start_spinbox, 0, 2)
        range_layout.addWidget(QLabel("结束帧:"), 1, 0); range_layout.addWidget(self.time_avg_end_slider, 1, 1); range_layout.addWidget(self.time_avg_end_spinbox, 1, 2)
        time_layout.addWidget(self.time_average_range_widget, 1, 0, 1, 3)
        scroll_layout.addWidget(time_group)

        axis_group = QGroupBox("坐标轴与标题"); axis_layout = QGridLayout(axis_group)
        title_label, title_layout, self.chart_title_edit = self._create_formula_input("图表标题:", "例: Frame {frame_index}, Time: {time:.3f}", parent_window, lambda: parent_window._show_help("axis_title"))
        axis_layout.addWidget(title_label, 0, 0); axis_layout.addLayout(title_layout, 0, 1)
        x_label, x_layout, self.x_axis_formula = self._create_formula_input("X轴公式:", "默认为 'x'", parent_window, lambda: parent_window._show_help("formula"))
        axis_layout.addWidget(x_label, 1, 0); axis_layout.addLayout(x_layout, 1, 1)
        y_label, y_layout, self.y_axis_formula = self._create_formula_input("Y轴公式:", "默认为 'y'", parent_window, lambda: parent_window._show_help("formula"))
        axis_layout.addWidget(y_label, 2, 0); axis_layout.addLayout(y_layout, 2, 1)
        
        axis_layout.addWidget(QLabel("拉伸比例:"), 3, 0)
        aspect_layout = QHBoxLayout()
        self.aspect_ratio_combo = QComboBox(); self.aspect_ratio_combo.addItems(["Auto", "Equal", "Custom"])
        aspect_layout.addWidget(self.aspect_ratio_combo, 1)
        self.aspect_ratio_spinbox = QDoubleSpinBox(); self.aspect_ratio_spinbox.setRange(0.01, 100.0); self.aspect_ratio_spinbox.setSingleStep(0.1); self.aspect_ratio_spinbox.setValue(1.0); self.aspect_ratio_spinbox.setVisible(False)
        aspect_layout.addWidget(self.aspect_ratio_spinbox)
        axis_layout.addLayout(aspect_layout, 3, 1)
        scroll_layout.addWidget(axis_group)

        heatmap_group = QGroupBox("背景热力图"); heatmap_group.setCheckable(True); self.heatmap_enabled = heatmap_group; h_layout = QGridLayout(heatmap_group)
        heat_label, heat_layout, self.heatmap_formula = self._create_formula_input("可视化公式:", "例: sqrt(u**2 + v**2)", parent_window, lambda: parent_window._show_help("formula"))
        h_layout.addWidget(heat_label, 0, 0); h_layout.addLayout(heat_layout, 0, 1)
        h_layout.addWidget(QLabel("颜色映射:"), 1, 0); self.heatmap_colormap = QComboBox(); self.heatmap_colormap.addItems(['viridis', 'plasma', 'inferno', 'magma', 'jet', 'coolwarm', 'RdBu_r']); h_layout.addWidget(self.heatmap_colormap, 1, 1)
        min_layout = QHBoxLayout(); self.heatmap_vmin = QLineEdit(); self.pick_vmin_btn = QPushButton("拾取"); self.pick_vmin_btn.clicked.connect(lambda: self.plot_widget.set_picker_mode(PickerMode.VMIN)); min_layout.addWidget(self.heatmap_vmin); min_layout.addWidget(self.pick_vmin_btn)
        max_layout = QHBoxLayout(); self.heatmap_vmax = QLineEdit(); self.pick_vmax_btn = QPushButton("拾取"); self.pick_vmax_btn.clicked.connect(lambda: self.plot_widget.set_picker_mode(PickerMode.VMAX)); max_layout.addWidget(self.heatmap_vmax); max_layout.addWidget(self.pick_vmax_btn)
        h_layout.addWidget(QLabel("最小值:"), 2, 0); h_layout.addLayout(min_layout, 2, 1); h_layout.addWidget(QLabel("最大值:"), 3, 0); h_layout.addLayout(max_layout, 3, 1)
        scroll_layout.addWidget(heatmap_group)
        
        contour_group = QGroupBox("前景等高线"); contour_group.setCheckable(True); self.contour_enabled = contour_group; c_layout = QGridLayout(contour_group)
        contour_label, contour_layout, self.contour_formula = self._create_formula_input("可视化公式:", "例: p - mean(p)", parent_window, lambda: parent_window._show_help("formula"))
        c_layout.addWidget(contour_label, 0, 0); c_layout.addLayout(contour_layout, 0, 1)
        c_layout.addWidget(QLabel("等高线数:"), 1, 0); self.contour_levels = QSpinBox(); self.contour_levels.setRange(2, 100); self.contour_levels.setValue(10); c_layout.addWidget(self.contour_levels, 1, 1)
        c_layout.addWidget(QLabel("线条颜色:"), 2, 0); self.contour_colors = QComboBox(); self.contour_colors.addItems(['black', 'white', 'red', 'blue', 'grey']); c_layout.addWidget(self.contour_colors, 2, 1)
        c_layout.addWidget(QLabel("线条宽度:"), 3, 0); self.contour_linewidth = QDoubleSpinBox(); self.contour_linewidth.setRange(0.1, 10.0); self.contour_linewidth.setValue(1.0); self.contour_linewidth.setSingleStep(0.1); c_layout.addWidget(self.contour_linewidth, 3, 1)
        self.contour_labels = QCheckBox("显示数值标签"); self.contour_labels.setChecked(True); c_layout.addWidget(self.contour_labels, 4, 0, 1, 2)
        scroll_layout.addWidget(contour_group)

        vector_group = QGroupBox("矢量/流线图"); vector_group.setCheckable(True); self.vector_enabled = vector_group; v_layout = QGridLayout(vector_group)
        v_layout.addWidget(QLabel("绘图类型:"), 0, 0); self.vector_plot_type = QComboBox()
        for item in VectorPlotType: self.vector_plot_type.addItem(item.value, item)
        v_layout.addWidget(self.vector_plot_type, 0, 1)
        u_label, u_layout, self.vector_u_formula = self._create_formula_input("U分量公式:", "例: u - u_global_mean", parent_window, lambda: parent_window._show_help("formula"))
        v_label, v_layout_input, self.vector_v_formula = self._create_formula_input("V分量公式:", "例: v - v_global_mean", parent_window, lambda: parent_window._show_help("formula"))
        v_layout.addWidget(u_label, 1, 0); v_layout.addLayout(u_layout, 1, 1); v_layout.addWidget(v_label, 2, 0); v_layout.addLayout(v_layout_input, 2, 1)
        
        self.quiver_options_group = QGroupBox("矢量图选项"); quiver_layout = QGridLayout(self.quiver_options_group)
        quiver_layout.addWidget(QLabel("矢量密度:"), 0, 0); self.quiver_density_spinbox = QSpinBox(); self.quiver_density_spinbox.setRange(1, 50); self.quiver_density_spinbox.setValue(10); quiver_layout.addWidget(self.quiver_density_spinbox, 0, 1)
        quiver_layout.addWidget(QLabel("矢量缩放:"), 1, 0); self.quiver_scale_spinbox = QDoubleSpinBox(); self.quiver_scale_spinbox.setRange(0.1, 100.0); self.quiver_scale_spinbox.setValue(1.0); quiver_layout.addWidget(self.quiver_scale_spinbox, 1, 1)
        v_layout.addWidget(self.quiver_options_group, 3, 0, 1, 2)

        self.streamline_options_group = QGroupBox("流线图选项"); stream_layout = QGridLayout(self.streamline_options_group)
        stream_layout.addWidget(QLabel("流线密度:"), 0, 0); self.stream_density_spinbox = QDoubleSpinBox(); self.stream_density_spinbox.setRange(0.2, 10.0); self.stream_density_spinbox.setValue(1.5); stream_layout.addWidget(self.stream_density_spinbox, 0, 1)
        stream_layout.addWidget(QLabel("流线线宽:"), 1, 0); self.stream_linewidth_spinbox = QDoubleSpinBox(); self.stream_linewidth_spinbox.setRange(0.2, 10.0); self.stream_linewidth_spinbox.setValue(1.0); stream_layout.addWidget(self.stream_linewidth_spinbox, 1, 1)
        stream_layout.addWidget(QLabel("流线颜色:"), 2, 0); self.stream_color_combo = QComboBox()
        for item in StreamlineColor: self.stream_color_combo.addItem(item.value, item)
        stream_layout.addWidget(self.stream_color_combo, 2, 1)
        v_layout.addWidget(self.streamline_options_group, 4, 0, 1, 2)
        scroll_layout.addWidget(vector_group)
        
        scroll_layout.addStretch(); scroll_widget.setLayout(scroll_layout); scroll_area.setWidget(scroll_widget); scroll_area.setWidgetResizable(True); layout.addWidget(scroll_area)
        return tab

    def _create_analysis_tab(self, parent_window) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab); analysis_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Main Probe Group
        probe_group = QGroupBox("数据探针"); probe_layout = QVBoxLayout(probe_group)
        coord_layout = QHBoxLayout(); coord_layout.addWidget(QLabel("鼠标坐标:")); self.probe_coord_label = QLabel("(0.00, 0.00)"); self.probe_coord_label.setFont(QFont("monospace")); coord_layout.addWidget(self.probe_coord_label); coord_layout.addStretch(); probe_layout.addLayout(coord_layout)
        
        self.probe_by_coords_btn = QPushButton("按坐标查询..."); self.probe_by_coords_btn.setToolTip("输入精确坐标查询探针数据"); probe_layout.addWidget(self.probe_by_coords_btn)
        
        self.probe_text = QTextEdit(); self.probe_text.setReadOnly(True); self.probe_text.setFont(QFont("Courier New", 9)); self.probe_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap); probe_layout.addWidget(self.probe_text)
        analysis_splitter.addWidget(probe_group)

        # Tools and Floating Probe Container
        tools_container = QWidget(); tools_main_layout = QVBoxLayout(tools_container); tools_main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Interactive Tools Group
        tools_group = QGroupBox("分析工具"); tools_layout = QGridLayout(tools_group)
        self.pick_timeseries_btn = QPushButton("拾取时间序列点"); self.pick_timeseries_btn.setCheckable(True); tools_layout.addWidget(self.pick_timeseries_btn, 0, 0)
        self.draw_profile_btn = QPushButton("绘制剖面图"); self.draw_profile_btn.setCheckable(True); tools_layout.addWidget(self.draw_profile_btn, 0, 1)
        self.pick_by_coords_btn = QPushButton("按坐标拾取..."); tools_layout.addWidget(self.pick_by_coords_btn, 1, 0)
        self.draw_profile_by_coords_btn = QPushButton("按坐标绘制剖面..."); tools_layout.addWidget(self.draw_profile_by_coords_btn, 1, 1)
        self.analysis_help_btn = QPushButton("帮助 (?)"); self.analysis_help_btn.setToolTip("打开分析功能使用指南"); self.analysis_help_btn.clicked.connect(lambda: parent_window._show_help("analysis")); tools_layout.addWidget(self.analysis_help_btn, 2, 0, 1, 2)
        tools_main_layout.addWidget(tools_group)

        # Floating Probe Group
        floating_probe_group = QGroupBox("悬浮探针显示"); fp_layout = QVBoxLayout(floating_probe_group)
        fp_layout.addWidget(QLabel("勾选要在图表上悬浮显示的变量:"))
        self.floating_probe_vars_list = QListWidget()
        self.floating_probe_vars_list.setStyleSheet("QListWidget::item { margin: 3px; }")
        fp_layout.addWidget(self.floating_probe_vars_list)
        tools_main_layout.addWidget(floating_probe_group)

        tools_main_layout.addStretch()
        analysis_splitter.addWidget(tools_container)
        
        analysis_splitter.setSizes([350, 250]) # Adjusted size for the new button
        layout.addWidget(analysis_splitter)
        return tab
        
    def _create_data_processing_tab(self, parent_window) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab); scroll_area = QScrollArea(); scroll_widget = QWidget(); scroll_layout = QVBoxLayout(scroll_widget)
        
        header_layout = QHBoxLayout()
        info_label = QLabel("在此处通过多种方式计算新变量，结果将永久保存在项目中。"); info_label.setWordWrap(True)
        header_layout.addWidget(info_label, 1)
        self.dp_help_btn = QPushButton("?"); self.dp_help_btn.setFixedSize(25, 25); self.dp_help_btn.setToolTip("打开数据处理功能指南")
        self.dp_help_btn.clicked.connect(lambda: parent_window._show_help("data_processing"))
        header_layout.addWidget(self.dp_help_btn)
        scroll_layout.addLayout(header_layout)

        compute_group = QGroupBox("1. 逐帧派生变量 (新数据列)"); custom_layout = QVBoxLayout(compute_group)
        info_label_1 = QLabel("基于<b>每个数据点在各自时刻</b>的值计算新变量。每行一个定义。"); info_label_1.setWordWrap(True); custom_layout.addWidget(info_label_1)
        self.new_variable_formula_edit = QTextEdit(); self.new_variable_formula_edit.setPlaceholderText("vel_mag = sqrt(u**2 + v**2)\nvorticity = curl(u, v)")
        self.new_variable_formula_edit.setFont(QFont("Courier New", 9)); self.new_variable_formula_edit.setFixedHeight(80)
        custom_layout.addWidget(self.new_variable_formula_edit)
        self.compute_and_add_btn = QPushButton("计算并添加 (逐帧)"); self.compute_and_add_btn.setEnabled(False)
        custom_btn_layout = QHBoxLayout(); custom_btn_layout.addStretch(); custom_btn_layout.addWidget(self.compute_and_add_btn); custom_layout.addLayout(custom_btn_layout)
        scroll_layout.addWidget(compute_group)

        time_agg_group = QGroupBox("2. 时间聚合变量 (新数据列)"); time_agg_layout = QVBoxLayout(time_agg_group)
        info_label_2 = QLabel("基于<b>每个空间点在所有时刻</b>的值进行聚合计算。每行一个定义。"); info_label_2.setWordWrap(True); time_agg_layout.addWidget(info_label_2)
        self.new_time_agg_formula_edit = QTextEdit(); self.new_time_agg_formula_edit.setPlaceholderText("u_time_avg = mean(u)\np_stdev = std(p)")
        self.new_time_agg_formula_edit.setFont(QFont("Courier New", 9)); self.new_time_agg_formula_edit.setFixedHeight(80)
        time_agg_layout.addWidget(self.new_time_agg_formula_edit)
        self.compute_and_add_time_agg_btn = QPushButton("计算并添加 (时间聚合)"); self.compute_and_add_time_agg_btn.setEnabled(False)
        time_agg_btn_layout = QHBoxLayout(); time_agg_btn_layout.addStretch(); time_agg_btn_layout.addWidget(self.compute_and_add_time_agg_btn); time_agg_layout.addLayout(time_agg_btn_layout)
        scroll_layout.addWidget(time_agg_group)

        # NEW: Combined computation group
        combined_group = QGroupBox("3. 组合批量计算 (高级)"); combined_layout = QVBoxLayout(combined_group)
        info_label_3 = QLabel("使用标记按顺序执行不同类型的计算。每行一个定义。"); info_label_3.setWordWrap(True); combined_layout.addWidget(info_label_3)
        self.combined_formula_edit = QTextEdit()
        self.combined_formula_edit.setText("#--- PER-FRAME ---#\n\n#--- TIME-AGGREGATED ---#\n")
        self.combined_formula_edit.setFont(QFont("Courier New", 9)); self.combined_formula_edit.setMinimumHeight(120)
        combined_layout.addWidget(self.combined_formula_edit)
        self.compute_combined_btn = QPushButton("执行组合计算"); self.compute_combined_btn.setEnabled(False)
        combined_btn_layout = QHBoxLayout(); combined_btn_layout.addStretch(); combined_btn_layout.addWidget(self.compute_combined_btn); combined_layout.addLayout(combined_btn_layout)
        scroll_layout.addWidget(combined_group)

        custom_group = QGroupBox("4. 全局常量 (标量值)"); custom_layout_2 = QVBoxLayout(custom_group)
        custom_info = QLabel("基于<b>整个数据集所有点</b>进行聚合，计算单个标量值。每行一个定义。"); custom_info.setWordWrap(True); custom_layout_2.addWidget(custom_info)
        self.custom_stats_input = QTextEdit(); self.custom_stats_input.setFont(QFont("Courier New", 9)); self.custom_stats_input.setPlaceholderText("tke_global = mean(0.5 * (u**2 + v**2))\navg_vorticity = mean(curl(u, v))")
        self.custom_stats_input.setFixedHeight(80); custom_layout_2.addWidget(self.custom_stats_input)
        self.save_and_calc_custom_stats_btn = QPushButton("保存并计算 (全局)"); self.save_and_calc_custom_stats_btn.setEnabled(False); custom_btn_layout_2 = QHBoxLayout(); custom_btn_layout_2.addStretch(); custom_btn_layout_2.addWidget(self.save_and_calc_custom_stats_btn); custom_layout_2.addLayout(custom_btn_layout_2)
        scroll_layout.addWidget(custom_group)

        results_group = QGroupBox("统计结果与管理"); results_layout = QVBoxLayout(results_group)
        self.stats_results_text = QTextEdit(); self.stats_results_text.setReadOnly(True); self.stats_results_text.setText("尚未计算。")
        results_layout.addWidget(self.stats_results_text)
        h_layout = QHBoxLayout()
        self.export_stats_btn = QPushButton("一键导出统计结果"); self.export_stats_btn.setEnabled(False)
        self.recalc_basic_stats_btn = QPushButton("重算基础统计")
        self.recalc_basic_stats_btn.setToolTip("重新计算所有原始变量的min/max/mean等基础值。")
        h_layout.addWidget(self.recalc_basic_stats_btn); h_layout.addWidget(self.export_stats_btn)
        results_layout.addLayout(h_layout)
        scroll_layout.addWidget(results_group)

        scroll_layout.addStretch(); scroll_widget.setLayout(scroll_layout); scroll_area.setWidget(scroll_widget); scroll_area.setWidgetResizable(True); layout.addWidget(scroll_area)
        return tab

    def _create_datamanagement_tab(self, parent_window) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        
        filter_group = QGroupBox("全局数据过滤器"); filter_layout = QVBoxLayout(filter_group)
        filter_help_layout = QHBoxLayout(); filter_help_layout.addWidget(QLabel("对此数据集应用SQL筛选条件。"), 1)
        dm_help_btn = QPushButton("?"); dm_help_btn.setFixedSize(25,25); dm_help_btn.setToolTip("打开数据管理与过滤帮助"); dm_help_btn.clicked.connect(lambda: parent_window._show_help("analysis")); filter_help_layout.addWidget(dm_help_btn)
        filter_layout.addLayout(filter_help_layout)
        self.filter_enabled_checkbox = QCheckBox("启用全局数据过滤器"); filter_layout.addWidget(self.filter_enabled_checkbox)
        
        filter_hbox = QHBoxLayout()
        self.filter_text_edit = QLineEdit()
        self.filter_text_edit.setPlaceholderText("SQL WHERE 子句, e.g., p > 1000 AND x < 0.5")
        filter_hbox.addWidget(self.filter_text_edit)
        
        self.build_filter_btn = QPushButton("构建...")
        self.build_filter_btn.setToolTip("使用辅助构建器创建过滤器")
        filter_hbox.addWidget(self.build_filter_btn)
        
        self.apply_filter_btn = QPushButton("应用")
        filter_hbox.addWidget(self.apply_filter_btn)
        filter_layout.addLayout(filter_hbox)
        layout.addWidget(filter_group)
        
        export_group = QGroupBox("数据导出"); export_layout = QVBoxLayout(export_group)
        info_label = QLabel("将当前数据集（可应用全局过滤器）导出为单个CSV文件。"); info_label.setWordWrap(True); export_layout.addWidget(info_label)
        self.export_data_csv_btn = QPushButton("导出数据"); export_layout.addWidget(self.export_data_csv_btn)
        layout.addWidget(export_group)

        var_management_group = QGroupBox("变量管理")
        vm_layout = QVBoxLayout(var_management_group)
        vm_layout.addWidget(QLabel("从数据库中选择一个变量进行操作："))
        
        self.variables_table = QTableWidget()
        self.variables_table.setColumnCount(3)
        self.variables_table.setHorizontalHeaderLabels(["变量名", "类型", "公式 / 来源"])
        self.variables_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.variables_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.variables_table.verticalHeader().setVisible(False)
        self.variables_table.horizontalHeader().setStretchLastSection(True)
        vm_layout.addWidget(self.variables_table)
        
        vm_buttons_layout = QHBoxLayout()
        vm_buttons_layout.addStretch()
        self.rename_variable_btn = QPushButton("重命名选中项...")
        self.delete_variable_btn = QPushButton("删除选中项")
        vm_buttons_layout.addWidget(self.rename_variable_btn)
        vm_buttons_layout.addWidget(self.delete_variable_btn)
        vm_layout.addLayout(vm_buttons_layout)
        layout.addWidget(var_management_group)

        db_group = QGroupBox("数据库维护"); db_layout = QVBoxLayout(db_group)
        self.db_info_label = QLabel("路径: N/A\n大小: 0.00 MB"); db_layout.addWidget(self.db_info_label)
        self.compact_db_btn = QPushButton("压缩优化数据库"); self.compact_db_btn.setToolTip("执行VACUUM命令，可减小文件体积并提升性能。"); db_layout.addWidget(self.compact_db_btn)
        layout.addWidget(db_group)

        layout.addStretch(); return tab

    def _create_export_tab(self, parent_window) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        cfg_group = QGroupBox("设置管理"); cfg_layout = QGridLayout(cfg_group)
        cfg_layout.addWidget(QLabel("配置文件:"), 0, 0); self.config_combo = QComboBox(); cfg_layout.addWidget(self.config_combo, 0, 1, 1, 2)
        btn_layout = QHBoxLayout(); self.save_config_btn = QPushButton("保存"); self.save_config_as_btn = QPushButton("另存为..."); btn_layout.addWidget(self.save_config_btn); btn_layout.addWidget(self.save_config_as_btn); cfg_layout.addLayout(btn_layout, 1, 1, 1, 2)
        self.config_status_label = QLabel(""); self.config_status_label.setStyleSheet("color: orange;"); cfg_layout.addWidget(self.config_status_label, 2, 0, 1, 3); layout.addWidget(cfg_group)

        export_group = QGroupBox("导出"); export_layout = QGridLayout(export_group)
        export_layout.addWidget(QLabel("分辨率(DPI):"), 0, 0); self.export_dpi = QSpinBox(); self.export_dpi.setRange(100, 1200); self.export_dpi.setValue(300); export_layout.addWidget(self.export_dpi, 0, 1)
        self.export_img_btn = QPushButton("保存当前渲染图表"); export_layout.addWidget(self.export_img_btn, 1, 0, 1, 2)
        export_layout.addWidget(QLabel("帧率(FPS):"), 2, 0); self.video_fps = QSpinBox(); self.video_fps.setRange(1, 60); self.video_fps.setValue(15); export_layout.addWidget(self.video_fps, 2, 1)
        export_layout.addWidget(QLabel("起始帧:"), 3, 0); self.video_start_frame = QSpinBox(); self.video_start_frame.setMinimum(0); export_layout.addWidget(self.video_start_frame, 3, 1)
        export_layout.addWidget(QLabel("结束帧:"), 4, 0); self.video_end_frame = QSpinBox(); self.video_end_frame.setMinimum(0); export_layout.addWidget(self.video_end_frame, 4, 1)
        export_layout.addWidget(QLabel("渲染网格:"), 5, 0); grid_res_layout = QHBoxLayout()
        self.video_grid_w = QSpinBox(); self.video_grid_w.setRange(50, 2000); self.video_grid_w.setValue(300); grid_res_layout.addWidget(self.video_grid_w)
        grid_res_layout.addWidget(QLabel("x")); self.video_grid_h = QSpinBox(); self.video_grid_h.setRange(50, 2000); self.video_grid_h.setValue(300); grid_res_layout.addWidget(self.video_grid_h)
        export_layout.addLayout(grid_res_layout, 5, 1); self.export_vid_btn = QPushButton("导出视频"); export_layout.addWidget(self.export_vid_btn, 6, 0, 1, 2)
        self.batch_export_btn = QPushButton("批量视频导出..."); export_layout.addWidget(self.batch_export_btn, 7, 0, 1, 2); layout.addWidget(export_group)
        
        perf_group = QGroupBox("性能"); perf_layout = QVBoxLayout(perf_group); self.gpu_checkbox = QCheckBox("启用GPU加速 (需NVIDIA/CuPy)")
        perf_layout.addWidget(self.gpu_checkbox); cache_layout = QHBoxLayout(); cache_layout.addWidget(QLabel("内存缓存:"))
        self.cache_size_spinbox = QSpinBox(); self.cache_size_spinbox.setRange(10, 2000); self.cache_size_spinbox.setValue(100); cache_layout.addWidget(self.cache_size_spinbox)
        self.apply_cache_btn = QPushButton("应用"); cache_layout.addWidget(self.apply_cache_btn); perf_layout.addLayout(cache_layout); layout.addWidget(perf_group); layout.addStretch(); return tab

    def _create_playback_group(self) -> QGroupBox:
        group = QGroupBox("播放控制"); layout = QVBoxLayout(group)
        
        info_layout = QHBoxLayout(); self.frame_info_label = QLabel("帧: 0/0"); info_layout.addWidget(self.frame_info_label); info_layout.addStretch(); self.timestamp_label = QLabel("时间戳: 0.0"); info_layout.addWidget(self.timestamp_label); layout.addLayout(info_layout)
        
        self.playback_widget = QWidget(); playback_layout = QVBoxLayout(self.playback_widget); playback_layout.setContentsMargins(0,0,0,0)
        self.time_slider = QSlider(Qt.Orientation.Horizontal); self.time_slider.setMinimum(0); playback_layout.addWidget(self.time_slider)
        
        btns_layout = QHBoxLayout()
        self.play_button = QPushButton("播放"); btns_layout.addWidget(self.play_button)
        self.prev_btn = QPushButton("<<"); btns_layout.addWidget(self.prev_btn)
        self.next_btn = QPushButton(">>"); btns_layout.addWidget(self.next_btn)
        btns_layout.addSpacing(10)
        btns_layout.addWidget(QLabel("跳帧:")); self.frame_skip_spinbox = QSpinBox(); self.frame_skip_spinbox.setRange(1, 100); self.frame_skip_spinbox.setValue(1); btns_layout.addWidget(self.frame_skip_spinbox)
        playback_layout.addLayout(btns_layout)
        
        time_var_layout = QHBoxLayout(); time_var_layout.setContentsMargins(0, 5, 0, 0)
        time_var_layout.addWidget(QLabel("时间轴变量:")); self.time_variable_combo = QComboBox(); self.time_variable_combo.setToolTip("选择哪个数据列作为播放和分析的时间依据"); time_var_layout.addWidget(self.time_variable_combo, 1);
        playback_layout.addLayout(time_var_layout)
        
        layout.addWidget(self.playback_widget)
        refresh_layout = QHBoxLayout(); refresh_layout.addStretch(); self.refresh_button = QPushButton("立即刷新"); refresh_layout.addWidget(self.refresh_button); layout.addLayout(refresh_layout)
        return group

    def _create_path_group(self) -> QGroupBox:
        group = QGroupBox("路径设置"); layout = QGridLayout(group)
        layout.addWidget(QLabel("项目目录:"), 0, 0); self.data_dir_line_edit = QLineEdit(); self.data_dir_line_edit.setReadOnly(True); layout.addWidget(self.data_dir_line_edit, 0, 1)
        self.change_data_dir_btn = QPushButton("..."); layout.addWidget(self.change_data_dir_btn, 0, 2)
        layout.addWidget(QLabel("输出目录:"), 1, 0); self.output_dir_line_edit = QLineEdit(); self.output_dir_line_edit.setReadOnly(True); layout.addWidget(self.output_dir_line_edit, 1, 1)
        self.change_output_dir_btn = QPushButton("..."); layout.addWidget(self.change_output_dir_btn, 1, 2); return group
    
    def _create_menu_bar(self, main_window: QMainWindow):
        menubar = main_window.menuBar()
        file_menu = menubar.addMenu('文件(&F)'); self.open_data_dir_action = QAction('设置项目目录...', main_window); self.set_output_dir_action = QAction('设置输出目录...', main_window)
        self.reload_action = QAction('重新导入数据', main_window); self.reload_action.setShortcut('Ctrl+R'); self.save_config_action = QAction('保存设置', main_window); self.save_config_action.setShortcut('Ctrl+S')
        self.save_config_as_action = QAction('设置另存为...', main_window); self.save_config_as_action.setShortcut('Ctrl+Shift+S'); self.new_config_action = QAction('新建设置...', main_window); self.new_config_action.setShortcut('Ctrl+N')
        self.exit_action = QAction('退出', main_window); self.exit_action.setShortcut('Ctrl+Q')
        file_menu.addAction(self.open_data_dir_action); file_menu.addAction(self.set_output_dir_action); file_menu.addAction(self.reload_action); file_menu.addSeparator()
        file_menu.addAction(self.save_config_action); file_menu.addAction(self.save_config_as_action); file_menu.addAction(self.new_config_action); file_menu.addSeparator(); file_menu.addAction(self.exit_action)
        
        view_menu = menubar.addMenu('视图(&V)'); self.reset_view_action = QAction('重置视图', main_window); self.reset_view_action.setShortcut('Ctrl+0')
        self.toggle_panel_action = QAction('显示/隐藏控制面板', main_window); self.toggle_panel_action.setShortcut('F4'); self.toggle_panel_action.setCheckable(True); self.toggle_panel_action.setChecked(True)
        self.full_screen_action = QAction('全屏', main_window); self.full_screen_action.setShortcut('F11'); self.full_screen_action.setCheckable(True)
        view_menu.addAction(self.reset_view_action); view_menu.addSeparator(); view_menu.addAction(self.toggle_panel_action); view_menu.addAction(self.full_screen_action)
        
        help_menu = menubar.addMenu('帮助(&H)')
        self.formula_help_action = QAction('公式指南', main_window); self.formula_help_action.setShortcut('F1')
        self.analysis_help_action = QAction("分析功能指南", main_window); self.analysis_help_action.setShortcut('F2')
        self.dp_help_action = QAction("数据处理指南", main_window)
        self.template_help_action = QAction("可视化模板指南", main_window)
        self.theme_help_action = QAction("绘图主题指南", main_window)
        self.about_action = QAction('关于 InterVis', main_window)
        help_menu.addAction(self.formula_help_action); help_menu.addAction(self.analysis_help_action); help_menu.addAction(self.dp_help_action)
        help_menu.addSeparator()
        help_menu.addAction(self.template_help_action); help_menu.addAction(self.theme_help_action)
        help_menu.addSeparator(); help_menu.addAction(self.about_action)

    def _create_tool_bar(self, main_window: QMainWindow):
        self.toolbar = QToolBar("MainToolBar"); self.toolbar.setObjectName("MainToolBar"); main_window.addToolBar(self.toolbar)
        self.toolbar.addAction(self.open_data_dir_action); self.toolbar.addAction(self.reload_action); self.toolbar.addSeparator()
        self.toolbar.addAction(self.save_config_action); self.toolbar.addSeparator(); self.toolbar.addAction(self.reset_view_action)

    def _create_status_bar(self, main_window: QMainWindow):
        self.status_bar = QStatusBar(); main_window.setStatusBar(self.status_bar)
        self.cache_label = QLabel("缓存: 0/100"); self.status_bar.addPermanentWidget(self.cache_label)
        self.gpu_status_label = QLabel("GPU: 检测中..."); self.status_bar.addPermanentWidget(self.gpu_status_label)
        self.status_bar.showMessage("准备就绪")
