#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pandas as pd
import logging
from typing import Optional, List, Dict, Any, Generator
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
        # 新增：用于存储全局统计信息
        self.global_stats: Dict[str, float] = {}

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
            # 确保只使用识别出的数值列，避免类型错误
            data = data[self.variables]
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
    def clear_all(self): 
        self.file_index.clear(); self.cache.clear(); self.variables.clear(); self.global_stats.clear()

    # --- 新增全局统计功能 ---
    def clear_global_stats(self):
        """清空已计算的全局统计数据"""
        self.global_stats.clear()
        logger.info("全局统计数据已清除。")

    def calculate_global_stats(self, progress_callback: Optional[callable] = None) -> Dict[str, float]:
        """
        计算所有数据文件中所有数值变量的全局统计量。
        这是一个耗时操作。
        """
        frame_count = self.get_frame_count()
        if frame_count == 0:
            return {}

        logger.info("开始计算全局统计数据...")
        
        # 使用流式方法以节省内存
        # 初始化统计追踪器
        sums = {var: 0.0 for var in self.variables}
        sq_sums = {var: 0.0 for var in self.variables}
        mins = {var: float('inf') for var in self.variables}
        maxs = {var: float('-inf') for var in self.variables}
        total_points = 0
        
        # 由于中位数无法流式计算，我们需要收集所有数据
        # 为了避免内存爆炸，这里我们只计算均值、标准差、总和、最大最小值
        # 中位数计算需要一次性加载所有数据，对于大数据集可能不可行。
        # 如果需要中位数，需要采用更复杂的近似算法或分块处理。
        # 这里为了演示，我们先实现可以流式处理的统计量。
        
        for i in range(frame_count):
            try:
                df = pd.read_csv(self.file_index[i]['path'], usecols=self.variables)
                
                # 更新统计量
                current_sums = df.sum()
                current_sq_sums = (df**2).sum()
                current_mins = df.min()
                current_maxs = df.max()
                
                for var in self.variables:
                    sums[var] += current_sums.get(var, 0)
                    sq_sums[var] += current_sq_sums.get(var, 0)
                    mins[var] = min(mins[var], current_mins.get(var, float('inf')))
                    maxs[var] = max(maxs[var], current_maxs.get(var, float('-inf')))

                total_points += len(df)
                
                if progress_callback:
                    progress_callback(i + 1, frame_count)
            except Exception as e:
                logger.error(f"处理文件 {self.file_index[i]['path']} 时出错: {e}")
                continue # 跳过错误的文件

        if total_points == 0:
            logger.warning("未能从任何文件中读取数据点，无法计算统计信息。")
            return {}

        results = {}
        for var in self.variables:
            mean = sums[var] / total_points
            # E[X^2] - (E[X])^2
            std_dev = ((sq_sums[var] / total_points) - mean**2)**0.5
            
            results[f"{var}_global_mean"] = mean
            results[f"{var}_global_sum"] = sums[var]
            results[f"{var}_global_std"] = std_dev
            results[f"{var}_global_min"] = mins[var]
            results[f"{var}_global_max"] = maxs[var]

        self.global_stats = results
        logger.info(f"全局统计数据计算完成。共处理 {total_points} 个数据点。")
        return self.global_stats