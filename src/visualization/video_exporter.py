#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, logging, time, numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QMessageBox
from PyQt6.QtCore import QThread, pyqtSignal, Qt

logger = logging.getLogger(__name__)

class VideoExportWorker(QThread):
    progress_updated = pyqtSignal(int, int, str)
    export_finished = pyqtSignal(bool, str)
    
    def __init__(self, dm, p_conf, fname, s_f, e_f, fps):
        super().__init__()
        self.dm, self.p_conf, self.fname, self.s_f, self.e_f, self.fps = dm, p_conf, fname, s_f, e_f, fps
        self.is_cancelled = False
        self.executor = ThreadPoolExecutor(max_workers=max(1, os.cpu_count() // 2))

    def cancel(self):
        self.is_cancelled = True; self.executor.shutdown(wait=False, cancel_futures=True)
    
    def run(self):
        try:
            total = self.e_f - self.s_f + 1; frames = {}
            futures = {self.executor.submit(self._render_frame, i): i for i in range(self.s_f, self.e_f + 1)}
            for future in as_completed(futures):
                if self.is_cancelled: break
                idx = futures[future]
                try: frames[idx] = future.result()
                except Exception as e: logger.error(f"渲染帧 {idx} 出错: {e}"); frames[idx] = None
                self.progress_updated.emit(len(frames), total, f"已渲染 {len(frames)}/{total} 帧")
            if self.is_cancelled: self.export_finished.emit(False, "导出已取消"); return
            self.progress_updated.emit(total, total, "正在整理帧...")
            images = [frames[i] for i in range(self.s_f, self.e_f + 1) if frames.get(i) is not None]
            if not images: raise ValueError("没有成功渲染任何帧")
            self.progress_updated.emit(total, total, "正在编码视频..."); self._create_video(images, self.fname, self.fps)
            self.export_finished.emit(True, f"视频已成功导出到:\n{self.fname}")
        except Exception as e: logger.error(f"视频导出失败: {e}", exc_info=True); self.export_finished.emit(False, f"导出失败: {e}")
        finally: self.executor.shutdown(wait=False)

    def _render_frame(self, idx):
        data = self.dm.get_frame_data(idx);
        if data is None: raise ValueError("无法加载数据")
        from src.visualization.plot_widget import PlotWidget
        from src.core.formula_validator import FormulaValidator
        from PyQt6.QtCore import QEventLoop # Import QEventLoop
        validator = FormulaValidator(); validator.update_allowed_variables(self.dm.get_variables())
        # 确保验证器也知道全局变量
        if 'global_scope' in self.p_conf:
            validator.update_custom_global_variables(self.p_conf['global_scope'])
            
        plotter = PlotWidget(validator); plotter.set_config(**self.p_conf)
        plotter.update_data(data)
        
        # Use QEventLoop to wait for plot_rendered signal with a timeout
        loop = QEventLoop()
        plotter.plot_rendered.connect(loop.quit)
        
        start_time = time.time()
        # 等待插值和渲染完成
        while plotter.is_busy_interpolating:
            if time.time() - start_time > 30: # 增加超时时间
                plotter.thread_pool.clear() # 尝试清理线程池
                raise TimeoutError(f"渲染帧 {idx} 超时")
            QApplication.processEvents() # 使用主应用的事件循环处理
            time.sleep(0.01)
        
        # 即使 is_busy_interpolating 变为 false, 信号可能还未发出
        # 给一小段时间让信号处理
        time.sleep(0.1)
        
        if loop.isRunning():
            loop.quit()

        return plotter.get_figure_as_numpy(dpi=150)

    def _create_video(self, images, fname, fps):
        try:
            import moviepy.editor as mp
            clips = [mp.ImageClip(m, duration=1.0/fps) for m in images]
            final_clip = mp.concatenate_videoclips(clips, method="compose")
            if fname.lower().endswith('.gif'): final_clip.write_gif(fname, fps=fps, logger=None)
            else: final_clip.write_videofile(fname, fps=fps, codec='libx264', logger=None)
        except ImportError:
            logger.warning("moviepy 未安装，尝试使用 imageio"); import imageio
            with imageio.get_writer(fname, fps=fps) as writer:
                for img in images: writer.append_data(img)

class VideoExportDialog(QDialog):
    def __init__(self, parent, dm, p_conf, fname, s_f, e_f, fps):
        super().__init__(parent); self.worker = None
        # 新增全局 QApplication 引用
        global QApplication
        from PyQt6.QtWidgets import QApplication
        
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
            self.worker.cancel(); self._log("正在取消..."); self.cancel_btn.setEnabled(False)
    
    def _on_progress_updated(self, current, total, msg):
        self.progress_bar.setMaximum(total); self.progress_bar.setValue(current); self.status_label.setText(msg)
    
    def _on_export_finished(self, success, msg):
        self.status_label.setText("完成！" if success else "失败！"); self._log(msg)
        self.cancel_btn.setEnabled(False); self.close_btn.setEnabled(True)
        if success: self.progress_bar.setValue(self.progress_bar.maximum()); QMessageBox.information(self, "成功", msg)
        else: QMessageBox.warning(self, "失败", msg)
    
    def _log(self, msg): self.log_text.append(msg)
    
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "确认", "导出正在进行，确定关闭？") == QMessageBox.StandardButton.Yes:
                self.worker.cancel(); event.accept()
            else: event.ignore()
        else: event.accept()