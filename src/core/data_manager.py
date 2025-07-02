#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import pandas as pd
import logging
import sqlite3
import shutil
from typing import Optional, List, Dict, Any, Tuple
from collections import OrderedDict
from PyQt6.QtCore import QObject, pyqtSignal

import pyarrow.parquet as pq
import pyarrow.dataset as ds
import pyarrow.compute as pc
import pyarrow as pa

logger = logging.getLogger(__name__)

METADATA_DB_FILENAME = "_intervis_metadata.db"
DATASETS_DIR_NAME = "datasets"
PROJECT_METADATA_TABLE = "project_metadata"
DATASETS_TABLE = "datasets"
VARIABLES_TABLE = "variables"


class DataManager(QObject):
    """负责管理项目中的多个Parquet数据集，并与元数据数据库交互。"""
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_directory: Optional[str] = None; self.metadata_db_path: Optional[str] = None
        self.datasets_root_dir: Optional[str] = None
        self.cache: OrderedDict[tuple, pd.DataFrame] = OrderedDict(); self.cache_max_size = 100
        self.active_dataset_uri: Optional[str] = None; self.active_dataset_schema: Optional[pa.Schema] = None
        self._frame_count: Optional[int] = None; self._sorted_time_values: Optional[List] = None
        self._time_value_map: Optional[Dict] = None
        self.time_variable: str = "frame_index"; self.global_stats: Dict[str, float] = {}
        self.filter_expression: Optional[pc.Expression] = None

    def setup_project_directory(self, directory: str) -> bool:
        self.project_directory = directory
        self.metadata_db_path = os.path.join(self.project_directory, METADATA_DB_FILENAME)
        self.datasets_root_dir = os.path.join(self.project_directory, DATASETS_DIR_NAME)
        os.makedirs(self.datasets_root_dir, exist_ok=True); self.clear_all()
        try: self.create_metadata_tables()
        except Exception as e:
            msg = f"初始化元数据数据库失败: {e}"; logger.error(msg, exc_info=True)
            self.error_occurred.emit(msg); return False
        logger.info(f"项目目录已设置为: {self.project_directory}"); return True

    def is_project_ready(self) -> bool:
        if self.metadata_db_path and os.path.exists(self.metadata_db_path) and self.datasets_root_dir and os.path.isdir(self.datasets_root_dir):
            with self.get_db_connection() as conn:
                try: return conn.execute(f"SELECT COUNT(id) FROM {DATASETS_TABLE}").fetchone()[0] > 0
                except sqlite3.Error: return False
        return False

    def get_db_connection(self) -> sqlite3.Connection:
        if not self.metadata_db_path: raise ConnectionError("元数据数据库路径未设置。")
        return sqlite3.connect(self.metadata_db_path, timeout=15)

    def create_metadata_tables(self):
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {PROJECT_METADATA_TABLE} (key TEXT PRIMARY KEY, value REAL NOT NULL);")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {DATASETS_TABLE} (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, uri TEXT NOT NULL, parent_id INTEGER, created_at TEXT NOT NULL, FOREIGN KEY (parent_id) REFERENCES {DATASETS_TABLE}(id) ON DELETE CASCADE);")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {VARIABLES_TABLE} (id INTEGER PRIMARY KEY, dataset_id INTEGER NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL, formula TEXT, FOREIGN KEY (dataset_id) REFERENCES {DATASETS_TABLE}(id) ON DELETE CASCADE);")
            conn.commit()

    def register_dataset(self, name: str, uri: str, schema: pa.Schema, parent_id: Optional[int] = None, variable_source: str = "raw") -> int:
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"INSERT INTO {DATASETS_TABLE} (name, uri, parent_id, created_at) VALUES (?, ?, ?, datetime('now', 'localtime'))", (name, uri, parent_id))
            dataset_id = cursor.lastrowid
            var_records = [(dataset_id, var_name, variable_source, None) for var_name in schema.names if var_name != 'frame_index']
            cursor.executemany(f"INSERT INTO {VARIABLES_TABLE} (dataset_id, name, type, formula) VALUES (?, ?, ?, ?)", var_records)
            conn.commit()
            return dataset_id

    def set_active_dataset(self, uri: Optional[str] = None):
        if not uri: # If URI is none, load the latest one
            with self.get_db_connection() as conn:
                latest_uri = conn.execute(f"SELECT uri FROM {DATASETS_TABLE} ORDER BY id DESC LIMIT 1").fetchone()
                uri = latest_uri[0] if latest_uri else None
        
        if not uri: self.active_dataset_uri = None; return

        self.active_dataset_uri = uri; self.cache.clear()
        self.active_dataset_schema = None; self._frame_count = None
        self._sorted_time_values = None; self._time_value_map = None
        
        self._get_active_schema(); self.set_time_variable(self.time_variable)
        logger.info(f"活动数据集已设置为: {self.active_dataset_uri}")

    def _get_active_dataset_object(self) -> Optional[ds.Dataset]:
        if not self.active_dataset_uri: return None
        try: return ds.dataset(self.active_dataset_uri, format="parquet", partitioning=["frame_index"])
        except Exception as e:
            logger.error(f"无法加载Parquet数据集 at '{self.active_dataset_uri}': {e}", exc_info=True)
            self.error_occurred.emit(f"无法加载Parquet数据集: {e}"); return None

    def _get_active_schema(self) -> pa.Schema:
        if self.active_dataset_schema is None:
            dataset = self._get_active_dataset_object()
            if dataset: self.active_dataset_schema = dataset.schema
        return self.active_dataset_schema

    def get_variables(self) -> List[str]:
        schema = self._get_active_schema()
        return schema.names if schema else []

    def get_time_candidates(self) -> List[str]:
        schema = self._get_active_schema()
        if not schema: return []
        return ['frame_index'] + [name for name in schema.names if pa.types.is_numeric(schema.field(name).type) and name != 'frame_index']
        
    def set_time_variable(self, variable_name: str):
        if variable_name not in self.get_variables(): variable_name = 'frame_index'
        self.time_variable = variable_name; self._sorted_time_values = None
        self._time_value_map = None; self.cache.clear(); self.get_frame_count()

    def _get_sorted_time_values(self) -> List:
        if self._sorted_time_values is not None: return self._sorted_time_values
        dataset = self._get_active_dataset_object()
        if not dataset: self._sorted_time_values = []; return []
        
        if self.time_variable == 'frame_index':
            partitions = [int(f.path.split('=')[-1]) for f in dataset.get_fragments()]
            self._sorted_time_values = sorted(partitions); self._time_value_map = {val: val for val in self._sorted_time_values}
        else:
            try:
                logger.info(f"为时间轴变量 '{self.time_variable}' 构建排序映射...")
                table = dataset.to_table(columns=[self.time_variable, 'frame_index'])
                df_sorted = table.to_pandas().sort_values(by=self.time_variable).drop_duplicates(subset=[self.time_variable], keep='first')
                self._sorted_time_values = df_sorted[self.time_variable].tolist()
                self._time_value_map = pd.Series(df_sorted['frame_index'].values, index=df_sorted[self.time_variable]).to_dict()
            except Exception as e:
                logger.error(f"为时间轴变量 '{self.time_variable}' 读取数据失败: {e}"); self.error_occurred.emit(f"无法使用 '{self.time_variable}'作为时间轴。")
                self.time_variable = 'frame_index'; return self._get_sorted_time_values()
        return self._sorted_time_values

    def get_frame_count(self) -> int:
        if self._frame_count is None: self._frame_count = len(self._get_sorted_time_values())
        return self._frame_count

    def get_frame_data(self, frame_index: int) -> Optional[pd.DataFrame]:
        time_values = self._get_sorted_time_values()
        if not (0 <= frame_index < len(time_values)): return None
        
        time_value = time_values[frame_index]
        cache_key = (self.active_dataset_uri, frame_index, self.time_variable, str(self.filter_expression))
        if cache_key in self.cache: self.cache.move_to_end(cache_key); return self.cache[cache_key]
        
        dataset = self._get_active_dataset_object();
        if not dataset: return None

        try:
            if self.time_variable == 'frame_index': filter_exp = (ds.field('frame_index') == time_value)
            else: physical_frame_index = self._time_value_map[time_value]; filter_exp = (ds.field('frame_index') == physical_frame_index)

            final_filter = filter_exp & self.filter_expression if self.filter_expression is not None else filter_exp
            
            table = dataset.to_table(filter=final_filter)
            df = table.to_pandas()
            if 'frame_index' not in df.columns: df['frame_index'] = self._time_value_map[time_value] if self.time_variable != 'frame_index' else time_value
            self.cache[cache_key] = df; self._enforce_cache_limit(); return df
        except Exception as e:
            msg = f"从Parquet加载帧 {frame_index} 失败: {e}"; logger.error(msg, exc_info=True); self.error_occurred.emit(msg); return None

    def get_time_averaged_data(self, start_frame: int, end_frame: int) -> Optional[pd.DataFrame]:
        time_values = self._get_sorted_time_values()
        if not (0 <= start_frame < len(time_values) and 0 <= end_frame < len(time_values) and start_frame <= end_frame): return None
        dataset = self._get_active_dataset_object();
        if not dataset: return None
        
        try:
            phys_indices = [self._time_value_map.get(t, t) for t in time_values[start_frame:end_frame+1]]
            frame_filter = ds.field('frame_index').isin(phys_indices)
            final_filter = frame_filter & self.filter_expression if self.filter_expression is not None else frame_filter
            
            vars_to_avg = [name for name in self.get_variables() if name not in ['x', 'y', self.time_variable, 'frame_index']]
            aggregations = [(var, "mean") for var in vars_to_avg]
            avg_table = dataset.to_table(filter=final_filter).group_by(['x', 'y']).aggregate(aggregations)
            df = avg_table.to_pandas(); df.columns = [c.replace('_mean', '') for c in df.columns]
            return df
        except Exception as e: msg = f"计算时间平均场失败: {e}"; logger.error(msg, exc_info=True); self.error_occurred.emit(msg); return None

    def get_timeseries_at_point(self, variable: str, point_coords: Tuple[float, float], tolerance: float) -> Optional[pd.DataFrame]:
        if variable not in self.get_variables(): raise ValueError(f"变量 '{variable}' 不存在。")
        dataset = self._get_active_dataset_object();
        if not dataset: return None
        
        x, y = point_coords
        point_filter = (pc.abs(ds.field('x') - x) <= tolerance) & (pc.abs(ds.field('y') - y) <= tolerance)
        final_filter = point_filter & self.filter_expression if self.filter_expression is not None else point_filter

        try:
            table = dataset.to_table(filter=final_filter, columns=[self.time_variable, variable])
            df = table.group_by(self.time_variable).aggregate([(variable, "mean")]).to_pandas()
            df.rename(columns={f'{variable}_mean': variable}, inplace=True); df.sort_values(by=self.time_variable, inplace=True)
            return df
        except Exception as e: msg = f"获取时间序列数据失败: {e}"; logger.error(msg, exc_info=True); self.error_occurred.emit(msg); return None

    def set_global_filter(self, filter_string: str):
        if not filter_string.strip(): self.filter_expression = None; self.cache.clear(); return
        try:
            # Simple parser for "VAR OP VAL (AND ...)" syntax
            expression = None
            for part in filter_string.split(" AND "):
                part = part.strip().replace('`', '')
                match = re.match(r"(\w+)\s*([<>=!]+)\s*(-?[\d.eE]+)", part)
                if not match: raise ValueError(f"无法解析过滤条件: '{part}'")
                var, op, val = match.groups()
                val = float(val)
                op_map = {'>': pc.greater, '>=': pc.greater_equal, '<': pc.less, '<=': pc.less_equal, '==': pc.equal, '!=': pc.not_equal}
                if op not in op_map: raise ValueError(f"不支持的操作符: '{op}'")
                
                term = op_map[op](ds.field(var), val)
                expression = expression & term if expression is not None else term
            self.filter_expression = expression
            self.cache.clear()
            logger.info(f"全局过滤器已设置为: {self.filter_expression}")
        except Exception as e: raise ValueError(f"设置过滤器失败: {e}")

    def get_all_datasets_info(self) -> List[Dict]:
        with self.get_db_connection() as conn:
            return conn.execute(f"SELECT id, name, uri, parent_id, created_at FROM {DATASETS_TABLE} ORDER BY id").fetchall()

    def delete_dataset(self, dataset_id: int):
        with self.get_db_connection() as conn:
            uri_to_delete = conn.execute(f"SELECT uri FROM {DATASETS_TABLE} WHERE id=?", (dataset_id,)).fetchone()
            if not uri_to_delete: raise FileNotFoundError("在数据库中找不到要删除的数据集ID。")
            
            # Delete DB entry (cascades to variables table)
            conn.execute(f"DELETE FROM {DATASETS_TABLE} WHERE id=?", (dataset_id,))
            conn.commit()
            
            # Delete files from disk
            if os.path.isdir(uri_to_delete[0]):
                shutil.rmtree(uri_to_delete[0])
                logger.info(f"已从磁盘删除数据集: {uri_to_delete[0]}")

    def save_global_stats(self, stats: Dict[str, float]):
        if not self.metadata_db_path: return
        with self.get_db_connection() as conn:
            conn.executemany(f"INSERT OR REPLACE INTO {PROJECT_METADATA_TABLE} (key, value) VALUES (?, ?)", list(stats.items()))
            conn.commit()
        self.global_stats.update(stats)

    def load_global_stats(self):
        with self.get_db_connection() as conn: self.global_stats = dict(conn.execute(f"SELECT key, value FROM {PROJECT_METADATA_TABLE}").fetchall())

    def _enforce_cache_limit(self):
        while len(self.cache) > self.cache_max_size: self.cache.popitem(last=False)
    def set_cache_size(self, size: int): self.cache_max_size = max(1, size); self._enforce_cache_limit()
    def get_frame_info(self, i: int) -> Optional[Dict[str, Any]]: 
        time_values = self._get_sorted_time_values()
        if not (0 <= i < len(time_values)): return None
        return {'path': f'dataset_frame_{i}', 'timestamp': time_values[i]}
    def get_cache_info(self) -> Dict: return {'size': len(self.cache), 'max_size': self.cache_max_size}
    def get_database_info(self) -> Dict[str, Any]:
        return {"db_path": self.metadata_db_path, "is_ready": self.is_project_ready(), "frame_count": self.get_frame_count(), "variables": self.get_variables(), "active_dataset": self.active_dataset_uri}
    def clear_all(self):
        self.active_dataset_uri=None; self.active_dataset_schema=None; self._variables=None; self._frame_count=None; self._sorted_time_values=None; self._time_value_map=None; self.time_variable="frame_index"; self.cache.clear(); self.global_stats.clear(); self.filter_expression=None; logger.info("DataManager 状态已清除。")
    def delete_project_data(self):
        self.clear_all()
        if self.metadata_db_path and os.path.exists(self.metadata_db_path): os.remove(self.metadata_db_path)
        if self.datasets_root_dir and os.path.isdir(self.datasets_root_dir): shutil.rmtree(self.datasets_root_dir)
        os.makedirs(self.datasets_root_dir, exist_ok=True); self.create_metadata_tables()