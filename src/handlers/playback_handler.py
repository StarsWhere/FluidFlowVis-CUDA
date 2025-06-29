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

    def connect_signals(self):
        self.ui.play_button.clicked.connect(self.toggle_play)
        self.ui.prev_btn.clicked.connect(self.prev_frame)
        self.ui.next_btn.clicked.connect(self.next_frame)
        self.ui.time_slider.valueChanged.connect(self.on_slider_changed)
        self.ui.frame_skip_spinbox.valueChanged.connect(self.on_frame_skip_changed)

    def on_slider_changed(self, value: int):
        if value != self.main_window.current_frame_index:
            self.main_window._load_frame(value)
    
    def on_frame_skip_changed(self, value: int):
        self.frame_skip_step = value
        self.play_timer.setInterval(50)

    def toggle_play(self):
        self.is_playing = not self.is_playing
        self.ui.play_button.setText("暂停" if self.is_playing else "播放")
        if self.is_playing:
            self.play_timer.setSingleShot(True)
            self.play_timer.start(0)
            self.ui.status_bar.showMessage("播放中...")
            # 如果是首次播放，自动将探针定位到中心
            if self.ui.plot_widget.last_mouse_coords is None and self.ui.plot_widget.current_data is not None and not self.ui.plot_widget.current_data.empty:
                x_min, x_max = self.ui.plot_widget.ax.get_xlim()
                y_min, y_max = self.ui.plot_widget.ax.get_ylim()
                center_x, center_y = (x_min + x_max) / 2, (y_min + y_max) / 2
                self.ui.plot_widget.last_mouse_coords = (center_x, center_y)
                self.ui.plot_widget.get_probe_data_at_coords(center_x, center_y)
        else:
            self.play_timer.stop()
            self.ui.status_bar.showMessage("已暂停")

    def _on_play_timer(self):
        self.play_timer.stop()
        if self.ui.plot_widget.is_busy_interpolating:
            self.skipped_frames += 1
            self.ui.status_bar.showMessage(f"渲染延迟，跳过 {self.skipped_frames} 帧...", 1000)
            if self.is_playing: self.play_timer.start()
            return
        
        self.skipped_frames = 0
        frame_count = self.dm.get_frame_count()
        if frame_count > 0:
            next_frame = (self.main_window.current_frame_index + self.frame_skip_step) % frame_count
            self.ui.time_slider.setValue(next_frame)

    def prev_frame(self):
        if self.main_window.current_frame_index > 0:
            self.ui.time_slider.setValue(self.main_window.current_frame_index - 1)
    
    def next_frame(self):
        frame_count = self.dm.get_frame_count()
        if frame_count > 0 and self.main_window.current_frame_index < frame_count - 1:
            self.ui.time_slider.setValue(self.main_window.current_frame_index + 1)

    def stop_playback(self):
        """停止播放并清理计时器。"""
        if self.is_playing:
            self.toggle_play()
        self.play_timer.stop()