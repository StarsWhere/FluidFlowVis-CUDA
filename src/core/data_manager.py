#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pandas as pd
import logging
from typing import Optional, List, Dict, Any, Generator
from collections import OrderedDict
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)
PYARROW_AVAILABLE = True

class DataManager(QObject):
    """
    负责数据文件的索引、加载和缓存。
    初始化过程被拆分，以支持后台线程扫描文件。
    """
    error_occurred = pyqtSignal(str) # 移除了 scan_finished 信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_directory: Optional[str] = None
        self.file_index: List[Dict[str, Any]] = []
        self.cache: OrderedDict[int, pd.DataFrame] = OrderedDict()
        self.cache_max_size = 100
        self.variables: List[str] = []
        self.global_stats: Dict[str, float] = {}
        self.custom_global_formulas: Dict[str, str] = {}

    def setup_directory(self, directory: str) -> bool:
        """设置并验证数据目录，为后台扫描做准备。"""
        self.data_directory = directory
        if not os.path.isdir(self.data_directory):
            msg = f"数据目录不存在: {self.data_directory}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            return False
        
        self.clear_all()
        logger.info(f"数据目录已设置为: {self.data_directory}")
        return True

    def post_scan_setup(self, file_index: List[Dict[str, Any]], variables: List[str]):
        """在后台扫描完成后，用扫描结果更新管理器状态。不再发射信号。"""
        self.file_index = file_index
        self.variables = variables
        if self.file_index:
            logger.info(f"数据变量已识别 (仅数值类型): {self.variables}")
            logger.info(f"成功索引 {len(self.file_index)} 帧数据")
        else:
            logger.warning("目录中未找到有效的CSV文件。")

    def _read_csv(self, path: str, use_cols: Optional[List[str]]) -> pd.DataFrame:
        """Helper function to read CSV with pyarrow fallback."""
        global PYARROW_AVAILABLE
        if PYARROW_AVAILABLE:
            try:
                return pd.read_csv(path, usecols=use_cols, engine='pyarrow')
            except Exception as e:
                # On first failure, log warning and disable for subsequent reads
                if "pyarrow" in str(e).lower():
                    logger.warning(f"Pyarrow engine failed ('{e}'). Falling back to default pandas engine for all subsequent reads. For better performance, `pip install pyarrow`.")
                    PYARROW_AVAILABLE = False
                return pd.read_csv(path, usecols=use_cols) # Fallback on any error
        return pd.read_csv(path, usecols=use_cols)

    def get_frame_data(self, frame_index: int) -> Optional[pd.DataFrame]:
        if not (0 <= frame_index < len(self.file_index)): return None
        if frame_index in self.cache:
            self.cache.move_to_end(frame_index)
            return self.cache[frame_index]
        try:
            data = self._read_csv(self.file_index[frame_index]['path'], use_cols=self.variables)
            self.cache[frame_index] = data
            self._enforce_cache_limit()
            return data
        except Exception as e:
            msg = f"加载帧 {frame_index} 数据失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"加载文件失败: {os.path.basename(self.file_index[frame_index]['path'])}")
            return None

    def iter_dataframes(self, use_cols: Optional[List[str]] = None) -> Generator[pd.DataFrame, None, None]:
        """一个生成器，用于逐个迭代处理所有数据文件，避免一次性加载到内存。"""
        cols_to_use = use_cols if use_cols is not None else self.variables
        for file_info in self.file_index:
            try:
                # The lambda version of usecols is slower, better to pass the list directly
                cols_to_yield = lambda c: c in cols_to_use if use_cols is not None else None
                yield self._read_csv(file_info['path'], use_cols=cols_to_yield)
            except Exception as e:
                logger.error(f"迭代读取文件 {file_info['path']} 时出错: {e}")
                continue

    def _enforce_cache_limit(self):
        while len(self.cache) > self.cache_max_size:
            self.cache.popitem(last=False)

    def set_cache_size(self, size: int):
        self.cache_max_size = max(1, size)
        self._enforce_cache_limit()
        logger.info(f"缓存大小已设置为: {self.cache_max_size}")

    def get_frame_count(self) -> int: return len(self.file_index)
    def get_frame_info(self, i: int) -> Optional[Dict[str, Any]]: return self.file_index[i] if 0 <= i < len(self.file_index) else None
    def get_cache_info(self) -> Dict: return {'size': len(self.cache), 'max_size': self.cache_max_size}
    def get_variables(self) -> List[str]: return self.variables
    
    def clear_all(self):
        self.file_index.clear(); self.cache.clear(); self.variables.clear(); self.global_stats.clear(); self.custom_global_formulas.clear()

    def clear_global_stats(self):
        """清空已计算的全局统计数据"""
        self.global_stats.clear()
        self.custom_global_formulas.clear()
        logger.info("全局统计数据已清除。")