#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计计算器模块
"""
import pandas as pd
import logging
import re
import os
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class StatisticsCalculator:
    """封装所有关于数据集的统计计算逻辑。"""
    def __init__(self, data_manager):
        self.data_manager = data_manager

    def calculate_global_stats(self, progress_callback: Optional[callable] = None) -> Dict[str, Dict[str, Any]]:
        """
        计算所有数据文件中所有数值变量的全局统计量。这是一个耗时操作。
        """
        frame_count = self.data_manager.get_frame_count()
        if frame_count == 0:
            return {}

        logger.info("开始计算全局统计数据...")
        
        variables = self.data_manager.get_variables()
        sums = {var: 0.0 for var in variables}
        sq_sums = {var: 0.0 for var in variables}
        mins = {var: float('inf') for var in variables}
        maxs = {var: float('-inf') for var in variables}
        total_points = 0
        
        for i, df in enumerate(self.data_manager.iter_dataframes(use_cols=variables)):
            try:
                current_sums = df.sum()
                current_sq_sums = (df**2).sum()
                current_mins = df.min()
                current_maxs = df.max()
                
                for var in variables:
                    sums[var] += current_sums.get(var, 0)
                    sq_sums[var] += current_sq_sums.get(var, 0)
                    mins[var] = min(mins[var], current_mins.get(var, float('inf')))
                    maxs[var] = max(maxs[var], current_maxs.get(var, float('-inf')))

                total_points += len(df)
                
                if progress_callback:
                    progress_callback(i + 1, frame_count)
            except Exception as e:
                path = self.data_manager.get_frame_info(i)['path']
                logger.error(f"处理文件 {path} 时出错: {e}")
                continue

        if total_points == 0:
            logger.warning("未能从任何文件中读取数据点，无法计算统计信息。")
            return {}

        stats_results = {}
        formula_descriptions = {}

        for var in variables:
            if var not in sums or total_points == 0: continue
            mean = sums[var] / total_points
            var_val = (sq_sums[var] / total_points) - mean**2
            std_dev = var_val**0.5 if var_val > 0 else 0.0
            
            stats_results[f"{var}_global_mean"] = mean
            formula_descriptions[f"{var}_global_mean"] = f"mean({var})"

            stats_results[f"{var}_global_sum"] = sums[var]
            formula_descriptions[f"{var}_global_sum"] = f"sum({var})"

            stats_results[f"{var}_global_std"] = std_dev
            formula_descriptions[f"{var}_global_std"] = f"std({var})"

            stats_results[f"{var}_global_var"] = var_val
            formula_descriptions[f"{var}_global_var"] = f"var({var})"

            stats_results[f"{var}_global_min"] = mins[var]
            formula_descriptions[f"{var}_global_min"] = f"min({var})"

            stats_results[f"{var}_global_max"] = maxs[var]
            formula_descriptions[f"{var}_global_max"] = f"max({var})"

        logger.info(f"全局统计数据计算完成。共处理 {total_points} 个数据点。")
        logger.info(f"全局统计数据计算完成。共处理 {total_points} 个数据点。")
        return {"stats": stats_results, "formulas": formula_descriptions}

    def calculate_custom_global_stats(self, definitions: List[str], base_global_stats: Dict, progress_callback: Optional[callable]) -> Dict[str, Dict[str, Any]]:
        """
        根据用户定义计算新的全局常量。
        """
        logger.info(f"开始计算自定义全局常量: {definitions}")
        available_globals = base_global_stats.copy()
        new_stats = {} # 存储名称到数值的映射
        new_formulas = {} # 存储名称到公式的映射
        
        num_defs = len(definitions)
        num_files = self.data_manager.get_frame_count()
        variables = self.data_manager.get_variables()

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
            
            processed_expr = inner_expr
            for var_name in sorted(available_globals.keys(), key=len, reverse=True):
                pattern = r'\b' + re.escape(var_name) + r'\b'
                replacement = '@' + var_name
                processed_expr = re.sub(pattern, replacement, processed_expr)
            logger.debug(f"Original expression: '{inner_expr}', Processed for eval: '{processed_expr}'")

            total_sum = 0.0
            total_sum_sq = 0.0
            total_count = 0

            for file_idx, df in enumerate(self.data_manager.iter_dataframes(use_cols=variables)):
                try:
                    expr_vals = df.eval(processed_expr, local_dict=available_globals, global_dict={})
                    
                    total_sum += expr_vals.sum()
                    if agg_func in ['std', 'var']:
                        total_sum_sq += (expr_vals**2).sum()
                    total_count += len(expr_vals)

                    if progress_callback:
                        progress_callback(def_idx * num_files + file_idx + 1, num_defs * num_files, f"正在计算 '{name}' ({file_idx+1}/{num_files})")
                except Exception as e:
                    path = self.data_manager.get_frame_info(file_idx)['path']
                    logger.error(f"Error evaluating expression '{processed_expr}' in file {path}: {e}")
                    raise RuntimeError(f"计算 '{name}' 时在文件 {os.path.basename(path)} 中出错: {e}")

            if total_count == 0:
                raise ValueError(f"计算 '{name}' 时未能处理任何数据点。")

            result = 0.0
            if agg_func == 'sum': result = total_sum
            elif agg_func == 'mean': result = total_sum / total_count
            elif agg_func in ['std', 'var']:
                mean_val = total_sum / total_count
                var_val = (total_sum_sq / total_count) - mean_val**2
                result = var_val if agg_func == 'var' else (var_val**0.5 if var_val > 0 else 0.0)

            available_globals[name] = result
            new_stats[name] = result
            new_formulas[name] = formula # 存储原始公式
            logger.info(f"计算完成: {name} = {result}")

        return {"stats": new_stats, "formulas": new_formulas}