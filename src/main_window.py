#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口界面 (已全面优化并补完所有代码)
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import textwrap

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QComboBox, QLineEdit, QPushButton,
    QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit,
    QStatusBar, QMenuBar, QFileDialog, QMessageBox,
    QScrollArea, QTabWidget, QInputDialog, QDialog, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings, QThread, QEventLoop
from PyQt6.QtGui import QAction, QKeySequence, QFont, QIcon


# 使用相对路径导入项目模块
from src.core.data_manager import DataManager
from src.visualization.plot_widget import PlotWidget
from src.core.formula_validator import FormulaValidator
from src.utils.help_dialog import HelpDialog
from src.utils.gpu_utils import is_gpu_available
from src.visualization.video_exporter import VideoExportDialog, VideoExportWorker

logger = logging.getLogger(__name__)

# --- 批量导出功能所需类别 ---

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

class BatchExportWorker(QThread):
    """在后台执行批量视频导出任务的工作线程。"""
    progress = pyqtSignal(int, int, str)  # current_index, total, filename
    log_message = pyqtSignal(str)
    finished = pyqtSignal(str)  # summary_message

    def __init__(self, config_files: List[str], data_manager: DataManager, output_dir: str, parent=None):
        super().__init__(parent)
        self.config_files = config_files
        self.data_manager = data_manager
        self.output_dir = output_dir
        self.is_cancelled = False

    def run(self):
        successful_exports = 0
        failed_exports = 0
        total_files = len(self.config_files)

        for i, filepath in enumerate(self.config_files):
            if self.is_cancelled:
                break
            
            filename = os.path.basename(filepath)
            self.progress.emit(i, total_files, filename)
            self.log_message.emit(f"正在读取配置文件: {filename}")

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                export_cfg = config.get("export", {})
                p_conf = {
                    'x_axis': config.get('axes', {}).get('x', 'x'),
                    'y_axis': config.get('axes', {}).get('y', 'y'),
                    'use_gpu': config.get('performance', {}).get('gpu', False),
                    'heatmap_config': config.get('heatmap', {}),
                    'contour_config': config.get('contour', {})
                }
                s_f = export_cfg.get("video_start_frame", 0)
                e_f = export_cfg.get("video_end_frame", self.data_manager.get_frame_count() - 1)
                fps = export_cfg.get("video_fps", 15)

                if s_f >= e_f:
                    raise ValueError("起始帧必须小于结束帧")

                config_name = os.path.splitext(filename)[0]
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                out_fname = os.path.join(self.output_dir, f"batch_{config_name}_{timestamp}.mp4")

                self.log_message.emit(f"准备导出视频: {os.path.basename(out_fname)}")
                
                video_worker = VideoExportWorker(self.data_manager, p_conf, out_fname, s_f, e_f, fps)
                
                loop = QEventLoop()
                export_success = False
                export_message = ""

                def on_video_finished(success, msg):
                    nonlocal export_success, export_message
                    export_success = success
                    export_message = msg
                    loop.quit()

                video_worker.export_finished.connect(on_video_finished)
                video_worker.progress_updated.connect(lambda cur, tot, msg: self.log_message.emit(f"  └ {msg}"))
                
                video_worker.start()
                loop.exec()

                if export_success:
                    self.log_message.emit(f"成功: {filename} -> {os.path.basename(out_fname)}")
                    successful_exports += 1
                else:
                    self.log_message.emit(f"失败: {filename}. 原因: {export_message}")
                    failed_exports += 1

            except Exception as e:
                self.log_message.emit(f"处理配置文件 '{filename}' 时发生严重错误: {e}")
                failed_exports += 1
        
        summary = f"成功导出 {successful_exports} 个视频，失败 {failed_exports} 个。"
        self.finished.emit(summary)

    def cancel(self):
        self.is_cancelled = True

# --- 全局统计功能所需类别 ---

class GlobalStatsWorker(QThread):
    """在后台计算全局统计数据"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager

    def run(self):
        try:
            results = self.data_manager.calculate_global_stats(
                lambda current, total: self.progress.emit(current, total)
            )
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"全局统计计算失败: {e}", exc_info=True)
            self.error.emit(str(e))

class CustomGlobalStatsWorker(QThread):
    """在后台计算自定义全局常量"""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, definitions: List[str], parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.definitions = definitions
    
    def run(self):
        try:
            results = self.data_manager.calculate_custom_global_stats(
                self.definitions,
                lambda current, total, msg: self.progress.emit(current, total, msg)
            )
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"自定义全局常量计算失败: {e}", exc_info=True)
            self.error.emit(str(e))

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

class MainWindow(QMainWindow):
    """
    应用程序的主窗口类，管理UI布局、用户交互和各个模块之间的协调。
    """
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("StarsWhere", "InterVis")
        self.data_manager = DataManager()
        self.formula_validator = FormulaValidator()
        
        self.current_frame_index: int = 0
        self.is_playing: bool = False
        self.frame_skip_step: int = 1 
        self.skipped_frames: int = 0
        self.config_is_dirty: bool = False
        self._is_loading_config: bool = False
        self.current_config_file: Optional[str] = None
        self._loaded_config: Optional[Dict[str, Any]] = None 
        self.batch_export_dialog: Optional[BatchExportDialog] = None
        self.batch_export_worker: Optional[BatchExportWorker] = None
        self.global_stats: Dict[str, float] = {}
        
        self.data_dir = self.settings.value("data_directory", os.path.join(os.getcwd(), "data"))
        self.output_dir = self.settings.value("output_directory", os.path.join(os.getcwd(), "output"))
        self.settings_dir = os.path.join(os.getcwd(), "settings")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.settings_dir, exist_ok=True)
        
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._on_play_timer)
        
        self._init_ui()
        self._connect_signals()
        self._load_settings()
        self._initialize_data()


    # region UI 初始化
    def _init_ui(self):
        self.setWindowTitle("InterVis v1.3")
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
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        
        self._create_menu_bar()
        self._create_status_bar()
        self._update_gpu_status_label()
    
    def _create_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(400)
        
        main_layout = QVBoxLayout(panel)
        self.tab_widget = QTabWidget()
        
        self.tab_widget.addTab(self._create_visualization_tab(), "可视化")
        self.tab_widget.addTab(self._create_probe_tab(), "数据探针")
        self.tab_widget.addTab(self._create_statistics_tab(), "全局统计")
        self.tab_widget.addTab(self._create_export_tab(), "导出与性能")
        
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self._create_playback_group())
        main_layout.addWidget(self._create_path_group())

        return panel
    
    def _create_visualization_tab(self) -> QWidget:
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
        axis_layout.addWidget(QLabel("Y轴变量:"), 1, 0)
        self.y_axis_combo = QComboBox()
        axis_layout.addWidget(self.y_axis_combo, 1, 1)
        scroll_layout.addWidget(axis_group)

        heatmap_group = QGroupBox("背景热力图")
        h_layout = QGridLayout(heatmap_group)
        self.heatmap_enabled = QCheckBox("启用"); self.heatmap_enabled.setChecked(True)
        h_layout.addWidget(self.heatmap_enabled, 0, 0, 1, 2)
        h_layout.addWidget(QLabel("变量:"), 1, 0)
        self.heatmap_variable = QComboBox(); h_layout.addWidget(self.heatmap_variable, 1, 1)
        
        h_formula_layout = QHBoxLayout()
        self.heatmap_formula = QLineEdit(); self.heatmap_formula.setPlaceholderText("例: p - mean(p)")
        h_help_btn = QPushButton("?"); h_help_btn.setFixedSize(25,25); h_help_btn.setToolTip("打开公式说明 (F1)"); h_help_btn.clicked.connect(self._show_formula_help)
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
        
    def _create_statistics_tab(self) -> QWidget:
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        
        # --- Basic Stats ---
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
        
        # --- Custom Constants ---
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
        custom_help_btn.clicked.connect(self._show_custom_stats_help)
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

        # --- Results ---
        results_group = QGroupBox("计算结果")
        results_layout = QVBoxLayout(results_group)
        self.stats_results_text = QTextEdit()
        self.stats_results_text.setReadOnly(True)
        self.stats_results_text.setFont(QFont("Courier New", 9))
        self.stats_results_text.setText("尚未计算。点击上方按钮开始。")
        results_layout.addWidget(self.stats_results_text)
        main_layout.addWidget(results_group)
        
        self.calc_basic_stats_btn.clicked.connect(self._start_global_stats_calculation)
        self.calc_custom_stats_btn.clicked.connect(self._start_custom_stats_calculation)
        self.export_stats_btn.clicked.connect(self._export_global_stats)

        main_layout.addStretch()
        return tab

    def _create_export_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        img_group = QGroupBox("图片导出")
        img_layout = QGridLayout(img_group)
        img_layout.addWidget(QLabel("分辨率(DPI):"), 0, 0)
        self.export_dpi = QSpinBox(); self.export_dpi.setRange(100, 1200); self.export_dpi.setValue(300); self.export_dpi.setSingleStep(50); img_layout.addWidget(self.export_dpi, 0, 1)
        export_img_btn = QPushButton("保存当前帧图片"); export_img_btn.clicked.connect(self._export_image)
        img_layout.addWidget(export_img_btn, 1, 0, 1, 2)
        layout.addWidget(img_group)
        
        vid_group = QGroupBox("视频导出")
        vid_layout = QGridLayout(vid_group)
        vid_layout.addWidget(QLabel("起始帧:"), 0, 0); self.video_start_frame = QSpinBox(); self.video_start_frame.setMinimum(0); vid_layout.addWidget(self.video_start_frame, 0, 1)
        vid_layout.addWidget(QLabel("结束帧:"), 1, 0); self.video_end_frame = QSpinBox(); self.video_end_frame.setMinimum(0); vid_layout.addWidget(self.video_end_frame, 1, 1)
        vid_layout.addWidget(QLabel("帧率(FPS):"), 2, 0); self.video_fps = QSpinBox(); self.video_fps.setRange(1, 60); self.video_fps.setValue(15); vid_layout.addWidget(self.video_fps, 2, 1)
        export_vid_btn = QPushButton("导出视频"); export_vid_btn.clicked.connect(self._export_video)
        vid_layout.addWidget(export_vid_btn, 3, 0, 1, 2)
        layout.addWidget(vid_group)
        
        batch_vid_group = QGroupBox("批量视频导出")
        batch_vid_layout = QVBoxLayout(batch_vid_group)
        batch_export_btn = QPushButton("选择设置并批量导出...")
        batch_export_btn.setToolTip("选择多个.json配置文件，为每个配置文件自动导出视频")
        batch_export_btn.clicked.connect(self._start_batch_export)
        batch_vid_layout.addWidget(batch_export_btn)
        layout.addWidget(batch_vid_group)
        
        perf_group = QGroupBox("性能设置")
        perf_layout = QVBoxLayout(perf_group)
        self.gpu_checkbox = QCheckBox("启用GPU加速 (需NVIDIA/CuPy)"); self.gpu_checkbox.setToolTip("使用CUDA加速公式计算和视频渲染"); self.gpu_checkbox.setEnabled(is_gpu_available()); self.gpu_checkbox.toggled.connect(self._on_gpu_toggle)
        perf_layout.addWidget(self.gpu_checkbox)
        cache_layout = QHBoxLayout(); cache_layout.addWidget(QLabel("内存缓存:"))
        self.cache_size_spinbox = QSpinBox(); self.cache_size_spinbox.setRange(10, 2000); self.cache_size_spinbox.setValue(100); self.cache_size_spinbox.setSingleStep(10); self.cache_size_spinbox.setSuffix(" 帧")
        cache_layout.addWidget(self.cache_size_spinbox)
        apply_cache_btn = QPushButton("应用"); apply_cache_btn.clicked.connect(self._apply_cache_settings); cache_layout.addWidget(apply_cache_btn)
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
        group = QGroupBox("播放控制"); layout = QVBoxLayout(group)
        info_layout = QHBoxLayout(); self.frame_info_label = QLabel("帧: 0/0"); info_layout.addWidget(self.frame_info_label); info_layout.addStretch(); self.timestamp_label = QLabel("时间戳: 0.0"); info_layout.addWidget(self.timestamp_label); layout.addLayout(info_layout)
        self.time_slider = QSlider(Qt.Orientation.Horizontal); self.time_slider.setMinimum(0); layout.addWidget(self.time_slider)
        btns_layout = QHBoxLayout(); self.play_button = QPushButton("播放"); btns_layout.addWidget(self.play_button); prev_btn = QPushButton("<<"); btns_layout.addWidget(prev_btn); next_btn = QPushButton(">>"); btns_layout.addWidget(next_btn); btns_layout.addSpacing(20); btns_layout.addWidget(QLabel("跳帧:")); self.frame_skip_spinbox = QSpinBox(); self.frame_skip_spinbox.setRange(1, 100); self.frame_skip_spinbox.setValue(1); self.frame_skip_spinbox.setSuffix(" 帧"); btns_layout.addWidget(self.frame_skip_spinbox); layout.addLayout(btns_layout)
        self.play_button.clicked.connect(self._toggle_play); prev_btn.clicked.connect(self._prev_frame); next_btn.clicked.connect(self._next_frame); self.time_slider.valueChanged.connect(self._on_slider_changed); self.frame_skip_spinbox.valueChanged.connect(self._on_frame_skip_changed)
        return group

    def _create_path_group(self) -> QGroupBox:
        group = QGroupBox("路径设置"); layout = QGridLayout(group)
        layout.addWidget(QLabel("数据目录:"), 0, 0); self.data_dir_line_edit = QLineEdit(self.data_dir); self.data_dir_line_edit.setReadOnly(True); layout.addWidget(self.data_dir_line_edit, 0, 1); self.change_data_dir_btn = QPushButton("..."); self.change_data_dir_btn.setToolTip("选择数据文件夹"); self.change_data_dir_btn.clicked.connect(self._change_data_directory); layout.addWidget(self.change_data_dir_btn, 0, 2)
        layout.addWidget(QLabel("输出目录:"), 1, 0); self.output_dir_line_edit = QLineEdit(self.output_dir); self.output_dir_line_edit.setReadOnly(True); layout.addWidget(self.output_dir_line_edit, 1, 1); self.change_output_dir_btn = QPushButton("..."); self.change_output_dir_btn.setToolTip("选择输出文件夹"); self.change_output_dir_btn.clicked.connect(self._change_output_directory); layout.addWidget(self.change_output_dir_btn, 1, 2)
        return group
    
    def _create_menu_bar(self):
        menubar = self.menuBar(); file_menu = menubar.addMenu('文件'); reload_action = QAction('重新加载数据', self); reload_action.setShortcut('Ctrl+R'); reload_action.triggered.connect(self._reload_data); file_menu.addAction(reload_action); file_menu.addSeparator(); exit_action = QAction('退出', self); exit_action.setShortcut('Ctrl+Q'); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        view_menu = menubar.addMenu('视图'); reset_view_action = QAction('重置视图', self); reset_view_action.setShortcut('Ctrl+0'); reset_view_action.triggered.connect(self.plot_widget.reset_view); view_menu.addAction(reset_view_action)
        help_menu = menubar.addMenu('帮助'); formula_help_action = QAction('公式指南', self); formula_help_action.setShortcut('F1'); formula_help_action.triggered.connect(self._show_formula_help); help_menu.addAction(formula_help_action); help_menu.addSeparator(); about_action = QAction('关于', self); about_action.triggered.connect(self._show_about); help_menu.addAction(about_action)

    def _create_status_bar(self):
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.cache_label = QLabel("缓存: 0/100"); self.status_bar.addPermanentWidget(self.cache_label)
        self.gpu_status_label = QLabel("GPU: 检测中..."); self.status_bar.addPermanentWidget(self.gpu_status_label)
        self.status_bar.showMessage("准备就绪")
    # endregion

    # region 信号与槽
    def _connect_signals(self):
        self.data_manager.loading_finished.connect(self._on_loading_finished)
        self.data_manager.error_occurred.connect(self._on_error)
        self.plot_widget.mouse_moved.connect(self._on_mouse_moved)
        self.plot_widget.probe_data_ready.connect(self._on_probe_data)
        self.plot_widget.value_picked.connect(self._on_value_picked)
        self.plot_widget.plot_rendered.connect(self._on_plot_rendered)
        self.plot_widget.interpolation_error.connect(self._on_interpolation_error)
        
        self.x_axis_combo.currentIndexChanged.connect(self._trigger_auto_apply)
        self.y_axis_combo.currentIndexChanged.connect(self._trigger_auto_apply)
        self.heatmap_enabled.toggled.connect(self._trigger_auto_apply)
        self.heatmap_variable.currentIndexChanged.connect(self._trigger_auto_apply)
        self.heatmap_formula.editingFinished.connect(self._trigger_auto_apply)
        self.heatmap_colormap.currentIndexChanged.connect(self._trigger_auto_apply)
        self.heatmap_vmin.editingFinished.connect(self._trigger_auto_apply)
        self.heatmap_vmax.editingFinished.connect(self._trigger_auto_apply)
        self.contour_enabled.toggled.connect(self._trigger_auto_apply)
        self.contour_variable.currentIndexChanged.connect(self._trigger_auto_apply)
        self.contour_formula.editingFinished.connect(self._trigger_auto_apply)
        self.contour_levels.valueChanged.connect(self._trigger_auto_apply)
        self.contour_colors.currentIndexChanged.connect(self._trigger_auto_apply)
        self.contour_linewidth.valueChanged.connect(self._trigger_auto_apply)
        self.contour_labels.toggled.connect(self._trigger_auto_apply)

        self.gpu_checkbox.toggled.connect(self._mark_config_as_dirty)
        self.cache_size_spinbox.valueChanged.connect(self._mark_config_as_dirty)
        self.frame_skip_spinbox.valueChanged.connect(self._mark_config_as_dirty)
        self.export_dpi.valueChanged.connect(self._mark_config_as_dirty)
        self.video_fps.valueChanged.connect(self._mark_config_as_dirty)
        self.video_start_frame.valueChanged.connect(self._mark_config_as_dirty)
        self.video_end_frame.valueChanged.connect(self._mark_config_as_dirty)

        self.config_combo.currentIndexChanged.connect(self._on_config_selected)
        self.save_config_btn.clicked.connect(self._save_current_config)
        self.new_config_btn.clicked.connect(self._create_new_config)

    def _trigger_auto_apply(self, *args):
        if self.data_manager.get_frame_count() > 0:
            self._apply_visualization_settings()

    def _on_gpu_toggle(self, is_on):
        self.plot_widget.set_config(use_gpu=is_on)
        self._update_gpu_status_label()
        self._trigger_auto_apply() # Re-render with new setting
        self._mark_config_as_dirty()

    def _on_loading_finished(self, success: bool, message: str):
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
                self._populate_config_combobox()
                self.calc_basic_stats_btn.setEnabled(True)
            else:
                QMessageBox.warning(self, "数据为空", "指定的数据目录中没有找到有效的CSV文件。")
                self.calc_basic_stats_btn.setEnabled(False)
        else:
            QMessageBox.critical(self, "错误", f"无法初始化数据管理器: {message}")
            self.calc_basic_stats_btn.setEnabled(False)

    def _on_interpolation_error(self, message: str):
        """Handles errors from the plot widget's interpolation worker."""
        # **FIX**: Instantiate QMessageBox to enable RichText formatting.
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("可视化错误")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(f"无法渲染图形，公式可能存在问题。<br><br><b>错误详情:</b><br>{message}")
        msg_box.exec()

        # Check which formula might be the culprit and clear it.
        # A common mistake is using a constant expression (which has no data variables) for a plot.
        
        # Check heatmap formula
        h_formula = self.heatmap_formula.text().strip()
        if h_formula:
            used_vars = self.formula_validator.get_used_variables(h_formula)
            # A valid plot formula must contain at least one per-point data variable.
            # If used_vars is empty, it's a constant expression.
            if not used_vars:
                logger.warning(f"检测到无效的热力图公式 (常量表达式): '{h_formula}'. 将被清除。")
                self.heatmap_formula.clear()

        # Check contour formula
        c_formula = self.contour_formula.text().strip()
        if c_formula:
            used_vars = self.formula_validator.get_used_variables(c_formula)
            if not used_vars:
                logger.warning(f"检测到无效的等高线公式 (常量表达式): '{c_formula}'. 将被清除。")
                self.contour_formula.clear()

    def _on_error(self, message: str):
        self.status_bar.showMessage(f"错误: {message}", 5000)
        QMessageBox.critical(self, "发生错误", message)

    def _on_mouse_moved(self, x: float, y: float):
        self.probe_coord_label.setText(f"({x:.3e}, {y:.3e})")

    def _on_probe_data(self, probe_data: dict):
        try:
            lines = [f"{'变量名':<16s} {'数值'}", "---------------------------"]
            lines.extend([f"{k:<16s} {v:12.6e}" for k, v in probe_data['variables'].items()])
            self.probe_text.setPlainText("\n".join(lines))
        except Exception as e:
            logger.debug(f"更新探针数据显示失败: {e}")

    def _on_value_picked(self, mode: str, value: float):
        target_widget = self.heatmap_vmin if mode == 'vmin' else self.heatmap_vmax
        target_widget.setText(f"{value:.4e}")
        self._trigger_auto_apply()

    def _on_plot_rendered(self):
        if self.is_playing:
            self.play_timer.start()

    def _toggle_play(self):
        self.is_playing = not self.is_playing
        self.play_button.setText("暂停" if self.is_playing else "播放")
        if self.is_playing:
            self.play_timer.setSingleShot(True)
            self.play_timer.start(0)
            self.status_bar.showMessage("播放中...")
            if self.plot_widget.last_mouse_coords is None and self.plot_widget.current_data is not None and not self.plot_widget.current_data.empty:
                x_min, x_max = self.plot_widget.current_data[self.plot_widget.x_axis].min(), self.plot_widget.current_data[self.plot_widget.x_axis].max()
                y_min, y_max = self.plot_widget.current_data[self.plot_widget.y_axis].min(), self.plot_widget.current_data[self.plot_widget.y_axis].max()
                center_x, center_y = (x_min + x_max) / 2, (y_min + y_max) / 2
                self.plot_widget.last_mouse_coords = (center_x, center_y)
                self.plot_widget.get_probe_data_at_coords(center_x, center_y)
        else:
            self.play_timer.stop()
            self.status_bar.showMessage("已暂停")

    def _on_play_timer(self):
        self.play_timer.stop()
        if self.plot_widget.is_busy_interpolating:
            self.skipped_frames += 1
            self.status_bar.showMessage(f"渲染延迟，跳过 {self.skipped_frames} 帧...", 1000)
            if self.is_playing: self.play_timer.start()
            return
        
        self.skipped_frames = 0
        next_frame = (self.current_frame_index + self.frame_skip_step) % self.data_manager.get_frame_count()
        self.time_slider.setValue(next_frame)

    def _prev_frame(self):
        if self.current_frame_index > 0: self.time_slider.setValue(self.current_frame_index - 1)
    def _next_frame(self):
        if self.current_frame_index < self.data_manager.get_frame_count() - 1: self.time_slider.setValue(self.current_frame_index + 1)
    def _on_slider_changed(self, value: int):
        if value != self.current_frame_index: self._load_frame(value)
    def _on_frame_skip_changed(self, value: int):
        self.frame_skip_step = value; self.play_timer.setInterval(50); self._mark_config_as_dirty()
    # endregion
    
    # region 核心逻辑
    def _initialize_data(self):
        self.status_bar.showMessage(f"扫描目录: {self.data_dir}...")
        self.data_manager.initialize(self.data_dir)

    def _populate_variable_combos(self):
        variables = self.data_manager.get_variables()
        if not variables: return
        
        combos = [self.x_axis_combo, self.y_axis_combo, self.heatmap_variable, self.contour_variable]
        for combo in combos:
            current_text = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
        
        self.heatmap_variable.addItem("无", None)
        self.contour_variable.addItem("无", None)
        
        for var in variables:
            for combo in combos: combo.addItem(var, var)
        
        for combo in combos:
            if combo.findText(current_text) != -1: combo.setCurrentText(current_text)
        
        if 'x' in variables: self.x_axis_combo.setCurrentText('x')
        if 'y' in variables: self.y_axis_combo.setCurrentText('y')
        if 'p' in variables: self.heatmap_variable.setCurrentText('p')
        
        for combo in combos:
            combo.blockSignals(False)

    def _load_frame(self, frame_index: int):
        if not (0 <= frame_index < self.data_manager.get_frame_count()): return
        data = self.data_manager.get_frame_data(frame_index)
        if data is not None:
            self.current_frame_index = frame_index
            self.plot_widget.update_data(data)
            self._update_frame_info()
            if self.plot_widget.last_mouse_coords:
                x, y = self.plot_widget.last_mouse_coords
                self.plot_widget.get_probe_data_at_coords(x, y)

    def _update_frame_info(self):
        fc = self.data_manager.get_frame_count()
        self.frame_info_label.setText(f"帧: {self.current_frame_index + 1}/{fc}")
        info = self.data_manager.get_frame_info(self.current_frame_index)
        if info: self.timestamp_label.setText(f"时间戳: {info['timestamp']}")
        cache = self.data_manager.get_cache_info()
        self.cache_label.setText(f"缓存: {cache['size']}/{cache['max_size']}")

    def _apply_visualization_settings(self):
        if self.data_manager.get_frame_count() == 0: return

        try:
            vmin = float(self.heatmap_vmin.text()) if self.heatmap_vmin.text().strip() else None
            vmax = float(self.heatmap_vmax.text()) if self.heatmap_vmax.text().strip() else None
        except ValueError:
            vmin, vmax = None, None # In case of bad input, just ignore it
            self.heatmap_vmin.clear(); self.heatmap_vmax.clear()
            QMessageBox.warning(self, "输入错误", "最小值/最大值必须是有效的数字。输入已被清除。")

        heat_cfg = {'enabled': self.heatmap_enabled.isChecked(), 'variable': self.heatmap_variable.currentData(), 'formula': self.heatmap_formula.text().strip(), 'colormap': self.heatmap_colormap.currentText(), 'vmin': vmin, 'vmax': vmax}
        # **FIX**: Clear field FIRST, then show message box.
        if heat_cfg['formula'] and not self.formula_validator.validate(heat_cfg['formula']):
            invalid_formula = heat_cfg['formula']
            self.heatmap_formula.clear()
            QMessageBox.warning(self, "公式错误", f"热力图公式无效，内容已清除:\n\n'{invalid_formula}'")
            return
            
        contour_cfg = {'enabled': self.contour_enabled.isChecked(), 'variable': self.contour_variable.currentData(), 'formula': self.contour_formula.text().strip(), 'levels': self.contour_levels.value(), 'colors': self.contour_colors.currentText(), 'linewidths': self.contour_linewidth.value(), 'show_labels': self.contour_labels.isChecked()}
        # **FIX**: Clear field FIRST, then show message box.
        if contour_cfg['formula'] and not self.formula_validator.validate(contour_cfg['formula']):
            invalid_formula = contour_cfg['formula']
            self.contour_formula.clear()
            QMessageBox.warning(self, "公式错误", f"等高线公式无效，内容已清除:\n\n'{invalid_formula}'")
            return

        self.plot_widget.set_config(
            heatmap_config=heat_cfg, 
            contour_config=contour_cfg, 
            x_axis=self.x_axis_combo.currentText(), 
            y_axis=self.y_axis_combo.currentText()
        )
        self._load_frame(self.current_frame_index)
        self.status_bar.showMessage("可视化设置已更新", 2000)
        self._mark_config_as_dirty()
    # endregion

    # region 菜单与文件操作
    def _show_formula_help(self):
        base_vars = self.data_manager.get_variables()
        HelpDialog(self.formula_validator.get_formula_help_html(base_vars), self).exec()

    def _show_custom_stats_help(self):
        help_text = """
        <html><head><style>
            body { font-family: sans-serif; line-height: 1.6; }
            h3 { color: #005A9C; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
            code { background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }
            ul li { margin-bottom: 5px; }
        </style></head><body>
            <h2>自定义常量计算指南</h2>
            <p>此功能允许您计算新的全局常量，这些常量将在整个数据集（所有帧）上进行聚合计算。</p>
            
            <h3>格式</h3>
            <p>每行输入一个定义，严格遵守以下格式：</p>
            <p><code>常量名称 = 聚合函数(表达式)</code></p>

            <ul>
                <li><b>常量名称:</b> 必须是有效的 Python 标识符 (只能包含字母、数字和下划线，且不能以数字开头)。</li>
                <li><b>聚合函数:</b> 当前支持以下函数：
                    <ul>
                        <li><code>mean(expr)</code>: 计算表达式在所有数据点上的平均值。</li>
                        <li><code>sum(expr)</code>: 计算总和。</li>
                        <li><code>std(expr)</code>: 计算标准差。</li>
                        <li><code>var(expr)</code>: 计算方差。</li>
                    </ul>
                </li>
                <li><b>表达式:</b> 这是一个标准的数学公式，可以包含：
                    <ul>
                        <li>数据中的原始变量 (如 <code>u</code>, <code>v</code>, <code>p</code>)。</li>
                        <li>之前计算出的基础统计量 (如 <code>u_global_mean</code>)。</li>
                        <li>科学常数 (如 <code>pi</code>)。</li>
                        <li>基本的数学运算符 (<code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>**</code>)。</li>
                    </ul>
                </li>
            </ul>

            <h3>示例</h3>
            <p><b>计算雷诺应力分量:</b></p>
            <p><code>reynolds_stress_uv = mean((u - u_global_mean) * (v - v_global_mean))</code></p>
            
            <p><b>计算全局湍动能 (TKE):</b></p>
            <p><code>tke_global = mean(0.5 * ((u - u_global_mean)**2 + (v - v_global_mean)**2))</code></p>

            <h3>工作流程</h3>
            <p>1. 首先点击 "开始计算基础统计" 来获得如 <code>u_global_mean</code> 等基础量。</p>
            <p>2. 在文本框中输入您的自定义常量定义。</p>
            <p>3. 点击 "计算自定义常量"。计算过程可能会很长。</p>
            <p>4. 计算成功后，新的常量将出现在下方的 "计算结果" 区域，并可在其他公式（如可视化公式或后续的自定义常量）中使用。</p>
        </body></html>
        """
        HelpDialog(help_text, self).exec()
        
    def _show_about(self): QMessageBox.about(self, "关于", "<h2>InterVis v1.3</h2><p>作者: StarsWhere</p><p>一个使用PyQt6和Matplotlib构建的数据可视化工具。</p>")
    
    def _reload_data(self):
        if self.is_playing: self._toggle_play()
        self._reset_global_stats()
        self.data_manager.clear_all(); self._initialize_data()

    def _change_data_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择数据目录", self.data_dir)
        if new_dir and new_dir != self.data_dir:
            self.data_dir = new_dir; self.data_dir_line_edit.setText(self.data_dir); self._reload_data()
            
    def _change_output_directory(self):
        new_dir = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir)
        if new_dir and new_dir != self.output_dir:
            self.output_dir = new_dir; self.output_dir_line_edit.setText(self.output_dir)
            
    def _apply_cache_settings(self): 
        self.data_manager.set_cache_size(self.cache_size_spinbox.value()); self._update_frame_info(); self._mark_config_as_dirty()

    def _export_image(self):
        fname = os.path.join(self.output_dir, f"frame_{self.current_frame_index:05d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        if self.plot_widget.save_figure(fname, self.export_dpi.value()):
            QMessageBox.information(self, "成功", f"图片已保存到:\n{fname}")
        else: QMessageBox.warning(self, "失败", "图片保存失败。")

    def _export_video(self):
        s_f, e_f = self.video_start_frame.value(), self.video_end_frame.value()
        if s_f >= e_f: QMessageBox.warning(self, "参数错误", "起始帧必须小于结束帧"); return
        fname = os.path.join(self.output_dir, f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        p_conf = {
            'x_axis': self.x_axis_combo.currentText(), 'y_axis': self.y_axis_combo.currentText(), 
            'use_gpu': self.gpu_checkbox.isChecked(), 'heatmap_config': self._get_current_config()['heatmap'], 
            'contour_config': self._get_current_config()['contour']
        }
        VideoExportDialog(self, self.data_manager, p_conf, fname, s_f, e_f, self.video_fps.value()).exec()
    # endregion
    
    # region 批量导出逻辑
    def _start_batch_export(self):
        if self.data_manager.get_frame_count() == 0:
            QMessageBox.warning(self, "无数据", "请先加载数据再执行批量导出。"); return
            
        config_files, _ = QFileDialog.getOpenFileNames(self, "选择要批量导出的配置文件", self.settings_dir, "JSON files (*.json)")
        if not config_files: return

        self.batch_export_dialog = BatchExportDialog(self)
        self.batch_export_worker = BatchExportWorker(config_files, self.data_manager, self.output_dir)
        self.batch_export_worker.progress.connect(self.batch_export_dialog.update_progress)
        self.batch_export_worker.log_message.connect(self.batch_export_dialog.add_log)
        self.batch_export_worker.finished.connect(self.batch_export_dialog.on_finish)
        self.batch_export_worker.finished.connect(self._on_batch_export_finished)
        self.batch_export_dialog.show()
        self.batch_export_worker.start()

    def _on_batch_export_finished(self, summary_message: str):
        if self.batch_export_dialog and self.batch_export_dialog.isVisible():
             QMessageBox.information(self, "批量导出完成", summary_message)
        else:
             self.status_bar.showMessage(summary_message, 10000)
        self.batch_export_worker = None; self.batch_export_dialog = None
    # endregion

    # region 全局统计逻辑
    def _reset_global_stats(self):
        self.global_stats.clear()
        self.data_manager.clear_global_stats()
        self.formula_validator.update_custom_global_variables({})
        self.stats_results_text.setText("数据已重载，请重新计算。")
        self.export_stats_btn.setEnabled(False)
        self.calc_custom_stats_btn.setEnabled(False)

    def _start_global_stats_calculation(self):
        if self.data_manager.get_frame_count() == 0:
            QMessageBox.warning(self, "无数据", "请先加载数据再计算统计量。"); return
            
        self.stats_progress_dialog = StatsProgressDialog(self, "正在计算基础统计")
        self.stats_worker = GlobalStatsWorker(self.data_manager)
        self.stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.stats_worker.finished.connect(self._on_global_stats_finished)
        self.stats_worker.error.connect(self._on_global_stats_error)
        
        self.stats_worker.start()
        self.stats_progress_dialog.exec()

    def _on_global_stats_finished(self, results: Dict[str, float]):
        self.stats_progress_dialog.accept()
        self.global_stats = results
        
        if not results:
            self.stats_results_text.setText("计算完成，但没有得到任何结果。\n请检查数据文件是否有效。")
            self.export_stats_btn.setEnabled(False)
            self.calc_custom_stats_btn.setEnabled(False)
            QMessageBox.warning(self, "计算完成", "未计算出任何统计数据。")
            return

        self._update_stats_display()
        self.export_stats_btn.setEnabled(True)
        self.calc_custom_stats_btn.setEnabled(True)
        
        self.formula_validator.update_custom_global_variables(self.global_stats)
        self._trigger_auto_apply()

        QMessageBox.information(self, "计算完成", "基础统计数据已计算并可用于公式中。")

    def _on_global_stats_error(self, error_msg: str):
        self.stats_progress_dialog.accept()
        QMessageBox.critical(self, "计算失败", f"计算基础统计时发生错误: \n{error_msg}")
        self.stats_results_text.setText(f"计算失败: {error_msg}")
        self.export_stats_btn.setEnabled(False)
        self.calc_custom_stats_btn.setEnabled(False)

    def _start_custom_stats_calculation(self):
        definitions_text = self.custom_stats_input.toPlainText().strip()
        if not definitions_text:
            QMessageBox.information(self, "无定义", "请输入至少一个自定义常量定义。"); return
        
        definitions = [line.strip() for line in definitions_text.split('\n') if line.strip()]
        
        self.stats_progress_dialog = StatsProgressDialog(self, "正在计算自定义常量")
        self.custom_stats_worker = CustomGlobalStatsWorker(self.data_manager, definitions)
        self.custom_stats_worker.progress.connect(self.stats_progress_dialog.update_progress)
        self.custom_stats_worker.finished.connect(self._on_custom_stats_finished)
        self.custom_stats_worker.error.connect(self._on_custom_stats_error)
        
        self.custom_stats_worker.start()
        self.stats_progress_dialog.exec()

    def _on_custom_stats_finished(self, new_stats: Dict[str, float]):
        self.stats_progress_dialog.accept()
        if not new_stats:
            QMessageBox.warning(self, "计算完成", "未计算出任何新的自定义常量。")
            return
        
        self._update_stats_display()
        self.formula_validator.update_custom_global_variables(self.data_manager.global_stats)
        self._trigger_auto_apply()
        QMessageBox.information(self, "计算完成", f"成功计算了 {len(new_stats)} 个自定义常量。")

    def _on_custom_stats_error(self, error_msg: str):
        self.stats_progress_dialog.accept()
        QMessageBox.critical(self, "计算失败", f"计算自定义常量时发生错误: \n{error_msg}")

    def _update_stats_display(self):
        """Helper to refresh the stats text edit from data_manager.global_stats"""
        all_stats = self.data_manager.global_stats
        if not all_stats:
            self.stats_results_text.setText("无统计结果。")
            return
        
        basic_stats_keys = {key for var in self.data_manager.get_variables() for key in all_stats if key.startswith(var + "_global_")}
        custom_stats_keys = set(all_stats.keys()) - basic_stats_keys
        
        lines = [f"全局统计计算结果 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})", "="*50]
        
        if basic_stats_keys:
            lines.append("\n--- 基础统计 ---")
            for var in sorted(self.data_manager.get_variables()):
                lines.append(f"\n[ 变量: {var} ]")
                var_keys = sorted([key for key in basic_stats_keys if key.startswith(var + "_global_")])
                for key in var_keys:
                    stat_name = key.replace(var + "_global_", "")
                    lines.append(f"  {stat_name:<10s}: {all_stats[key]:15.6e}")
        
        if custom_stats_keys:
            lines.append("\n\n--- 自定义常量 ---")
            for key in sorted(list(custom_stats_keys)):
                lines.append(f"{key:<25s}: {all_stats[key]:15.6e}")
                
        self.stats_results_text.setText("\n".join(lines))

    def _export_global_stats(self):
        if not self.global_stats:
            QMessageBox.warning(self, "无数据", "没有可导出的统计数据。"); return
        
        filepath = os.path.join(self.output_dir, f"global_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.stats_results_text.toPlainText())
            self.status_bar.showMessage(f"统计结果已保存到输出目录", 5000)
            QMessageBox.information(self, "导出成功", f"统计结果已直接保存到输出目录:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"无法保存文件: {e}")
    # endregion

    # region 设置管理逻辑
    def _mark_config_as_dirty(self, *args):
        if self._is_loading_config: return
        current_ui_config = self._get_current_config()
        if self._loaded_config != current_ui_config:
            self.config_is_dirty = True
            self.config_status_label.setText("存在未保存的修改")
        else:
            self.config_is_dirty = False
            self.config_status_label.setText("")

    def _populate_config_combobox(self):
        self.config_combo.blockSignals(True)
        self.config_combo.clear()

        default_config_path = os.path.join(self.settings_dir, "default.json")
        if not os.path.exists(default_config_path):
            logger.info("未找到 default.json，正在创建一个新的。")
            try:
                with open(default_config_path, 'w', encoding='utf-8') as f:
                    self._populate_variable_combos()
                    json.dump(self._get_current_config(), f, indent=4)
            except Exception as e: logger.error(f"创建默认配置文件失败: {e}")

        config_files = [f for f in os.listdir(self.settings_dir) if f.endswith('.json')]
        self.config_combo.addItems(config_files)
        last_config = os.path.basename(self.settings.value("last_config_file", default_config_path))
        if last_config in config_files: self.config_combo.setCurrentText(last_config)
        
        self.config_combo.blockSignals(False)
        self._load_config_by_name(self.config_combo.currentText())

    def _on_config_selected(self, index: int):
        if self.config_is_dirty:
            reply = QMessageBox.question(self, '未保存的修改', "当前设置已被修改，是否要在切换前保存？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self._save_current_config()
            elif reply == QMessageBox.StandardButton.Cancel:
                self.config_combo.blockSignals(True)
                self.config_combo.setCurrentText(os.path.basename(self.current_config_file))
                self.config_combo.blockSignals(False)
                return
        self._load_config_by_name(self.config_combo.currentText())

    def _load_config_by_name(self, filename: str):
        if not filename: return
        filepath = os.path.join(self.settings_dir, filename)
        if not os.path.exists(filepath):
            logger.error(f"Config file not found: {filepath}")
            QMessageBox.critical(self, "加载失败", f"找不到配置文件: {filename}"); return
        
        self._is_loading_config = True
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self._apply_config(config)
            self.current_config_file = filepath
            self.settings.setValue("last_config_file", filepath)
            self._loaded_config = self._get_current_config()
            self.config_is_dirty = False
            self.config_status_label.setText("")
            self.status_bar.showMessage(f"已加载设置: {filename}", 3000)
        except Exception as e:
            logger.error(f"加载配置文件 '{filename}' 失败: {e}", exc_info=True)
            QMessageBox.critical(self, "加载失败", f"无法加载或解析配置文件。\n\n错误: {e}")
        finally:
            self._is_loading_config = False

    def _save_current_config(self):
        if not self.current_config_file:
            QMessageBox.warning(self, "错误", "没有选定的配置文件。"); return
        
        try:
            with open(self.current_config_file, 'w', encoding='utf-8') as f:
                current_config = self._get_current_config()
                json.dump(current_config, f, indent=4)
            self._loaded_config = current_config
            self.config_is_dirty = False
            self.config_status_label.setText("设置已保存")
            self.status_bar.showMessage(f"设置已保存到 {os.path.basename(self.current_config_file)}", 3000)
        except Exception as e:
            logger.error(f"保存配置文件 '{self.current_config_file}' 失败: {e}", exc_info=True)
            QMessageBox.critical(self, "保存失败", f"无法写入配置文件。\n\n错误: {e}")

    def _create_new_config(self):
        text, ok = QInputDialog.getText(self, "新建设置", "请输入新配置文件的名称:")
        if ok and text:
            if any(c in r'/\:*?"<>|' for c in text):
                QMessageBox.warning(self, "名称无效", "文件名不能包含以下字符: /\\:*?\"<>|"); return

            new_filename = f"{text}.json"
            new_filepath = os.path.join(self.settings_dir, new_filename)
            
            if os.path.exists(new_filepath):
                reply = QMessageBox.question(self, "文件已存在", f"文件 '{new_filename}' 已存在。是否要覆盖它？")
                if reply != QMessageBox.StandardButton.Yes: return

            self.current_config_file = new_filepath
            self._save_current_config()
            
            self.config_combo.blockSignals(True)
            if self.config_combo.findText(new_filename) == -1: self.config_combo.addItem(new_filename)
            self.config_combo.setCurrentText(new_filename)
            self.config_combo.blockSignals(False)
            self.settings.setValue("last_config_file", new_filepath)
            self.config_is_dirty = False; self.config_status_label.setText("")

    def _get_current_config(self) -> Dict[str, Any]:
        return {
            "version": "1.3", "axes": {"x": self.x_axis_combo.currentText(), "y": self.y_axis_combo.currentText()},
            "heatmap": {'enabled': self.heatmap_enabled.isChecked(), 'variable': self.heatmap_variable.currentData(), 'formula': self.heatmap_formula.text(), 'colormap': self.heatmap_colormap.currentText(), 'vmin': self.heatmap_vmin.text().strip() or None, 'vmax': self.heatmap_vmax.text().strip() or None},
            "contour": {'enabled': self.contour_enabled.isChecked(), 'variable': self.contour_variable.currentData(), 'formula': self.contour_formula.text(), 'levels': self.contour_levels.value(), 'colors': self.contour_colors.currentText(), 'linewidths': self.contour_linewidth.value(), 'show_labels': self.contour_labels.isChecked()},
            "playback": {"frame_skip_step": self.frame_skip_spinbox.value()},
            "export": {"dpi": self.export_dpi.value(), "video_fps": self.video_fps.value(), "video_start_frame": self.video_start_frame.value(), "video_end_frame": self.video_end_frame.value()},
            "performance": {"gpu": self.gpu_checkbox.isChecked(), "cache": self.cache_size_spinbox.value()}
        }
    
    def _apply_config(self, config: Dict[str, Any]):
        for widget in self.findChildren(QWidget): widget.blockSignals(True)
        try:
            perf = config.get("performance", {}); axes = config.get("axes", {}); heatmap = config.get("heatmap", {}); contour = config.get("contour", {}); playback = config.get("playback", {}); export = config.get("export", {})
            if self.gpu_checkbox.isEnabled(): self.gpu_checkbox.setChecked(perf.get("gpu", False))
            self.cache_size_spinbox.setValue(perf.get("cache", 100)); self.data_manager.set_cache_size(self.cache_size_spinbox.value())
            if axes.get("x"): self.x_axis_combo.setCurrentText(axes["x"])
            if axes.get("y"): self.y_axis_combo.setCurrentText(axes["y"])
            self.heatmap_enabled.setChecked(heatmap.get("enabled", True))
            self.heatmap_variable.setCurrentText(heatmap.get("variable") or "无")
            self.heatmap_formula.setText(heatmap.get("formula", ""))
            self.heatmap_colormap.setCurrentText(heatmap.get("colormap", "viridis"))
            self.heatmap_vmin.setText(str(heatmap.get("vmin") or ""))
            self.heatmap_vmax.setText(str(heatmap.get("vmax") or ""))
            self.contour_enabled.setChecked(contour.get("enabled", False))
            self.contour_variable.setCurrentText(contour.get("variable") or "无")
            self.contour_formula.setText(contour.get("formula", ""))
            self.contour_levels.setValue(contour.get("levels", 10))
            self.contour_colors.setCurrentText(contour.get("colors", "black"))
            self.contour_linewidth.setValue(contour.get("linewidths", 1.0))
            self.contour_labels.setChecked(contour.get("show_labels", True))
            self.frame_skip_spinbox.setValue(playback.get("frame_skip_step", 1))
            self.export_dpi.setValue(export.get("dpi", 300))
            self.video_fps.setValue(export.get("video_fps", 15))
            self.video_start_frame.setValue(export.get("video_start_frame", 0))
            self.video_end_frame.setValue(export.get("video_end_frame", 0))
        except Exception as e:
            logger.error(f"应用设置失败: {e}", exc_info=True)
            QMessageBox.critical(self, "错误", f"应用设置失败，文件可能已损坏或版本不兼容。\n\n错误: {e}")
        finally:
            for widget in self.findChildren(QWidget): widget.blockSignals(False)
            self._connect_signals() # Reconnect after blocking all
            self._apply_visualization_settings()
            self._update_gpu_status_label()

    # endregion
    
    # region 程序设置与关闭
    def _load_settings(self):
        self.restoreGeometry(self.settings.value("geometry", self.saveGeometry()))
        self.restoreState(self.settings.value("windowState", self.saveState()))
        self.frame_skip_spinbox.setValue(self.settings.value("frame_skip_step", 1, type=int))
        self.export_dpi.setValue(self.settings.value("export_dpi", 300, type=int))
        self.video_fps.setValue(self.settings.value("video_fps", 15, type=int))
        self.cache_size_spinbox.setValue(self.settings.value("cache_size", 100, type=int))
        if self.gpu_checkbox.isEnabled():
            self.gpu_checkbox.setChecked(self.settings.value("use_gpu", False, type=bool))
        self._update_gpu_status_label()

    def _save_settings(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("data_directory", self.data_dir)
        self.settings.setValue("output_directory", self.output_dir)
        self.settings.setValue("frame_skip_step", self.frame_skip_spinbox.value())
        self.settings.setValue("export_dpi", self.export_dpi.value())
        self.settings.setValue("video_fps", self.video_fps.value())
        self.settings.setValue("cache_size", self.cache_size_spinbox.value())
        self.settings.setValue("use_gpu", self.gpu_checkbox.isChecked())
        if self.current_config_file:
            self.settings.setValue("last_config_file", self.current_config_file)

    def closeEvent(self, event):
        if self.batch_export_worker and self.batch_export_worker.isRunning():
            reply = QMessageBox.question(self, "确认", "批量导出正在进行中，确定要退出吗？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.batch_export_worker.cancel(); self.batch_export_worker.wait()
            else:
                event.ignore(); return

        if self.config_is_dirty:
            reply = QMessageBox.question(self, '未保存的修改', "当前设置已被修改，是否要在退出前保存？", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save: self._save_current_config()
            elif reply == QMessageBox.StandardButton.Cancel: event.ignore(); return

        self._save_settings()
        self.play_timer.stop()
        self.plot_widget.thread_pool.clear(); self.plot_widget.thread_pool.waitForDone()
        logger.info("应用程序正常关闭")
        super().closeEvent(event)
    # endregion

    # region 辅助方法
    def _update_gpu_status_label(self):
        if is_gpu_available():
            status, color = ("GPU: 启用", "green") if self.gpu_checkbox.isChecked() else ("GPU: 可用 (未启用)", "orange")
        else:
            status, color = ("GPU: 不可用", "red")
        self.gpu_status_label.setText(status)
        self.gpu_status_label.setStyleSheet(f"color: {color};")
    # endregion