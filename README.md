

# InterVis v3.3-ProFinal (交互式计算与可视分析平台)

[![Python Version](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![UI Framework](https://img.shields.io/badge/UI-PyQt6-brightgreen.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![Version](https://img.shields.io/badge/Version-3.3--ProFinal-blue)](https://github.com/StarsWhere/InterVis)

**English:** An high-performance, interactive platform for visualizing and analyzing time-series scientific data, now powered by a database core and featuring advanced analytical tools.
<br>
**中文:** 一款用于时序性科学计算数据的 **交互式计算** 与可视分析的高性能平台，现已由数据库核心驱动，并配备了高级分析工具。

---

InterVis 专为需要分析、理解并深入挖掘数值模拟（如CFD、物理学）数据的研究人员、工程师和学生而设计。它彻底改变了处理由大量CSV文件组成的时序数据集的方式。

**在 v3.x 版本中，InterVis 从一个“可视化工具”蜕变为一个“交互式计算与分析平台”**，引入了革命性的数据库核心、强大的在线计算能力和一系列专业的分析工具。它不仅能看，更能算、能分析！

![Main Application Interface](png/main_interface.png)
> *InterVis v3.3 主界面，一个强大的交互式计算与可视分析环境。*

## 核心功能 (Key Features)

*   ⚡ **数据库驱动核心 (Database-Driven Core):**
    *   **一键式数据预处理:** 首次加载时，自动将项目目录下的所有CSV文件高效整合到一个可移植的SQLite数据库中。
    *   **性能革命:** 所有后续操作均由高性能的SQL查询驱动，**速度提升10倍以上**，告别文件I/O瓶颈。
    *   **项目化管理:** 以文件夹作为“项目”进行管理，自动处理数据和配置，工作流清晰高效。

*   🚀 **高级计算与公式引擎 (Advanced Computing & Formula Engine):**
    *   **派生变量计算:** 用户可自定义公式，计算新的物理量（如`tke = 0.5 * (u**2+v**2)`），并将其作为 **永久列** 添加到数据库中。
    *   **实时空间运算:** 在公式中直接使用 `grad_x()`, `div()`, `curl()` 等函数，对任意标量或矢量场进行 **实时** 梯度、散度和旋度计算并可视化。
    *   **统一公式接口:** 无论是坐标轴、热力图还是矢量场，都可使用包含聚合、全局常量和空间运算的复杂公式。

*   📊 **多层实时交互可视化 (Multi-Layer Interactive Visualization):**
    *   在完全自定义的坐标系上，流畅地探索 **热力图、等高线图、矢量图和流线图** 的多层叠加。
    *   **自动刷新与视图重置:** 调整任何可视化参数（如颜色映射、公式、线条宽度）后，图表将自动刷新并重置视图，确保所见即所得。
    *   **坐标轴比例控制:** 支持在`'auto'`（自动拉伸）和`'equal'`（等比例）模式间切换，以满足不同的分析需求。
    *   支持交互式缩放、平移和数据探针，深入洞察数据细节。

*   🔬 **专业分析工具集 (Professional Analysis Toolkit):**
    *   **时间分析:** 支持在“瞬时场”和“时间平均场”之间切换，以观察稳态特征。
    *   **一维剖面图:** 通过鼠标或坐标输入在图上定义一条线，并实时查看多个变量沿着该线的分布情况。
    *   **时间序列分析与FFT:** 拾取图上任意一点，查看其物理量随时间的变化，并可一键进行**快速傅里叶变换(FFT)**以分析频域特性。
    *   **全局数据过滤器:** 应用SQL `WHERE`子句对整个数据集进行筛选，所有计算和可视化将只在数据子集上进行。

*   🖼️ **高质量导出与报告 (High-Quality Export & Reporting):**
    *   支持导出高DPI的PNG图表和高分辨率的MP4视频。
    *   **智能导出逻辑:** 在“时间平均场”模式下会自动禁用视频导出功能，批量导出时也会自动跳过此类配置，防止误操作。
    *   **并行批量处理功能**可根据不同的JSON配置文件，自动并发地完成一系列视频的导出任务。

## 功能详解 (Features in Detail)

### 1. 数据库核心与项目工作流
InterVis v3.x 引入了全新的工作流程。您不再是打开单个文件，而是打开一个“项目”。
1.  **选择项目目录:** 通过 `文件 -> 设置项目目录` 选择包含您所有CSV文件的文件夹。
2.  **自动导入:** 如果是首次加载，InterVis会提示您将所有CSV数据导入到一个名为 `_intervis_data.db` 的数据库中。这个过程是全自动的，并且有进度条显示。
3.  **即时加载:** 之后每次打开该项目，InterVis都会直接从数据库加载数据，启动和加载速度极快。

![New Workflow](png/feature_workflow_db.png)
> *首次加载项目时，自动化的数据库导入流程。*

### 2. 派生变量计算与实时空间运算
这是v3.x最强大的功能之一。在“逐帧计算”和“可视化”面板中，您可以永久性地扩展您的数据集或进行即时的高级计算。
*   **创建永久变量:** 在“逐帧计算”标签页中，输入新变量名（如 `tke`）和其SQL兼容的计算公式，程序会高效地将计算结果存入数据库的新列中。
*   **实时场论计算:** 在可视化公式中输入 `curl(u, v)`，即可立即看到流场的涡量分布；输入 `grad_x(p)` 来查看压力梯度。所有这些计算都是在后台实时完成的，无需预处理。

![Live Spatial Calculation](png/feature_compute_spatial.png)
> *直接在热力图公式中使用`curl(u,v)`来实时可视化涡量场。*

### 3. 高级分析工具
InterVis 提供了一套用于深入数据挖掘的工具。
*   **时间平均场:** 在“可视化”标签页中选择“时间平均场”模式，并指定一个帧范围，即可消除瞬时波动，观察稳态特征。
*   **剖面图与时间序列:** 在“分析”标签页中，您可以轻松地拾取点或线，生成对应的时间序列图（含FFT）或一维剖面图，并支持在弹出的窗口中切换不同变量。

![Analysis Tools](png/feature_analysis_tools.png)
> *时间序列分析窗口，包含FFT频谱图。*

## 技术栈 (Technology Stack)

*   **数据后端 (Data Backend):** SQLite
*   **用户界面 (GUI):** PyQt6
*   **绘图引擎 (Plotting Engine):** Matplotlib
*   **数据处理与计算 (Data Handling & Computing):** Pandas, NumPy, SciPy
*   **视频编码 (Video Encoding):** MoviePy (推荐), imageio (备用)
*   **GPU 加速 (GPU Acceleration):** CuPy (可选, 推荐用于 NVIDIA GPU)
*   **并行处理 (Parallel Processing):** Concurrent.futures (用于视频导出和高级统计)

## 安装 (Installation)

1.  **克隆仓库 (Clone the repository):**
    ```bash
    git clone https://github.com/StarsWhere/InterVis.git
    cd InterVis
    ```

2.  **创建虚拟环境 (Create a virtual environment) (推荐):**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

3.  **安装依赖 (Install dependencies):**
    ```bash
    pip install -r requirements.txt
    ```

4.  **(可选) 安装 GPU 支持 (Optional: Install GPU support):**
    如果您有 NVIDIA GPU 和 CUDA 环境，安装 CuPy 可以极大地提升性能。
    > 访问 [CuPy 安装指南](https://docs.cupy.dev/en/stable/install.html) 获取详细指令。

## 使用方法 (Usage)

1.  **准备项目文件夹 (Prepare your project folder):**
    *   创建一个文件夹 (例如 `my_simulation_run`)。
    *   将您的所有 `.csv` 数据文件放入此文件夹。请确保文件按时间顺序命名（例如 `data_001.csv`, `data_002.csv`, ...）。

2.  **运行程序 (Run the application):**
    ```bash
    python main.py
    ```

3.  **推荐分析流程 (Recommended Analysis Workflow):**
    1.  **加载项目:** 使用 `文件 -> 设置项目目录...` 选择您的项目文件夹，并完成首次数据导入。
    2.  **计算全局统计:** 切换到“全局统计”标签页，点击“重新计算所有基础统计”。
    3.  **派生新变量:** 切换到“逐帧计算”标签页，定义并计算您需要分析的关键派生变量。
    4.  **交互式可视化:** 返回“可视化”标签页，使用所有可用变量和函数进行探索。
    5.  **深入分析:** 使用“分析”标签页的工具，或在“全局统计”中定义更复杂的常量进行研究。

## 目录结构 (Directory Structure)

```
InterVis/
├── data/                       # [示例] 用户项目目录 (存放CSV文件)
│   └── ...
├── logs/                       # 程序自动生成的日志文件目录
│   └── InterVis20250629.log
├── output/                     # 程序默认的输出目录 (图片, 视频, 数据)
├── png/                        # [示例] 用于README的图片资源
│   └── main_interface.png
├── settings/                   # 程序自动生成的可视化配置文件目录
│   └── default.json
├── src/                        # 源代码目录
│   ├── core/                   # 核心逻辑与数据处理
│   │   ├── computation_core.py # 空间运算核心
│   │   ├── constants.py        # 全局枚举与常量
│   │   ├── data_manager.py     # 数据库交互与缓存
│   │   ├── formula_engine.py   # 公式解析与验证
│   │   ├── rendering_core.py   # 数据准备与插值
│   │   ├── statistics_calculator.py # 统计SQL生成
│   │   └── workers.py          # 后台工作线程
│   ├── handlers/               # UI事件与业务逻辑处理器
│   │   ├── compute_handler.py  # “逐帧计算”面板逻辑
│   │   ├── config_handler.py   # 配置加载与保存逻辑
│   │   ├── export_handler.py   # 导出功能逻辑
│   │   ├── playback_handler.py # 播放控制逻辑
│   │   └── stats_handler.py    # 统计面板逻辑
│   ├── ui/                     # UI相关模块
│   │   ├── dialogs.py          # 自定义对话框
│   │   ├── profile_plot_dialog.py # 剖面图窗口
│   │   ├── timeseries_dialog.py # 时间序列图窗口
│   │   └── ui_setup.py         # 主窗口UI布局
│   ├── utils/                  # 工具类模块
│   │   ├── gpu_utils.py        # GPU可用性检测
│   │   ├── help_content.py     # 帮助文档内容
│   │   └── logger.py           # 日志系统设置
│   └── visualization/          # 可视化相关模块
│       ├── headless_renderer.py # 无头渲染器 (用于导出)
│       ├── plot_widget.py      # 主绘图控件
│       └── video_exporter.py   # 视频导出器
├── .gitignore                  # Git忽略文件配置
├── main.py                     # 主程序入口
├── README.md                   # 项目说明文档
└── requirements.txt            # Python依赖列表
```

---

## 路线图与未来愿景 (Roadmap & Future Vision)

InterVis v3.3 已经构建了一个强大而稳健的基础。为了使其成为理工科领域不可或缺的桌面级分析工具，我们规划了以下一系列功能新增和优化改进。我们欢迎社区的开发者们参与讨论和贡献，共同实现这一愿景。

---

### **第一优先级：核心体验与易用性增强 (Tier 1: Core Experience & Usability Enhancements)**

这些功能旨在降低上手门槛，提升现有工作流的效率和美观度，让非专业用户也能轻松获得高质量的分析结果。

*   #### **[UI/UX] 可视化模板与“快速设置” (Visualization Templates & "Quick Sets")**
    *   **用户价值:** 当前大量的可视化选项对新用户可能构成挑战。“快速设置”能让用户一键应用常见的可视化方案，极大降低学习成本。
    *   **核心功能点:**
        *   在“可视化”选项卡顶部增加一个下拉菜单，提供预设模板，如：“速度云图与流线”、“压力云图与等压线”、“涡量图”。
        *   选择模板后，自动填充热力图、等高线图、矢量图的公式和样式选项。
        *   允许用户将自己的当前设置保存为新的模板。
    *   **技术实现思路:** 模板本质上就是 `config.json` 文件。此功能只需读取预设的JSON文件并调用 `config_handler.apply_config()` 即可。

*   #### **[UI/UX] 增强的交互模式提示 (Enhanced Interactive Mode Hints)**
    *   **用户价值:** 状态栏的提示不够醒目，用户在进入拾取、剖面图等模式后容易忘记当前状态。
    *   **核心功能点:**
        *   当进入交互模式时，在绘图区域的角落显示一个半透明的、更醒目的浮动提示框（例如，“剖面图模式：请点击定义起点”）。
        *   当模式完成或取消时，提示框自动淡出。
    *   **技术实现思路:** 在`PlotWidget`上叠加一个自定义的`QLabel`，通过控制其可见性和内容来实现。

*   #### **[功能] 绘图美学与论文级导出 (Aesthetics & Publication-Quality Export)**
    *   **用户价值:** 让用户无需借助其他软件，即可直接从InterVis导出可用于学术论文或报告的精美图表。
    *   **核心功能点:**
        *   **颜色条(Colorbar)精细控制:** 在UI上提供输入框，用于修改颜色条的标签、字体大小、刻度格式。
        *   **图例(Legend)支持:** 允许为等高线或矢量图层手动添加和自定义图例。
        *   **绘图主题(Themes):** 提供几个内置的Matplotlib样式主题，如 `ggplot`, `seaborn-paper`, `grayscale` 等，一键切换。
    *   **技术实现思路:** 通过UI控件直接修改Matplotlib `colorbar`和`legend`对象的属性。主题可以通过`plt.style.use()`来实现。

*   #### **[工程] 安装与分发 (Installation & Distribution)**
    *   **用户价值:** 为非Python开发者提供最简单的安装方式，是软件能否被广泛应用的关键。
    *   **核心功能点:**
        *   提供完整的 `requirements.txt` 文件。（已完成）
        *   使用 `PyInstaller` 或 `cx_Freeze` 将应用打包成独立的、无需安装Python环境的可执行文件（`.exe` for Windows, `.app` for macOS）。
    *   **技术实现思路:** 编写打包脚本，处理好依赖项（特别是`MoviePy`和`CuPy`这类复杂库）的打包问题。

---

### **第二优先级：分析能力扩展 (Tier 2: Expanding Analytical Capabilities)**

这些功能将为平台引入全新的分析维度，使其能够解决更广泛、更深入的科学问题。

*   #### **[功能] 多视图/对比视图模式 (Multi-View / Comparison Mode)**
    *   **用户价值:** 直观地对比不同时刻、不同变量或不同过滤条件下的数据，是进行深入分析的常用手段。
    *   **核心功能点:**
        *   允许用户将主绘图区分割为两个或多个并排/堆叠的子视图。
        *   提供视图同步选项：同步时间轴、同步相机（缩放/平移）、或完全独立。
        *   每个子视图可以加载不同的可视化配置文件。
    *   **技术实现思路:** 使用`QSplitter`作为`PlotWidget`的容器。创建一个视图管理类来处理视图间的同步逻辑，通过信号和槽机制进行通信。

*   #### **[功能] 更多的定量分析工具 (More Quantitative Analysis Tools)**
    *   **用户价值:** 从“看一看”的定性分析，走向“算一算”的定量分析。
    *   **核心功能点:**
        *   **区域积分/平均:** 允许用户在图上交互式地绘制一个矩形或多边形区域，程序自动计算该区域内某个公式（如压力`p`）的积分或平均值。
        *   **粒子追踪:** 允许用户在流场中放置一个或多个虚拟粒子，并计算它们随时间的运动轨迹（迹线、流线或脉线）。
    *   **技术实现思路:** 区域计算需要获取多边形内的网格点，并进行加权求和。粒子追踪则需要在每个时间步上进行速度插值和位置积分。

*   #### **[功能] 脚本/宏功能 (Scripting/Macro Engine)**
    *   **用户价值:** 为高级用户提供自动化和自定义分析的终极解决方案，将平台从一个封闭的“工具”提升为一个开放的“环境”。
    *   **核心功能点:**
        *   在UI中嵌入一个简单的Python脚本编辑器和控制台。
        *   向脚本环境安全地暴露核心对象，如 `data_manager`, `plot_widget` 等。
        *   用户可以编写脚本来循环处理数据、执行复杂的计算序列、自动导出结果等。
    *   **技术实现思路:** 集成`IPython`的Qt Console小部件 (`ipykernel`, `qtconsole`) 是一个成熟且功能强大的方案。

---

### **第三优先级：迈向三维与未来 (Tier 3: Towards 3D and Beyond)**

这是最具挑战性也最具价值的长期目标，将使InterVis的应用领域产生质的飞跃。

*   #### **[功能] 3D 可视化支持 (3D Visualization Support)**
    *   **用户价值:** 解锁对真实三维模拟数据（如3D CFD、电磁场、传热）的分析能力。
    *   **核心功能点:**
        *   增加对3D数据的读取和管理能力（例如，每个CSV文件代表一个Z平面）。
        *   引入新的3D可视化窗口或模式。
        *   支持核心的3D可视化类型：
            *   **切片图 (Slice Plane):** 在3D空间中显示可任意拖动和旋转的2D切片。
            *   **等值面 (Isosurface):** 显示某个物理量等于特定值的3D表面。
            *   **3D矢量图/流线 (3D Glyphs/Streamlines):** 在3D空间中显示矢量或流线。
    *   **技术实现思路:** 集成一个专为科学可视化设计的、比Matplotlib更强大的3D引擎。`Mayavi` 或 `PyVista` (基于VTK) 是理想的选择。这需要一个独立的3D绘图控件，并重构部分渲染和数据处理逻辑。

*   #### **[工程] 插件系统 (Plugin System)**
    *   **用户价值:** 允许社区和用户自己开发和分享功能模块，极大地丰富平台生态。
    *   **核心功能点:**
        *   定义一个清晰的插件接口（API）。
        *   插件可以添加新的分析工具到UI、注册新的函数到公式引擎、或提供新的数据导入/导出格式。
        *   InterVis启动时会自动扫描插件目录并加载插件。
    *   **技术实现思路:** 可以参考`setuptools`的`entry_points`机制，或实现一个简单的基于文件约定的插件发现系统。

## 贡献 (Contributing)
欢迎各种形式的贡献！如果您有任何建议、发现任何错误或想要添加新功能，请随时提交 Pull Request 或创建 Issue。

## 许可证 (License)
本项目采用 [MIT License](LICENSE) 开源。

## 作者 (Author)
*   **StarsWhere** - [GitHub Profile](https://github.com/StarsWhere)