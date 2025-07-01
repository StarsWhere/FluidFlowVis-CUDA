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
from typing import List, Dict, Any, Tuple
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed, BrokenProcessPool
from scipy.interpolate import interpn

from PyQt6.QtCore import QThread, pyqtSignal

from src.core.data_manager import DataManager
from src.core.statistics_calculator import StatisticsCalculator
from src.visualization.video_exporter import VideoExportWorker
from src.core.formula_engine import FormulaEngine
from src.core.computation_core import compute_gridded_field

logger = logging.getLogger(__name__)


# --- Helper functions for parallel processing (must be at top level) ---

def _parallel_simple_derived_var_calc(args: Tuple) -> List[Tuple[float, int]]:
    """
    为单个帧计算简单（非空间）公式，并将结果映射回原始点ID。
    此函数设计用于在单独的进程中运行。
    """
    time_value, db_path, time_variable, new_var_formula, all_globals = args
    # 每个子进程创建自己的实例
    dm = DataManager()
    dm.setup_project_directory(os.path.dirname(db_path))
    dm.set_time_variable(time_variable)
    formula_engine = FormulaEngine()
    formula_engine.update_allowed_variables(dm.get_variables())
    formula_engine.update_custom_global_variables(all_globals)

    try:
        # 在get_frame_data之前刷新schema，确保'id'列可用
        dm.refresh_schema_info(include_id=True)
        frame_data = dm.get_frame_data(dm._get_sorted_time_values().index(time_value))

        if frame_data is None or frame_data.empty:
            return []
        
        # 使用强大的 FormulaEngine 进行计算
        new_values = formula_engine.evaluate_formula(frame_data, new_var_formula)

        if 'id' not in frame_data.columns:
            logger.error(f"致命错误：在时间为 {time_value} 的帧数据中未找到 'id' 列。无法映射结果。")
            return []
        
        point_ids = frame_data['id'].values
        
        update_data = []
        for i in range(len(point_ids)):
            if not np.isnan(new_values.iloc[i]):
                update_data.append((float(new_values.iloc[i]), int(point_ids[i])))
        
        return update_data

    except Exception as e:
        logger.error(f"时间值为 {time_value} 的子进程在简单计算期间失败: {e}", exc_info=True)
        return []

def _parallel_spatial_derived_var_calc(args: Tuple) -> List[Tuple[float, int]]:
    """
    为单个帧计算空间公式，并将结果映射回原始点ID。
    此函数设计用于在单独的进程中运行。
    """
    time_value, db_path, time_variable, new_var_formula, x_formula, y_formula, grid_res, all_globals = args
    try:
        # 每个子进程创建自己的实例
        dm = DataManager()
        dm.setup_project_directory(os.path.dirname(db_path))
        dm.set_time_variable(time_variable)
        formula_engine = FormulaEngine()
        # 在刷新schema之前更新变量，以防公式依赖于新变量
        all_vars_from_db = dm.get_variables()
        formula_engine.update_allowed_variables(all_vars_from_db)
        formula_engine.update_custom_global_variables(all_globals)
        
        # 在get_frame_data之前刷新schema，确保'id'列可用
        dm.refresh_schema_info(include_id=True)
        frame_data = dm.get_frame_data(dm._get_sorted_time_values().index(time_value))

        if frame_data is None or frame_data.empty:
            return []

        # 使用核心计算函数获取最终的网格化场
        computation_result = compute_gridded_field(
            frame_data, new_var_formula, x_formula, y_formula, formula_engine, grid_res, use_gpu=False
        )
        
        result_grid = computation_result.get('result_data')
        grid_x = computation_result.get('grid_x')
        grid_y = computation_result.get('grid_y')

        if result_grid is None or grid_x is None or grid_y is None or np.all(np.isnan(result_grid)) :
            logger.warning(f"时间为 {time_value} 的帧未能为公式 '{new_var_formula}' 生成有效的网格")
            return []
            
        # 获取此帧的原始坐标以对网格进行采样
        original_x = formula_engine.evaluate_formula(frame_data, x_formula)
        original_y = formula_engine.evaluate_formula(frame_data, y_formula)
        points_to_sample = np.vstack([original_y, original_x]).T
        
        # 用于interpn的网格坐标
        grid_coords = (grid_y[:, 0], grid_x[0, :])
        
        # 在原始数据点位置对计算出的网格进行采样
        sampled_values = interpn(grid_coords, result_grid, points_to_sample, method='linear', bounds_error=False, fill_value=np.nan)
        
        # 将原始ID与新计算的值组合
        if 'id' not in frame_data.columns:
            logger.error(f"致命错误：在时间为 {time_value} 的帧数据中未找到 'id' 列。无法映射结果。")
            return []
            
        point_ids = frame_data['id'].values
        
        # 为UPDATE查询返回一个 (new_value, point_id) 列表
        update_data = []
        for i in range(len(point_ids)):
            if not np.isnan(sampled_values[i]):
                update_data.append((float(sampled_values[i]), int(point_ids[i])))
        
        return update_data

    except Exception as e:
        # 添加更详细的日志记录
        logger.error(f"时间值为 {time_value} 的子进程在空间计算期间失败。公式: '{new_var_formula}'. 错误: {e}", exc_info=True)
        return []

def _parallel_spatial_calc(args: Tuple) -> Tuple[Any, float]:
    """
    可被序列化并由子进程执行的函数。
    """
    time_value, db_path, time_variable, inner_expr, agg_func, base_globals = args
    try:
        # 每个子进程创建自己的 DataManager 和 FormulaEngine 实例
        dm = DataManager()
        dm.setup_project_directory(os.path.dirname(db_path))
        dm.set_time_variable(time_variable) # Ensure correct time axis
        formula_engine = FormulaEngine()
        formula_engine.update_allowed_variables(dm.get_variables())
        formula_engine.update_custom_global_variables(base_globals)
        
        # Fetch data for a specific time value
        frame_data = dm.get_frame_data(dm._get_sorted_time_values().index(time_value))
        if frame_data is None or frame_data.empty:
            return time_value, np.nan
        
        grid_comp = compute_gridded_field(frame_data, inner_expr, 'x', 'y', formula_engine, (100,100))
        result_grid = grid_comp.get('result_data')
        if result_grid is None:
            return time_value, np.nan
        
        with np.errstate(invalid='ignore'):
            if agg_func == 'mean': return time_value, np.nanmean(result_grid)
            if agg_func == 'sum': return time_value, np.nansum(result_grid)
            if agg_func == 'std': return time_value, np.nanstd(result_grid)
            if agg_func == 'var': return time_value, np.nanvar(result_grid)
            return time_value, np.nan
    except Exception as e:
        logger.error(f"子进程(时间值 {time_value}) 计算失败: {e}", exc_info=True)
        return time_value, np.nan

# --- End of helper function ---

class DatabaseImportWorker(QThread):
    """扫描CSV，导入数据库，并自动计算基础统计数据。"""
    progress = pyqtSignal(int, int, str)
    log_message = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self.formula_engine = formula_engine # Store the FormulaEngine instance
        self.is_cancelled = False
    
    def run(self):
        try:
            logger.info(f"后台数据库导入开始: 从 {self.dm.project_directory} 到 {self.dm.db_path}")
            csv_files = sorted([f for f in os.listdir(self.dm.project_directory) if f.lower().endswith('.csv')])
            if not csv_files:
                self.error.emit("目录中未找到任何CSV文件。"); return

            self.progress.emit(0, len(csv_files) + 2, f"分析 {csv_files[0]}...")
            df_sample = pd.read_csv(os.path.join(self.dm.project_directory, csv_files[0]), nrows=10)
            numeric_cols = df_sample.select_dtypes(include=np.number).columns.tolist()
            if not numeric_cols: raise ValueError("第一个CSV文件中未找到数值列。")
            all_cols = df_sample.columns.tolist()

            conn = self.dm.get_db_connection()
            self.dm.create_database_tables(conn)
            
            # Add frame_index and source_file columns to the definition
            cols_def_parts = [f'"{col}" REAL' for col in all_cols]
            table_def = f"""
                CREATE TABLE timeseries_data (
                    id INTEGER PRIMARY KEY,
                    frame_index INTEGER NOT NULL,
                    source_file TEXT,
                    {", ".join(cols_def_parts)}
                );
            """
            conn.execute("DROP TABLE IF EXISTS timeseries_data;") # Ensure fresh start
            conn.execute(table_def)
            conn.commit()

            for i, filename in enumerate(csv_files):
                if self.is_cancelled: break
                self.progress.emit(i + 1, len(csv_files) + 2, f"正在导入: {filename}")
                # Load all original columns
                df = pd.read_csv(os.path.join(self.dm.project_directory, filename), dtype={col: float for col in numeric_cols})
                df['frame_index'] = i
                df['source_file'] = filename
                # Ensure columns match the table schema order
                df_ordered = df[['frame_index', 'source_file'] + all_cols]
                df_ordered.to_sql('timeseries_data', conn, if_exists='append', index=False)
            
            if self.is_cancelled: conn.close(); os.remove(self.dm.db_path); return

            self.progress.emit(len(csv_files) + 1, len(csv_files) + 2, "创建索引...")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_frame ON timeseries_data (frame_index);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_coords ON timeseries_data (x, y);")
            conn.commit(); conn.close()
            
            self.log_message.emit("导入完成，正在计算基础统计数据...")
            self.dm.refresh_schema_info()
            # Calculate stats for all numeric columns found
            stats_worker = GlobalStatsWorker(self.dm, self.formula_engine, self.dm.get_time_candidates()) # Pass formula_engine
            stats_worker.progress.connect(lambda cur, tot, msg: self.progress.emit(len(csv_files) + 2, len(csv_files) + 2, f"统计: {msg}"))
            stats_worker.error.connect(self.error.emit)
            stats_worker.finished.connect(lambda: self.finished.emit())
            stats_worker.run()

        except Exception as e:
            logger.error(f"数据库导入失败: {e}", exc_info=True)
            self.error.emit(str(e))
            if self.dm.db_path and os.path.exists(self.dm.db_path):
                try:
                    # Ensure connection is closed before removing
                    if 'conn' in locals() and conn: conn.close()
                    os.remove(self.dm.db_path)
                except Exception as ce: logger.error(f"清理失败的DB文件时出错: {ce}")


class DerivedVariableWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, definitions: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self.definitions = definitions # List of (new_name, formula)
        self.formula_engine = FormulaEngine()

    def run(self):
        conn = None
        total_steps = len(self.definitions)

        try:
            conn = self.dm.get_db_connection()
            
            for i, (new_name, formula) in enumerate(self.definitions):
                safe_name = f'"{new_name}"'
                
                # Step 1: Add new column
                self.progress.emit(i, total_steps, f"步骤 {i+1}/{total_steps}: 准备计算 '{new_name}'...")
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(timeseries_data);")
                if any(col[1] == new_name for col in cursor.fetchall()):
                    logger.info(f"已存在的列 '{new_name}' 已被删除，将重新计算。")
                    cursor.execute(f"ALTER TABLE timeseries_data DROP COLUMN {safe_name};")
                cursor.execute(f"ALTER TABLE timeseries_data ADD COLUMN {safe_name} REAL;")
                conn.commit()

                # Step 2: Choose computation path and execute
                if any(f in formula for f in self.formula_engine.spatial_functions):
                    logger.info(f"检测到空间运算，为 '{new_name}' 切换到逐帧插值计算模式。")
                    self._run_parallel_computation(conn, new_name, formula, is_spatial=True, step_info=(i, total_steps))
                else:
                    logger.info(f"为 '{new_name}' 使用逐帧并行计算模式（支持复杂函数）。")
                    self._run_parallel_computation(conn, new_name, formula, is_spatial=False, step_info=(i, total_steps))
                
                # Step 3: Save definition and update stats for this variable
                self.dm.save_variable_definition(new_name, formula, "per-frame")
                self.dm.refresh_schema_info()
                self.formula_engine.update_allowed_variables(self.dm.get_variables()) # Make new var available for next formula

                stats_worker = GlobalStatsWorker(self.dm, self.formula_engine, [new_name])
                stats_worker.error.connect(lambda e: logger.error(f"计算 '{new_name}' 统计时出错: {e}"))
                stats_worker.run()
            
            self.progress.emit(total_steps, total_steps, "全部完成！")
            self.finished.emit()

        except Exception as e:
            logger.error(f"计算派生变量失败: {e}", exc_info=True)
            self.error.emit(str(e))
            # Cleanup is tricky in a loop, better to just report error
        finally:
            if conn:
                conn.close()

    def _run_parallel_computation(self, conn, new_name, formula, is_spatial, step_info):
        current_step, total_steps = step_info
        safe_name = f'"{new_name}"'
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(timeseries_data);")
        if 'id' not in [col[1] for col in cursor.fetchall()]:
            raise RuntimeError("数据表 'timeseries_data' 必须包含 'id' 主键。")

        time_values = self.dm._get_sorted_time_values()
        total_frames = len(time_values)
        if total_frames == 0: return

        # Load fresh globals before each calculation
        self.dm.load_global_stats()
        all_globals = self.dm.global_stats.copy()

        if is_spatial:
            x_formula, y_formula, grid_res = 'x', 'y', (150, 150)
            tasks = [(t_val, self.dm.db_path, self.dm.time_variable, formula, x_formula, y_formula, grid_res, all_globals) for t_val in time_values]
            worker_func = _parallel_spatial_derived_var_calc
        else:
            tasks = [(t_val, self.dm.db_path, self.dm.time_variable, formula, all_globals) for t_val in time_values]
            worker_func = _parallel_simple_derived_var_calc

        all_update_data = []
        processed_count = 0
        
        try:
            # [FIX] 限制最大工作进程数为CPU核心数的一半，以降低内存压力
            with ProcessPoolExecutor(max_workers=max(1, os.cpu_count() // 2)) as executor:
                future_to_frame = {executor.submit(worker_func, task): task[0] for task in tasks}
                for future in as_completed(future_to_frame):
                    try:
                        frame_results = future.result()
                        if frame_results:
                            all_update_data.extend(frame_results)
                    except Exception as exc:
                        # Log non-critical exceptions from individual futures
                        logger.error(f"子进程计算 '{new_name}' 时发生可捕获的异常: {exc}", exc_info=True)
                    
                    processed_count += 1
                    progress_msg = f"步骤 {current_step+1}/{total_steps} ('{new_name}'): 计算帧 {processed_count}/{total_frames}"
                    self.progress.emit(current_step, total_steps, progress_msg)
        except BrokenProcessPool as e:
            # Specifically catch BrokenProcessPool to give a more informative error
            logger.error(f"并行计算池在处理 '{new_name}' 时崩溃。这通常由内存不足或底层库（如SciPy）的严重错误引起。错误: {e}", exc_info=True)
            raise RuntimeError(f"并行计算池崩溃。请检查数据有效性（尤其是退化情况）和系统内存。")
        except Exception as e:
            logger.error(f"并行计算池在处理 '{new_name}' 时失败: {e}", exc_info=True)
            raise e

        if not all_update_data:
            raise ValueError(f"公式 '{formula}' 未对任何点计算出有效结果。请检查公式和数据。")

        progress_msg = f"步骤 {current_step+1}/{total_steps} ('{new_name}'): 写回 {len(all_update_data)} 个结果..."
        self.progress.emit(current_step, total_steps, progress_msg)
        
        update_query = f"UPDATE timeseries_data SET {safe_name} = ? WHERE id = ?"
        chunk_size = 50000
        for i in range(0, len(all_update_data), chunk_size):
            chunk = all_update_data[i:i + chunk_size]
            cursor.executemany(update_query, chunk)
            conn.commit()
            
class TimeAggregatedVariableWorker(QThread):
    """
    [OPTIMIZED] 为每个空间点计算时间聚合值，并将其作为新列添加。
    此版本使用高效的SQL操作，并支持批量计算。
    """
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, definitions: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self.formula_engine = formula_engine
        self.definitions = definitions # List of (new_name, formula)

    def _parse_formula(self, formula: str) -> Tuple[str, str]:
        """解析 'agg_func(expression)' 格式的公式。"""
        match = re.fullmatch(r'\s*(\w+)\s*\((.*)\)\s*', formula, re.DOTALL)
        if not match:
            raise ValueError(f"公式格式无效 '{formula}' (需要 agg_func(expression))")
        agg_func_str, inner_expr = match.groups()
        return agg_func_str.lower(), inner_expr.strip()

    def run(self):
        conn = None
        total_steps = len(self.definitions)

        try:
            conn = self.dm.get_db_connection()
            
            for i, (new_name, formula) in enumerate(self.definitions):
                self.progress.emit(i, total_steps, f"步骤 {i+1}/{total_steps}: 开始计算 '{new_name}'...")
                
                safe_name = f'"{new_name}"'
                temp_table_name = f"__temp_agg_{new_name.replace(' ', '_')}"
                
                agg_func, inner_expr = self._parse_formula(formula)
                
                agg_map = {'mean': 'AVG', 'sum': 'SUM', 'min': 'MIN', 'max': 'MAX'}
                sql_agg_func = agg_map.get(agg_func)
                is_variance = agg_func in ['var', 'std']

                if not sql_agg_func and not is_variance:
                    raise ValueError(f"不支持的时间聚合函数: '{agg_func}'. 支持: mean, sum, min, max, std, var")

                cursor = conn.cursor()
                
                # 1. Prepare database table
                self.progress.emit(i, total_steps, f"({i+1}.1) 准备 '{new_name}' 的数据库列...")
                cursor.execute("PRAGMA table_info(timeseries_data);")
                if any(col[1] == new_name for col in cursor.fetchall()):
                    cursor.execute(f"ALTER TABLE timeseries_data DROP COLUMN {safe_name};")
                cursor.execute(f"ALTER TABLE timeseries_data ADD COLUMN {safe_name} REAL;")
                conn.commit()

                if is_variance:
                    agg_expr = f"AVG(pow({inner_expr}, 2)) - pow(AVG({inner_expr}), 2)"
                    if agg_func == 'std':
                        agg_expr = f"SQRT({agg_expr})"
                else:
                    agg_expr = f"{sql_agg_func}({inner_expr})"

                # 2. Calculate aggregates into a temp table
                self.progress.emit(i, total_steps, f"({i+1}.2) 计算 '{new_name}' 的聚合值 (SQL)...")
                cursor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
                create_temp_query = f"""
                    CREATE TEMP TABLE {temp_table_name} AS
                    SELECT x, y, {agg_expr} as agg_value
                    FROM timeseries_data
                    GROUP BY x, y
                """
                cursor.execute(create_temp_query)
                
                # 3. Index temp table
                self.progress.emit(i, total_steps, f"({i+1}.3) 为临时数据创建索引...")
                cursor.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_temp_coords ON {temp_table_name} (x, y);")
                conn.commit()

                # 4. Update main table
                self.progress.emit(i, total_steps, f"({i+1}.4) 将聚合值写回主表...")
                update_query = f"""
                    UPDATE timeseries_data
                    SET {safe_name} = (
                        SELECT agg_value
                        FROM {temp_table_name}
                        WHERE {temp_table_name}.x = timeseries_data.x AND {temp_table_name}.y = timeseries_data.y
                    )
                """
                cursor.execute(update_query)
                conn.commit()
                
                # 5. Save definition and compute stats
                self.progress.emit(i, total_steps, f"({i+1}.5) 计算 '{new_name}' 的全局统计...")
                self.dm.save_variable_definition(new_name, formula, "time-aggregated")
                self.dm.refresh_schema_info() # Refresh schema for next loop iteration
                
                stats_worker = GlobalStatsWorker(self.dm, self.formula_engine, [new_name])
                stats_worker.error.connect(lambda e: logger.error(f"计算 '{new_name}' 统计时出错: {e}"))
                stats_worker.run()
            
            self.progress.emit(total_steps, total_steps, "全部完成！")
            self.finished.emit()

        except Exception as e:
            logger.error(f"计算时间聚合变量失败: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            if conn:
                try: # Cleanup last temp table if it exists
                    cursor = conn.cursor()
                    cursor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
                except Exception as e_cleanup:
                    logger.warning(f"清理临时表失败: {e_cleanup}")
                finally:
                    conn.close()


class BatchExportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log_message = pyqtSignal(str)
    summary_ready = pyqtSignal(str) 

    def __init__(self, config_files: List[str], data_manager: DataManager, output_dir: str, parent=None):
        super().__init__(parent); self.config_files, self.dm, self.output_dir = config_files, data_manager, output_dir; self.is_cancelled = False

    def run(self):
        successful, failed, skipped, total = 0, 0, 0, len(self.config_files)
        for i, filepath in enumerate(self.config_files):
            if self.is_cancelled: break
            filename = os.path.basename(filepath)
            self.progress.emit(i, total, filename); self.log_message.emit(f"读取配置: {filename}")
            try:
                with open(filepath, 'r', encoding='utf-8') as f: config = json.load(f)

                is_time_avg = config.get('analysis',{}).get('time_average',{}).get('enabled', False)
                if is_time_avg:
                    self.log_message.emit(f"跳过: {filename} (配置为时间平均场模式)")
                    skipped += 1
                    continue

                export_cfg = config.get("export", {})
                p_conf = {
                    'x_axis_formula': config.get('axes',{}).get('x_formula','x'), 'y_axis_formula': config.get('axes',{}).get('y_formula','y'),
                    'chart_title': config.get('axes',{}).get('title',''), 'use_gpu': config.get('performance',{}).get('gpu',False),
                    'heatmap_config': config.get('heatmap',{}), 'contour_config': config.get('contour',{}), 'vector_config': config.get('vector',{}),
                    'analysis': config.get('analysis',{}),
                    'grid_resolution': (export_cfg.get("video_grid_w",300), export_cfg.get("video_grid_h",300)),
                    'export_dpi': export_cfg.get("dpi",300), 'global_scope': self.dm.global_stats
                }
                s_f, e_f, fps = export_cfg.get("video_start_frame",0), export_cfg.get("video_end_frame",self.dm.get_frame_count()-1), export_cfg.get("video_fps",15)
                if s_f >= e_f: raise ValueError("起始帧需小于结束帧")

                out_fname = os.path.join(self.output_dir, f"batch_{os.path.splitext(filename)[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
                self.log_message.emit(f"准备导出: {os.path.basename(out_fname)}")
                
                vid_worker = VideoExportWorker(self.dm, p_conf, out_fname, s_f, e_f, fps)
                vid_worker.progress_updated.connect(lambda cur, tot, msg: self.log_message.emit(f"  └ {msg}"))
                vid_worker.run(); vid_worker.wait()

                if vid_worker.success: self.log_message.emit(f"成功: {filename}"); successful += 1
                else: self.log_message.emit(f"失败: {filename}. 原因: {vid_worker.message}"); failed += 1
            except Exception as e: self.log_message.emit(f"处理 '{filename}' 时发生严重错误: {e}"); failed += 1
        
        summary_message = f"成功导出 {successful} 个视频，失败 {failed} 个，跳过 {skipped} 个。"
        self.summary_ready.emit(summary_message)

    def cancel(self): self.is_cancelled = True

class GlobalStatsWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, vars_to_calc: List[str], parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self.formula_engine = formula_engine # Store the FormulaEngine instance
        self.vars_to_calc = vars_to_calc
        self.calculator = StatisticsCalculator(self.dm)

    def run(self):
        try:
            # Filter out non-numeric columns like 'source_file'
            numeric_vars = [v for v in self.vars_to_calc if v != 'source_file' and v != 'id']
            if not numeric_vars:
                self.finished.emit()
                return

            queries = self.calculator.get_global_stats_queries(numeric_vars)
            if not queries: self.finished.emit(); return
            
            stats_results = {}
            conn = self.dm.get_db_connection()
            total = len(queries)
            for i, (var, query) in enumerate(queries.items()):
                self.progress.emit(i + 1, total, f"变量: {var}")
                res = conn.execute(query).fetchone()
                mean, sum_val, min_val, max_val, var_val, std_val = res if res and all(r is not None for r in res) else (0,0,0,0,0,0)
                stats_results.update({f"{var}_global_mean": mean, f"{var}_global_sum": sum_val, f"{var}_global_min": min_val, f"{var}_global_max": max_val, f"{var}_global_var": var_val, f"{var}_global_std": std_val})

            conn.close()
            self.dm.save_global_stats(stats_results)
            self.finished.emit()
        except Exception as e:
            logger.error(f"全局统计计算失败: {e}", exc_info=True)
            self.error.emit(str(e))

class CustomGlobalStatsWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, formula_engine: FormulaEngine, definitions: List[str], parent=None):
        super().__init__(parent)
        self.calculator = StatisticsCalculator(data_manager)
        self.definitions, self.dm = definitions, data_manager
        self.formula_engine = formula_engine # Store the FormulaEngine instance

    def run(self):
        try:
            self.dm.load_global_stats()
            base_stats = self.dm.global_stats.copy()
            if not base_stats and any('global' in d for d in self.definitions): raise RuntimeError("计算前必须有基础统计数据。")
            
            new_stats, new_formulas = {}, {}
            
            # Execute definitions sequentially
            for i, definition in enumerate(self.definitions):
                # Update globals with results from previous definitions in this batch
                current_globals = {**base_stats, **new_stats}
                self.formula_engine.update_custom_global_variables(current_globals)

                name, formula, _ = self.calculator.parse_definition(definition)

                if any(sf in formula for sf in self.formula_engine.spatial_functions): # Use self.formula_engine
                    result = self._calculate_spatial_stats_parallel(name, formula, current_globals, i)
                else:
                    result = self._calculate_sql_stats(definition, current_globals, i)
                
                new_stats[name] = result
                new_formulas[name] = formula

            self.dm.save_global_stats(new_stats)
            self.dm.custom_global_formulas.update(new_formulas)
            self.finished.emit()
            
        except Exception as e:
            logger.error(f"自定义全局常量计算失败: {e}", exc_info=True)
            self.error.emit(str(e))

    def _calculate_sql_stats(self, definition, globals_dict, i):
        self.progress.emit(i+1, len(self.definitions), f"SQL: {definition}")
        _, _, query = self.calculator.get_custom_global_stats_query(definition, globals_dict)
        conn = self.dm.get_db_connection()
        result = conn.execute(query).fetchone()[0]
        conn.close()
        return result

    def _calculate_spatial_stats_parallel(self, name, formula, globals_dict, i):
        logger.info(f"并行空间运算: {formula}")
        agg_match = re.match(r'(\w+)\((.*)\)', formula)
        if not agg_match: raise ValueError("空间运算常量需含聚合函数(mean,sum等)。")
        
        agg_func, inner_expr = agg_match.groups()
        time_values = self.dm._get_sorted_time_values()
        frame_count = len(time_values)
        frame_results = []
        
        tasks = [(t_val, self.dm.db_path, self.dm.time_variable, inner_expr, agg_func, globals_dict) for t_val in time_values]
        
        processed_count = 0
        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            future_to_frame = {executor.submit(_parallel_spatial_calc, task): task[0] for task in tasks}
            for future in as_completed(future_to_frame):
                time_val, result = future.result()
                if not np.isnan(result):
                    frame_results.append(result)
                processed_count += 1
                msg = f"'{name}': 并行计算帧 {processed_count}/{frame_count}"
                # Use a finer-grained progress update
                self.progress.emit(i * frame_count + processed_count, len(self.definitions) * frame_count, msg)

        if not frame_results: raise ValueError(f"未能为 '{name}' 计算出有效结果。")
        return np.mean(frame_results)

class DataExportWorker(QThread):
    """后台导出数据到CSV的线程。"""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data_manager, filepath, filter_clause, parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self.filepath = filepath
        self.filter_clause = filter_clause.replace("AND", "", 1).strip() if filter_clause.startswith("AND") else filter_clause

    def run(self):
        try:
            conn = self.dm.get_db_connection()
            
            count_query = f"SELECT COUNT(*) FROM timeseries_data"
            if self.filter_clause: count_query += f" WHERE {self.filter_clause}"
            total_rows = conn.execute(count_query).fetchone()[0]
            if total_rows == 0: self.error.emit("没有符合过滤条件的数据可导出。"); return

            query = "SELECT * FROM timeseries_data"
            if self.filter_clause: query += f" WHERE {self.filter_clause}"
            
            logger.info(f"开始导出数据，查询: {query}")
            
            chunksize = 50000
            chunks = pd.read_sql_query(query, conn, chunksize=chunksize)
            
            is_first_chunk = True
            rows_written = 0
            for i, chunk in enumerate(chunks):
                mode = 'w' if is_first_chunk else 'a'
                header = is_first_chunk
                chunk.to_csv(self.filepath, mode=mode, header=header, index=False)
                is_first_chunk = False
                rows_written += len(chunk)
                self.progress.emit(rows_written, total_rows, f"已导出 {rows_written}/{total_rows} 行")

            conn.close()
            self.finished.emit()

        except Exception as e:
            logger.error(f"导出数据到CSV失败: {e}", exc_info=True)
            self.error.emit(str(e))