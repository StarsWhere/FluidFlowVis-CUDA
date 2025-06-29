#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公式引擎模块
"""
import ast
import re
import logging
import pandas as pd
from typing import Set, List, Dict, Any

logger = logging.getLogger(__name__)

class FormulaEngine:
    """负责验证、解析和评估用户定义的数学公式。"""
    def __init__(self):
        # 允许的操作符和函数
        self.allowed_op_types = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd}
        self.allowed_functions = {'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'exp', 'log', 'log10', 'sqrt', 'abs', 'floor', 'ceil', 'round', 'min', 'max'}
        self.allowed_aggregates = {'mean', 'sum', 'median', 'std', 'var', 'min_frame', 'max_frame'}

        # 内置常量
        self.science_constants = {
            'pi': 3.141592653589793, 'e': 2.718281828459045, 'g': 9.80665,
            'c': 299792458, 'h': 6.62607015e-34, 'k_B': 1.380649e-23,
            'N_A': 6.02214076e23, 'R': 8.314462618,
        }
        
        # 动态变量
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

    def validate(self, formula: str) -> bool:
        if not formula.strip(): return True
        try:
            tree = ast.parse(formula, mode='eval')
            return self._validate_node(tree.body)
        except Exception as e:
            logger.warning(f"公式验证失败: '{formula}' - {e}")
            return False
    
    def _validate_node(self, node) -> bool:
        if isinstance(node, ast.Constant): return isinstance(node.value, (int, float, complex))
        if isinstance(node, (ast.Num, ast.NameConstant)): return True
        if isinstance(node, ast.Name):
            # 如果是已知的科学常量、自定义全局变量或允许的函数名，则通过
            if node.id in self.science_constants or \
               node.id in self.custom_global_variables or \
               node.id in self.allowed_functions:
                return True
            # 否则，视为一个变量。变量的实际有效性（是否存在于数据中）将在评估时检查。
            # 这里不严格要求变量必须在 self.allowed_variables 中，以支持动态数据列。
            # 但需要避免与聚合函数名冲突，因为聚合函数应该通过 ast.Call 处理
            return node.id not in self.allowed_aggregates
        if isinstance(node, ast.BinOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.left) and self._validate_node(node.right)
        if isinstance(node, ast.UnaryOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.operand)
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, 'id', None)
            if func_name in self.allowed_functions:
                return all(self._validate_node(arg) for arg in node.args)
            if func_name in self.allowed_aggregates:
                return len(node.args) == 1 and self._validate_node(node.args[0])
        return False
            
    def get_used_variables(self, formula: str) -> Set[str]:
        if not self.validate(formula): return set()
        tree = ast.parse(formula, mode='eval')
        return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in self.allowed_variables}

    def evaluate_formula(self, data: pd.DataFrame, formula: str) -> pd.Series:
        formula_stripped = formula.strip()
        if not formula_stripped:
            # 如果是空公式，并且数据中包含 'x' 或 'y'，则尝试使用它们作为默认值
            # 这种情况应该由上层调用者确保不会发生，但作为最后的防御
            if 'x' in data.columns: return data['x']
            elif 'y' in data.columns: return data['y']
            raise ValueError("传入了空公式")

        # 特殊处理单个变量作为公式的情况，无论是否在 allowed_variables 中
        # 因为 x, y 可能是隐式变量，不一定在数据文件中直接列出
        if formula_stripped in data.columns:
            return data[formula_stripped]

        eval_globals = self.get_all_constants_and_globals()
        local_scope = eval_globals.copy()
        processed_formula = formula
        
        # 1. 预处理聚合函数
        agg_pattern = re.compile(r'(\b(?:' + '|'.join(self.allowed_aggregates) + r'))\s*\((.*?)\)')
        matches = list(agg_pattern.finditer(formula))
        for i, match in enumerate(reversed(matches)):
            agg_func_name, inner_expr = match.groups()
            if inner_expr.count('(') != inner_expr.count(')'): continue # 简单括号匹配
            
            try:
                inner_values = data.eval(inner_expr, global_dict=eval_globals, local_dict={})
            except Exception as e:
                raise ValueError(f"评估聚合函数内表达式 '{inner_expr}' 时出错: {e}")

            if agg_func_name == 'mean': scalar_result = inner_values.mean()
            elif agg_func_name == 'sum': scalar_result = inner_values.sum()
            elif agg_func_name == 'median': scalar_result = inner_values.median()
            elif agg_func_name == 'std': scalar_result = inner_values.std()
            elif agg_func_name == 'var': scalar_result = inner_values.var()
            elif agg_func_name == 'min_frame': scalar_result = inner_values.min()
            elif agg_func_name == 'max_frame': scalar_result = inner_values.max()
            else: scalar_result = 0.0

            temp_var_name = f"__agg_result_{len(matches) - 1 - i}__"
            local_scope[temp_var_name] = scalar_result
            processed_formula = processed_formula[:match.start()] + f"@{temp_var_name}" + processed_formula[match.end():]

        # 2. 为所有外部变量添加 '@' 前缀以供 pandas.eval 使用
        all_external_vars = sorted(eval_globals.keys(), key=len, reverse=True)
        for var_name in all_external_vars:
            pattern = r'\b' + re.escape(var_name) + r'\b'
            replacement = '@' + var_name
            processed_formula = re.sub(pattern, replacement, processed_formula)

        # 3. 最终求值
        try:
            logger.debug(f"原始公式: '{formula}', 处理后公式: '{processed_formula}', 作用域: {list(local_scope.keys())}")
            return data.eval(processed_formula, global_dict={}, local_dict=local_scope)
        except Exception as e:
            raise ValueError(f"评估最终公式 '{processed_formula}' 时失败: {e}")