#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帮助文档内容模块
"""
from typing import List, Dict

# ... [保留 get_formula_help_html, get_custom_stats_help_html, get_axis_title_help_html, get_analysis_help_html 的完整代码]

def get_formula_help_html(base_variables: List[str], custom_global_variables: Dict[str, float], science_constants: Dict[str, float]) -> str:
    """生成公式帮助的HTML内容"""
    var_list_html = "".join([f"<li><code>{var}</code></li>" for var in sorted(list(base_variables))])
    const_list_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in science_constants.items()])
    
    all_globals = sorted(custom_global_variables.items())
    custom_globals_html = "".join([f"<li><code>{key}</code>: {val:.4e}</li>" for key, val in all_globals])

    global_section = ""
    if custom_globals_html:
        global_section += f"""
        <h3>全局变量与常量</h3>
        <p>这些是在“全局统计”标签页中自动计算或由用户定义的常量，它们在所有计算中可用:</p>
        <ul>{custom_globals_html}</ul>
        """

    return f"""
    <html><head><style>
        body {{ font-family: sans-serif; line-height: 1.6; }}
        h2 {{ color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; }}
        h3 {{ color: #005A9C; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
        code {{ background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }}
        ul {{ list-style-type: none; padding-left: 0; }} li {{ margin-bottom: 5px; }}
        .note {{ border-left: 3px solid #17a2b8; padding-left: 15px; background-color: #e2f3f5; margin-top:10px; }}
        .new {{ color: red; font-weight: bold; }}
    </style></head><body>
        <h2>公式语法说明</h2><p>您可以使用标准的Python数学表达式来创建新的派生变量或进行可视化。</p>
        
        <h3>可用变量与常量</h3>
        <h4>数据变量 (逐点变化)</h4>
        <p>以下变量来自您的数据，代表每个数据点的属性:</p>
        <ul>{var_list_html or "<li>(无可用数据)</li>"}</ul>
        {global_section or "<h4>全局变量与常量</h4><p>(请先在“全局统计”标签页中进行计算)</p>"}
        <h4>科学常量</h4><ul>{const_list_html}</ul>

        <h3>函数列表</h3>
        <h4>标准数学函数</h4>
        <ul>
            <li><b>基本运算符:</b> <code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>**</code> (乘方), <code>()</code></li>
            <li><b>通用函数:</b> <code>sin</code>, <code>cos</code>, <code>sqrt</code>, <code>log</code>, <code>abs</code>, <code>min(a,b)</code>, <code>max(a,b)</code> 等。</li>
        </ul>

        <h4><span class="new">逐帧</span>聚合函数 (对当前帧所有点计算)</h4>
        <div class="note"><p>这些函数在“逐帧计算”或可视化公式中使用，对当前显示帧的数据进行聚合。</p></div>
        <ul>
            <li><code>mean(expr)</code>, <code>sum(expr)</code>, <code>std(expr)</code>, <code>var(expr)</code>, <code>median(expr)</code></li>
            <li><code>min_frame(expr)</code>, <code>max_frame(expr)</code> (为避免与`min/max`数学函数冲突)</li>
        </ul>

        <h4>空间运算/矩阵函数 (对网格化场计算)</h4>
        <div class="note">
            <p>这些函数对插值到网格上的<b>空间场</b>进行操作，用于计算导数等。它们可以<b>相互嵌套</b>。</p>
        </div>
        <ul>
            <li><code>grad_x(field)</code>: 计算标量场 <code>field</code> 的X方向梯度 (∂/dx)。</li>
            <li><code>grad_y(field)</code>: 计算标量场 <code>field</code> 的Y方向梯度 (∂/dy)。</li>
            <li><code>div(u_field, v_field)</code>: 计算矢量场 <code>(u, v)</code> 的散度 (∂u/∂x + ∂v/∂y)。</li>
            <li><code>curl(u_field, v_field)</code>: 计算2D矢量场 <code>(u, v)</code> 的旋度 (∂v/∂x - ∂u/∂y)，结果为标量。</li>
            <li><code>laplacian(field)</code>: 计算标量场 <code>field</code> 的拉普拉斯算子 (∂²/∂x² + ∂²/∂y²)。</li>
        </ul>

        <h3>示例</h3>
        <ul>
            <li><b>速度大小 (热力图):</b> <code>sqrt(u**2 + v**2)</code></li>
            <li><b>动压 (等高线):</b> <code>0.5 * rho * (u**2 + v**2)</code></li>
            <li><b>压力波动 (帧内):</b> <code>p - mean(p)</code></li>
            <li><b>速度脉动 (矢量图U分量):</b> <code>u - u_global_mean</code></li>
            <li><b>涡量 (热力图):</b> <code>curl(u, v)</code></li>
            <li><b>压力梯度X分量 (热力图):</b> <code>grad_x(p)</code></li>
            <li><b>嵌套示例 (复杂):</b> <code>grad_x(curl(rho*u, rho*v))</code></li>
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
        .note { border-left: 3px solid #f0ad4e; padding-left: 15px; background-color: #fcf8e3; margin-top:10px; }
        .new { color: red; font-weight: bold; }
    </style></head><body>
        <h2>自定义常量计算指南</h2>
        <p>此功能允许您基于<b>整个数据集</b>计算新的<b>全局常量</b>。这些定义会<span class="new">永久保存在数据库中</span>，并可在所有可视化公式中使用。</p>

        <h3>基本格式</h3>
        <p>每行定义一个常量: <code>new_constant_name = aggregate_function(expression)</code></p>

        <h3>计算模式</h3>
        <p>引擎会自动选择最高效的计算路径：</p>
        <ul>
            <li><b>标准公式 (无空间运算):</b> 使用<b>超快SQL查询</b>在数据库中直接完成。</li>
            <li><b>含空间运算的公式 (如 <code>curl</code>, <code>grad_x</code>等):</b> 自动切换到<span class="new">并行的逐帧迭代</span>模式。这会充分利用您的CPU多核性能，但仍可能需要一些时间。</li>
        </ul>

        <h3>组件说明</h3>
        <ul>
            <li><b><code>new_constant_name</code></b>: 新常量的名称 (字母、数字、下划线)。</li>
            <li><b><code>aggregate_function</code></b>: 聚合函数，对所有帧或所有点生效。支持 <code>mean</code>, <code>sum</code>, <code>std</code>, <code>var</code>。</li>
            <li><b><code>expression</code></b>: 数学表达式，支持:
                <ul>
                    <li>原始数据变量 (如 <code>u</code>, <code>p</code>)。</li>
                    <li>任何已计算的全局常量 (包括之前定义的)。</li>
                    <li>标准数学函数 (<code>sqrt</code>, <code>sin</code>等)。</li>
                    <li>新增的空间函数 (<code>grad_x</code>, <code>div</code>, <code>curl</code> 等)。</li>
                </ul>
            </li>
        </ul>

        <h3>工作流程</h3>
        <ol>
            <li>在文本框中添加或编辑您的定义。</li>
            <li>点击“<b>保存定义并重新计算</b>”按钮。</li>
            <li>您的定义会被保存到数据库，然后程序会开始计算。</li>
            <li>计算完成后，新的常量即可在任何地方使用。</li>
        </ol>

        <h3>示例</h3>
        <h4>1. 计算平均湍动能 (TKE) - <span style="color:green;">快速SQL模式</span></h4>
        <code>tke_global_mean = mean(0.5 * (u**2 + v**2))</code>

        <h4>2. 计算雷诺应力 - <span style="color:green;">快速SQL模式</span></h4>
        <code>reynolds_stress_uv = mean((u - u_global_mean) * (v - v_global_mean))</code>

        <h4>3. <span class="new">计算全场平均涡量 - 并行迭代模式</span></h4>
        <div class="note">
            <p>因为包含 <code>curl()</code>，此计算会并行地遍历所有帧，对每一帧计算涡量场，然后取所有帧涡量均值的均值。</p>
        </div>
        <code>mean_vorticity = mean(curl(u, v))</code>
    </body></html>
    """

def get_axis_title_help_html() -> str:
    return """
    <html><head><style>
        body { font-family: sans-serif; line-height: 1.6; }
        h2 { color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; }
        code { background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }
        ul { list-style-type: disc; padding-left: 20px; }
        .note {{ border-left: 3px solid #17a2b8; padding-left: 15px; background-color: #e2f3f5; margin-top:10px; }}
    </style></head><body>
        <h2>坐标轴与标题指南</h2>
        <ul>
            <li><b>X轴与Y轴公式:</b> 定义数据点在图表上的坐标。可使用任何数据变量和全局常量，如 <code>x</code>, <code>rho*u</code>, <code>x-x_global_mean</code>。</li>
            <li><b>图表标题:</b>
                <p>可以是静态文本，或使用 <code>{...}</code> 占位符语法包含动态信息。</p>
                <div class="note">
                    <p><b>注意:</b> 请不要使用Python的f-string (即不要在字符串前加'f')，直接使用大括号即可。</p>
                </div>
                <p>可用占位符:</p>
                <ul>
                    <li><code>{frame_index}</code> - 当前帧的索引。</li>
                    <li><code>{time}</code> - 当前帧的时间戳。您可以进行格式化，例如 <code>{time:.3f}</code> 会将时间戳显示为三位小数。</li>
                </ul>
                <p><b>示例:</b> <code>Frame: {frame_index}, Time: {time:.4f}s</code></p>
            </li>
        </ul>
    </body></html>
    """

def get_analysis_help_html() -> str:
    """生成“分析”选项卡功能的帮助HTML内容"""
    return """
    <html><head><style>
        body { font-family: sans-serif; line-height: 1.6; }
        h2 { color: #005A9C; border-bottom: 2px solid #005A9C; padding-bottom: 5px; }
        h3 { color: #28a745; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
        code { background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }
        ul { list-style-type: circle; padding-left: 20px; }
        .note { border-left: 3px solid #ffc107; padding-left: 15px; background-color: #fff9e2; margin-top:10px; }
        .new { color: #007bff; font-weight: bold; }
    </style></head><body>
        <h2>分析与数据管理指南</h2>
        <p>本页包含“分析”、“数据管理”和“可视化”中高级功能的说明。</p>

        <h3><span class="new">全局数据过滤器</span> (位于“数据管理”选项卡)</h3>
        <p>此功能允许您对<b>整个数据集</b>应用一个筛选条件，所有后续的可视化、统计计算和导出都将只考虑满足条件的数据点。</p>
        <ul>
            <li><b>语法:</b> 使用标准的 <b>SQL `WHERE` 子句</b> 语法 (不需要写 "WHERE" 关键字)。</li>
            <li><b>变量:</b> 您可以使用数据库中的任何原始或派生变量名。</li>
            <li><b>示例:</b>
                <ul>
                    <li><code>p > 101325</code> (只分析压力高于一个大气压的区域)</li>
                    <li><code>sqrt(u*u + v*v) > 100</code> (只分析高速区域)</li>
                    <li><code>x < 0.5 AND y > 0.2</code> (只分析某个几何区域)</li>
                </ul>
            </li>
        </ul>
        <div class="note">
            <p><b>重要:</b> 应用或更改过滤器后，建议点击主工具栏的“重置视图”按钮，以确保您看到的是过滤后数据的完整视图。</p>
        </div>

        <h3><span class="new">时间分析</span> (位于“可视化”选项卡)</h3>
        <p>此功能允许您在两种模式间切换：</p>
        <ul>
            <li><b>瞬时场:</b> 默认模式，显示单个时间步（帧）的数据。</li>
            <li><b>时间平均场:</b> 计算并显示一个指定时间范围（从起始帧到结束帧）内所有数据点的<b>平均值</b>。这对于观察稳态特征、消除瞬时波动非常有用。</li>
        </ul>

        <h2 style="margin-top:20px;">交互式分析工具</h2>

        <h3>数据探针</h3>
        <p>当您在图表上移动鼠标时，“数据探针”窗口会实时显示两种信息：</p>
        <ul>
            <li><b>最近原始数据点:</b> 离您鼠标最近的原始数据文件中那个点的值。</li>
            <li><b>鼠标位置插值数据:</b> 根据周围数据点插值计算出的、您鼠标精确位置上的值。这对于查看平滑的热力图和等高线图的精确数值非常有用。</li>
        </ul>

        <h3>一维剖面图</h3>
        <p>此功能允许您在2D图上画一条线，并查看变量如何沿着这条线变化。</p>
        <ol>
            <li>点击“<b>绘制剖面图</b>”按钮，鼠标将变为十字形。</li>
            <li>在图表上<b>第一次点击</b>，定义剖面线的<b>起点</b>。</li>
            <li>移动鼠标，您会看到一条预览线。<b>第二次点击</b>，定义剖面线的<b>终点</b>。</li>
            <li>一个新窗口会弹出，显示主热力图变量沿着这条线的数值分布图。</li>
        </ol>

        <h3>时间序列分析</h3>
        <p>此功能用于查看图上某一个固定点，其物理量随时间的变化情况。</p>
        <ol>
            <li>点击“<b>拾取时间序列点</b>”按钮，或点击“<b>按坐标拾取...</b>”按钮并输入精确坐标。</li>
            <li>一个新窗口会弹出。您可以在此窗口的下拉菜单中选择不同的变量，查看它们在该点的时间序列图。</li>
            <li>点击“<b>计算FFT</b>”按钮，可以对当前的时间序列进行快速傅里叶变换，分析其频域特性。</li>
        </ol>
    </body></html>
    """

def get_template_help_html() -> str:
    """生成可视化模板帮助的HTML内容"""
    return """
    <html><head><style>
        body { font-family: sans-serif; line-height: 1.6; }
        h2 { color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 5px; }
        h3 { color: #28a745; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
        code { background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }
        ul { list-style-type: circle; padding-left: 20px; }
        .note { border-left: 3px solid #17a2b8; padding-left: 15px; background-color: #e2f3f5; margin-top:10px; }
    </style></head><body>
        <h2>可视化模板指南</h2>
        <p><b>可视化模板</b>是一个强大的功能，它能让您一键保存和加载<b>一整套完整的可视化方案</b>。这对于重复性工作和快速切换分析视角非常有用。</p>
        
        <h3>模板是什么？</h3>
        <p>一个模板本质上是您在“可视化”选项卡中所有设置的一个快照，它包括：</p>
        <ul>
            <li>时间分析模式 (瞬时场/时间平均场)</li>
            <li>坐标轴与标题的公式</li>
            <li>热力图的所有设置 (启用状态, 公式, 颜色映射, 范围)</li>
            <li>等高线图的所有设置 (启用状态, 公式, 线条属性)</li>
            <li>矢量/流线图的所有设置 (启用状态, 公式, 类型, 选项)</li>
        </ul>
        <div class="note">
            <p><b>注意:</b> 模板<b>不包含</b>“导出与性能”或“数据管理”中的设置。它专注于“看”的方面。如需保存包含所有设置的完整配置，请使用“导出与性能”选项卡中的“设置管理”功能。</p>
        </div>

        <h3>如何使用？</h3>
        <h4>加载模板</h4>
        <ol>
            <li>从“可视化模板”下拉菜单中选择一个您想要的模板。</li>
            <li>点击旁边的“<b>加载</b>”按钮。</li>
            <li>当前所有可视化设置将立即被模板中的设置所覆盖，图表也会自动刷新。</li>
        </ol>
        
        <h4>保存新模板</h4>
        <ol>
            <li>首先，按照您的喜好，调整好“可视化”选项卡中的各项设置。</li>
            <li>点击“<b>另存为...</b>”按钮。</li>
            <li>在弹出的对话框中为您的新模板输入一个描述性的名称（如 `vorticity_and_pressure`），然后点击OK。</li>
            <li>您的模板现在就被保存下来了，并会出现在下拉菜单中，供将来使用。</li>
        </ol>

        <h3>应用场景示例</h3>
        <ul>
            <li><b>场景一:</b> 您经常需要查看速度云图和压力等值线。您可以将这套配置保存为“速度与压力”模板，以后只需一键加载即可。</li>
            <li><b>场景二:</b> 您想对比涡量和散度场。您可以分别创建两个模板，然后在它们之间快速切换，进行对比分析。</li>
        </ul>
    </body></html>
    """

def get_theme_help_html() -> str:
    """生成绘图主题帮助的HTML内容"""
    return """
    <html><head><style>
        body { font-family: sans-serif; line-height: 1.6; }
        h2 { color: #6f42c1; border-bottom: 2px solid #6f42c1; padding-bottom: 5px; }
        h3 { color: #6f42c1; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
        code { background-color: #f0f0f0; padding: 2px 5px; border: 1px solid #ddd; border-radius: 3px; font-family: monospace; }
        ul { list-style-type: circle; padding-left: 20px; }
        .note { border-left: 3px solid #ffc107; padding-left: 15px; background-color: #fff9e2; margin-top:10px; }
    </style></head><body>
        <h2>绘图主题指南</h2>
        <p><b>绘图主题</b>功能专注于图表的美学风格，让您能够轻松地改变图表的外观，以适应不同的展示需求，例如学术论文、PPT演示或个人偏好。</p>

        <h3>主题是什么？</h3>
        <p>主题是图表视觉元素（如颜色、字体、线条样式等）的一组集合。它与“可视化模板”不同：</p>
        <ul>
            <li><b>主题</b>控制“怎么画”（外观风格）。</li>
            <li><b>模板</b>控制“画什么”（数据内容与公式）。</li>
        </ul>
        <p>一个主题主要保存以下类型的设置：</p>
        <ul>
            <li>坐标轴、刻度和网格的颜色与线型</li>
            <li>背景颜色</li>
            <li>字体系列、大小和颜色</li>
            <li>默认的线条颜色和样式</li>
        </ul>
        <div class="note">
            <p><b>注意:</b> 主题是一个全局设置。应用一个新主题后，当前图表和所有后续绘制的图表（包括剖面图、时间序列图等）都会使用新的风格。</p>
        </div>
        
        <h3>如何使用？</h3>
        <h4>应用主题</h4>
        <ol>
            <li>从“绘图主题”下拉菜单中选择一个主题（例如 `dark_mode` 或 `paper_bw`）。</li>
            <li>点击“<b>应用</b>”按钮。</li>
            <li>图表将立即使用新的风格重新绘制。</li>
        </ol>

        <h4>保存自定义主题</h4>
        <p>目前，InterVis不提供在UI中直接编辑主题细节的功能。但您可以通过编辑JSON文件来创建自己的主题：</p>
        <ol>
            <li>在 `settings/themes/` 文件夹中，复制一个现有的主题文件（例如 `default.json`）并重命名。</li>
            <li>用文本编辑器打开这个新的JSON文件。</li>
            <li>文件内容是Matplotlib的 `rcParams`。您可以修改其中的值，例如将 `axes.facecolor` 改为您喜欢的颜色。关于可用的参数，请参考Matplotlib的官方文档。</li>
            <li>保存文件后，重启InterVis，您的新主题就会出现在下拉菜单中。</li>
        </ol>
        <p>您也可以点击“<b>另存为...</b>”按钮，它会将当前正在使用的Matplotlib样式参数保存为一个新的主题文件，您可以基于此文件进行修改。</p>
        
    </body></html>
    """