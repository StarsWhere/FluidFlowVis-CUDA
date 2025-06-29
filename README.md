### **`README.md` (完整更新版)**

请直接用以下内容覆盖您的 `README.md` 文件。

```markdown
# InterVis v3.0-Compute (交互式计算与可视分析平台)

[![Python Version](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![UI Framework](https://img.shields.io/badge/UI-PyQt6-brightgreen.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![Version](https://img.shields.io/badge/Version-3.0--ComputeReady-blue)](https://github.com/StarsWhere/InterVis)

**English:** An high-performance, interactive platform for visualizing and **computing** on time-series scientific data, now powered by a database core and ready for advanced analytics.
<br>
**中文:** 一款用于时序性科学计算数据的 **交互式计算** 与可视分析的高性能平台，现已由数据库核心驱动，并为高级分析做好准备。

---

InterVis 专为需要分析、理解并深入挖掘数值模拟（如CFD、物理学）数据的研究人员、工程师和学生而设计。它彻底改变了处理由大量CSV文件组成的时序数据集的方式。

**在 v3.0 版本中，InterVis 从一个“可视化工具”蜕变为一个“交互式计算平台”**，引入了革命性的数据库核心和强大的在线计算能力。它不仅能看，更能算！

![Main Application Interface](png/main_interface.png)
> *InterVis v3.0 主界面，一个强大的交互式计算与可视分析环境。*

## 核心功能 (Key Features)

*   ⚡ **数据库驱动核心 (Database-Driven Core):**
    *   **一键式数据预处理:** 首次加载时，自动将项目目录下的所有CSV文件高效整合到一个可移植的SQLite数据库中。
    *   **性能革命:** 所有后续操作（数据加载、统计、导出）均由高性能的SQL查询驱动，**速度提升10倍以上**，告别文件I/O瓶颈。
    *   **项目化管理:** 以文件夹作为“项目”进行管理，自动处理数据和配置，工作流清晰高效。

*   🚀 **高级计算与公式引擎 (Advanced Computing & Formula Engine):**
    *   **派生变量计算:** 用户可自定义公式，计算新的物理量（如`tke = 0.5 * (u**2+v**2)`），并将其作为 **永久列** 添加到数据库中，供后续所有分析使用。
    *   **空间与矩阵运算:** 在公式中直接使用 `grad_x()`, `div()`, `curl()` 等函数，对任意标量或矢量场进行 **实时** 梯度、散度和旋度计算并可视化，无需预处理。
    *   **统一公式接口:** 无论是坐标轴、热力图、等高线还是矢量场，都可以使用包含聚合、全局常量和空间运算的复杂公式。

*   📊 **多层实时交互可视化 (Multi-Layer Interactive Visualization):**
    *   在完全自定义的坐标系上，流畅地探索 **热力图、等高线图、矢量图和流线图** 的多层叠加。
    *   支持交互式缩放、平移和数据探针，深入洞察数据细节。

*   🌐 **SQL驱动的全局统计 (SQL-Powered Global Statistics):**
    *   **基础与自定义统计:** 利用SQL聚合查询，秒速计算出基础统计量和用户定义的复杂全局常量（如雷诺应力）。
    *   **支持高级公式:** 在定义常量时，可直接使用空间运算函数，例如 `mean_vorticity = mean(curl(u, v))`。

*   🖼️ **高质量导出与报告 (High-Quality Export & Reporting):**
    *   支持导出高DPI的PNG图像和高分辨率的MP4视频。
    *   批量处理功能可根据不同的JSON配置文件，自动完成一系列视频的导出任务。

## 功能详解 (Features in Detail)

### 1. 数据库核心与项目工作流
InterVis v3.0 引入了全新的工作流程。您不再是打开单个文件，而是打开一个“项目”。
1.  **选择项目目录:** 通过 `文件 -> 设置项目目录` 选择包含您所有CSV文件的文件夹。
2.  **自动导入:** 如果是首次加载，InterVis会提示您将所有CSV数据导入到一个名为 `_intervis_data.db` 的数据库中。这个过程是全自动的，并且有进度条显示。
3.  **即时加载:** 之后每次打开该项目，InterVis都会直接从数据库加载数据，启动和加载速度极快。

![New Workflow](png/feature_workflow_db.png)
> *首次加载项目时，自动化的数据库导入流程。*

### 2. 派生变量计算 (Derived Variables)
这是v3.0最强大的新功能之一。在全新的“计算”标签页中，您可以永久性地扩展您的数据集。
*   **创建新变量:** 输入新变量名（如 `tke`）和其计算公式（如 `0.5 * (u**2 + v**2 + w**2)`）。
*   **计算并存储:** 点击“计算”，InterVis会执行 `ALTER TABLE` 和 `UPDATE` 操作，将计算结果高效地存入数据库的新列中。
*   **无缝使用:** `tke` 现在就像一个原始变量一样，可用于任何后续的可视化、统计或进一步的计算。

![Derived Variable Calculation](png/feature_compute_derived.png)
> *在“计算”标签页中定义并计算新的派生变量。*

### 3. 实时空间/矩阵运算 (Live Spatial/Matrix Operations)
无需离开可视化界面，即可进行复杂的场论计算。
*   **可视化涡量:** 在热力图公式中输入 `curl(u, v)`，即可立即看到流场的涡量分布。
*   **可视化散度:** 输入 `div(u, v)` 来分析流场的可压缩性。
*   **可视化压力梯度:** 输入 `grad_x(p)` 或 `grad_y(p)` 来查看压力在特定方向上的变化率。

![Live Spatial Calculation](png/feature_compute_spatial.png)
> *直接在热力图公式中使用`curl(u,v)`来实时可视化涡量场。*

所有这些计算都是在后台实时完成的：程序获取相应的数据场，插值到网格上，使用NumPy进行梯度等运算，然后将结果矩阵呈现出来。

## 技术栈 (Technology Stack)

*   **数据后端 (Data Backend):** SQLite
*   **用户界面 (GUI):** PyQt6
*   **绘图引擎 (Plotting Engine):** Matplotlib
*   **数据处理与计算 (Data Handling & Computing):** Pandas, NumPy, SciPy
*   **数据I/O加速 (Data I/O Acceleration):** PyArrow (推荐)
*   **视频编码 (Video Encoding):** MoviePy (推荐), imageio (备用)
*   **GPU 加速 (GPU Acceleration):** CuPy (可选, 推荐用于 NVIDIA GPU)

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
    python src/main.py
    ```

3.  **推荐分析流程 (Recommended Analysis Workflow):**
    1.  **加载项目:** 使用 `文件 -> 设置项目目录...` 选择您的项目文件夹，并完成首次数据导入。
    2.  **计算全局统计:** 切换到“全局统计”标签页，点击“开始计算基础统计”。
    3.  **派生新变量:** 切换到“计算”标签页，定义并计算您需要分析的关键派生变量（如TKE、涡量等）。
    4.  **交互式可视化:** 返回“可视化”标签页，使用所有可用变量（原始的、派生的）和函数（包括空间运算）来创建图表。
    5.  **深入分析:** 定义更复杂的全局常量，或使用探针、导出等功能进行深入分析。

## 目录结构 (Directory Structure)
```
InterVis/
├── my_simulation_run/ # 您的项目目录
│   ├── data_001.csv
│   └── _intervis_data.db  # 程序自动创建的数据库
├── src/               # 源代码
│   ├── core/
│   │   ├── data_manager.py # 已重构为数据库管理器
│   │   ├── formula_engine.py # 已扩展以支持空间运算
│   │   └── workers.py      # 新增和重构了后台计算线程
│   ├── handlers/
│   │   └── compute_handler.py # 新增，处理计算逻辑
│   ├── ui/
│   └── ... (其他目录结构保持模块化)
├── main.py
└── requirements.txt
```

## 未来计划 (Future Plans)

*   [x] ~~**数据库核心迁移 (Database Core Migration):**~~ **(v2.0 已实现)**
*   [x] ~~**派生变量计算 (Derived Variable Computation):**~~ **(v3.0 已实现)**
*   [x] ~~**空间/矩阵运算 (Spatial/Matrix Operations):**~~ **(v3.0 已实现)**
*   [ ] **高级数据过滤与查询UI (Advanced Data Filtering & Query UI):**
    *   增加一个图形化的查询构建器，让用户可以通过点击轻松构建复杂的SQL `WHERE`子句，用于分析数据的特定子集。
*   [ ] **时间序列分析 (Time-Series Analysis):**
    *   实现对单个点或区域的数据进行时间演化分析，并绘制时序图。
    *   集成傅里叶变换 (FFT) 功能，用于频域分析。
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