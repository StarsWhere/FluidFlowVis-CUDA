#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公式引擎模块
"""
import ast
import re
import logging
import pandas as pd
from typing import Set, List, Dict, Any, Tuple
import numpy as np 
import pyarrow as pa # NEW

logger = logging.getLogger(__name__)

class FormulaEngine:
    """负责验证、解析和评估用户定义的数学公式。"""
    def __init__(self):
        self.allowed_op_types = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd}
        self.simple_math_functions = {'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'exp', 'log', 'log10', 'sqrt', 'abs', 'floor', 'ceil', 'round', 'min', 'max', 'pow'}
        self.spatial_functions = {'grad_x', 'grad_y', 'div', 'curl', 'laplacian'}
        self.allowed_functions = self.simple_math_functions.union(self.spatial_functions)
        self.allowed_aggregates = {'mean', 'sum', 'median', 'std', 'var', 'min_frame', 'max_frame'}
        self.science_constants = {'pi': np.pi, 'e': np.e, 'g': 9.80665, 'c': 299792458, 'h': 6.62607015e-34, 'k_B': 1.380649e-23, 'N_A': 6.02214076e23, 'R': 8.314462618}
        self.allowed_variables: Set[str] = set()
        self.custom_global_variables: Dict[str, float] = {}
    
    def update_allowed_variables(self, variables: List[str]):
        self.allowed_variables = set(variables)
        logger.debug(f"公式引擎已更新可用变量: {self.allowed_variables}")

    def update_custom_global_variables(self, global_vars: Dict[str, float]):
        self.custom_global_variables = global_vars
        logger.debug(f"公式引擎已更新全局变量: {list(self.custom_global_variables.keys())}")

    def get_all_constants_and_globals(self) -> Dict:
        return {**self.science_constants, **self.custom_global_variables}

    def validate_syntax(self, formula: str) -> Tuple[bool, str]:
        if not formula.strip(): return True, ""
        try:
            tree = ast.parse(formula, mode='eval')
            if self._validate_node(tree.body): return True, ""
            return False, "公式包含不允许的结构或函数。"
        except SyntaxError as e: return False, f"语法错误: {e}"
        except Exception as e:
            logger.warning(f"公式验证失败: '{formula}' - {e}")
            return False, f"验证失败: {e}"
    
    def _validate_node(self, node) -> bool:
        if isinstance(node, ast.Constant): return isinstance(node.value, (int, float, complex))
        if isinstance(node, (ast.Num, ast.NameConstant)): return True
        if isinstance(node, ast.Name):
            if node.id in self.get_all_constants_and_globals() or node.id in self.allowed_functions: return True
            return node.id not in self.allowed_aggregates
        if isinstance(node, ast.BinOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.left) and self._validate_node(node.right)
        if isinstance(node, ast.UnaryOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.operand)
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, 'id', None)
            if func_name in self.allowed_functions: return all(self._validate_node(arg) for arg in node.args)
            if func_name in self.allowed_aggregates: return len(node.args) == 1 and self._validate_node(node.args[0])
        return False
            
    def get_used_variables(self, formula: str) -> Set[str]:
        try:
            tree = ast.parse(formula, mode='eval')
            return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in self.allowed_variables}
        except:
            return {var for var in self.allowed_variables if re.search(r'\b' + var + r'\b', formula)}

    def evaluate_formula(self, data: pd.DataFrame, formula: str) -> pd.Series:
        """
        [MODIFIED] Now directly accepts and works with pandas DataFrame, as workers will convert arrow batches.
        This makes the engine's core logic simpler and more focused.
        """
        formula_stripped = formula.strip()
        if not formula_stripped: raise ValueError("传入了空公式")

        if formula_stripped in data.columns: return data[formula_stripped]

        is_spatial = any(re.search(r'\b' + re.escape(f) + r'\s*\(', formula_stripped) for f in self.spatial_functions)
        if is_spatial:
            raise ValueError(f"空间函数 (如 grad_x, div) 无法直接在 evaluate_formula 中求值。请使用 computation_core。")

        eval_globals = {**self.get_all_constants_and_globals(), '__builtins__': None}
        safe_math = {'sin': np.sin, 'cos': np.cos, 'tan': np.tan, 'asin': np.arcsin, 'acos': np.arccos, 'atan': np.arctan, 'sinh': np.sinh, 'cosh': np.cosh, 'tanh': np.tanh, 'exp': np.exp, 'log': np.log, 'log10': np.log10, 'sqrt': np.sqrt, 'abs': np.abs, 'floor': np.floor, 'ceil': np.ceil, 'round': np.round, 'min': np.minimum, 'max': np.maximum, 'pow': np.power}
        
        # Using a dictionary for local_scope is more explicit and safer than passing the dataframe directly
        local_scope = {col: data[col] for col in data.columns}
        local_scope.update(safe_math)
        
        processed_formula = formula
        agg_pattern = re.compile(r'(\b(?:' + '|'.join(self.allowed_aggregates) + r'))\s*\((.*?)\)')
        
        matches = []
        for match in agg_pattern.finditer(formula):
            open_brackets = 0; expr_start = match.start(2); expr_end = -1
            sub_expr_str = formula[expr_start:]
            for i, char in enumerate(sub_expr_str):
                if char == '(': open_brackets += 1
                elif char == ')':
                    open_brackets -= 1
                    if open_brackets == -1: expr_end = i; break
            
            if expr_end != -1:
                inner_expr = sub_expr_str[:expr_end]
                full_match_str = match.group(1) + '(' + inner_expr + ')'
                matches.append((full_match_str, match.group(1), inner_expr))

        matches.sort(key=lambda x: len(x[0]), reverse=True)

        for i, (full_match, agg_func_name, inner_expr) in enumerate(matches):
            try:
                inner_values = pd.eval(inner_expr, global_dict=eval_globals, local_dict=local_scope)
            except Exception as e: raise ValueError(f"评估聚合函数内表达式 '{inner_expr}' 时出错: {e}")

            if agg_func_name == 'mean': scalar_result = np.mean(inner_values)
            elif agg_func_name == 'sum': scalar_result = np.sum(inner_values)
            elif agg_func_name == 'median': scalar_result = np.median(inner_values)
            elif agg_func_name == 'std': scalar_result = np.std(inner_values)
            elif agg_func_name == 'var': scalar_result = np.var(inner_values)
            elif agg_func_name == 'min_frame': scalar_result = np.min(inner_values)
            elif agg_func_name == 'max_frame': scalar_result = np.max(inner_values)
            else: scalar_result = 0.0

            temp_var_name = f"__agg_result_{i}__"
            eval_globals[temp_var_name] = scalar_result
            processed_formula = processed_formula.replace(full_match, temp_var_name, 1)

        try:
            logger.debug(f"原始公式: '{formula}', 处理后公式: '{processed_formula}', 作用域键: {list(eval_globals.keys())}")
            return pd.eval(processed_formula, global_dict=eval_globals, local_dict=local_scope)
        except Exception as e: raise ValueError(f"评估最终公式 '{processed_formula}' 时失败: {e}")