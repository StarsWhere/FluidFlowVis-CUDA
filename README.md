# InterVis (交互可视分析器)

[![Python Version](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-PyQt6-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**InterVis (交互可视分析器)** 是一款为科学与工程领域设计的高性能、交互式2D数据可视化与分析工具。它特别适用于处理时间序列性的模拟数据（如计算流体动力学CFD结果），允许用户动态地探索数据、生成派生变量、并导出高质量的图像和视频。


---

## ✨ 核心功能

*   **交互式可视化**:
    *   支持将任意数据变量映射到 **背景热力图** (Heatmap) 和 **前景等高线** (Contour)。
    *   通过鼠标拖拽、滚轮缩放实现流畅的视图平移和缩放。
    *   实时 **数据探针** 功能，鼠标悬停即可查看任意点的精确数据值。

*   **强大的公式引擎**:
    *   无需修改原始数据，即可在运行时通过数学公式动态创建新的派生变量。
    *   支持丰富的数学函数 (如 `sqrt`, `sin`, `log` 等) 和常量 (`pi`, `e`)。
    *   示例：通过 `sqrt(u**2 + v**2)` 直接可视化速度大小。

*   **性能优化**:
    *   **GPU加速**: 若检测到 NVIDIA GPU 和 CuPy 环境，可一键启用CUDA加速公式计算，大幅提升大规模数据处理和渲染速度。
    *   **多线程处理**: 在视频导出和数据插值时采用多线程/多进程，避免UI冻结，提升响应速度。
    *   **智能缓存**: 内置LRU缓存机制，高效管理内存，加速常用数据帧的访问。

*   **专业的导出功能**:
    *   **高质量图片导出**: 将当前视图保存为高分辨率PNG图片，DPI可自定义。
    *   **视频动画导出**: 将指定帧范围的数据动画导出为 MP4 视频文件。
    *   **批量处理**: 核心亮点功能！通过选择多个配置文件（`.json`），实现全自动的批量视频导出，极大提升了生成多工况对比视频的效率。

*   **灵活的配置管理**:
    *   所有可视化设置（坐标轴、颜色映射、公式、导出参数等）均可保存为独立的 `.json` 配置文件。
    *   方便地加载、切换、新建和修改配置，实现结果的可复现性和工作的延续性。

---

## 🔧 安装与运行

### 1. 环境要求
*   Python 3.9 或更高版本
*   推荐使用 `venv` 或 `conda` 创建独立的虚拟环境。

### 2. 克隆仓库
```bash
git clone https://github.com/your-username/InterVis.git
cd InterVis
```

### 3. 安装依赖
应用所需的所有库都已在 `requirements.txt` 文件中列出。
```bash
pip install -r requirements.txt
```
**注意**: GPU加速是可选的。如果您拥有NVIDIA显卡并已安装CUDA工具包，可以通过安装CuPy来启用此功能。请根据您的CUDA版本选择合适的CuPy包，例如：
```bash
# for CUDA 11.x
pip install cupy-cuda11x

# for CUDA 12.x
pip install cupy-cuda12x
```
如果未安装CuPy，应用仍可正常运行，但无法使用GPU加速。

### 4. 准备数据
将您的数据文件放置在 `data` 目录下（或在应用内指定其他目录）。
*   数据格式要求：一系列的 `.csv` 文件。
*   每个 `.csv` 文件代表一个时间步（一帧）。
*   文件名应按时间顺序排列（如 `frame_0001.csv`, `frame_0002.csv`, ...）。
*   CSV文件内应包含可用于绘图的数值列（如 `x`, `y`, `p`, `u`, `v` 等）。

### 5. 运行应用
```bash
python main.py
```

---

## 🚀 使用指南

1.  **启动应用**: 运行 `main.py` 后，主窗口将出现。
2.  **加载数据**: 应用会自动扫描 `data` 目录。您也可以点击路径设置旁的 `...` 按钮选择您的数据目录。
3.  **基本可视化**:
    *   在右侧控制面板的 **"可视化"** 选项卡中，选择X轴和Y轴的变量。
    *   配置 **背景热力图**：勾选“启用”，选择一个变量或输入一个公式（如 `p`），然后选择一个颜色映射。
    *   配置 **前景等高线**：勾选“启用”，选择一个变量或输入公式（如 `sqrt(u**2+v**2)`），并调整等高线数量、颜色等。
4.  **播放与探索**:
    *   使用底部的播放控制条来播放动画、逐帧查看或拖动时间滑块。
    *   在 **"数据探针"** 选项卡中，查看鼠标下的实时数据。
5.  **保存设置**:
    *   在 **"导出与性能"** 选项卡下的 **"设置管理"** 部分，可以点击 **"保存设置"** 将当前的可视化配置保存下来，或点击 **"新建设置"** 创建一个新配置。
6.  **导出结果**:
    *   **导出图片**: 设置DPI，点击“保存当前帧图片”。
    *   **导出视频**: 设置起止帧和FPS，点击“导出视频”。
    *   **批量导出**: 点击“选择设置并批量导出...”，选择一个或多个 `.json` 配置文件，应用将自动为每个配置生成一段视频。

---

## 🛠️ 技术栈

*   **GUI框架**: [PyQt6](https://riverbankcomputing.com/software/pyqt/)
*   **绘图核心**: [Matplotlib](https://matplotlib.org/)
*   **数据处理**: [NumPy](https://numpy.org/) & [Pandas](https://pandas.pydata.org/)
*   **空间插值**: [SciPy](https://scipy.org/)
*   **视频编码**: [MoviePy](https://zulko.github.io/moviepy/) / [ImageIO](https://imageio.github.io/)
*   **GPU计算 (可选)**: [CuPy](https://cupy.dev/)

---

## 🤝 贡献

欢迎提交问题 (Issues) 和合并请求 (Pull Requests)。

## 📜 许可证

本项目采用 [MIT License](LICENSE) 授权。