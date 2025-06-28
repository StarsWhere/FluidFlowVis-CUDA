#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pandas as pd
import logging
from typing import Optional, List, Dict, Any
from collections import OrderedDict
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class DataManager(QObject):
    loading_finished = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_directory: Optional[str] = None
        self.file_index: List[Dict[str, Any]] = []
        self.cache: OrderedDict[int, pd.DataFrame] = OrderedDict()
        self.cache_max_size = 100
        self.variables: List[str] = []

    def set_data_directory(self, directory: str): self.data_directory = directory
        
    def initialize(self, directory: str):
        self.set_data_directory(directory)
        if not os.path.isdir(self.data_directory):
            msg = f"数据目录不存在: {self.data_directory}"; logger.error(msg); self.error_occurred.emit(msg); return False
        self.clear_all()
        logger.info(f"开始扫描数据目录: {self.data_directory}")
        try:
            csv_files = sorted([f for f in os.listdir(self.data_directory) if f.lower().endswith('.csv')])
            if not csv_files:
                logger.warning("目录中未找到CSV文件。"); self.loading_finished.emit(False, "目录中无CSV文件"); return True
            for filename in csv_files:
                self.file_index.append({'path': os.path.join(self.data_directory, filename), 'timestamp': len(self.file_index)})
            
            df_sample = pd.read_csv(self.file_index[0]['path'], nrows=5)
            self.variables = [col for col in df_sample.columns if pd.api.types.is_numeric_dtype(df_sample[col])]
            logger.info(f"数据变量已识别 (仅数值类型): {self.variables}")
            msg = f"成功加载 {len(self.file_index)} 帧索引"; logger.info(msg); self.loading_finished.emit(True, msg); return True
        except Exception as e:
            msg = f"扫描数据目录失败: {e}"; logger.error(msg, exc_info=True); self.error_occurred.emit(msg); return False

    def get_frame_data(self, frame_index: int) -> Optional[pd.DataFrame]:
        if not (0 <= frame_index < len(self.file_index)): return None
        if frame_index in self.cache:
            self.cache.move_to_end(frame_index); return self.cache[frame_index]
        try:
            data = pd.read_csv(self.file_index[frame_index]['path'])
            self.cache[frame_index] = data; self._enforce_cache_limit(); return data
        except Exception as e:
            msg = f"加载帧 {frame_index} 数据失败: {e}"; logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"加载文件失败: {os.path.basename(self.file_index[frame_index]['path'])}"); return None

    def _enforce_cache_limit(self):
        while len(self.cache) > self.cache_max_size: self.cache.popitem(last=False)
    def set_cache_size(self, size: int):
        self.cache_max_size = max(1, size); self._enforce_cache_limit()
        logger.info(f"缓存大小已设置为: {self.cache_max_size}")
    def get_frame_count(self) -> int: return len(self.file_index)
    def get_frame_info(self, i: int): return self.file_index[i] if 0 <= i < len(self.file_index) else None
    def get_cache_info(self) -> Dict: return {'size': len(self.cache), 'max_size': self.cache_max_size}
    def get_variables(self) -> List[str]: return self.variables
    def clear_all(self): self.file_index.clear(); self.cache.clear(); self.variables.clear()