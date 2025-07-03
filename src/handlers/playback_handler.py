# src/handlers/playback_handler.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
播放控制处理器
"""
import logging
from PyQt6.QtCore import QTimer

logger = logging.getLogger(__name__)

class PlaybackHandler:
    """处理与时间轴、播放、暂停、逐帧导航相关的逻辑。"""
    
    def __init__(self, main_window, ui, data_manager):
        self.main_window = main_window
        self.ui = ui
        self.dm = data_manager
        
        self.is_playing: bool = False
        self.frame_skip_step: int = 1 
        self.skipped_frames: int = 0
        
        self.play_timer = QTimer(main_window)
        self.play_timer.timeout.connect(self._on_play_timer)
        self._is_enabled = True

    def connect_signals(self):
        self.ui.play_button.clicked.connect(self.toggle_play)
        self.ui.prev_btn.clicked.connect(self.prev_frame)
        self.ui.next_btn.clicked.connect(self.next_frame)
        self.ui.time_slider.valueChanged.connect(self.on_slider_changed)
        self.ui.frame_skip_spinbox.valueChanged.connect(self.on_frame_skip_changed)
        self.ui.time_variable_combo.currentIndexChanged.connect(self.on_time_variable_changed)

    def update_time_axis_candidates(self):
        """使用来自DataManager的候选项更新时间轴下拉菜单。"""
        self.ui.time_variable_combo.blockSignals(True)
        current_selection = self.ui.time_variable_combo.currentText()
        self.ui.time_variable_combo.clear()
        
        candidates = self.dm.get_time_candidates()
        if not candidates:
            self.ui.time_variable_combo.setEnabled(False)
            return
            
        self.ui.time_variable_combo.addItems(candidates)
        self.ui.time_variable_combo.setEnabled(True)
        
        if current_selection in candidates:
            self.ui.time_variable_combo.setCurrentText(current_selection)
        elif self.dm.time_variable in candidates:
             self.ui.time_variable_combo.setCurrentText(self.dm.time_variable)
        
        self.ui.time_variable_combo.blockSignals(False)
        # 触发一次更新以确保一致性
        self.on_time_variable_changed()

    def on_time_variable_changed(self):
        """当用户在下拉菜单中选择一个新的时间变量时调用。"""
        new_time_var = self.ui.time_variable_combo.currentText()
        if not new_time_var or new_time_var == self.dm.time_variable:
            return

        self.stop_playback()
        self.dm.set_time_variable(new_time_var)
        self.dm.ensure_index_on(new_time_var) # [OPTIMIZED] 确保在新列上创建索引
        
        frame_count = self.dm.get_frame_count()
        self.ui.time_slider.setMaximum(frame_count - 1 if frame_count > 0 else 0)
        
        # 通知主窗口刷新
        self.main_window._force_refresh_plot(reset_view=True)
        self.main_window.ui.status_bar.showMessage(f"时间轴已更新为: {new_time_var}", 3000)

    def set_enabled(self, enabled: bool):
        """启用或禁用整个播放控制逻辑。"""
        self._is_enabled = enabled
        if not enabled and self.is_playing:
            self.stop_playback()
        self.ui.playback_widget.setEnabled(enabled)

    def on_slider_changed(self, value: int):
        if not self._is_enabled: return
        # A block to prevent recursive signal loop when slider is updated programmatically
        if self.ui.time_slider.signalsBlocked(): return
        if value != self.main_window.current_frame_index:
            self.main_window._load_frame(value)
    
    def on_frame_skip_changed(self, value: int):
        self.frame_skip_step = value

    def toggle_play(self):
        if not self._is_enabled: return
        self.is_playing = not self.is_playing
        self.ui.play_button.setText("暂停" if self.is_playing else "播放")
        if self.is_playing:
            self.play_timer.setSingleShot(True)
            self.play_timer.start(0)
            self.main_window.ui.status_bar.showMessage("播放中...")
            if self.ui.plot_widget.last_mouse_coords is None and self.ui.plot_widget.current_data is not None:
                try:
                    x_min, x_max = self.ui.plot_widget.ax.get_xlim(); y_min, y_max = self.ui.plot_widget.ax.get_ylim()
                    center_x, center_y = (x_min + x_max) / 2, (y_min + y_max) / 2
                    self.ui.plot_widget.last_mouse_coords = (center_x, center_y)
                    self.ui.plot_widget.get_probe_data_at_coords(center_x, center_y)
                except Exception as e:
                    logger.warning(f"自动定位探针失败: {e}")
        else:
            self.play_timer.stop()
            self.main_window.ui.status_bar.showMessage("已暂停")

    def _on_play_timer(self):
        self.play_timer.stop()
        if not self.is_playing or not self._is_enabled: return
        
        if self.ui.plot_widget.is_busy_interpolating:
            self.skipped_frames += 1
            self.main_window.ui.status_bar.showMessage(f"渲染延迟，跳过 {self.skipped_frames} 帧...", 1000)
            if self.is_playing: self.play_timer.start(50)
            return
        
        self.skipped_frames = 0
        frame_count = self.dm.get_frame_count()
        if frame_count > 0:
            next_frame = (self.main_window.current_frame_index + self.frame_skip_step) % frame_count
            self.ui.time_slider.setValue(next_frame)

    def prev_frame(self):
        if not self._is_enabled: return
        if self.main_window.current_frame_index > 0:
            self.ui.time_slider.setValue(self.main_window.current_frame_index - 1)
    
    def next_frame(self):
        if not self._is_enabled: return
        frame_count = self.dm.get_frame_count()
        if frame_count > 0 and self.main_window.current_frame_index < frame_count - 1:
            self.ui.time_slider.setValue(self.main_window.current_frame_index + 1)

    def stop_playback(self):
        """停止播放并清理计时器。"""
        if self.is_playing:
            self.is_playing = False
            self.ui.play_button.setText("播放")
        self.play_timer.stop()