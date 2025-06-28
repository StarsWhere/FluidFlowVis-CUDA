#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pandas as pd
import logging
import re
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
        
        sums = {var: 0.0 for var in self.variables}
        sq_sums = {var: 0.0 for var in self.variables}
        mins = {var: float('inf') for var in self.variables}
        maxs = {var: float('-inf') for var in self.variables}
        total_points = 0
        
        for i in range(frame_count):
            try:
                df = pd.read_csv(self.file_index[i]['path'], usecols=self.variables)
                
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
                continue

        if total_points == 0:
            logger.warning("未能从任何文件中读取数据点，无法计算统计信息。")
            return {}

        results = {}
        for var in self.variables:
            if var not in sums or total_points == 0: continue
            mean = sums[var] / total_points
            # E[X^2] - (E[X])^2
            var_val = (sq_sums[var] / total_points) - mean**2
            std_dev = var_val**0.5 if var_val > 0 else 0.0
            
            results[f"{var}_global_mean"] = mean
            results[f"{var}_global_sum"] = sums[var]
            results[f"{var}_global_std"] = std_dev
            results[f"{var}_global_var"] = var_val
            results[f"{var}_global_min"] = mins[var]
            results[f"{var}_global_max"] = maxs[var]

        self.global_stats = results
        logger.info(f"全局统计数据计算完成。共处理 {total_points} 个数据点。")
        return self.global_stats

    def calculate_custom_global_stats(self, definitions: List[str], progress_callback: Optional[callable]) -> Dict[str, float]:
        """
        根据用户定义计算新的全局常量。
        """
        logger.info(f"开始计算自定义全局常量: {definitions}")
        available_globals = self.global_stats.copy()
        new_stats = {}
        
        num_defs = len(definitions)
        num_files = self.get_frame_count()

        for def_idx, definition in enumerate(definitions):
            if '=' not in definition:
                raise ValueError(f"定义无效 (缺少 '='): {definition}")
            
            name, formula = definition.split('=', 1)
            name = name.strip()
            formula = formula.strip()
            
            if not name.isidentifier():
                raise ValueError(f"常量名称无效: '{name}'")

            match = re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula)
            if not match:
                raise ValueError(f"公式格式无效 (需要 agg_func(expression)): {formula}")

            agg_func, inner_expr = match.groups()
            supported_aggs = {'mean', 'sum', 'std', 'var'}
            if agg_func not in supported_aggs:
                raise ValueError(f"不支持的全局聚合函数: {agg_func}。支持的: {supported_aggs}")
            
            # **FIX:** Pre-process the inner expression for pandas.eval
            # It needs '@' to distinguish environment variables from columns.
            processed_expr = inner_expr
            # Sort keys by length, descending, to replace longer names first (e.g., 'var_abc' before 'var')
            for var_name in sorted(available_globals.keys(), key=len, reverse=True):
                # Use word boundaries (\b) to ensure we replace whole words only
                pattern = r'\b' + re.escape(var_name) + r'\b'
                replacement = '@' + var_name
                processed_expr = re.sub(pattern, replacement, processed_expr)
            logger.debug(f"Original expression: '{inner_expr}', Processed for eval: '{processed_expr}'")

            total_sum = 0.0
            total_sum_sq = 0.0
            total_count = 0

            for file_idx, file_info in enumerate(self.file_index):
                try:
                    df = pd.read_csv(file_info['path'], usecols=self.variables)
                    # Use the processed expression with '@' symbols
                    expr_vals = df.eval(processed_expr, local_dict=available_globals, global_dict={})
                    
                    total_sum += expr_vals.sum()
                    if agg_func in ['std', 'var']:
                        total_sum_sq += (expr_vals**2).sum()
                    total_count += len(expr_vals)

                    if progress_callback:
                        progress_callback(def_idx * num_files + file_idx + 1, num_defs * num_files, f"正在计算 '{name}' ({file_idx+1}/{num_files})")
                except Exception as e:
                    logger.error(f"Error evaluating expression '{processed_expr}' in file {file_info['path']}: {e}")
                    raise RuntimeError(f"计算 '{name}' 时在文件 {os.path.basename(file_info['path'])} 中出错: {e}")

            if total_count == 0:
                raise ValueError(f"计算 '{name}' 时未能处理任何数据点。")

            result = 0.0
            if agg_func == 'sum':
                result = total_sum
            elif agg_func == 'mean':
                result = total_sum / total_count
            elif agg_func in ['std', 'var']:
                mean_val = total_sum / total_count
                var_val = (total_sum_sq / total_count) - mean_val**2
                if agg_func == 'var':
                    result = var_val
                else: # std
                    result = var_val**0.5 if var_val > 0 else 0.0

            available_globals[name] = result
            new_stats[name] = result
            logger.info(f"计算完成: {name} = {result}")

        self.global_stats.update(new_stats)
        return new_stats