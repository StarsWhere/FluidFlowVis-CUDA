#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计计算SQL生成器模块
"""
import logging
import re
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class StatisticsCalculator:
    """封装所有关于数据集的统计计算逻辑，核心是生成SQL查询。"""
    
    def __init__(self, data_manager):
        self.data_manager = data_manager

    def get_global_stats_queries(self, vars_to_calc: List[str]) -> Dict[str, str]:
        """为指定的数值变量生成计算全局统计量的SQL查询。"""
        if not vars_to_calc:
            return {}
        queries = {}
        for var in vars_to_calc:
            safe_var = f'"{var}"'
            # Using SQLite's built-in functions for variance/stddev is generally fine and fast.
            # AVG(X*X) - AVG(X)*AVG(X) is a more stable way to calculate variance in a single pass.
            variance_formula = f"(AVG({safe_var} * {safe_var}) - AVG({safe_var}) * AVG({safe_var}))"
            queries[var] = f"""
                SELECT 
                    AVG({safe_var}),
                    SUM({safe_var}),
                    MIN({safe_var}),
                    MAX({safe_var}),
                    {variance_formula},
                    SQRT({variance_formula})
                FROM timeseries_data
            """
        logger.info(f"为 {len(vars_to_calc)} 个变量生成了基础统计SQL查询。")
        return queries
    
    def parse_definition(self, definition: str) -> Tuple[str, str, str]:
        """解析单条定义，返回 name, formula, 和 aggregation_function。"""
        if '=' not in definition: raise ValueError(f"定义无效 (缺少 '='): {definition}")
        name, formula = definition.split('=', 1)
        name, formula = name.strip(), formula.strip()
        if not name.isidentifier(): raise ValueError(f"常量名称无效: '{name}'")

        match = re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula, re.DOTALL)
        if not match: raise ValueError(f"公式格式无效 (需 agg_func(expression)): {formula}")
        
        agg_func_str, _ = match.groups()
        return name, formula, agg_func_str.lower()

    def get_custom_global_stats_query(self, definition: str, available_globals: Dict) -> Tuple[str, str, str]:
        """
        根据用户定义，生成用于计算新全局常量的SQL查询。
        此方法假定公式不包含空间运算。
        """
        name, formula, agg_func_str = self.parse_definition(definition)
        
        # We don't check for conflict here, as we might be recalculating an existing constant.
        
        match = re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula, re.DOTALL)
        agg_func_str, inner_expr = match.groups()

        agg_map = {'mean': 'AVG', 'sum': 'SUM'}
        sql_agg_func = agg_map.get(agg_func_str.lower())
        
        if not sql_agg_func and agg_func_str.lower() not in ['std', 'var']:
            raise ValueError(f"不支持的聚合函数: {agg_func_str}. 支持: {list(agg_map.keys()) + ['std', 'var']}")

        processed_expr = inner_expr
        # Replace global variables with their numeric values in the expression
        for var_name in sorted(available_globals.keys(), key=len, reverse=True):
            # Use word boundaries to avoid replacing parts of other words
            pattern = r'\b' + re.escape(var_name) + r'\b'
            replacement = str(available_globals[var_name])
            processed_expr = re.sub(pattern, replacement, processed_expr)
        
        # Use single-pass variance calculation for std and var
        if agg_func_str.lower() == 'std':
            final_query = f"SELECT SQRT(AVG(pow({processed_expr}, 2)) - pow(AVG({processed_expr}), 2)) FROM timeseries_data"
        elif agg_func_str.lower() == 'var':
            final_query = f"SELECT AVG(pow({processed_expr}, 2)) - pow(AVG({processed_expr}), 2) FROM timeseries_data"
        else:
            final_query = f"SELECT {sql_agg_func}({processed_expr}) FROM timeseries_data"
        
        logger.info(f"生成的SQL查询为: {final_query}")
        return name, formula, final_query