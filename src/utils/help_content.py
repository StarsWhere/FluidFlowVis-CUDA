# src/utils/help_content.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帮助文档内容模块

此模块包含了应用程序中所有“帮助”按钮所显示的HTML内容。
文档被设计为尽可能详尽和用户友好，包含了大量的代码示例和概念解释，
以帮助用户充分利用 InterVis 的各项功能。

文档通过多个函数生成，每个函数对应一个特定的帮助主题。
内容使用了基础的HTML和CSS进行格式化，以提高可读性。
"""
from typing import List, Dict

# ----------------------------------------------------------------------------
# 核心功能帮助: 公式、数据处理、分析
# ----------------------------------------------------------------------------

def get_formula_help_html(base_variables: List[str], custom_global_variables: Dict[str, float], science_constants: Dict[str, float]) -> str:
    """
    生成用于“可视化”和“派生变量”公式输入的帮助HTML内容。
    这是最核心的帮助文档之一，解释了所有可用的变量、常量和函数。
    """
    # 动态生成可用数据变量列表
    var_list_html = "".join([f"<li><code>{var}</code></li>" for var in sorted(list(base_variables))])
    if not var_list_html:
        var_list_html = "<li><i>(当前项目无可用数据变量)</i></li>"

    # 动态生成科学常量列表
    const_list_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in science_constants.items()])

    # 动态生成用户定义的全局常量列表
    all_globals = sorted(custom_global_variables.items())
    custom_globals_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in all_globals])

    global_section = ""
    if custom_globals_html:
        global_section = f"""
        <h3>全局常量 (Global Constants)</h3>
        <p>
            这些是在“数据处理”选项卡中计算或由用户定义的<b>单个标量值</b>。
            它们在所有计算中都可用，可以像普通数字一样使用。
        </p>
        <ul>{custom_globals_html}</ul>
        """
    else:
        global_section = """
        <h3>全局常量 (Global Constants)</h3>
        <p><i>(请先在“数据处理”选项卡中进行计算，此处将显示结果)</i></p>
        """

    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; }}
            h2 {{ color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; margin-top: 25px;}}
            h3 {{ color: #005A9C; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 20px; }}
            h4 {{ color: #333; margin-bottom: 5px; }}
            code {{
                background-color: #f0f0f0;
                padding: 3px 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: "Courier New", Courier, monospace;
                font-size: 0.95em;
            }}
            ul {{ list-style-type: none; padding-left: 0; }}
            li {{ margin-bottom: 8px; }}
            .note {{
                border-left: 4px solid #17a2b8; /* Info blue */
                padding: 10px 15px;
                background-color: #e2f3f5;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }}
            .warning {{
                border-left: 4px solid #f0ad4e; /* Warning yellow */
                padding: 10px 15px;
                background-color: #fcf8e3;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }}
            .new-feature {{
                color: #d9534f; /* Danger red */
                font-weight: bold;
                font-style: italic;
            }}
            .example-box {{
                background-color: #f9f9f9;
                border: 1px solid #eee;
                padding: 15px;
                margin-top: 10px;
                border-radius: 5px;
            }}
            .example-box code {{
                display: block;
                white-space: pre-wrap;
                padding: 10px;
            }}
        </style>
    </head>
    <body>
        <h2>公式语法指南</h2>
        <p>您可以使用标准的Python数学表达式和一系列强大的内置函数来创建新的派生变量或定义复杂的可视化方案。</p>
        <div class="note">
            <p><b>核心思想:</b> 公式引擎允许您将原始数据 (如速度分量 <code>u</code>, <code>v</code>, 压力 <code>p</code>) 组合、变换，以揭示更深层次的物理现象 (如涡量、动能、散度等)。</p>
        </div>

        <!-- ==================== 变量与常量 ==================== -->
        <h2>可用变量与常量</h2>
        
        <h3>数据变量 (Data Variables)</h3>
        <p>这些变量直接来自您的数据文件，代表每个数据点在某一时刻的属性。它们是<b>逐点变化</b>的。</p>
        <ul>{var_list_html}</ul>

        {global_section}

        <h3>科学常量 (Scientific Constants)</h3>
        <p>这是一些常用的物理和数学常量，已为您内置。</p>
        <ul>{const_list_html}</ul>

        <!-- ==================== 函数列表 ==================== -->
        <h2>函数列表 (Function Reference)</h2>

        <h3>1. 标准数学函数和运算符</h3>
        <p>这些函数和运算符像在计算器或Python中一样工作。</p>
        
        <h4>基本运算符</h4>
        <ul>
            <li><code>+</code> (加), <code>-</code> (减), <code>*</code> (乘), <code>/</code> (除)</li>
            <li><code>**</code> (乘方). <b>示例:</b> <code>u**2</code> 表示 u的平方。</li>
            <li><code>()</code> (括号). 用于控制运算优先级。<b>示例:</b> <code>0.5 * (u + v)</code>。</li>
        </ul>
        
        <h4>通用函数 (作用于单个值)</h4>
        <ul>
            <li><code>sqrt(x)</code>: 计算 x 的平方根。<b>示例:</b> <code>sqrt(u**2 + v**2)</code></li>
            <li><code>abs(x)</code>: 计算 x 的绝对值。</li>
            <li><code>sin(x)</code>, <code>cos(x)</code>, <code>tan(x)</code>: 三角函数 (x 的单位为弧度)。</li>
            <li><code>asin(x)</code>, <code>acos(x)</code>, <code>atan(x)</code>: 反三角函数。</li>
            <li><code>sinh(x)</code>, <code>cosh(x)</code>, <code>tanh(x)</code>: 双曲函数。</li>
            <li><code>exp(x)</code>: 计算 e 的 x 次方 (e<sup>x</sup>)。</li>
            <li><code>log(x)</code>: 计算 x 的自然对数 (ln(x))。</li>
            <li><code>log10(x)</code>: 计算 x 的以10为底的对数。</li>
            <li><code>pow(x, y)</code>: 计算 x 的 y 次方 (x<sup>y</sup>)，等同于 <code>x**y</code>。</li>
            <li><code>floor(x)</code>: 对 x 向下取整。</li>
            <li><code>ceil(x)</code>: 对 x 向上取整。</li>
            <li><code>round(x)</code>: 对 x 四舍五入。</li>
            <li><code>min(a, b)</code>: 返回 a 和 b 中的较小值。<b>注意:</b> 仅接受两个参数。</li>
            <li><code>max(a, b)</code>: 返回 a 和 b 中的较大值。<b>注意:</b> 仅接受两个参数。</li>
        </ul>

        <h3>2. <span class="new-feature">逐帧</span>聚合函数 (Frame Aggregation)</h3>
        <div class="note">
            <p>
                这些函数非常特殊：它们会对<b>当前显示帧</b>的所有数据点进行计算，得出一个<b>单一值</b>，
                然后将这个值用于公式中的每一个点。这对于计算<b>脉动量</b>或<b>偏差</b>非常有用。
            </p>
        </div>
        <ul>
            <li><code>mean(expr)</code>: 计算当前帧所有点上 <code>expr</code> 表达式的<b>平均值</b>。</li>
            <li><code>sum(expr)</code>: 计算当前帧所有点上 <code>expr</code> 表达式的<b>总和</b>。</li>
            <li><code>std(expr)</code>: 计算当前帧所有点上 <code>expr</code> 表达式的<b>标准差</b>。</li>
            <li><code>var(expr)</code>: 计算当前帧所有点上 <code>expr</code> 表达式的<b>方差</b>。</li>
            <li><code>median(expr)</code>: 计算当前帧所有点上 <code>expr</code> 表达式的<b>中位数</b>。</li>
            <li><code>min_frame(expr)</code>: 计算当前帧所有点上 <code>expr</code> 表达式的<b>最小值</b> (为避免与 <code>min(a,b)</code> 冲突而命名)。</li>
            <li><code>max_frame(expr)</code>: 计算当前帧所有点上 <code>expr</code> 表达式的<b>最大值</b> (为避免与 <code>max(a,b)</code> 冲突而命名)。</li>
        </ul>
        <div class="example-box">
            <h4>聚合函数示例: 计算压力脉动</h4>
            <p>假设您想可视化压力相对于当前帧平均压力的偏离程度：</p>
            <code>p - mean(p)</code>
            <p>
                <b>工作原理:</b>
                <ol>
                    <li>引擎首先计算当前帧所有点的 <code>p</code> 的平均值，得到一个标量，例如 101325。</li>
                    <li>然后，对于每一个数据点，它用该点的压力值减去这个平均值。</li>
                    <li>结果是一个新的场，显示了高压区和低压区。</li>
                </ol>
            </p>
        </div>
        
        <h3>3. <span class="new-feature">空间运算/矩阵函数</span> (Spatial Operations)</h3>
        <div class="warning">
            <p>
                <b>高级功能:</b> 这些函数不对原始的、离散的数据点进行操作。相反，它们对数据经过<b>插值形成的连续空间场</b>进行操作。
                这使我们能够计算各种导数，如梯度、散度和旋度。
            </p>
            <p><b>核心特性:</b> 这些函数可以<b>相互嵌套</b>，从而构建出非常复杂的物理量！</p>
        </div>
        <ul>
            <li>
                <h4><code>grad_x(field)</code> 和 <code>grad_y(field)</code></h4>
                <p>计算标量场 <code>field</code> 在 X 或 Y 方向的<b>梯度 (偏导数)</b>。</p>
                <ul>
                    <li>数学上: ∂(field)/∂x  和  ∂(field)/∂y</li>
                    <li><b>用途:</b> 表示物理量在空间中的变化率。例如，压力梯度驱动流动。</li>
                </ul>
            </li>
            <li>
                <h4><code>div(u_field, v_field)</code></h4>
                <p>计算2D矢量场 <code>(u, v)</code> 的<b>散度</b>。</p>
                <ul>
                    <li>数学上: ∂u/∂x + ∂v/∂y</li>
                    <li><b>用途:</b> 衡量流场的“源”或“汇”的强度。正散度表示流体在流出该点（膨胀），负散度表示流入（压缩）。对于不可压缩流，散度应为零。</li>
                </ul>
            </li>
            <li>
                <h4><code>curl(u_field, v_field)</code></h4>
                <p>计算2D矢量场 <code>(u, v)</code> 的<b>旋度</b>。在2D情况下，结果是一个标量。</p>
                <ul>
                    <li>数学上: ∂v/∂x - ∂u/∂y</li>
                    <li><b>用途:</b> 衡量流体微团的<b>旋转强度</b>。这通常被称为<b>涡量 (Vorticity)</b>，是流体分析中的一个核心概念。正值和负值表示不同的旋转方向。</li>
                </ul>
            </li>
            <li>
                <h4><code>laplacian(field)</code></h4>
                <p>计算标量场 <code>field</code> 的<b>拉普拉斯算子</b>，即梯度的散度。</p>
                <ul>
                    <li>数学上: ∂²(field)/∂x² + ∂²(field)/∂y²</li>
                    <li><b>用途:</b> 在传热和扩散问题中非常重要，表示一个点的值与其周围点的平均值之间的差异。在流体中，可用于压力泊松方程等。</li>
                </ul>
            </li>
        </ul>

        <!-- ==================== 示例 ==================== -->
        <h2>综合示例 (Examples)</h2>

        <div class="example-box">
            <h4>示例 1: 速度大小 (动能的可视化基础)</h4>
            <p>用于热力图，显示流速快的区域。</p>
            <code>sqrt(u**2 + v**2)</code>
        </div>
        
        <div class="example-box">
            <h4>示例 2: 动压 (Dynamic Pressure)</h4>
            <p>用于等高线图，显示与流速相关的压力。</p>
            <code>0.5 * rho * (u**2 + v**2)</code>
        </div>
        
        <div class="example-box">
            <h4>示例 3: 速度脉动 (Velocity Fluctuation)</h4>
            <p>用于矢量图的U分量，显示速度相对于<b>全局平均速度</b>的偏离。这需要先在“数据处理”中计算出 <code>u_global_mean</code>。</p>
            <code>u - u_global_mean</code>
        </div>
        
        <div class="example-box">
            <h4>示例 4: 涡量 (Vorticity) - <span class="new-feature">空间运算</span></h4>
            <p>一个经典的空间运算应用，直接计算速度场 (u, v) 的旋度。</p>
            <code>curl(u, v)</code>
        </div>

        <div class="example-box">
            <h4>示例 5: 压力梯度X分量 - <span class="new-feature">空间运算</span></h4>
            <p>计算压力场 <code>p</code> 在 X 方向的变化率。</p>
            <code>grad_x(p)</code>
        </div>
        
        <div class="example-box">
            <h4>示例 6: 嵌套空间运算 (高级)</h4>
            <p>展示函数嵌套的能力。这个公式计算了“X方向动量通量(rho*u)”的Y向梯度。这可能用于分析动量输运。</p>
            <code>grad_y(rho * u)</code>
            <p><b>工作原理:</b></p>
            <ol>
                <li>引擎首先计算 <code>rho * u</code> 的逐点值。</li>
                <li>然后将这个新的标量场插值到网格上。</li>
                <li>最后，对这个插值后的场计算Y方向的梯度。</li>
            </ol>
        </div>
        
        <div class="example-box">
            <h4>示例 7: 极其复杂的嵌套 - <span class="new-feature">探索性分析</span></h4>
            <p>这个公式在物理上可能没有明确意义，但它展示了引擎的能力：计算“涡量场”的拉普拉斯算子。</p>
            <code>laplacian(curl(u, v))</code>
            <p><b>工作原理:</b></p>
            <ol>
                <li><b>最内层:</b> 计算 <code>u</code> 和 <code>v</code> 场。</li>
                <li><b>中间层:</b> 计算它们的旋度 <code>curl(u, v)</code>，得到一个标量的涡量场。</li>
                <li><b>最外层:</b> 对这个涡量场计算拉普拉斯算子。</li>
            </ol>
        </div>
    </body>
    </html>
    """

def get_data_processing_help_html() -> str:
    """
    为“数据处理”选项卡生成统一的、极其详细的帮助文档。
    这是另一个核心帮助文档，解释了三种不同的计算模式和批量处理。
    """
    return """
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; }}
            h2 {{ color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 5px; margin-top: 25px; }}
            h3 {{ color: #28a745; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 20px; }}
            code {{
                background-color: #f0f0f0;
                padding: 3px 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: "Courier New", Courier, monospace;
                font-size: 0.95em;
            }}
            ul, ol {{ padding-left: 25px; }}
            li {{ margin-bottom: 8px; }}
            .note {{
                border-left: 4px solid #17a2b8; /* Info blue */
                padding: 10px 15px;
                background-color: #e2f3f5;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }}
            .warning {{
                border-left: 4px solid #f0ad4e; /* Warning yellow */
                padding: 10px 15px;
                background-color: #fcf8e3;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }}
            .new-feature {{
                color: #d9534f; /* Danger red */
                font-weight: bold;
                font-style: italic;
            }}
            .section-box {{
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 20px;
                margin-top: 25px;
                background-color: #fff;
            }}
            .code-block {{
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                padding: 15px;
                margin-top: 10px;
                border-radius: 5px;
                font-family: "Courier New", Courier, monospace;
                white-space: pre-wrap;
                word-break: break-all;
            }}
        </style>
    </head>
    <body>
        <h2>数据处理中心指南</h2>
        <p>
            此选项卡是 InterVis 的“大脑”，它让您可以执行<b>四种核心的计算任务</b>，
            从而极大地扩展您的分析能力。计算结果将被<b>永久保存</b>在项目的数据库中，
            供后续的可视化和进一步计算使用。
        </p>

        <!-- ==================== 逐帧派生变量 ==================== -->
        <div class="section-box">
            <h3>1. 逐帧派生变量 (Per-Frame Derived Variables)</h3>
            <p>
                此功能在您的数据集中创建<b>新数据列</b>。新列中的每个值都是基于<b>同一行（即同一个数据点、同一时刻）</b>的其他值计算得出的。
            </p>
            
            <h4>核心思想与用途</h4>
            <ul>
                <li><b>计算基础:</b> 空间点 (x, y) 在时刻 t 的值。</li>
                <li><b>目的:</b> 计算那些<b>随时间和空间都变化</b>的物理量。</li>
            </ul>
            
            <h4><span class="new-feature">定义格式 (支持批量)</span></h4>
            <p>在输入框中，每行输入一个定义，格式为: <code>new_variable_name = formula</code></p>
            <div class="code-block"># 以 '#' 开头的行是注释，将被忽略
velocity_magnitude = sqrt(u**2 + v**2)
tke = 0.5 * rho * velocity_magnitude**2
vorticity = curl(u, v)</div>
            <div class="note">
                <p><b><span class="new-feature">自动依赖排序:</span></b></p>
                <p>
                    您<b>无需</b>按计算顺序列出您的定义。InterVis会自动分析变量之间的依赖关系，
                    并以正确的顺序执行计算。例如，以下定义是完全有效的，即使 <code>tke</code> 在 <code>velocity_magnitude</code> 之前定义:
                </p>
                <div class="code-block"># InterVis 会先计算 velocity_magnitude, 再计算 tke
tke = 0.5 * rho * velocity_magnitude**2
velocity_magnitude = sqrt(u**2 + v**2)</div>
            </div>
        </div>
        
        <!-- ==================== 时间聚合变量 ==================== -->
        <div class="section-box">
            <h3>2. <span class="new-feature">时间聚合变量</span> (Time-Aggregated Variables)</h3>
            <p>
                此功能也在您的数据集中创建<b>新数据列</b>，但其计算方式完全不同。它会为<b>每一个空间点 (x, y)</b>，汇总其<b>所有时间步</b>的数据，得出一个聚合值（如时间平均值），然后将这个值赋给该空间点在<b>所有时刻</b>的新列中。
            </p>
            
            <h4>核心思想与用途</h4>
            <ul>
                <li><b>计算基础:</b> 空间点 (x, y) 在<b>所有</b>时刻 t 的值的集合。</li>
                <li><b>目的:</b> 计算<b>不随时间变化</b>的统计场，例如定常分析或雷诺分解。</li>
            </ul>

            <h4><span class="new-feature">定义格式 (支持批量和自动排序)</span></h4>
            <p>每行一个定义，格式为: <code>new_variable_name = aggregate_function(expression)</code>。同样支持自动依赖排序。</p>
            <ul>
                <li>
                    <b><code>aggregate_function</code></b>:
                    支持 <code>mean</code>, <code>sum</code>, <code>std</code>, <code>var</code>, <code>min</code>, <code>max</code>。
                </li>
                <li><b><code>expression</code></b>: 一个简单的数学表达式，如 <code>u</code> 或 <code>p*0.1</code>。</li>
            </ul>
            <div class="code-block">u_time_avg = mean(u)
v_time_avg = mean(v)
p_fluctuation_strength = std(p)</div>
             <div class="note">
                <p><b>雷诺分解示例:</b>
                <ol>
                    <li>首先，使用此功能计算时间平均速度 <code>u_time_avg = mean(u)</code>。</li>
                    <li>然后，使用上面的“逐帧派生变量”功能计算脉动速度: <code>u_fluctuation = u - u_time_avg</code>。</li>
                </ol>
                现在您就有了一个新的、随时间变化的“脉动速度”场可以进行可视化分析了。
                </p>
            </div>
        </div>

        <!-- ==================== 组合批量计算 ==================== -->
        <div class="section-box" style="border-color: #d9534f; border-width: 2px;">
            <h3 style="color: #d9534f;">3. <span class="new-feature">组合批量计算 (高级)</span></h3>
            <p>
                此功能是上述两种计算模式的强大结合，允许您在一个任务中定义<b>一系列按顺序执行的计算步骤</b>。
                这对于需要多步推导的复杂分析（例如，计算雷诺应力产生项）至关重要，因为它确保了后续计算可以使用前面步骤中刚刚生成的新变量。
            </p>
            
            <h4>核心思想与用途</h4>
            <ul>
                <li><b>计算基础:</b> 混合使用“逐帧”和“时间聚合”计算。</li>
                <li><b>目的:</b> 自动执行依赖于先前计算结果的多步骤分析流程。</li>
            </ul>

            <h4><span class="new-feature">定义格式</span></h4>
            <p>使用特殊的注释行来分隔不同类型的计算块。<b>执行将严格按照从上到下的顺序进行。</b> 每个块内部的定义也会被自动排序。</p>
            <ul>
                <li><b><code>#--- PER-FRAME ---#</code></b>: 在此标记下的所有定义都将作为<b>逐帧派生变量</b>进行计算。</li>
                <li><b><code>#--- TIME-AGGREGATED ---#</code></b>: 在此标记下的所有定义都将作为<b>时间聚合变量</b>进行计算。</li>
            </ul>
            <div class="code-block"># 这是一个计算雷诺分解的复杂示例

#--- PER-FRAME ---#
# 第一步：计算每个点的瞬时速度大小
velocity_magnitude = sqrt(u**2 + v**2)

#--- TIME-AGGREGATED ---#
# 第二步：计算整个时间序列上的平均速度大小
# 注意：这里的 velocity_magnitude 是上一步刚刚创建的
avg_velocity_magnitude = mean(velocity_magnitude)

#--- PER-FRAME ---#
# 第三步：计算每个点的速度脉动量
# 注意：这里的 avg_velocity_magnitude 是第二步创建的，它是一个不随时间变化的场
velocity_fluctuation = velocity_magnitude - avg_velocity_magnitude
</div>
             <div class="warning">
                <p><b>工作流程:</b></p>
                <ol>
                    <li>InterVis 将首先执行第一个 <code>#--- PER-FRAME ---#</code> 块。</li>
                    <li>完成后，它会更新数据库和变量列表。新变量 <code>velocity_magnitude</code> 现在可用了。</li>
                    <li>然后，它会执行 <code>#--- TIME-AGGREGATED ---#</code> 块，此时它可以访问 <code>velocity_magnitude</code>。</li>
                    <li>完成后，再次更新状态。新变量 <code>avg_velocity_magnitude</code> 现在可用了。</li>
                    <li>最后，它执行第三个块，完成整个计算链。</li>
                </ol>
                <p>这种顺序执行的能力避免了手动分步计算，极大地提高了复杂分析的效率。</p>
            </div>
        </div>

        <!-- ==================== 全局常量 ==================== -->
        <div class="section-box">
            <h3>4. 全局常量 (Global Constants)</h3>
            <p>
                此功能用于计算代表<b>整个数据集</b>（跨越所有时间、所有空间点）特征的<b>单个标量值</b>。
            </p>
            
            <h4>核心思想与用途</h4>
            <ul>
                <li><b>计算基础:</b> <b>所有</b>空间点 (x, y) 在<b>所有</b>时刻 t 的值的集合。</li>
                <li><b>目的:</b> 计算一个能代表整个仿真过程的<b>单一数字</b>，用于后续的公式计算或图表标题。</li>
            </ul>

            <h4><span class="new-feature">定义格式 (支持批量和自动排序)</span></h4>
            <p>与上面类似，每行一个定义，并支持自动依赖排序。</p>
            <div class="code-block"># 计算全局平均湍动能
tke_global_mean = mean(0.5 * rho * (u**2 + v**2))
# 计算基于上面结果的某个特征长度
# (假设 length_scale 是一个已知的原始变量)
some_reynolds_number = u_global_mean * length_scale / nu
</div>
        </div>
        
        <div class="warning">
            <p>
                <b>总结与区分:</b>
                <ul>
                    <li><b>1. 逐帧派生变量:</b> <code>f(point, time) -> value(point, time)</code>。结果随时间和空间变化。</li>
                    <li><b>2. 时间聚合变量:</b> <code>f(point, all_times) -> value(point)</code>。结果只随空间变化，不随时间变化。</li>
                    <li><b>3. 组合批量计算:</b> 混合以上两种模式，按顺序执行。</li>
                    <li><b>4. 全局常量:</b> <code>f(all_points, all_times) -> single_value</code>。结果是一个不随任何因素变化的标量。</li>
                </ul>
            </p>
        </div>
    </body>
    </html>
    """

def get_axis_title_help_html() -> str:
    """为“坐标轴与标题”部分生成帮助HTML内容。"""
    return """
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; }}
            h2 {{ color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; margin-top: 25px; }}
            code {{
                background-color: #f0f0f0;
                padding: 3px 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: "Courier New", Courier, monospace;
                font-size: 0.95em;
            }}
            ul {{ list-style-type: disc; padding-left: 20px; }}
            li {{ margin-bottom: 8px; }}
            .note {{
                border-left: 4px solid #17a2b8; /* Info blue */
                padding: 10px 15px;
                background-color: #e2f3f5;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }}
            .example-box {{
                background-color: #f9f9f9;
                border: 1px solid #eee;
                padding: 15px;
                margin-top: 10px;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <h2>坐标轴与标题指南</h2>
        <p>此部分允许您完全自定义图表的外观，包括坐标轴的定义和图表的动态标题。</p>

        <h3>X轴与Y轴公式</h3>
        <p>
            这里定义的公式决定了数据点在图表上的<b>空间位置</b>。
            您可以使用任何数据变量和全局常量来创建非标准的坐标系。
        </p>
        <ul>
            <li><b>默认值:</b> <code>x</code> 和 <code>y</code>，直接使用数据中的坐标。</li>
            <li><b>平移坐标系:</b> <code>x - x_global_mean</code> (将视图中心移至平均x位置)。</li>
            <li><b>使用物理量作为坐标:</b>
                <ul>
                    <li>X轴: <code>x</code> (空间位置)</li>
                    <li>Y轴: <code>p</code> (压力)</li>
                    <li>这将绘制出压力沿X轴的分布，对于分析边界层等非常有用。</li>
                </ul>
            </li>
            <li><b>无量纲化:</b> 假设您已在“数据处理”中计算了 <code>domain_length</code> 常量。
                <ul>
                    <li>X轴: <code>x / domain_length</code></li>
                </ul>
            </li>
        </ul>

        <h3>图表标题</h3>
        <p>
            标题可以是静态文本，也可以通过 <code>{{...}}</code> 占位符语法包含动态信息，
            使您的图表和视频更具信息量。
        </p>
        <div class="note">
            <p><b>语法提示:</b> 请直接使用大括号 <code>{{}}</code>，不要在字符串前加 'f' (这不是Python的f-string)。</p>
        </div>
        
        <h4>可用占位符</h4>
        <ul>
            <li>
                <code>{{frame_index}}</code>: 当前帧的<b>索引</b> (从0开始)。
            </li>
            <li>
                <code>{{time}}</code>: 当前帧的<b>时间戳</b>。这个值由主窗口下方“播放控制”面板中选择的“时间轴变量”决定。
            </li>
            <li>
                <code>{{any_global_constant}}</code>: 您可以在标题中引用<b>任何已计算的全局常量</b>！
            </li>
        </ul>
        
        <h4>格式化</h4>
        <p>您可以在占位符中像Python f-string一样使用格式说明符：</p>
        <ul>
            <li><code>{{time:.3f}}</code>: 将时间戳显示为三位小数的浮点数 (例如: <code>1.234</code>)。</li>
            <li><code>{{time:.4e}}</code>: 将时间戳显示为四位小数的科学计数法 (例如: <code>1.2340e-03</code>)。</li>
        </ul>

        <div class="example-box">
            <h4>标题示例</h4>
            <p><b>简单示例:</b></p>
            <code>Frame: {{frame_index}}, Time: {{time:.4f}}s</code>
            <hr>
            <p><b>高级示例 (包含全局常量):</b></p>
            <code>Simulation at t={{time:.2e}}s, Global TKE = {{tke_global_mean:.3f}}</code>
        </div>
    </body>
    </html>
    """

def get_analysis_help_html() -> str:
    """生成“分析”、“数据管理”和“可视化”中高级功能的统一帮助HTML内容。"""
    return """
    <html>
    <head>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; }
            h2 { color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; margin-top: 25px; }
            h3 { color: #5bc0de; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 20px; }
            code {
                background-color: #f0f0f0;
                padding: 3px 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: "Courier New", Courier, monospace;
                font-size: 0.95em;
            }
            ul, ol { padding-left: 25px; }
            li { margin-bottom: 8px; }
            .note {
                border-left: 4px solid #f0ad4e; /* Warning yellow */
                padding: 10px 15px;
                background-color: #fcf8e3;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }
            .success {
                border-left: 4px solid #28a745; /* Success green */
                padding: 10px 15px;
                background-color: #eaf6ec;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }
            .new-feature {
                color: #007bff; /* Primary blue */
                font-weight: bold;
            }
            .section-box {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 20px;
                margin-top: 25px;
                background-color: #f9f9f9;
            }
        </style>
    </head>
    <body>
        <h2>分析与数据管理高级指南</h2>
        <p>本页整合了多个选项卡中的高级功能，它们共同构成了 InterVis 强大的分析能力。</p>

        <!-- ==================== 全局过滤器 ==================== -->
        <div class="section-box">
            <h3><span class="new-feature">全局数据过滤器</span> (位于“数据管理”选项卡)</h3>
            <p>
                这是一个极其强大的功能，允许您对<b>整个数据集</b>应用一个筛选条件。
            </p>
            <ul>
                <li><b>语法:</b> 使用标准的 <b>SQL <code>WHERE</code> 子句</b> 语法。</li>
                <li><b><span class="new-feature">辅助构建器:</span></b> 点击 "构建..." 按钮，可以使用可视化界面来添加条件。</li>
                <li><b>用途:</b>
                    <ul>
                        <li><b>区域分析:</b> 只分析某个几何区域，例如 <code>x > 0.5 AND y < 0.2</code>。</li>
                        <li><b>现象隔离:</b> 只分析高压区 (<code>p > 101325</code>)。</li>
                    </ul>
                </li>
            </ul>
            <div class="note">
                <h4><span class="new-feature">关于Zarr后端的重要说明</span></h4>
                <p>
                    随着后端升级到高性能的Zarr格式，全局过滤器的实现正在进行重构。在当前版本中：
                    <ul>
                        <li>过滤器<b>可以</b>被设置，并将成功应用于“<b>数据导出</b>”功能。</li>
                        <li>过滤器<b>暂不</b>应用于实时可视化或“数据处理”中的计算任务。此功能将在未来的更新中通过更高效的方式（如Dask集成）实现。</li>
                    </ul>
                    感谢您的理解！
                </p>
            </div>
        </div>

        <!-- ... (Rest of the analysis help content remains the same) ... -->
        
        <div class="section-box">
            <h3><span class="new-feature">数据导出</span> (位于“数据管理”选项卡)</h3>
            <p>
                此功能允许您将当前数据集（可选择应用全局过滤器）导出为文件，并提供了高度的灵活性。
            </p>
            <h4>操作步骤:</h4>
            <ol>
                <li>点击“数据管理”选项卡下的“<b>导出数据...</b>”按钮。</li>
                <li>
                    <b>选择变量:</b> 一个新对话框会弹出，列出所有可用的数据变量。您可以按住 <code>Ctrl</code> 或 <code>Shift</code> 键选择您想要导出的一个或多个变量列。
                </li>
                <li>
                    <b>选择格式:</b> 点击“OK”后，会弹出文件保存对话框。您可以在此处指定文件名，并从下拉菜单中选择文件类型：
                    <ul>
                        <li><code>.csv</code>: 传统的逗号分隔值文本文件，通用性好。</li>
                        <li><code>.parquet</code>: 高性能的列式二进制文件格式。对于大型数据集，它通常比CSV文件<b>更小</b>且读写<b>更快</b>。推荐在进行后续数据分析时使用此格式。</li>
                    </ul>
                </li>
                <li>导出过程将在后台进行，并有进度条显示。</li>
            </ol>
            <div class="success">
                <p><b>最佳实践:</b> 当您需要将数据导入其他分析工具（如Python Pandas, R, MATLAB）时，优先选择 <b>Parquet</b> 格式可以大大提高效率。</p>
            </div>
        </div>
        
        <div class="section-box">
            <h3><span class="new-feature">时间分析模式</span> (位于“可视化”选项卡)</h3>
            <p>此功能允许您在两种核心可视化模式间切换：</p>
            <ul>
                <li>
                    <b>瞬时场 (Instantaneous Field):</b>
                    默认模式，显示单个时间步（帧）的数据。
                </li>
                <li>
                    <b>时间平均场 (Time-Averaged Field):</b>
                    计算并显示一个指定时间范围（从起始帧到结束帧）内所有数据点的<b>算术平均值</b>。
                </li>
            </ul>
        </div>

        <div class="section-box">
            <h3><span class="new-feature">时间轴变量</span> (位于主窗口下方“播放控制”面板)</h3>
            <p>此功能允许您指定数据中的<b>哪一列</b>作为时间演化的依据。</p>
            <ul>
                <li><b>默认值:</b> <code>frame_index</code> (文件导入的顺序)。</li>
                <li><b>选择:</b> 您可以从下拉菜单中选择<b>任何数值型变量</b>。</li>
                <li><b>影响范围:</b> 播放控制、时间序列图的X轴、图表标题中的<code>{{time}}</code>占位符。</li>
            </ul>
        </div>

        <h2>交互式分析工具</h2>

        <div class="section-box">
            <h3>数据探针 (Data Probe)</h3>
            <p>当您在图表上移动鼠标时，“数据探针”窗口会实时显示原始数据和插值后的可视化数据。</p>
            <ul>
                <li><b><span class="new-feature">按坐标查询:</span></b>
                    点击“<b>按坐标查询...</b>”按钮，可以输入精确坐标来更新探针。
                </li>
            </ul>
        </div>

        <div class="section-box">
            <h3>一维剖面图 (1D Profile Plot)</h3>
            <p>在2D图上画一条直线，并立即查看各个物理量如何沿着这条线变化。</p>
        </div>

        <div class="section-box">
            <h3>时间序列分析 (Time Series Analysis)</h3>
            <p>查看图上某一个固定点上的物理量随时间的变化情况，并进行频域分析 (FFT)。</p>
        </div>
    </body>
    </html>
    """

def get_template_help_html() -> str:
    """生成可视化模板帮助的HTML内容。"""
    return """
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; }}
            h2 {{ color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 5px; margin-top: 25px; }}
            h3 {{ color: #28a745; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 20px; }}
            code {{
                background-color: #f0f0f0;
                padding: 3px 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: "Courier New", Courier, monospace;
                font-size: 0.95em;
            }}
            ul, ol {{ padding-left: 25px; }}
            li {{ margin-bottom: 8px; }}
            .note {{
                border-left: 4px solid #17a2b8; /* Info blue */
                padding: 10px 15px;
                background-color: #e2f3f5;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <h2>可视化模板指南</h2>
        <p>
            <b>可视化模板</b>是一个强大的效率工具，它能让您一键<b>保存和加载一整套完整的可视化方案</b>。
            这对于需要频繁切换不同分析视角或进行重复性工作的用户来说，可以极大地节省时间。
        </p>
        
        <h3>模板是什么？</h3>
        <p>一个模板本质上是您在“可视化”选项卡中所有设置的一个<b>快照</b>。它记录了“画什么”和“怎么画（数据层面）”的所有信息，包括：</p>
        <ul>
            <li>时间分析模式 (瞬时场 / 时间平均场) 及其参数。</li>
            <li>坐标轴 (X/Y) 和图表标题的公式。</li>
            <li><b>热力图</b>的所有设置 (是否启用, 公式, 颜色映射, 颜色范围)。</li>
            <li><b>等高线图</b>的所有设置 (是否启用, 公式, 线条数量, 颜色, 宽度, 是否显示标签)。</li>
            <li><b>矢量/流线图</b>的所有设置 (是否启用, 公式, 绘图类型, 以及各自的详细选项如密度、缩放、颜色等)。</li>
        </ul>
        <div class="note">
            <p>
                <b>模板 vs. 设置文件 vs. 主题</b>
                <ul>
                    <li><b>模板:</b> 专注于<b>“看”</b>什么。只保存“可视化”选项卡的内容。</li>
                    <li><b>设置文件 (来自“导出与性能”):</b> 保存<b>所有选项卡</b>的几乎所有设置，是一个完整的项目状态复现文件。</li>
                    <li><b>主题:</b> 专注于图表的<b>“美学”</b>，如颜色、字体等，与显示的数据内容无关。</li>
                </ul>
            </p>
        </div>

        <h3>如何使用？</h3>
        <h4>加载模板</h4>
        <ol>
            <li>从“可视化模板”下拉菜单中选择一个您想要的模板。</li>
            <li>点击旁边的“<b>加载</b>”按钮。</li>
            <li>当前“可视化”选项卡的所有设置将立即被模板中的设置所覆盖，图表也会自动刷新以应用新方案。</li>
        </ol>
        
        <h4>保存新模板</h4>
        <ol>
            <li>首先，在“可视化”选项卡中，精心调整好您想要保存的各项设置。</li>
            <li>点击“<b>另存为...</b>”按钮。</li>
            <li>在弹出的对话框中为您的新模板输入一个描述性的名称（例如 `vorticity_and_pressure_contours`），然后点击OK。</li>
            <li>您的模板现在就被保存下来了，并会出现在下拉菜单中，供将来一键调用。</li>
        </ol>

        <h3>应用场景示例</h3>
        <ul>
            <li>
                <b>场景一: 标准流程</b><br>
                您经常需要首先查看速度云图 (热力图)，然后查看压力等值线 (等高线图)。
                您可以将这套配置保存为“速度与压力”模板，以后每次分析新数据时，只需一键加载即可。
            </li>
            <li>
                <b>场景二: 对比分析</b><br>
                您想对比“涡量场”和“散度场”的特征。您可以分别创建两个模板，一个用于显示涡量，另一个用于显示散度。
                然后您可以在这两个模板之间快速切换，以在同一数据集上进行对比分析。
            </li>
            <li>
                <b>场景三: 复杂方案存档</b><br>
                您配置了一个非常复杂的可视化方案，例如：背景是温度热力图，前景是压力等高线，上面再叠加马赫数等于1的特殊等高线，并附带速度脉动矢量图。
                您可以将这个复杂的组合保存为一个模板，以便日后复现或分享给同事。
            </li>
        </ul>
    </body>
    </html>
    """

def get_theme_help_html() -> str:
    """生成绘图主题帮助的HTML内容。"""
    return """
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; }}
            h2 {{ color: #6f42c1; border-bottom: 2px solid #6f42c1; padding-bottom: 5px; margin-top: 25px; }}
            h3 {{ color: #6f42c1; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 20px; }}
            code {{
                background-color: #f0f0f0;
                padding: 3px 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: "Courier New", Courier, monospace;
                font-size: 0.95em;
            }}
            ul, ol {{ padding-left: 25px; }}
            li {{ margin-bottom: 8px; }}
            .note {{
                border-left: 4px solid #ffc107; /* Warning yellow */
                padding: 10px 15px;
                background-color: #fff9e2;
                margin-top: 15px;
                margin-bottom: 15px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <h2>绘图主题指南</h2>
        <p>
            <b>绘图主题</b>功能专注于图表的<b>美学风格</b>，让您能够轻松地改变图表的外观，
            以适应不同的展示需求，例如学术论文（通常需要黑白、清晰的风格）、PPT演示（可能需要深色背景）或个人偏好。
        </p>

        <h3>主题是什么？</h3>
        <p>主题是图表视觉元素（如颜色、字体、线条样式等）的一组预设集合。它与“可视化模板”有本质区别：</p>
        <ul>
            <li><b>主题</b>控制“<b>怎么画</b>”（外观风格，Look and Feel）。</li>
            <li><b>模板</b>控制“<b>画什么</b>”（数据内容与公式）。</li>
        </ul>
        <p>一个主题主要保存以下类型的设置：</p>
        <ul>
            <li>坐标轴、刻度和网格的颜色与线型</li>
            <li>图表和坐标轴的背景颜色</li>
            <li>所有文本（标题、标签）的字体系列、大小和颜色</li>
            <li>默认的线条颜色和样式 (例如，用于剖面图)</li>
        </ul>
        <div class="note">
            <p><b>重要:</b> 主题是一个<b>全局设置</b>。应用一个新主题后，当前主图表和所有后续绘制的图表
            （包括弹出的剖面图、时间序列图等）都会<b>立即采用</b>新的风格。</p>
        </div>
        
        <h3>如何使用？</h3>
        <h4>应用主题</h4>
        <ol>
            <li>从“绘图主题”下拉菜单中选择一个主题（例如 <code>dark_mode.json</code> 或 <code>paper_bw.json</code>）。</li>
            <li>点击“<b>应用</b>”按钮。</li>
            <li>图表将立即使用新的风格重新绘制。</li>
        </ol>

        <h4>保存自定义主题</h4>
        <p>您可以通过编辑JSON文件来创建自己的主题，实现高度定制化：</p>
        <ol>
            <li>
                在您的InterVis安装目录中，找到 <code>settings/themes/</code> 文件夹。
            </li>
            <li>
                复制一个现有的主题文件（例如 <code>default.json</code>）并重命名为您想要的名字（例如 <code>my_custom_theme.json</code>）。
            </li>
            <li>
                用任何文本编辑器打开这个新的JSON文件。
            </li>
            <li>
                文件内容是Matplotlib的 <code>rcParams</code> 键值对。您可以修改其中的值，
                例如将 <code>axes.facecolor</code> 改为您喜欢的颜色代码，或者更改 <code>font.size</code>。
                关于所有可用的参数，请参考Matplotlib的官方文档。
            </li>
            <li>
                保存文件后，重启InterVis，您的新主题就会自动出现在下拉菜单中。
            </li>
        </ol>
        <p>
            您也可以点击“<b>另存为...</b>”按钮，它会将当前正在使用的Matplotlib样式参数保存为一个新的主题文件，
            您可以基于此文件进行修改，这是一个快速创建自定义主题的起点。
        </p>
        
    </body>
    </html>
    """