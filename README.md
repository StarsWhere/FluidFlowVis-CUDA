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
    *   支持交互式缩放、平移和数据探针，深入洞察数据细节。
    *   默认配置优化，首次加载自动应用热力图，并填充第一个可用变量。

*   🔬 **专业分析工具集 (Professional Analysis Toolkit):**
    *   **时间分析:** 支持在“瞬时场”和“时间平均场”之间切换，以观察稳态特征。
    *   **一维剖面图:** 通过鼠标或坐标输入在图上定义一条线，并实时查看多个变量沿着该线的分布情况。
    *   **时间序列分析与FFT:** 拾取图上任意一点，查看其物理量随时间的变化，并可一键进行**快速傅里叶变换(FFT)**以分析频域特性。
    *   **全局数据过滤器:** 应用SQL `WHERE`子句对整个数据集进行筛选，所有计算和可视化将只在数据子集上进行。

*   🖼️ **高质量导出与报告 (High-Quality Export & Reporting):**
    *   支持导出高DPI的PNG图像和高分辨率的MP4视频。
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

## 待办事项与未来计划 (TODO & Future Plans)

以下是根据当前用户反馈和未来发展方向整理的待办列表和计划。

### **近期修复与优化 (Immediate TODOs)**

*   [ ] **自动刷新与视图重置:**
    *   当用户调整任何可视化设置（如颜色映射、线条宽度等）时，应自动重新渲染图表并**重置视图**（等同于点击“立即刷新”）。
    *   对于文本输入框（如公式编辑），应在用户按下`Enter`键或焦点离开输入框时触发刷新，以避免在输入过程中频繁重绘。
*   [ ] **统一“立即刷新”功能:**
    *   即使在“时间平均场”模式下，也应保留“立即刷新”按钮的可用性，以便用户在调整参数后可以手动触发重算。
*   [ ] **UI文本优化:**
    *   将“导出与性能”标签页中的“保存当前帧图片”按钮重命名为“**保存当前渲染图表**”，使其含义更清晰。
    *   所有默认的图表标题和标签应使用**英文**，以保证软件的国际通用性。

### **未来功能规划 (Future Features)**

*   [ ] **坐标轴比例控制 (Axis Scaling Control):**
    *   在“可视化”面板中增加一个新功能，允许用户手动设置坐标轴的**拉伸比例**（Aspect Ratio）。
    *   此设置将影响“重置视图”的行为和滚轮缩放的效果，默认为`'auto'`以保持当前行为。
*   [ ] **导出逻辑增强 (Enhanced Export Logic):**
    *   在“时间平均场”模式下，应**禁用“导出视频”**功能，因为该模式下不存在时间序列。
    *   在“批量视频导出”时，程序应能自动识别并**跳过**那些可视化模式被设置为“时间平均场”的配置文件，并在日志中给予提示。
*   [ ] **高级数据过滤与查询UI (Advanced Data Filtering & Query UI):**
    *   增加一个图形化的查询构建器，让用户可以通过点击轻松构建复杂的SQL `WHERE`子句。
*   [ ] **3D 可视化支持 (3D Visualization Support):**
    *   增加对 3D 数据的支持，能够可视化特定平面上的切片数据。
*   [ ] **插件系统 (Plugin System):**
    *   开发一个插件架构，允许用户编写自己的Python脚本来添加新的计算函数或分析工具。

## 贡献 (Contributing)
欢迎各种形式的贡献！如果您有任何建议、发现任何错误或想要添加新功能，请随时提交 Pull Request 或创建 Issue。

## 许可证 (License)
本项目采用 [MIT License](LICENSE) 开源。

## 作者 (Author)
*   **StarsWhere** - [GitHub Profile](https://github.com/StarsWhere)