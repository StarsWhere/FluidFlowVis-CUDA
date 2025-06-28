#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ast
from typing import Set, List
import logging

logger = logging.getLogger(__name__)

class FormulaValidator:
    def __init__(self):
        self.allowed_op_types = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd}
        self.allowed_functions = {'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'exp', 'log', 'log10', 'sqrt', 'abs', 'floor', 'ceil', 'round', 'min', 'max'}
        self.allowed_constants = {'pi', 'e', 'inf', 'nan'}
        self.allowed_variables: Set[str] = set()
    
    def update_allowed_variables(self, variables: List[str]):
        self.allowed_variables = set(variables)
        logger.debug(f"公式验证器已更新可用变量: {self.allowed_variables}")

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
        if isinstance(node, ast.Name): return node.id in self.allowed_variables or node.id in self.allowed_constants or node.id in self.allowed_functions
        if isinstance(node, ast.BinOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.left) and self._validate_node(node.right)
        if isinstance(node, ast.UnaryOp): return type(node.op) in self.allowed_op_types and self._validate_node(node.operand)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in self.allowed_functions:
                return all(self._validate_node(arg) for arg in node.args)
        return False
            
    def get_used_variables(self, formula: str) -> Set[str]:
        if not self.validate(formula): return set()
        variables = set()
        tree = ast.parse(formula, mode='eval')
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in self.allowed_variables:
                variables.add(node.id)
        return variables

    def get_formula_help_html(self) -> str:
        var_list_html = "".join([f"<li><code>{var}</code></li>" for var in sorted(list(self.allowed_variables))])
        return f"""
        <html><head><style>
            body {{ font-family: sans-serif; line-height: 1.6; }}
            h3 {{ color: #005A9C; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
            code {{ background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }}
            ul {{ list-style-type: none; padding-left: 0; }} li {{ margin-bottom: 5px; }}
        </style></head><body>
            <h3>公式语法说明</h3><p>您可以使用标准的Python数学表达式来创建新的派生变量。</p>
            <h3>基本运算符</h3><ul><li><code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>**</code> (乘方), <code>()</code></li></ul>
            <h3>可用变量</h3><p>以下变量来自您加载的数据文件:</p><ul>{var_list_html or "<li>(无可用数据)</li>"}</ul>
            <h3>数学函数</h3><ul>
                <li><b>三角:</b> <code>sin</code>, <code>cos</code>, <code>tan</code>, <code>asin</code>, <code>acos</code>, <code>atan</code></li>
                <li><b>双曲:</b> <code>sinh</code>, <code>cosh</code>, <code>tanh</code></li>
                <li><b>指数/对数:</b> <code>exp</code>, <code>log</code>, <code>log10</code></li>
                <li><b>其他:</b> <code>sqrt</code>, <code>abs</code>, <code>floor</code>, <code>ceil</code>, <code>round</code></li>
                <li><b>比较:</b> <code>min(a, b)</code>, <code>max(a, b)</code></li>
            </ul>
            <h3>数学常量</h3><ul><li><code>pi</code>, <code>e</code></li></ul>
            <h3>示例</h3><ul>
                <li><b>速度大小:</b> <code>sqrt(u**2 + v**2)</code></li>
                <li><b>动能:</b> <code>0.5 * rho * (u**2 + v**2 + w**2)</code></li>
            </ul>
        </body></html>"""