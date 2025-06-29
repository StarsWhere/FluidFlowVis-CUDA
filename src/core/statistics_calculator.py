#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计计算器模块
"""
import pandas as pd
import numpy as np
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
        使用Welford算法的并行版本，以获得更好的数值稳定性。
        """
        frame_count = self.data_manager.get_frame_count()
        if frame_count == 0:
            return {}

        logger.info("开始计算全局统计数据...")
        
        variables = self.data_manager.get_variables()
        
        # 初始化统计量
        global_counts = {var: 0 for var in variables}
        global_means = {var: 0.0 for var in variables}
        global_m2s = {var: 0.0 for var in variables} # M2: Sum of squares of differences from the current mean
        global_mins = {var: float('inf') for var in variables}
        global_maxs = {var: float('-inf') for var in variables}
        global_sums = {var: 0.0 for var in variables}

        for i, df in enumerate(self.data_manager.iter_dataframes(use_cols=variables)):
            try:
                if df.empty:
                    continue

                chunk_counts = df.count()
                
                # 更新 Min/Max/Sum
                global_mins = df.min().combine(pd.Series(global_mins), min, fill_value=float('inf'))
                global_maxs = df.max().combine(pd.Series(global_maxs), max, fill_value=float('-inf'))
                global_sums = df.sum().add(pd.Series(global_sums), fill_value=0)

                # Welford 算法组合两个数据集 (现有聚合 vs 新的df)
                for var in variables:
                    if var not in chunk_counts or chunk_counts[var] == 0:
                        continue
                    
                    count_a = global_counts[var]
                    mean_a = global_means[var]
                    m2_a = global_m2s[var]
                    
                    count_b = chunk_counts[var]
                    mean_b = df[var].mean()
                    m2_b = df[var].var(ddof=0) * count_b
                    
                    new_count = count_a + count_b
                    delta = mean_b - mean_a
                    
                    global_means[var] = (count_a * mean_a + count_b * mean_b) / new_count
                    global_m2s[var] = m2_a + m2_b + (delta**2 * count_a * count_b) / new_count
                    global_counts[var] = new_count

                if progress_callback:
                    progress_callback(i + 1, frame_count)
            except Exception as e:
                path = self.data_manager.get_frame_info(i)['path']
                logger.error(f"处理文件 {path} 时出错: {e}")
                continue

        total_points = next((c for c in global_counts.values() if c > 0), 0)
        if total_points == 0:
            logger.warning("未能从任何文件中读取数据点，无法计算统计信息。")
            return {}

        stats_results = {}
        formula_descriptions = {}

        for var in variables:
            if global_counts.get(var, 0) == 0: continue
            count = global_counts[var]
            mean = global_means[var]
            var_val = global_m2s[var] / count # Population variance
            std_dev = var_val**0.5 if var_val > 0 else 0.0
            
            stats_results[f"{var}_global_mean"] = mean
            formula_descriptions[f"{var}_global_mean"] = f"mean({var})"

            stats_results[f"{var}_global_sum"] = global_sums[var]
            formula_descriptions[f"{var}_global_sum"] = f"sum({var})"

            stats_results[f"{var}_global_std"] = std_dev
            formula_descriptions[f"{var}_global_std"] = f"std({var})"

            stats_results[f"{var}_global_var"] = var_val
            formula_descriptions[f"{var}_global_var"] = f"var({var})"

            stats_results[f"{var}_global_min"] = global_mins[var]
            formula_descriptions[f"{var}_global_min"] = f"min({var})"

            stats_results[f"{var}_global_max"] = global_maxs[var]
            formula_descriptions[f"{var}_global_max"] = f"max({var})"

        logger.info(f"全局统计数据计算完成。共处理 {total_points} 个数据点。")
        return {"stats": stats_results, "formulas": formula_descriptions}

    def calculate_custom_global_stats(self, definitions: List[str], base_global_stats: Dict, progress_callback: Optional[callable]) -> Dict[str, Dict[str, Any]]:
        """
        根据用户定义计算新的全局常量。
        重构为单次遍历，以显著提升性能。
        """
        logger.info(f"开始使用单遍算法计算自定义全局常量: {definitions}")
        
        # --- 1. 解析所有定义 ---
        parsed_defs = []
        available_globals = base_global_stats.copy()
        
        for definition in definitions:
            if '=' not in definition: raise ValueError(f"定义无效 (缺少 '='): {definition}")
            name, formula = definition.split('=', 1)
            name, formula = name.strip(), formula.strip()
            
            if not name.isidentifier(): raise ValueError(f"常量名称无效: '{name}'")
            if name in available_globals: raise ValueError(f"常量名称 '{name}' 与现有变量冲突。")

            match = re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula)
            if not match: raise ValueError(f"公式格式无效 (需要 agg_func(expression)): {formula}")
            
            agg_func, inner_expr = match.groups()
            supported_aggs = {'mean', 'sum', 'std', 'var'}
            if agg_func not in supported_aggs: raise ValueError(f"不支持的聚合函数: {agg_func}")
            
            # 预处理表达式，替换全局变量占位符
            processed_expr = inner_expr
            for var_name in sorted(available_globals.keys(), key=len, reverse=True):
                pattern = r'\b' + re.escape(var_name) + r'\b'
                replacement = '@' + var_name
                processed_expr = re.sub(pattern, replacement, processed_expr)
            
            parsed_defs.append({'name': name, 'formula': formula, 'agg_func': agg_func, 'inner_expr': processed_expr})
            available_globals[name] = 0 # 临时占位，以供后续公式使用

        # --- 2. 初始化累加器 ---
        accumulators = {
            d['name']: {'sum': 0.0, 'sum_sq': 0.0, 'count': 0} for d in parsed_defs
        }

        # --- 3. 单次遍历数据集 ---
        num_files = self.data_manager.get_frame_count()
        variables = self.data_manager.get_variables()

        for file_idx, df in enumerate(self.data_manager.iter_dataframes(use_cols=variables)):
            try:
                # 在当前DataFrame上计算所有表达式
                for p_def in parsed_defs:
                    acc = accumulators[p_def['name']]
                    expr_vals = df.eval(p_def['inner_expr'], local_dict=base_global_stats, global_dict={})
                    
                    acc['sum'] += expr_vals.sum()
                    if p_def['agg_func'] in ['std', 'var']:
                        acc['sum_sq'] += (expr_vals**2).sum()
                    acc['count'] += len(expr_vals)
            except Exception as e:
                path = self.data_manager.get_frame_info(file_idx)['path']
                err_msg = f"计算表达式时在文件 {os.path.basename(path)} 中出错: {e}"
                logger.error(err_msg)
                raise RuntimeError(err_msg)

            if progress_callback:
                progress_callback(file_idx + 1, num_files, f"正在处理文件 {file_idx+1}/{num_files}")

        # --- 4. 计算最终结果 ---
        new_stats = {}
        new_formulas = {}
        
        for p_def in parsed_defs:
            name = p_def['name']
            acc = accumulators[name]
            total_count = acc['count']

            if total_count == 0:
                logger.warning(f"计算 '{name}' 时未能处理任何数据点，跳过。")
                continue

            result = 0.0
            agg_func = p_def['agg_func']
            
            if agg_func == 'sum':
                result = acc['sum']
            elif agg_func == 'mean':
                result = acc['sum'] / total_count
            elif agg_func in ['std', 'var']:
                mean_val = acc['sum'] / total_count
                var_val = (acc['sum_sq'] / total_count) - mean_val**2
                result = var_val if agg_func == 'var' else (np.sqrt(var_val) if var_val > 0 else 0.0)

            # 更新结果和可用于后续计算的变量池
            base_global_stats[name] = result 
            new_stats[name] = result
            new_formulas[name] = p_def['formula']
            logger.info(f"计算完成: {name} = {result}")

        return {"stats": new_stats, "formulas": new_formulas}