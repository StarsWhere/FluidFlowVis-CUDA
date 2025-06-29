#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, logging, time, numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QMessageBox
from PyQt6.QtCore import QThread, pyqtSignal, Qt

logger = logging.getLogger(__name__)

# 导入新的无头渲染器
from src.visualization.headless_renderer import HeadlessPlotter

class VideoExportWorker(QThread):
    progress_updated = pyqtSignal(int, int, str)
    export_finished = pyqtSignal(bool, str)
    
    def __init__(self, dm, p_conf, fname, s_f, e_f, fps):
        super().__init__()
        self.dm, self.p_conf, self.fname, self.s_f, self.fps = dm, p_conf, fname, s_f, fps
        self.e_f = min(e_f, self.dm.get_frame_count() - 1)
        self.is_cancelled = False
        self.executor = ThreadPoolExecutor(max_workers=max(1, os.cpu_count() // 2))

    def cancel(self):
        self.is_cancelled = True
        self.executor.shutdown(wait=True, cancel_futures=True)
    
    def run(self):
        try:
            total = self.e_f - self.s_f + 1
            if total <= 0: raise ValueError("帧范围无效，起始帧必须小于或等于结束帧。")
            
            frames, futures = {}, {self.executor.submit(self._render_frame, i): i for i in range(self.s_f, self.e_f + 1)}
            
            processed_count = 0
            for future in as_completed(futures):
                if self.is_cancelled: break
                idx = futures[future]
                try: 
                    result = future.result()
                    if result is not None: frames[idx] = result
                except Exception as e: 
                    logger.error(f"渲染帧 {idx} 出错: {e}")
                
                processed_count += 1
                self.progress_updated.emit(processed_count, total, f"已处理 {processed_count}/{total} 帧")

            if self.is_cancelled: 
                self.export_finished.emit(False, "导出已取消"); return

            images = [frames[i] for i in range(self.s_f, self.e_f + 1) if i in frames]
            if not images: raise ValueError("没有成功渲染任何帧。请检查日志。")

            if self.is_cancelled: # 在开始编码前再次检查
                self.export_finished.emit(False, "导出已取消"); return

            self.progress_updated.emit(total, total, "正在编码视频...")
            self._create_video(images, self.fname, self.fps)
            self.export_finished.emit(True, f"视频已成功导出到:\n{self.fname}")

        except Exception as e:
            logger.error(f"视频导出失败: {e}", exc_info=True)
            self.export_finished.emit(False, f"导出失败: {e}")
        finally:
            self.executor.shutdown(wait=True, cancel_futures=True)
            logger.info("VideoExportWorker 线程已结束。")

    def _render_frame(self, idx):
        if self.is_cancelled: return None
        data = self.dm.get_frame_data(idx)
        if data is None: raise ValueError(f"无法为帧 {idx} 加载数据")

        # 无头渲染器现在在内部创建自己的公式引擎实例
        plotter = HeadlessPlotter(self.p_conf)
        return plotter.render_frame(data, self.dm.get_variables())

    def _create_video(self, images, fname, fps):
        try:
            import moviepy.editor as mp
            logger.info(f"使用 moviepy 编码视频: {fname}")
            clips = [mp.ImageClip(m, duration=1.0/fps) for m in images]
            final_clip = mp.concatenate_videoclips(clips, method="compose")
            codec = 'libx264' if fname.lower().endswith('.mp4') else 'libvpx'
            if fname.lower().endswith('.gif'): 
                final_clip.write_gif(fname, fps=fps, logger=None)
            else: 
                final_clip.write_videofile(fname, fps=fps, codec=codec, logger='bar', threads=os.cpu_count())
        except ImportError:
            logger.warning("moviepy 未安装，尝试使用 imageio")
            import imageio
            with imageio.get_writer(fname, fps=fps, codec='libx264', quality=8, pixelformat='yuv420p', macro_block_size=1) as writer:
                for img in images: writer.append_data(img)

class VideoExportDialog(QDialog):
    def __init__(self, parent, dm, p_conf, fname, s_f, e_f, fps):
        super().__init__(parent)
        self.worker = None
        self._init_ui(fname, s_f, e_f, fps)
        self._start_export(dm, p_conf, fname, s_f, e_f, fps)
    
    def _init_ui(self, fname, s_f, e_f, fps):
        self.setWindowTitle("正在导出视频"); self.setModal(True); self.setFixedSize(450, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>文件:</b> {os.path.basename(fname)}<br><b>帧:</b> {s_f}-{e_f} ({e_f-s_f+1}帧)<br><b>帧率:</b> {fps}fps"))
        self.progress_bar = QProgressBar(); layout.addWidget(self.progress_bar)
        self.status_label = QLabel("准备..."); layout.addWidget(self.status_label)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); layout.addWidget(self.log_text)
        btn_layout = QHBoxLayout(); btn_layout.addStretch()
        self.cancel_btn = QPushButton("取消"); self.cancel_btn.clicked.connect(self._cancel_export); btn_layout.addWidget(self.cancel_btn)
        self.close_btn = QPushButton("关闭"); self.close_btn.clicked.connect(self.accept); self.close_btn.setEnabled(False); btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)
    
    def _start_export(self, dm, p_conf, fname, s_f, e_f, fps):
        self.worker = VideoExportWorker(dm, p_conf, fname, s_f, e_f, fps)
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.export_finished.connect(self._on_export_finished)
        self.worker.start(); self._log("开始并行渲染...")
    
    def _cancel_export(self):
        if self.worker and self.worker.isRunning():
            self._log("正在取消..."); self.cancel_btn.setEnabled(False); self.worker.cancel()
    
    def _on_progress_updated(self, current, total, msg):
        self.progress_bar.setMaximum(total); self.progress_bar.setValue(current); self.status_label.setText(msg)
    
    def _on_export_finished(self, success, msg):
        self.status_label.setText("完成！" if success else "失败！"); self._log(msg)
        self.cancel_btn.setEnabled(False); self.close_btn.setEnabled(True)
        if success: self.progress_bar.setValue(self.progress_bar.maximum()); QMessageBox.information(self, "成功", msg)
        else: QMessageBox.warning(self, "失败", msg)
    
    def _log(self, msg): self.log_text.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, "确认", "导出正在进行，确定关闭？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes: self.worker.cancel(); self.worker.wait(30000); event.accept() # 增加等待时间
            else: event.ignore()
        else: event.accept()