#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, logging, time, numpy as np
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QMessageBox
from PyQt6.QtCore import QThread, pyqtSignal, Qt

logger = logging.getLogger(__name__)

from src.visualization.headless_renderer import HeadlessPlotter

class VideoExportWorker(QThread):
    progress_updated = pyqtSignal(int, int, str)
    export_finished = pyqtSignal(bool, str)
    
    def __init__(self, dm, p_conf, fname, s_f, e_f, fps):
        super().__init__()
        self.dm, self.p_conf, self.fname, self.s_f, self.fps = dm, p_conf, fname, s_f, fps
        self.e_f = min(e_f, self.dm.get_frame_count() - 1)
        self.is_cancelled = False
        self.executor = ThreadPoolExecutor(max_workers=max(1, os.cpu_count()))
        self.temp_dir = None
        self.success = False
        self.message = ""

    def cancel(self):
        self.is_cancelled = True
        self.executor.shutdown(wait=False, cancel_futures=True)
    
    def run(self):
        self.temp_dir = tempfile.mkdtemp(prefix="intervis_export_")
        logger.info(f"为视频导出创建临时目录: {self.temp_dir}")
        
        try:
            total = self.e_f - self.s_f + 1
            if total <= 0: raise ValueError("帧范围无效。")
            
            frame_paths, futures = {}, {self.executor.submit(self._render_frame, i, self.temp_dir): i for i in range(self.s_f, self.e_f + 1)}
            
            processed_count = 0
            for future in as_completed(futures):
                if self.is_cancelled: break
                idx, result_path = futures[future], future.result()
                if result_path: frame_paths[idx] = result_path
                processed_count += 1
                self.progress_updated.emit(processed_count, total, f"已渲染 {processed_count}/{total} 帧")

            if self.is_cancelled:
                self.success, self.message = False, "导出已取消"
                self.export_finished.emit(self.success, self.message); return

            image_files = [frame_paths[i] for i in range(self.s_f, self.e_f + 1) if i in frame_paths]
            if not image_files: raise ValueError("没有成功渲染任何帧。")

            self.progress_updated.emit(total, total, "正在编码视频...")
            self._create_video(image_files, self.fname, self.fps)
            
            self.success, self.message = True, f"视频已成功导出到:\n{self.fname}"
            self.export_finished.emit(self.success, self.message)

        except Exception as e:
            logger.error(f"视频导出失败: {e}", exc_info=True)
            self.success, self.message = False, f"导出失败: {e}"
            self.export_finished.emit(self.success, self.message)
        finally:
            self.executor.shutdown(wait=True)
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _render_frame(self, idx, temp_dir):
        if self.is_cancelled: return None
        try:
            data = self.dm.get_frame_data(idx)
            if data is None: raise ValueError(f"无法为帧 {idx} 加载数据")

            frame_conf = self.p_conf.copy()
            raw_title = frame_conf.get('chart_title', '')

            # --- FIX: Evaluate the title for each frame ---
            # This logic ensures that placeholders like {frame_index} and {time} are correctly
            # replaced with the actual values for the current frame being rendered.
            if raw_title and '{' in raw_title and '}' in raw_title:
                try:
                    info = self.dm.get_frame_info(idx)
                    # Use a default value for timestamp if it's not available
                    time_val = info.get('timestamp', float(idx)) if info else float(idx)
                    # Format the title string with the frame-specific data
                    evaluated_title = raw_title.format(frame_index=idx, time=time_val)
                    frame_conf['chart_title'] = evaluated_title
                except (KeyError, ValueError, IndexError) as e:
                    logger.warning(f"格式化标题失败: '{raw_title}' with index={idx}, error: {e}. 使用原始标题。")
                    # Fallback to the raw title if formatting fails
                    frame_conf['chart_title'] = raw_title
            
            plotter = HeadlessPlotter(frame_conf)
            image_array = plotter.render_frame(data, self.dm.get_variables())
            
            import imageio
            frame_path = os.path.join(temp_dir, f'frame_{idx:06d}.png')
            imageio.imwrite(frame_path, image_array)
            return frame_path
        except Exception as e:
            logger.error(f"渲染帧 {idx} 失败: {e}")
            return None

    def _create_video(self, image_files, fname, fps):
        try:
            import moviepy.editor as mp
            logger.info(f"使用 moviepy 从临时文件编码视频: {fname}")
            clip = mp.ImageSequenceClip(image_files, fps=fps)
            if fname.lower().endswith('.gif'): 
                clip.write_gif(fname, fps=fps, logger=None)
            else: 
                clip.write_videofile(fname, fps=fps, codec='libx264', logger='bar', threads=os.cpu_count())
            clip.close()
        except Exception as e:
            logger.warning(f"Moviepy 失败: {e}. 尝试 ImageIO...")
            try:
                import imageio
                writer_kwargs = {'fps': fps}
                if fname.lower().endswith('.mp4'):
                    writer_kwargs.update({'codec': 'libx264', 'quality': 8, 'pixelformat': 'yuv420p'})
                with imageio.get_writer(fname, **writer_kwargs) as writer:
                    for i, fpath in enumerate(image_files):
                        if self.is_cancelled: break
                        self.progress_updated.emit(i+1, len(image_files), f"ImageIO 编码帧 {i+1}/{len(image_files)}")
                        writer.append_data(imageio.v2.imread(fpath))
            except Exception as e2:
                raise RuntimeError(f"Moviepy 和 ImageIO 均导出失败: {e2}")

class VideoExportDialog(QDialog):
    def __init__(self, parent, dm, p_conf, fname, s_f, e_f, fps):
        super().__init__(parent); self.worker = None
        self._init_ui(fname, s_f, e_f, fps); self._start_export(dm, p_conf, fname, s_f, e_f, fps)
    
    def _init_ui(self, fname, s_f, e_f, fps):
        self.setWindowTitle("正在导出视频"); self.setModal(True); self.setFixedSize(450, 320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>文件:</b> {os.path.basename(fname)}<br><b>帧:</b> {s_f}-{e_f}<br><b>帧率:</b> {fps}fps"))
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
            if reply == QMessageBox.StandardButton.Yes: self.worker.cancel(); self.worker.wait(30000); event.accept()
            else: event.ignore()
        else: event.accept()