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
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from scipy.interpolate import interpn
import shutil

from PyQt6.QtCore import QThread, pyqtSignal

import pyarrow.parquet as pq
import pyarrow.dataset as ds
import pyarrow.compute as pc
import pyarrow as pa

from src.core.data_manager import DataManager
from src.core.statistics_calculator import StatisticsCalculator
from src.visualization.video_exporter import VideoExportWorker
from src.core.formula_engine import FormulaEngine
from src.core.computation_core import compute_gridded_field

logger = logging.getLogger(__name__)


# --- Helper functions for parallel processing (must be at top level) ---
def _parallel_spatial_calc(args: Tuple) -> Tuple[Any, float]:
    return 0, np.nan


class DatabaseImportWorker(QThread):
    """[UNCHANGED] Scans CSVs and imports them into a partitioned Parquet dataset."""
    progress = pyqtSignal(int, int, str)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self.dm = data_manager; self.is_cancelled = False
    
    def run(self):
        try:
            logger.info(f"后台Parquet数据集创建开始: 从 {self.dm.project_directory}")
            csv_files = sorted([f for f in os.listdir(self.dm.project_directory) if f.lower().endswith('.csv')])
            if not csv_files: self.error.emit("目录中未找到任何CSV文件。"); return

            dataset_name = f"raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            dataset_uri = os.path.join(self.dm.datasets_root_dir, dataset_name)
            os.makedirs(dataset_uri, exist_ok=True)
            self.log_message.emit(f"正在创建新的Parquet数据集: {dataset_name}")

            first_file_schema = None; total_files = len(csv_files)
            for i, filename in enumerate(csv_files):
                if self.is_cancelled: break
                self.progress.emit(i + 1, total_files, f"正在转换: {filename}")
                
                filepath = os.path.join(self.dm.project_directory, filename)
                df = pd.read_csv(filepath); df['frame_index'] = i
                table = pa.Table.from_pandas(df, preserve_index=False)
                
                if first_file_schema is None: first_file_schema = table.schema

                pq.write_to_dataset(table, root_path=dataset_uri, partition_cols=['frame_index'],
                                    schema=first_file_schema, existing_data_behavior='overwrite_or_ignore')

            if self.is_cancelled: shutil.rmtree(dataset_uri); self.error.emit("用户取消了导入操作。"); return
            
            self.log_message.emit("正在注册数据集元数据...")
            dataset_id = self.dm.register_dataset(dataset_name, dataset_uri, first_file_schema)
            
            self.log_message.emit("正在计算基础统计数据...")
            stats_worker = GlobalStatsWorker(self.dm, dataset_uri)
            stats_worker.progress.connect(self.progress)
            stats_worker.error.connect(self.error.emit)
            stats_worker.finished.connect(lambda: self.finished.emit(dataset_uri))
            stats_worker.run() # Run synchronously within this worker

        except Exception as e:
            logger.error(f"创建Parquet数据集失败: {e}", exc_info=True); self.error.emit(str(e))
            if 'dataset_uri' in locals() and os.path.exists(dataset_uri): shutil.rmtree(dataset_uri)


class DerivedVariableWorker(QThread):
    """[UNCHANGED] Reads a source Parquet dataset, computes new variables, and writes a new Parquet dataset."""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(str, str, object)
    error = pyqtSignal(str)

    def __init__(self, source_dataset_uri: str, output_dataset_uri: str, definitions: List[Tuple[str, str]], formula_engine: FormulaEngine, parent=None):
        super().__init__(parent)
        self.source_uri, self.output_uri = source_dataset_uri, output_dataset_uri
        self.output_name = os.path.basename(output_dataset_uri)
        self.definitions, self.formula_engine = definitions, formula_engine

    def run(self):
        try:
            source_dataset = ds.dataset(self.source_uri, format="parquet", partitioning=["frame_index"])
            source_schema = source_dataset.schema
            
            new_schema = source_schema
            for name, formula in self.definitions:
                if name not in new_schema.names: new_schema = new_schema.append(pa.field(name, pa.float64()))

            fragments = list(source_dataset.get_fragments()); total_fragments = len(fragments)
            
            for i, fragment in enumerate(fragments):
                self.progress.emit(i + 1, total_fragments, f"处理帧 {i+1}/{total_fragments}")
                table = fragment.to_table(); df = table.to_pandas()
                partition_value = int(str(fragment.partition_expression).split("=")[1].strip())
                df['frame_index'] = partition_value
                self.formula_engine.update_allowed_variables(list(df.columns))

                for new_name, formula in self.definitions: df[new_name] = self.formula_engine.evaluate_formula(df, formula)
                
                output_table = pa.Table.from_pandas(df, schema=new_schema, preserve_index=False)
                pq.write_to_dataset(output_table, root_path=self.output_uri, partition_cols=['frame_index'],
                                    schema=new_schema, existing_data_behavior='overwrite_or_ignore')

            logger.info(f"成功创建派生数据集: {self.output_uri}")
            self.finished.emit(self.output_uri, self.output_name, new_schema)
        except Exception as e:
            logger.error(f"创建派生数据集 '{self.output_name}' 失败: {e}", exc_info=True)
            self.error.emit(str(e))
            if os.path.exists(self.output_uri): shutil.rmtree(self.output_uri)


class GlobalStatsWorker(QThread):
    """[REWRITTEN] Calculates basic statistics for a Parquet dataset."""
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, data_manager: DataManager, dataset_uri: str, parent=None):
        super().__init__(parent)
        self.dm = data_manager
        self.dataset_uri = dataset_uri

    def run(self):
        try:
            dataset = ds.dataset(self.dataset_uri, format="parquet")
            schema = dataset.schema
            
            vars_to_calc = [field.name for field in schema if (field.type.is_floating() or field.type.is_integer()) and field.name != 'frame_index']
            if not vars_to_calc:
                self.finished.emit()
                return

            self.progress.emit(0, 1, "正在准备聚合查询...")
            aggregations = []
            for var in vars_to_calc:
                aggregations.append((var, "min"))
                aggregations.append((var, "max"))
                aggregations.append((var, "mean"))
            
            self.progress.emit(0, 1, "正在计算全局统计...")
            results_table = dataset.to_table().aggregate(aggregations)
            results = results_table.to_pydict()
            
            stats_to_save = {}
            for i, (var, agg_op) in enumerate(aggregations):
                # The result keys are like 'var_agg', e.g., 'u_min'
                result_key = f"{var}_{agg_op}"
                # Our convention is 'var_global_agg'
                db_key = f"{var}_global_{agg_op}"
                stats_to_save[db_key] = results[result_key][0]

            self.dm.save_global_stats(stats_to_save)
            self.progress.emit(1, 1, "统计数据已保存。")
            self.finished.emit()
        except Exception as e:
            logger.error(f"全局统计计算失败: {e}", exc_info=True)
            self.error.emit(str(e))


# --- Placeholder Workers ---
class TimeAggregatedVariableWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, *args, **kwargs): super().__init__(); self.error.emit("功能已禁用，待重构。")
    def run(self): pass

class BatchExportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log_message = pyqtSignal(str)
    summary_ready = pyqtSignal(str) 
    def __init__(self, *args, **kwargs): super().__init__(); self.summary_ready.emit("功能已禁用，待重构。")
    def run(self): pass

class CustomGlobalStatsWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, *args, **kwargs): super().__init__(); self.error.emit("功能已禁用，待重构。")
    def run(self): pass

class DataExportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, *args, **kwargs): super().__init__(); self.error.emit("功能已禁用，待重构。")
    def run(self): pass