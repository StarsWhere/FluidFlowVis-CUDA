#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ast
import re
import logging
import pandas as pd
from typing import Set, List, Dict, Any

logger = logging.getLogger(__name__)

class FormulaValidator:
    def __init__(self):
        self.allowed_op_types = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd}
        self.allowed_functions = {'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'exp', 'log', 'log10', 'sqrt', 'abs', 'floor', 'ceil', 'round', 'min', 'max'}
        
        # 单帧聚合函数
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
            # 捕获因换行符等问题导致的语法错误
            if isinstance(e, SyntaxError):
                logger.warning(f"公式语法错误: '{formula}' - {e}")
            else:
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
            func_name = getattr(node.func, 'id', None)
            if func_name in self.allowed_functions:
                return all(self._validate_node(arg) for arg in node.args)
            if func_name in self.allowed_aggregates:
                # 聚合函数只接受一个参数，该参数必须是合法的表达式
                return len(node.args) == 1 and self._validate_node(node.args[0])
        return False
            
    def get_used_variables(self, formula: str) -> Set[str]:
        if not self.validate(formula): return set()
        variables = set()
        tree = ast.parse(formula, mode='eval')
        for node in ast.walk(tree):
            # 提取作为逐点数组使用的变量
            if isinstance(node, ast.Name) and node.id in self.allowed_variables:
                variables.add(node.id)
        return variables

    def evaluate_formula(self, data: pd.DataFrame, formula: str) -> pd.Series:
        """
        统一的公式求值引擎。
        - 支持全局变量 (T_global_mean 等)。
        - 支持单帧聚合函数 (mean(p) 等)。
        - 返回计算结果的Pandas Series。
        """
        if not formula:
            raise ValueError("传入了空公式")

        # 准备求值环境
        eval_globals = self.get_all_constants_and_globals()
        local_scope = eval_globals.copy()
        processed_formula = formula
        
        # 1. 处理聚合函数
        agg_pattern = re.compile(r'(\b(?:' + '|'.join(self.allowed_aggregates) + r'))\s*\((.*?)\)')
        matches = list(agg_pattern.finditer(formula))
        for i, match in enumerate(reversed(matches)):
            agg_func_name, inner_expr = match.groups()
            
            if inner_expr.count('(') != inner_expr.count(')'): continue
            
            try:
                inner_values = data.eval(inner_expr, global_dict=eval_globals, local_dict={})
            except Exception as e:
                raise ValueError(f"评估聚合函数内部表达式 '{inner_expr}' (在 {agg_func_name} 中) 时出错: {e}")

            scalar_result = 0.0
            if agg_func_name == 'mean': scalar_result = inner_values.mean()
            elif agg_func_name == 'sum': scalar_result = inner_values.sum()
            elif agg_func_name == 'median': scalar_result = inner_values.median()
            elif agg_func_name == 'std': scalar_result = inner_values.std()
            elif agg_func_name == 'var': scalar_result = inner_values.var()
            elif agg_func_name == 'min_frame': scalar_result = inner_values.min()
            elif agg_func_name == 'max_frame': scalar_result = inner_values.max()

            temp_var_name = f"__agg_result_{len(matches) - 1 - i}__"
            local_scope[temp_var_name] = scalar_result
            
            start, end = match.span()
            # **重要**：替换时直接带上@符号
            processed_formula = processed_formula[:start] + f"@{temp_var_name}" + processed_formula[end:]

        # 2. **FIX**: 为所有已知的全局变量和科学常数添加@前缀
        # 按名称长度降序排序，以避免替换子字符串 (例如, 'var' 不会错误地替换 'var_abc' 的一部分)
        all_external_vars = sorted(eval_globals.keys(), key=len, reverse=True)
        
        for var_name in all_external_vars:
            # 使用\b来确保只匹配整个单词
            pattern = r'\b' + re.escape(var_name) + r'\b'
            replacement = '@' + var_name
            processed_formula = re.sub(pattern, replacement, processed_formula)

        # 3. 最终求值
        try:
            logger.debug(f"原始公式: '{formula}', 处理后公式: '{processed_formula}', 作用域: {list(local_scope.keys())}")
            return data.eval(processed_formula, global_dict={}, local_dict=local_scope)
        except Exception as e:
            raise ValueError(f"评估最终公式 '{processed_formula}' 时失败: {e}")


    def get_formula_help_html(self, base_variables: List[str]) -> str:
        var_list_html = "".join([f"<li><code>{var}</code></li>" for var in sorted(list(self.allowed_variables))])
        const_list_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in self.science_constants.items()])
        
        all_globals = sorted(self.custom_global_variables.items())
        basic_globals = []
        custom_globals = []

        if base_variables:
            basic_prefixes = tuple(f"{var}_global_" for var in base_variables)
            for key, val in all_globals:
                if key.startswith(basic_prefixes):
                    basic_globals.append((key, val))
                else:
                    custom_globals.append((key, val))
        else:
            custom_globals = all_globals
            
        basic_globals_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in basic_globals])
        custom_globals_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in custom_globals])

        global_section = ""
        if basic_globals_html:
            global_section += f"""
            <h3>基础统计变量 (跨所有帧)</h3>
            <p>这些是根据每个原始变量自动计算的统计量:</p>
            <ul>{basic_globals_html}</ul>
            """
        if custom_globals_html:
            global_section += f"""
            <h3>自定义全局常量 (跨所有帧)</h3>
            <p>这些是在“全局统计”标签页中由用户定义的常量:</p>
            <ul>{custom_globals_html}</ul>
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
            <p>这些函数对当前帧的所有数据点进行计算，返回一个标量值。聚合函数内部也支持公式:</p>
            <ul>
                <li><code>mean(expr)</code>: 平均值, 如 <code>mean(p)</code> 或 <code>mean(u*u + v*v)</code></li>
                <li><code>sum(expr)</code>: 总和</li>
                <li><code>median(expr)</code>: 中位数</li>
                <li><code>std(expr)</code>: 标准差</li>
                <li><code>var(expr)</code>: 方差</li>
                <li><code>min_frame(expr)</code>: 帧内最小值</li>
                <li><code>max_frame(expr)</code>: 帧内最大值</li>
            </ul>
            <p><b>注意:</b> 为避免与 `min/max` 数学函数冲突, 帧内聚合请使用 `min_frame/max_frame`。</p>

            {global_section or "<h3>全局统计变量</h3><p>(请先在“全局统计”标签页中进行计算)</p>"}
            
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
                <li><b>动压:</b> <code>0.5 * rho * (u**2 + v**2)</code></li>
                <li><b>雷诺应力分量 (全局):</b> <code>rho * (u - u_global_mean) * (v - v_global_mean)</code></li>
                <li><b>压力波动 (帧内):</b> <code>p - mean(p)</code></li>
                <li><b>湍动能 (帧内):</b> <code>0.5 * (std(u)**2 + std(v)**2)</code></li>
                <li><b>马赫数归一化:</b> <code>Ma / Ma_global_max</code></li>
            </ul>
        </body></html>"""