#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帮助文档内容模块
"""
from typing import List, Dict

def get_formula_help_html(base_variables: List[str], custom_global_variables: Dict[str, float], science_constants: Dict[str, float]) -> str:
    """生成公式帮助的HTML内容"""
    var_list_html = "".join([f"<li><code>{var}</code></li>" for var in sorted(list(base_variables))])
    const_list_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in science_constants.items()])
    
    all_globals = sorted(custom_global_variables.items())
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
        <p>这些是在“全局统计”标签页中根据每个原始变量自动计算的统计量:</p>
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
        h2 {{ color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; }}
        h3 {{ color: #005A9C; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
        code {{ background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }}
        ul {{ list-style-type: none; padding-left: 0; }} li {{ margin-bottom: 5px; }}
    </style></head><body>
        <h2>公式语法说明</h2><p>您可以使用标准的Python数学表达式来创建新的派生变量。</p>
        
        <h3>通用语法</h3>
        <ul>
            <li><b>基本运算符:</b> <code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>**</code> (乘方), <code>()</code></li>
            <li><b>标准数学函数:</b> <code>sin</code>, <code>cos</code>, <code>sqrt</code>, <code>log</code>, <code>abs</code>, <code>min(a,b)</code>, <code>max(a,b)</code> 等。</li>
        </ul>

        <h3>公式应用场景</h3>
        <p>您可以在以下场景中使用公式:</p>
        <ul>
            <li><b>坐标轴:</b> 变换X轴和Y轴的显示坐标。</li>
            <li><b>热力图/等高线:</b> 定义用于着色或绘制等高线的标量场。</li>
            <li><b>矢量/流线图:</b> 定义矢量场的U (水平) 和V (垂直) 分量。</li>
        </ul>

        <h3>可用变量与常量</h3>
        
        <h4>数据变量 (逐点变化)</h4>
        <p>以下变量来自您加载的数据文件，代表每个数据点的属性:</p>
        <ul>{var_list_html or "<li>(无可用数据)</li>"}</ul>
        
        <h4>单帧聚合函数 (对当前帧计算)</h4>
        <p>这些函数对当前帧的所有数据点进行计算，返回一个标量值。聚合函数内部也支持公式:</p>
        <ul>
            <li><code>mean(expr)</code>: 平均值, 如 <code>mean(p)</code> 或 <code>mean(u*u + v*v)</code></li>
            <li><code>sum(expr)</code>: 总和</li>
            <li><code>std(expr)</code>: 标准差</li>
            <li>...等等 (<code>median</code>, <code>var</code>, <code>min_frame</code>, <code>max_frame</code>)</li>
        </ul>
        <p><b>注意:</b> 为避免与 `min/max` 数学函数冲突, 帧内聚合请使用 `min_frame/max_frame`。</p>

        {global_section or "<h4>全局统计变量</h4><p>(请先在“全局统计”标签页中进行计算)</p>"}
        
        <h4>科学常量</h4><ul>{const_list_html}</ul>

        <h3>示例</h3>
        <ul>
            <li><b>速度大小 (用于热力图):</b> <code>sqrt(u**2 + v**2)</code></li>
            <li><b>动压 (用于等高线):</b> <code>0.5 * rho * (u**2 + v**2)</code></li>
            <li><b>压力波动 (帧内):</b> <code>p - mean(p)</code></li>
            <li><b>马赫数归一化 (使用全局值):</b> <code>Ma / Ma_global_max</code></li>
            <li><b>速度脉动 (用于矢量图):</b>
              <ul>
                <li>U分量公式: <code>u - u_global_mean</code></li>
                <li>V分量公式: <code>v - v_global_mean</code></li>
              </ul>
            </li>
            <li><b>质量通量 (用于流线图):</b>
              <ul>
                <li>U分量公式: <code>rho * u</code></li>
                <li>V分量公式: <code>rho * v</code></li>
              </ul>
            </li>
        </ul>
    </body></html>"""

def get_custom_stats_help_html() -> str:
    """生成自定义全局统计帮助的HTML内容"""
    return """
    <html><head><style>
        body { font-family: sans-serif; line-height: 1.6; }
        h2 { color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; }
        h3 { color: #005A9C; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
        code { background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }
        ul { list-style-type: circle; padding-left: 20px; }
        .note { border-left: 3px solid #f0ad4e; padding-left: 15px; background-color: #fcf8e3; }
    </style></head><body>
        <h2>自定义常量计算指南</h2>
        <p>
            此功能允许您基于整个数据集 (所有CSV文件) 计算新的<b>全局常量</b>。
            这些常量计算完成后，即可在任何可视化公式中使用，就像 `pi` 或 `u_global_mean` 一样。
        </p>

        <h3>基本格式</h3>
        <p>每行定义一个常量，必须遵循以下格式:</p>
        <code>new_constant_name = aggregate_function(expression)</code>

        <h3>核心组件</h3>
        <ul>
            <li>
                <b><code>new_constant_name</code></b><br>
                您为新常量指定的名称。必须是有效的Python标识符 (只能包含字母、数字和下划线，且不能以数字开头)。
            </li>
            <li>
                <b><code>aggregate_function</code></b><br>
                一个聚合函数，用于将表达式在整个数据集上的计算结果合并成一个单一的数值。支持的函数有:
                <ul>
                    <li><code>mean</code>: 计算表达式在所有数据点上的平均值。</li>
                    <li><code>sum</code>: 计算总和。</li>
                    <li><code>std</code>: 计算标准差。</li>
                    <li><code>var</code>: 计算方差。</li>
                </ul>
            </li>
            <li>
                <b><code>expression</code></b><br>
                一个数学表达式，其计算基于<b>每个数据点</b>。您可以在此表达式中使用:
                <ul>
                    <li>原始数据变量 (如 <code>u</code>, <code>v</code>, <code>p</code>, <code>rho</code> 等)。</li>
                    <li>所有已计算的基础统计量 (如 <code>u_global_mean</code>, <code>p_global_max</code> 等)。</li>
                    <li>在此文本框中，位于当前行<b>之前</b>已定义的其他自定义常量。</li>
                    <li>标准数学运算符 (<code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>**</code>) 和函数 (<code>sqrt</code>, <code>sin</code> 等)。</li>
                </ul>
            </li>
        </ul>

        <h3>示例</h3>
        
        <h4>1. 计算平均湍动能 (TKE)</h4>
        <p>假设湍动能由速度分量的平方和定义。</p>
        <code>tke_global_mean = mean(0.5 * (u**2 + v**2 + w**2))</code>
        <p class="note">
            这里，<code>0.5 * (u**2 + v**2 + w**2)</code> 会对数据集中的每一个点进行计算，然后 <code>mean(...)</code> 函数计算所有这些结果的平均值。
        </p>

        <h4>2. 计算雷诺应力</h4>
        <p>雷诺应力是速度脉动的乘积的平均值。</p>
        <code>reynolds_stress_uv = mean((u - u_global_mean) * (v - v_global_mean))</code>

        <h4>3. 计算基于前面结果的派生常量</h4>
        <p>您可以分步定义复杂的常量。</p>
        <code>tke_fluct_mean = mean(0.5 * ((u - u_global_mean)**2 + (v - v_global_mean)**2))</code><br>
        <code>intensity_fluct_ratio = sqrt(tke_fluct_mean) / u_global_mean</code>

        <p class="note">
            <b>重要:</b> 计算顺序是自上而下的。确保在使用一个自定义常量之前，它已经在前面的行中被定义。
        </p>
    </body></html>
    """
