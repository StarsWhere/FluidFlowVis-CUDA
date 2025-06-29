# InterVis v3.3-ProFinal (交互式计算与可视分析平台)

[![Python Version](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![UI Framework](https://img.shields.io/badge/UI-PyQt6-brightgreen.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![Version](https://img.shields.io/badge/Version-3.3--ProFinal-blue)](https://github.com/StarsWhere/InterVis)

**English:** A high-performance, interactive platform for visualizing and analyzing time-series scientific data, now powered by a database core and featuring advanced analytical tools.
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
    *   **自动刷新与视图重置:** 调整任何可视化参数后，图表将自动刷新，确保所见即所得。
    *   **坐标轴比例控制:** 支持在`'Auto'`（自动拉伸）、`'Equal'`（等比例）和`'Custom'`（自定义）模式间切换。
    *   支持交互式缩放、平移和数据探针，深入洞察数据细节。

*   🔬 **专业分析工具集 (Professional Analysis Toolkit):**
    *   **时间分析:** 支持在“瞬时场”和“时间平均场”之间切换，以观察稳态特征。
    *   **一维剖面图:** 通过鼠标或坐标输入在图上定义一条线，并实时查看多个变量沿着该线的分布情况。
    *   **时间序列分析与FFT:** 拾取图上任意一点，查看其物理量随时间的变化，并可一键进行**快速傅里叶变换(FFT)**以分析频域特性。
    *   **全局数据过滤器:** 应用SQL `WHERE`子句对整个数据集进行筛选，所有计算和可视化将只在数据子集上进行。

*   ✨ **模板与主题系统 (Template & Theme System):**
    *   **可视化模板:** 一键保存和加载包含公式、图层、范围在内的 **一整套可视化方案**，极大提升重复性工作的效率。
    *   **绘图主题:** 轻松切换图表的整体美学风格（如 `dark_mode`, `paper_bw`），适应学术论文、PPT演示等不同场景的需求。

*   🖼️ **高效导出与报告 (Efficient Export & Reporting):**
    *   **高质量输出:** 支持导出高DPI的PNG图表和高分辨率的MP4/GIF视频。
    *   **并行帧渲染:** 在导出视频时，使用多线程并行渲染每一帧图像，大幅缩短视频生成时间。
    *   **批量导出:** 可选择多个配置文件，程序将按顺序自动完成一系列视频的导出任务。

## 技术栈 (Technology Stack)

*   **数据后端 (Data Backend):** SQLite
*   **用户界面 (GUI):** PyQt6
*   **绘图引擎 (Plotting Engine):** Matplotlib
*   **数据处理与计算 (Data Handling & Computing):** Pandas, NumPy, SciPy
*   **视频编码 (Video Encoding):** MoviePy (推荐), imageio (备用)
*   **GPU 加速 (GPU Acceleration):** CuPy (可选, 推荐用于 NVIDIA GPU)
*   **并行处理 (Parallel Processing):** Concurrent.futures (用于视频帧渲染和高级统计)

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
    4.  **交互式可视化:** 返回“可视化”标签页，使用所有可用变量、函数、模板和主题进行探索。
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
│   ├── templates/              # 可视化模板目录
│   ├── themes/                 # 绘图主题目录
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
│   │   ├── stats_handler.py    # 统计面板逻辑
│   │   ├── template_handler.py # 可视化模板逻辑
│   │   └── theme_handler.py    # 绘图主题逻辑
│   ├── ui/                     # UI相关模块
│   │   ├── dialogs.py          # 自定义对话框
│   │   ├── profile_plot_dialog.py # 剖面图窗口
│   │   ├── timeseries_dialog.py # 时间序列图窗口
│   │   └── ui_setup.py         # 主窗口UI布局
│   ├── utils/                  # 工具类模块
│   │   ├── gpu_utils.py        # GPU可用性检测
│   │   ├── help_content.py     # 帮助文档内容
│   │   ├── help_dialog.py      # 帮助文档窗口
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

*   #### **[已完成] 可视化模板与绘图主题 (Visualization Templates & Themes)**
    *   **成果:** v3.3版本已成功集成了可视化模板和绘图主题系统。用户现在可以一键加载整套可视化方案，或切换图表的整体外观，极大提升了工作效率和图表的美观度。

*   #### **[规划中] 增强的交互模式提示 (Enhanced Interactive Mode Hints)**
    *   **目标:** 解决当前仅依赖状态栏提示信息不够醒目的问题，避免用户在进入拾取、剖面图等模式后忘记当前状态。
    *   **方案:** 当进入交互模式时，在绘图区域的角落显示一个半透明的、更醒目的浮动提示框（例如，“剖面图模式：请点击定义起点”）。当模式切换或取消时，提示框自动淡出。

*   #### **[规划中] 论文级图表导出 (Publication-Quality Export)**
    *   **目标:** 让用户无需借助其他软件，即可直接从InterVis导出可用于学术论文或报告的精美图表。
    *   **方案:**
        *   **颜色条(Colorbar)精细控制:** 在UI上提供输入框，用于修改颜色条的标签、字体大小、刻度格式。
        *   **图例(Legend)支持:** 允许为等高线或矢量图层手动添加和自定义图例。
        *   **细节微调:** 提供更多对坐标轴、标题、刻度标签等细节的控制选项。

*   #### **[规划中] 应用打包与分发 (Installation & Distribution)**
    *   **目标:** 为非Python开发者提供最简单的安装方式，是软件能否被广泛应用的关键。
    *   **方案:** 使用 `PyInstaller` 或 `cx_Freeze` 将应用打包成独立的、无需安装Python环境的可执行文件（`.exe` for Windows, `.app` for macOS），并解决 `MoviePy`、`CuPy` 等复杂库的打包问题。

---

### **第二优先级：分析能力扩展 (Tier 2: Expanding Analytical Capabilities)**

这些功能将为平台引入全新的分析维度，使其能够解决更广泛、更深入的科学问题。

*   #### **[规划中] 多视图/对比视图模式 (Multi-View / Comparison Mode)**
    *   **目标:** 提供直观对比不同时刻、不同变量或不同过滤条件下数据的能力，这是进行深入分析的常用手段。
    *   **方案:**
        *   允许用户将主绘图区分割为两个或多个并排/堆叠的子视图。
        *   提供视图同步选项：同步时间轴、同步相机（缩放/平移）、或完全独立。
        *   每个子视图可以加载不同的可视化模板或配置。

*   #### **[规划中] 更多的定量分析工具 (More Quantitative Analysis Tools)**
    *   **目标:** 实现从“定性观察”到“定量计算”的跨越。
    *   **方案:**
        *   **区域积分/平均:** 允许用户在图上交互式地绘制一个矩形或多边形区域，程序自动计算该区域内某个物理量（如压力`p`）的积分或平均值。
        *   **粒子追踪:** 允许用户在流场中放置一个或多个虚拟粒子，并计算它们随时间的运动轨迹（迹线、流线或脉线）。

*   #### **[规划中] 脚本/宏功能 (Scripting/Macro Engine)**
    *   **目标:** 为高级用户提供自动化和自定义分析的终极解决方案，将平台从一个封闭的“工具”提升为一个开放的“环境”。
    *   **方案:**
        *   在UI中嵌入一个简单的Python脚本编辑器和控制台。
        *   向脚本环境安全地暴露核心API，如 `data_manager`, `plot_widget` 等。
        *   用户可以编写脚本来循环处理数据、执行复杂的计算序列、自动导出结果等，实现完全可编程的分析流程。

---

### **第三优先级：迈向三维与未来 (Tier 3: Towards 3D and Beyond)**

这是最具挑战性也最具价值的长期目标，将使InterVis的应用领域产生质的飞跃。

*   #### **[远景] 3D 可视化支持 (3D Visualization Support)**
    *   **目标:** 解锁对真实三维模拟数据（如3D CFD、电磁场、传热）的分析能力。
    *   **方案:**
        *   扩展数据模型以支持3D数据（例如，(x, y, z) 坐标）。
        *   集成一个专为科学可视化设计的、比Matplotlib更强大的3D引擎，如 `PyVista` (基于VTK) 或 `Mayavi`。
        *   实现核心的3D可视化类型：
            *   **切片图 (Slice Plane):** 在3D空间中显示可任意拖动和旋转的2D切片。
            *   **等值面 (Isosurface):** 显示某个物理量等于特定值的3D表面。
            *   **3D矢量图/流线 (3D Glyphs/Streamlines):** 在3D空间中显示矢量或流线。

*   #### **[远景] 插件系统 (Plugin System)**
    *   **目标:** 允许社区和用户自己开发和分享功能模块，极大地丰富平台生态，构建一个开放的、可扩展的分析平台。
    *   **方案:**
        *   定义一个清晰的插件接口（API）。
        *   插件可以添加新的分析工具到UI、注册新的函数到公式引擎、或提供新的数据导入/导出格式。
        *   InterVis启动时会自动扫描插件目录并加载插件。

## 贡献 (Contributing)
欢迎各种形式的贡献！如果您有任何建议、发现任何错误或想要添加新功能，请随时提交 Pull Request 或创建 Issue。

## 许可证 (License)
本项目采用 [MIT License](LICENSE) 开源。

## 作者 (Author)
*   **StarsWhere** - [GitHub Profile](https://github.com/StarsWhere)