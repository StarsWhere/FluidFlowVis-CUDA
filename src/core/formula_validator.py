#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ast
from typing import Set, List, Dict
import logging

logger = logging.getLogger(__name__)

class FormulaValidator:
    def __init__(self):
        self.allowed_op_types = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd}
        self.allowed_functions = {'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'exp', 'log', 'log10', 'sqrt', 'abs', 'floor', 'ceil', 'round', 'min', 'max'}
        
        # 新增：单帧聚合函数
        self.allowed_aggregates = {'mean', 'sum', 'median', 'std', 'var', 'min_frame', 'max_frame'}

        self.science_constants = {
            'pi': 3.141592653589793, 'e': 2.718281828459045, 'g': 9.80665,
            'c': 299792458, 'h': 6.62607015e-34, 'k_B': 1.380649e-23,
            'N_A': 6.02214076e23, 'R': 8.314462618,
        }
        
        self.allowed_variables: Set[str] = set()
        self.custom_global_variables: Dict[str, float] = {}
    
    def update_allowed_variables(self, variables: List[str]):
        self.allowed_variables = set(variables)
        logger.debug(f"公式验证器已更新可用变量: {self.allowed_variables}")

    def update_custom_global_variables(self, global_vars: Dict[str, float]):
        self.custom_global_variables = global_vars
        logger.debug(f"公式验证器已更新全局变量: {list(self.custom_global_variables.keys())}")

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
            return (node.id in self.allowed_variables or 
                    node.id in self.science_constants or
                    node.id in self.custom_global_variables or
                    node.id in self.allowed_functions)
        if isinstance(node, ast.BinOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.left) and self._validate_node(node.right)
        if isinstance(node, ast.UnaryOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.operand)
        if isinstance(node, ast.Call):
            # 标准数学函数
            if isinstance(node.func, ast.Name) and node.func.id in self.allowed_functions:
                return all(self._validate_node(arg) for arg in node.args)
            # 新增：聚合函数
            if isinstance(node.func, ast.Name) and node.func.id in self.allowed_aggregates:
                # 聚合函数只接受一个参数，且该参数必须是合法的逐点变量
                if len(node.args) == 1 and isinstance(node.args[0], ast.Name):
                    return node.args[0].id in self.allowed_variables
        return False
            
    def get_used_variables(self, formula: str) -> Set[str]:
        if not self.validate(formula): return set()
        variables = set()
        tree = ast.parse(formula, mode='eval')
        for node in ast.walk(tree):
            # 提取作为逐点数组使用的变量
            if isinstance(node, ast.Name) and node.id in self.allowed_variables:
                # 确保它不是聚合函数的参数，因为那些是预先计算的
                # (这个逻辑在插值器中处理，这里简单提取所有用到的变量即可)
                variables.add(node.id)
        return variables

    def get_formula_help_html(self) -> str:
        var_list_html = "".join([f"<li><code>{var}</code></li>" for var in sorted(list(self.allowed_variables))])
        const_list_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in self.science_constants.items()])
        global_var_list_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in sorted(self.custom_global_variables.items())])
        
        global_section = ""
        if global_var_list_html:
            global_section = f"""
            <h3>全局统计变量 (跨所有帧)</h3>
            <p>这些变量是根据所有数据文件计算得出的，可在“全局统计”标签页中重新计算:</p>
            <ul>{global_var_list_html}</ul>
            """

        return f"""
        <html><head><style>
            body {{ font-family: sans-serif; line-height: 1.6; }}
            h3 {{ color: #005A9C; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
            code {{ background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }}
            ul {{ list-style-type: none; padding-left: 0; }} li {{ margin-bottom: 5px; }}
        </style></head><body>
            <h3>公式语法说明</h3><p>您可以使用标准的Python数学表达式来创建新的派生变量。</p>
            <h3>基本运算符</h3><ul><li><code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>**</code> (乘方), <code>()</code></li></ul>
            <h3>数据变量 (逐点变化)</h3><p>以下变量来自您加载的数据文件:</p><ul>{var_list_html or "<li>(无可用数据)</li>"}</ul>
            
            <h3>单帧聚合函数 (对当前帧计算)</h3>
            <p>这些函数对当前帧的所有数据点进行计算，返回一个标量值:</p>
            <ul>
                <li><code>mean(var)</code>: 平均值, 如 <code>mean(p)</code></li>
                <li><code>sum(var)</code>: 总和</li>
                <li><code>median(var)</code>: 中位数</li>
                <li><code>std(var)</code>: 标准差</li>
                <li><code>var(var)</code>: 方差</li>
                <li><code>min_frame(var)</code>: 帧内最小值</li>
                <li><code>max_frame(var)</code>: 帧内最大值</li>
            </ul>
            <p><b>注意:</b> 为避免与 `min/max` 数学函数冲突, 帧内聚合请使用 `min_frame/max_frame`。</p>

            {global_section}
            <h3>科学常量</h3><ul>{const_list_html}</ul>
            <h3>标准数学函数</h3><ul>
                <li><b>三角:</b> <code>sin</code>, <code>cos</code>, <code>tan</code>, <code>asin</code>, <code>acos</code>, <code>atan</code></li>
                <li><b>双曲:</b> <code>sinh</code>, <code>cosh</code>, <code>tanh</code></li>
                <li><b>指数/对数:</b> <code>exp</code>, <code>log</code>, <code>log10</code></li>
                <li><b>其他:</b> <code>sqrt</code>, <code>abs</code>, <code>floor</code>, <code>ceil</code>, <code>round</code></li>
                <li><b>比较:</b> <code>min(a, b)</code>, <code>max(a, b)</code></li>
            </ul>
            <h3>示例</h3><ul>
                <li><b>速度大小:</b> <code>sqrt(u**2 + v**2)</code></li>
                <li><b>雷诺应力分量 (全局):</b> <code>rho * (u - u_global_mean) * (v - v_global_mean)</code></li>
                <li><b>压力波动 (帧内):</b> <code>p - mean(p)</code></li>
            </ul>
        </body></html>"""