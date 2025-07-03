# src/core/workers.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台工作线程模块
"""
import os
import json
import logging
import pandas as pd
import sqlite3
import re
import numpy as np
import zarr
import shutil
from typing import List, Dict, Any, Tuple
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from scipy.interpolate import interpn

from PyQt6.QtCore import QThread, pyqtSignal

from numcodecs import Blosc

from src.core.data_manager import DataManager
from src.core.statistics_calculator import StatisticsCalculator
from src.visualization.video_exporter import VideoExportWorker
from src.core.formula_engine import FormulaEngine
from src.core.computation_core import compute_gridded_field

try:
    import pyarrow
    PYARROW_AVAILABLE = True
except ImportError:
    PYARROW_AVAILABLE = False


logger = logging.getLogger(__name__)


# --- [REFACTORED] Helper functions for parallel processing with Zarr ---

def _parallel_simple_derived_var_calc_zarr(args: Tuple):
    frame_idx, project_dir, time_variable, new_var_formula, new_var_name, all_globals, required_columns = args
    dm = DataManager(); dm.setup_project_directory(project_dir); dm.set_time_variable(time_variable)
    formula_engine = FormulaEngine()
    formula_engine.update_allowed_variables(dm.get_variables(include_id=True)); formula_engine.update_custom_global_variables(all_globals)
    try:
        frame_data = dm.get_frame_data(frame_idx, required_columns=required_columns)
        if frame_data is None or frame_data.empty: return
        new_values = formula_engine.evaluate_formula(frame_data, new_var_formula)
        zarr_root = zarr.open(dm.zarr_path, mode='r+')
        zarr_root[new_var_name][frame_idx, :] = new_values.values
    except Exception as e: logger.error(f"帧 {frame_idx} 的子进程在简单计算期间失败: {e}", exc_info=True)

def _parallel_spatial_derived_var_calc_zarr(args: Tuple):
    frame_idx, project_dir, time_variable, new_var_formula, new_var_name, x_formula, y_formula, grid_res, all_globals, required_columns = args
    dm = DataManager(); dm.setup_project_directory(project_dir); dm.set_time_variable(time_variable)
    formula_engine = FormulaEngine()
    formula_engine.update_allowed_variables(dm.get_variables(include_id=True)); formula_engine.update_custom_global_variables(all_globals)
    try:
        frame_data = dm.get_frame_data(frame_idx, required_columns=required_columns)
        if frame_data is None or frame_data.empty: return
        computation_result = compute_gridded_field(frame_data, new_var_formula, x_formula, y_formula, formula_engine, grid_res, use_gpu=False)
        result_grid, grid_x, grid_y = computation_result.get('result_data'), computation_result.get('grid_x'), computation_result.get('grid_y')
        zarr_root = zarr.open(dm.zarr_path, mode='r+')
        if result_grid is None or grid_x is None or grid_y is None or np.all(np.isnan(result_grid)):
            num_points = zarr_root[new_var_name].shape[1]
            zarr_root[new_var_name][frame_idx, :] = np.full(num_points, np.nan)
            return
        original_x = formula_engine.evaluate_formula(frame_data, x_formula)
        original_y = formula_engine.evaluate_formula(frame_data, y_formula)
        points_to_sample = np.vstack([original_y, original_x]).T
        sampled_values = interpn((grid_y[:, 0], grid_x[0, :]), result_grid, points_to_sample, method='linear', bounds_error=False, fill_value=np.nan)
        zarr_root[new_var_name][frame_idx, :] = sampled_values
    except Exception as e: logger.error(f"帧 {frame_idx} 的子进程在空间计算期间失败。公式: '{new_var_formula}'. 错误: {e}", exc_info=True)

# --- End of helper functions ---

class DataImportWorker(QThread):
    progress, log_message, finished, error = pyqtSignal(int, int, str), pyqtSignal(str), pyqtSignal(), pyqtSignal(str)
    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, parent=None):
        super().__init__(parent); self.dm, self.formula_engine, self.is_cancelled = data_manager, formula_engine, False
    
    def run(self):
        conn = None
        try:
            logger.info(f"后台数据导入开始: 从 {self.dm.project_directory} 到 {self.dm.db_path} 和 {self.dm.zarr_path}")
            csv_files = sorted([f for f in os.listdir(self.dm.project_directory) if f.lower().endswith('.csv')])
            if not csv_files: self.error.emit("目录中未找到任何CSV文件。"); return

            conn = self.dm.get_db_connection(); self.dm.create_database_tables(conn)
            
            total_steps = len(csv_files) + 1
            self.progress.emit(0, total_steps, f"分析 {csv_files[0]}...")
            
            df_sample = pd.read_csv(os.path.join(self.dm.project_directory, csv_files[0]), nrows=10)
            all_cols = df_sample.columns.tolist()
            if 'x' not in all_cols or 'y' not in all_cols: raise ValueError("CSV文件必须包含 'x' 和 'y' 列。")

            num_frames = len(csv_files)
            num_points = len(pd.read_csv(os.path.join(self.dm.project_directory, csv_files[0])))
            
            zarr_root = zarr.open(self.dm.zarr_path, mode='w')

            self.progress.emit(0, total_steps, "创建Zarr数据存储...")
            chunk_shape = (1, num_points)
            
            for col in all_cols:
                zarr_root.create_dataset(col, shape=(num_frames, num_points), chunks=chunk_shape, dtype=df_sample[col].dtype, compressor=None)
            zarr_root.create_dataset('frame_index', shape=(num_frames, num_points), chunks=chunk_shape, dtype='i4', compressor=None)
            zarr_root.create_dataset('id', shape=(num_frames, num_points), chunks=chunk_shape, dtype='i4', compressor=None)

            for i, filename in enumerate(csv_files):
                if self.is_cancelled: break
                self.progress.emit(i + 1, total_steps, f"正在导入: {filename}")
                df = pd.read_csv(os.path.join(self.dm.project_directory, filename))
                
                zarr_root['frame_index'][i, :] = i
                zarr_root['id'][i, :] = np.arange(num_points) + i * num_points
                
                for col in df.columns:
                    if col in zarr_root: zarr_root[col][i, :] = df[col].values

            if self.is_cancelled:
                conn.close()
                if os.path.exists(self.dm.db_path): os.remove(self.dm.db_path)
                if os.path.isdir(self.dm.zarr_path): shutil.rmtree(self.dm.zarr_path)
                return

            conn.close()
            self.log_message.emit("导入完成，正在计算基础统计数据...")
            self.dm.post_import_setup()
            stats_worker = GlobalStatsWorker(self.dm, self.formula_engine, self.dm.get_variables(include_id=False))
            stats_worker.progress.connect(lambda cur, tot, msg: self.progress.emit(total_steps, total_steps, f"统计: {msg}"))
            stats_worker.error.connect(self.error.emit)
            stats_worker.finished.connect(self.finished.emit)
            stats_worker.run()

        except Exception as e:
            logger.error(f"数据导入失败: {e}", exc_info=True)
            self.error.emit(str(e))
            if conn: conn.close()
            if self.dm.db_path and os.path.exists(self.dm.db_path):
                try: os.remove(self.dm.db_path)
                except Exception as ce: logger.error(f"清理失败的DB文件时出错: {ce}")
            if self.dm.zarr_path and os.path.isdir(self.dm.zarr_path):
                 try: shutil.rmtree(self.dm.zarr_path)
                 except Exception as ce: logger.error(f"清理失败的Zarr存储时出错: {ce}")

class DerivedVariableWorker(QThread):
    progress, finished, error = pyqtSignal(int, int, str), pyqtSignal(), pyqtSignal(str)
    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, definitions: List[Tuple[str, str]], parent=None):
        super().__init__(parent); self.dm, self.formula_engine, self.definitions = data_manager, formula_engine, definitions
    def run(self):
        try:
            for i, (new_name, formula) in enumerate(self.definitions):
                self.progress.emit(i, len(self.definitions), f"步骤 {i+1}/{len(self.definitions)}: 准备计算 '{new_name}'...")
                
                # [FIXED] 移除 with 语句
                root = zarr.open(self.dm.zarr_path, mode='a')
                if new_name in root: del root[new_name]
                ref_array = root[self.dm.get_variables()[0]]
                # [FIXED] 使用 'compressors' (复数) 来消除警告
                root.create_dataset(new_name, shape=ref_array.shape, chunks=ref_array.chunks, dtype='f4', compressors=ref_array.compressors)
                
                is_spatial = any(re.search(r'\b' + re.escape(f) + r'\s*\(', formula) for f in self.formula_engine.spatial_functions)
                required_columns = self.formula_engine.get_used_variables(formula)
                self._run_parallel_computation(new_name, formula, is_spatial, (i, len(self.definitions)), list(required_columns))
                self.dm.save_variable_definition(new_name, formula, "per-frame")
                self.dm.refresh_schema_info(); self.formula_engine.update_allowed_variables(self.dm.get_variables())
                stats_worker = GlobalStatsWorker(self.dm, self.formula_engine, [new_name])
                stats_worker.error.connect(lambda e: logger.error(f"计算 '{new_name}' 的统计数据时出错: {e}")); stats_worker.run()
            self.progress.emit(len(self.definitions), len(self.definitions), "全部完成！"); self.finished.emit()
        except Exception as e: logger.error(f"计算派生变量失败: {e}", exc_info=True); self.error.emit(str(e))
    def _run_parallel_computation(self, new_name, formula, is_spatial, step_info, required_columns):
        current_step, total_steps, total_frames = *step_info, self.dm.get_frame_count()
        if total_frames == 0: return
        self.dm.load_global_stats(); all_globals = self.dm.global_stats.copy()
        if is_spatial:
            x_formula, y_formula, grid_res = 'x', 'y', (150, 150)
            required_columns.extend(self.formula_engine.get_used_variables(x_formula))
            required_columns.extend(self.formula_engine.get_used_variables(y_formula))
            tasks = [(idx, self.dm.project_directory, self.dm.time_variable, formula, new_name, x_formula, y_formula, grid_res, all_globals, list(set(required_columns))) for idx in range(total_frames)]
            worker_func = _parallel_spatial_derived_var_calc_zarr
        else:
            tasks = [(idx, self.dm.project_directory, self.dm.time_variable, formula, new_name, all_globals, list(set(required_columns))) for idx in range(total_frames)]
            worker_func = _parallel_simple_derived_var_calc_zarr
        processed_count = 0
        try:
            with ProcessPoolExecutor(max_workers=max(1, os.cpu_count() // 2)) as executor:
                futures = [executor.submit(worker_func, task) for task in tasks]
                for future in as_completed(futures):
                    future.result()
                    processed_count += 1
                    self.progress.emit(current_step, total_steps, f"步骤 {current_step+1}/{total_steps} ('{new_name}'): 计算帧 {processed_count}/{total_frames}")
        except Exception as e: raise RuntimeError(f"并行计算池在处理 '{new_name}' 时崩溃: {e}")

class TimeAggregatedVariableWorker(QThread):
    progress, finished, error = pyqtSignal(int, int, str), pyqtSignal(), pyqtSignal(str)
    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, definitions: List[Tuple[str, str]], parent=None):
        super().__init__(parent); self.dm, self.formula_engine, self.definitions = data_manager, formula_engine, definitions
    def _parse_formula(self, formula: str):
        match = re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula, re.DOTALL)
        if not match: raise ValueError(f"公式格式无效 '{formula}' (需要 agg_func(expression))")
        return match.groups()[0].lower(), match.groups()[1].strip()
    def run(self):
        try:
            for i, (new_name, formula) in enumerate(self.definitions):
                self.progress.emit(i, len(self.definitions), f"步骤 {i+1}/{len(self.definitions)}: 开始计算 '{new_name}'...")
                agg_func, inner_expr = self._parse_formula(formula)
                required_vars = self.formula_engine.get_used_variables(inner_expr); required_vars.update(['x', 'y'])
                self.progress.emit(i, len(self.definitions), f"({i+1}.1) 从Zarr加载 {required_vars}...")
                data_dict = {var: self.dm.zarr_root[var][:].flatten() for var in required_vars if var in self.dm.zarr_root}
                df = pd.DataFrame(data_dict)
                self.progress.emit(i, len(self.definitions), f"({i+1}.2) 计算表达式 '{inner_expr}'...")
                self.formula_engine.update_custom_global_variables(self.dm.global_stats)
                df['eval_result'] = self.formula_engine.evaluate_formula(df, inner_expr)
                self.progress.emit(i, len(self.definitions), f"({i+1}.3) 按坐标分组和聚合...")
                aggregated_series = df.groupby(['x', 'y'])['eval_result'].agg(agg_func)
                self.progress.emit(i, len(self.definitions), f"({i+1}.4) 广播结果...")
                broadcasted_values = df.set_index(['x', 'y']).index.map(aggregated_series).values
                self.progress.emit(i, len(self.definitions), f"({i+1}.5) 写入Zarr存储...")
                # [FIXED] 移除 with 语句
                root = zarr.open(self.dm.zarr_path, mode='a')
                ref_shape = root[self.dm.get_variables()[0]].shape
                if new_name in root: del root[new_name]
                ref_array = root[self.dm.get_variables()[0]]
                # [FIXED] 使用 'compressors' (复数) 来消除警告
                new_array = root.create_dataset(new_name, shape=ref_shape, chunks=(1, ref_shape[1]), dtype='f4', compressors=ref_array.compressors)
                new_array[:] = broadcasted_values.reshape(ref_shape)
                
                self.dm.save_variable_definition(new_name, formula, "time-aggregated")
                self.dm.refresh_schema_info()
                stats_worker = GlobalStatsWorker(self.dm, self.formula_engine, [new_name])
                stats_worker.error.connect(lambda e: logger.error(f"计算 '{new_name}' 统计时出错: {e}")); stats_worker.run()
            self.progress.emit(len(self.definitions), len(self.definitions), "全部完成！"); self.finished.emit()
        except Exception as e: logger.error(f"计算时间聚合变量失败: {e}", exc_info=True); self.error.emit(str(e))

class BatchExportWorker(QThread):
    progress, log_message, summary_ready = pyqtSignal(int, int, str), pyqtSignal(str), pyqtSignal(str)
    def __init__(self, config_files: List[str], data_manager: DataManager, output_dir: str, formula_engine: FormulaEngine, parent=None):
        super().__init__(parent); self.config_files, self.dm, self.output_dir, self.formula_engine, self.is_cancelled = config_files, data_manager, output_dir, formula_engine, False
    def run(self):
        successful, failed, skipped, total = 0, 0, 0, len(self.config_files)
        self.formula_engine.update_allowed_variables(self.dm.get_variables())
        for i, filepath in enumerate(self.config_files):
            if self.is_cancelled: break
            filename = os.path.basename(filepath)
            self.progress.emit(i, total, filename); self.log_message.emit(f"读取配置: {filename}")
            try:
                with open(filepath, 'r', encoding='utf-8') as f: config = json.load(f)
                if config.get('analysis', {}).get('time_average', {}).get('enabled', False):
                    self.log_message.emit(f"跳过: {filename} (时间平均场模式)"); skipped += 1; continue
                required_vars, formulas = set(), [config['axes'].get('x_formula', 'x'), config['axes'].get('y_formula', 'y')]
                if config.get('heatmap', {}).get('enabled'): formulas.append(config['heatmap'].get('formula'))
                if config.get('contour', {}).get('enabled'): formulas.append(config['contour'].get('formula'))
                if config.get('vector', {}).get('enabled'): formulas.extend([config['vector'].get('u_formula'), config['vector'].get('v_formula')])
                for f in filter(None, formulas): required_vars.update(self.formula_engine.get_used_variables(f))
                self.log_message.emit(f"  └ 依赖变量: {required_vars if required_vars else '无'}")
                export_cfg = config.get("export", {})
                p_conf = {'x_axis_formula': config.get('axes', {}).get('x_formula', 'x'), 'y_axis_formula': config.get('axes', {}).get('y_formula', 'y'), 'chart_title': config.get('axes', {}).get('title', ''), 'use_gpu': config.get('performance', {}).get('gpu', False), 'heatmap_config': config.get('heatmap', {}), 'contour_config': config.get('contour', {}), 'vector_config': config.get('vector', {}), 'analysis': config.get('analysis', {}), 'grid_resolution': (export_cfg.get("video_grid_w", 300), export_cfg.get("video_grid_h", 300)), 'export_dpi': export_cfg.get("dpi", 300), 'global_scope': self.dm.global_stats, 'required_variables': list(required_vars)}
                s_f, e_f, fps = export_cfg.get("video_start_frame", 0), export_cfg.get("video_end_frame", self.dm.get_frame_count() - 1), export_cfg.get("video_fps", 15)
                if s_f >= e_f: raise ValueError("起始帧需小于结束帧")
                out_fname = os.path.join(self.output_dir, f"batch_{os.path.splitext(filename)[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
                self.log_message.emit(f"准备导出: {os.path.basename(out_fname)}")
                vid_worker = VideoExportWorker(self.dm, p_conf, out_fname, s_f, e_f, fps)
                vid_worker.progress_updated.connect(lambda cur, tot, msg: self.log_message.emit(f"  └ {msg}"))
                vid_worker.run(); vid_worker.wait()
                if vid_worker.success: self.log_message.emit(f"成功: {filename}"); successful += 1
                else: self.log_message.emit(f"失败: {filename}. 原因: {vid_worker.message}"); failed += 1
            except Exception as e: self.log_message.emit(f"处理 '{filename}' 时发生严重错误: {e}"); failed += 1
        self.summary_ready.emit(f"成功导出 {successful} 个视频，失败 {failed} 个，跳过 {skipped} 个。")
    def cancel(self): self.is_cancelled = True

class GlobalStatsWorker(QThread):
    progress, finished, error = pyqtSignal(int, int, str), pyqtSignal(), pyqtSignal(str)
    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, vars_to_calc: List[str], parent=None):
        super().__init__(parent); self.dm, self.formula_engine, self.vars_to_calc = data_manager, formula_engine, vars_to_calc
    def run(self):
        try:
            numeric_vars = [v for v in self.vars_to_calc if v in self.dm.zarr_root]
            if not numeric_vars: self.finished.emit(); return
            self.progress.emit(0, len(numeric_vars), f"正在为 {len(numeric_vars)} 个变量计算基础统计...")
            stats_results = {}
            for i, var in enumerate(numeric_vars):
                if var not in self.dm.zarr_root: continue
                self.progress.emit(i, len(numeric_vars), f"正在计算: {var}")
                arr = self.dm.zarr_root[var]
                stats_results.update({
                    f"{var}_global_mean": float(np.mean(arr)), f"{var}_global_sum": float(np.sum(arr)),
                    f"{var}_global_min": float(np.min(arr)), f"{var}_global_max": float(np.max(arr)),
                    f"{var}_global_std": float(np.std(arr)), f"{var}_global_var": float(np.var(arr))
                })
            if stats_results: self.dm.save_global_stats(stats_results)
            self.progress.emit(len(numeric_vars), len(numeric_vars), "统计计算完成！"); self.finished.emit()
        except Exception as e: logger.error(f"全局统计计算失败: {e}", exc_info=True); self.error.emit(str(e))

class CustomGlobalStatsWorker(QThread):
    progress, finished, error = pyqtSignal(int, int, str), pyqtSignal(), pyqtSignal(str)
    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, definitions: List[str], parent=None):
        super().__init__(parent); self.calculator, self.definitions, self.dm, self.formula_engine = StatisticsCalculator(data_manager), definitions, data_manager, formula_engine
    def run(self):
        try:
            self.dm.load_global_stats(); base_stats, new_stats, new_formulas = self.dm.global_stats.copy(), {}, {}
            for i, definition in enumerate(self.definitions):
                current_globals = {**base_stats, **new_stats}
                self.formula_engine.update_custom_global_variables(current_globals)
                name, formula, agg_func = self.calculator.parse_definition(definition)
                self.progress.emit(i, len(self.definitions), f"计算: {name}...")
                if any(sf in formula for sf in self.formula_engine.spatial_functions):
                    raise NotImplementedError(f"全局常量的空间运算 ({name}) 在Zarr后端下尚未实现。")
                match = re.fullmatch(r'\s*\w+\s*\((.*)\)\s*', formula, re.DOTALL)
                inner_expr = match.groups()[0] if match else formula
                required_vars = self.formula_engine.get_used_variables(inner_expr)
                if not required_vars: result = self.formula_engine.evaluate_formula(pd.DataFrame(), inner_expr)
                else:
                    df = pd.DataFrame({var: self.dm.zarr_root[var][:].flatten() for var in required_vars})
                    eval_series = self.formula_engine.evaluate_formula(df, inner_expr)
                    agg_map = {'mean': np.mean, 'sum': np.sum, 'std': np.std, 'var': np.var, 'min': np.min, 'max': np.max}
                    if agg_func not in agg_map: raise ValueError(f"不支持的全局聚合函数: '{agg_func}'")
                    result = agg_map[agg_func](eval_series)
                new_stats[name], new_formulas[name] = float(result), formula
            self.dm.save_global_stats(new_stats); self.dm.custom_global_formulas.update(new_formulas); self.finished.emit()
        except Exception as e: logger.error(f"自定义全局常量计算失败: {e}", exc_info=True); self.error.emit(str(e))

class DataExportWorker(QThread):
    progress, finished, error = pyqtSignal(int, int, str), pyqtSignal(), pyqtSignal(str)
    def __init__(self, data_manager: DataManager, filepath: str, filter_clause: str, selected_variables: List[str], parent=None):
        super().__init__(parent); self.dm, self.filepath, self.filter_clause, self.selected_variables = data_manager, filepath, filter_clause, selected_variables
    def run(self):
        try:
            if not self.selected_variables: self.error.emit("没有选择任何要导出的变量列。"); return
            zarr_root = self.dm.zarr_root
            if not zarr_root: self.error.emit("数据存储未加载。"); return
            if self.filter_clause: logger.warning("数据导出中的过滤器功能在Zarr后端下暂不支持，此设置将被忽略。")
            total_frames = self.dm.get_frame_count()
            if self.filepath.lower().endswith('.parquet'):
                if not PYARROW_AVAILABLE: self.error.emit("Parquet 导出失败: 需要安装 'pyarrow' 库。"); return
                all_chunks = []
                for i in range(total_frames):
                    df_chunk = self.dm.get_frame_data(i, self.selected_variables)
                    all_chunks.append(df_chunk)
                    self.progress.emit(i + 1, total_frames, f"已读取 {i+1}/{total_frames} 帧到内存")
                if not all_chunks: self.error.emit("没有数据可写入 Parquet 文件。"); return
                self.progress.emit(total_frames, total_frames, "正在将数据写入 Parquet 文件...")
                pd.concat(all_chunks, ignore_index=True).to_parquet(self.filepath, engine='pyarrow', compression='snappy')
            else:
                is_first_chunk = True
                for i in range(total_frames):
                    df_chunk = self.dm.get_frame_data(i, self.selected_variables)
                    df_chunk.to_csv(self.filepath, mode='w' if is_first_chunk else 'a', header=is_first_chunk, index=False)
                    is_first_chunk = False
                    self.progress.emit(i + 1, total_frames, f"已导出 {i + 1}/{total_frames} 帧")
            self.finished.emit()
        except Exception as e: logger.error(f"导出数据失败: {e}", exc_info=True); self.error.emit(str(e))