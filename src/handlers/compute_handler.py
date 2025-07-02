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
import pyarrow as pa

from src.core.data_manager import DataManager
from src.core.statistics_calculator import StatisticsCalculator
from src.visualization.video_exporter import VideoExportWorker
from src.core.formula_engine import FormulaEngine
from src.core.computation_core import compute_gridded_field

logger = logging.getLogger(__name__)


# --- Helper functions for parallel processing (must be at top level) ---
# NOTE: These are still placeholders and will be re-implemented later.
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
            self.dm.register_dataset(dataset_name, dataset_uri, first_file_schema)
            self.log_message.emit("基础统计计算将在后续步骤中实现。")
            self.finished.emit(dataset_uri)
        except Exception as e:
            logger.error(f"创建Parquet数据集失败: {e}", exc_info=True); self.error.emit(str(e))
            if 'dataset_uri' in locals() and os.path.exists(dataset_uri): shutil.rmtree(dataset_uri)


class DerivedVariableWorker(QThread):
    """[REWRITTEN] Reads a source Parquet dataset, computes new variables, and writes a new Parquet dataset."""
    progress = pyqtSignal(int, int, str)
    # Returns: output_uri, output_name, output_schema
    finished = pyqtSignal(str, str, object)
    error = pyqtSignal(str)

    def __init__(self, source_dataset_uri: str, output_dataset_uri: str, definitions: List[Tuple[str, str]], formula_engine: FormulaEngine, parent=None):
        super().__init__(parent)
        self.source_uri = source_dataset_uri
        self.output_uri = output_dataset_uri
        self.output_name = os.path.basename(output_dataset_uri)
        self.definitions = definitions
        self.formula_engine = formula_engine

    def run(self):
        try:
            source_dataset = ds.dataset(self.source_uri, format="parquet", partitioning=["frame_index"])
            source_schema = source_dataset.schema
            
            # 1. Determine the new schema
            new_schema = source_schema
            for name, formula in self.definitions:
                if name not in new_schema.names:
                    new_schema = new_schema.append(pa.field(name, pa.float64()))

            # 2. Process fragments one by one
            fragments = list(source_dataset.get_fragments())
            total_fragments = len(fragments)
            
            for i, fragment in enumerate(fragments):
                self.progress.emit(i + 1, total_fragments, f"处理帧 {i+1}/{total_fragments}")
                
                # Read fragment into a pandas DataFrame
                table = fragment.to_table()
                df = table.to_pandas()
                
                # Attach partition key back as a column
                partition_value = int(str(fragment.partition_expression).split("=")[1].strip())
                df['frame_index'] = partition_value

                # Update formula engine with current data columns
                self.formula_engine.update_allowed_variables(list(df.columns))

                # Calculate all new variables for this fragment
                for new_name, formula in self.definitions:
                    # evaluate_formula now directly works on the dataframe
                    df[new_name] = self.formula_engine.evaluate_formula(df, formula)
                
                # Convert back to pyarrow Table with the new, full schema
                output_table = pa.Table.from_pandas(df, schema=new_schema, preserve_index=False)
                
                # Write to the output dataset
                pq.write_to_dataset(
                    output_table,
                    root_path=self.output_uri,
                    partition_cols=['frame_index'],
                    schema=new_schema,
                    existing_data_behavior='overwrite_or_ignore'
                )

            logger.info(f"成功创建派生数据集: {self.output_uri}")
            self.finished.emit(self.output_uri, self.output_name, new_schema)

        except Exception as e:
            logger.error(f"创建派生数据集 '{self.output_name}' 失败: {e}", exc_info=True)
            self.error.emit(str(e))
            # Clean up partially created dataset
            if os.path.exists(self.output_uri):
                shutil.rmtree(self.output_uri)


# NOTE: The following workers are now obsolete in their current form.
# They will be completely rewritten in the next steps. For now, they are
# left here to avoid breaking imports, but they should not be called.

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

class GlobalStatsWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    def __init__(self, *args, **kwargs): super().__init__(); self.error.emit("功能已禁用，待重构。")
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