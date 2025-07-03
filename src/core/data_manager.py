# src/core/data_manager.py

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pandas as pd
import numpy as np
import logging
import sqlite3
import zarr
from typing import Optional, List, Dict, Any, Generator, Tuple
from collections import OrderedDict
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

META_DB_FILENAME = "_intervis_meta.db"
ZARR_STORE_NAME = "_intervis_data.zarr"
METADATA_TABLE_NAME = "intervis_metadata"
CUSTOM_CONSTANTS_TABLE_NAME = "intervis_custom_constants"
VARIABLE_DEFINITIONS_TABLE_NAME = "intervis_variable_definitions"

class DataManager(QObject):
    """
    [REFACTORED] 负责数据库(元数据)和Zarr(时序数据)的连接、查询。
    """
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_directory: Optional[str] = None
        self.db_path: Optional[str] = None
        self.zarr_path: Optional[str] = None
        self.zarr_root: Optional[zarr.Group] = None
        
        self._variables: Optional[List[str]] = None
        self._frame_count: Optional[int] = None
        self._sorted_time_values: Optional[List] = None
        
        self.time_variable: str = "frame_index"
        
        self.global_stats: Dict[str, float] = {}
        self.custom_global_formulas: Dict[str, str] = {}
        
        self.global_filter_clause: str = ""

    def setup_project_directory(self, directory: str) -> bool:
        self.project_directory = directory
        self.db_path = os.path.join(self.project_directory, META_DB_FILENAME)
        self.zarr_path = os.path.join(self.project_directory, ZARR_STORE_NAME)
        
        if not os.path.isdir(self.project_directory):
            msg = f"项目目录不存在: {self.project_directory}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            return False
        
        self.clear_all()
        logger.info(f"项目目录已设置为: {self.project_directory}")
        
        if self.is_zarr_ready():
            try:
                self.zarr_root = zarr.open(self.zarr_path, mode='r')
            except Exception as e:
                logger.error(f"打开Zarr存储失败: {e}", exc_info=True)
                self.error_occurred.emit(f"无法读取数据存储: {e}")
                return False
        
        return True

    def is_database_ready(self) -> bool:
        return self.is_meta_db_ready() and self.is_zarr_ready()

    def is_meta_db_ready(self) -> bool:
        if self.db_path and os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'rb') as f:
                    return f.read(16) == b'SQLite format 3\x00'
            except Exception:
                return False
        return False
    
    def is_zarr_ready(self) -> bool:
        return self.zarr_path and os.path.isdir(self.zarr_path)

    def get_db_connection(self) -> sqlite3.Connection:
        if not self.db_path: raise ConnectionError("数据库路径未设置。")
        return sqlite3.connect(self.db_path, timeout=15)
    
    def create_database_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {METADATA_TABLE_NAME} (key TEXT PRIMARY KEY, value REAL NOT NULL);")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {CUSTOM_CONSTANTS_TABLE_NAME} (id INTEGER PRIMARY KEY, definition TEXT NOT NULL UNIQUE);")
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {VARIABLE_DEFINITIONS_TABLE_NAME} (name TEXT PRIMARY KEY, formula TEXT NOT NULL, type TEXT NOT NULL);")
        conn.commit()
        logger.info("数据库元数据、自定义常量和变量定义表已确认存在。")

    def post_import_setup(self):
        if self.is_zarr_ready():
            self.zarr_root = zarr.open(self.zarr_path, mode='r')
        self.refresh_schema_info()
        self.load_global_stats()
        time_candidates = self.get_time_candidates()
        if time_candidates:
            self.set_time_variable('frame_index' if 'frame_index' in time_candidates else time_candidates[0])
        logger.info("数据库和数据存储设置完成。")

    def refresh_schema_info(self, include_id=False):
        self._variables = None
        self._frame_count = None
        self._sorted_time_values = None
        self.get_frame_count()
        logger.info("DataManager schema info has been refreshed.")

    def set_global_filter(self, filter_text: str):
        # NOTE: Zarr filtering is complex. The clause is stored but not yet applied to computations.
        self.global_filter_clause = filter_text

    def set_time_variable(self, variable_name: str):
        if variable_name not in self.get_variables():
            msg = f"尝试将时间变量设置为不存在的列: {variable_name}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            return
            
        logger.info(f"时间轴变量已更改为: '{variable_name}'")
        self.time_variable = variable_name
        self._frame_count = None
        self._sorted_time_values = None

    def ensure_index_on(self, column_name: str):
        pass

    def _get_sorted_time_values(self) -> List:
        if self._sorted_time_values is None:
            if not self.zarr_root or self.time_variable not in self.zarr_root: return []
            try:
                time_data = self.zarr_root[self.time_variable][:, 0]
                self._sorted_time_values = sorted(list(pd.unique(time_data)))
            except Exception as e:
                logger.error(f"无法从Zarr获取时间变量 '{self.time_variable}' 的唯一值: {e}")
                self._sorted_time_values = []
        return self._sorted_time_values

    def get_frame_data(self, frame_index: int, required_columns: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
        if self.zarr_root is None or not (0 <= frame_index < self.get_frame_count()): return None

        if not required_columns: required_columns = self.get_variables(include_id=True)
        
        try:
            frame_data_dict = {col: self.zarr_root[col][frame_index, :] for col in required_columns if col in self.zarr_root}
            return pd.DataFrame(frame_data_dict)
        except Exception as e:
            msg = f"从Zarr存储加载帧 {frame_index} 数据失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(msg)
            return None

    def get_time_averaged_data(self, start_frame: int, end_frame: int) -> Optional[pd.DataFrame]:
        """[REIMPLEMENTED] 使用Zarr高效地计算时间平均场。"""
        if self.zarr_root is None or not (0 <= start_frame < self.get_frame_count() and 0 <= end_frame < self.get_frame_count() and start_frame <= end_frame):
            return None
        
        try:
            variables = self.get_variables()
            vars_to_avg = [var for var in variables if var not in ['id', self.time_variable, 'frame_index']]
            
            # 1. 获取参考坐标
            x_coords = self.zarr_root['x'][0, :]
            y_coords = self.zarr_root['y'][0, :]
            avg_df = pd.DataFrame({'x': x_coords, 'y': y_coords})

            # 2. 对每个变量，加载数据切片并计算平均值
            for var in vars_to_avg:
                if var in self.zarr_root:
                    # 加载时间范围内的所有数据
                    data_slice = self.zarr_root[var][start_frame : end_frame + 1, :]
                    # 沿时间轴（axis=0）计算平均值
                    mean_values = data_slice.mean(axis=0)
                    avg_df[var] = mean_values
            
            return avg_df
        except Exception as e:
            msg = f"计算时间平均场失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(msg)
            return None

    def get_timeseries_at_point(self, variable: str, point_coords: Tuple[float, float], tolerance: float) -> Optional[pd.DataFrame]:
        """[REIMPLEMENTED] 使用Zarr高效地获取单个点的时间序列。"""
        if self.zarr_root is None or variable not in self.zarr_root:
            raise ValueError(f"变量 '{variable}' 不存在。")
        
        try:
            x, y = point_coords
            x_min, x_max = x - tolerance, x + tolerance
            y_min, y_max = y - tolerance, y + tolerance

            # 1. 从第0帧加载所有坐标以找到空间点索引
            x_coords = self.zarr_root['x'][0, :]
            y_coords = self.zarr_root['y'][0, :]
            
            # 2. 找到在容差范围内的点的索引
            indices = np.where(
                (x_coords >= x_min) & (x_coords <= x_max) &
                (y_coords >= y_min) & (y_coords <= y_max)
            )[0]
            
            if indices.size == 0:
                logger.warning(f"在坐标({x:.2f}, {y:.2f})附近找不到任何数据点。")
                return pd.DataFrame(columns=[self.time_variable, variable])

            # 3. 使用高级索引从Zarr中一次性读取所有帧的、指定点的数据
            # 这是Zarr的一个非常强大的特性
            data_slice = self.zarr_root[variable][:, indices]
            
            # 4. 沿空间点轴（axis=1）计算平均值，得到时间序列
            time_series_values = data_slice.mean(axis=1)
            
            # 5. 获取时间轴数据
            time_values = self._get_sorted_time_values()

            # 6. 组合成DataFrame
            return pd.DataFrame({
                self.time_variable: time_values,
                variable: time_series_values
            })
            
        except Exception as e:
            msg = f"获取时间序列数据失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"时间序列查询失败: {e}")
            return None

    def get_frame_count(self) -> int:
        if self._frame_count is None:
            if self.zarr_root and self.get_variables():
                first_var = self.get_variables()[0]
                self._frame_count = self.zarr_root[first_var].shape[0]
            else: self._frame_count = 0
        return self._frame_count

    def get_frame_info(self, i: int) -> Optional[Dict[str, Any]]: 
        time_values = self._get_sorted_time_values()
        if not (0 <= i < len(time_values)): return None
        return {'path': f'zarr_frame_{i}', 'timestamp': time_values[i]}

    def get_cache_info(self) -> Dict: return {'size': 0, 'max_size': 0}
    def set_cache_size(self, size: int): pass
    def _enforce_cache_limit(self): pass

    def get_database_info(self) -> Dict[str, Any]:
        db_size_mb = os.path.getsize(self.db_path) / (1024*1024) if self.is_meta_db_ready() else 0
        zarr_size_mb = 0
        if self.is_zarr_ready():
            try:
                zarr_size_mb = zarr.open(self.zarr_path, mode='r').nbytes / (1024*1024)
            except Exception: pass
        
        return {
            "db_path": self.db_path, "zarr_path": self.zarr_path,
            "is_ready": self.is_database_ready(), "frame_count": self.get_frame_count(),
            "variables": self.get_variables(), "db_size_mb": db_size_mb,
            "zarr_size_mb": zarr_size_mb, "global_filter": self.global_filter_clause
        }

    def get_variables(self, include_id: bool = False) -> List[str]:
        if self._variables is None:
            if self.zarr_root: self._variables = sorted(list(self.zarr_root.keys()))
            else: self._variables = []
        
        return self._variables if include_id else [col for col in self._variables if col != 'id']

    def get_time_candidates(self) -> List[str]:
        if not self.is_zarr_ready(): return []
        return self.get_variables()

    def clear_all(self):
        if self.zarr_root:
            try: self.zarr_root.store.close()
            except Exception: pass
        
        self.zarr_root = None
        self._variables = None; self._frame_count = None; self._sorted_time_values = None
        self.time_variable = "frame_index"
        self.clear_global_stats()
        self.global_filter_clause = ""
        logger.info("DataManager 状态已清除。")

    def delete_variable(self, var_name: str):
        core_vars = {'x', 'y', 'id', 'frame_index', 'source_file'}
        if var_name in core_vars: raise ValueError(f"无法删除核心变量 '{var_name}'。")

        try:
            with zarr.open(self.zarr_path, mode='a') as root:
                if var_name in root: del root[var_name]
        except Exception as e: raise RuntimeError(f"从Zarr删除变量 '{var_name}' 失败: {e}")

        conn = self.get_db_connection()
        try:
            cursor = conn.cursor(); cursor.execute("BEGIN TRANSACTION;")
            cursor.execute(f"DELETE FROM {METADATA_TABLE_NAME} WHERE key LIKE ?", (f"{var_name}_global_%",))
            cursor.execute(f"DELETE FROM {VARIABLE_DEFINITIONS_TABLE_NAME} WHERE name = ?", (var_name,))
            conn.commit()
        except Exception as e:
            conn.rollback(); raise RuntimeError(f"数据库操作失败: {e}")
        finally: conn.close()
        
        self.refresh_schema_info(); self.load_global_stats()

    def rename_variable(self, old_name: str, new_name: str):
        core_vars = {'x', 'y', 'id', 'frame_index', 'source_file'}
        if old_name in core_vars: raise ValueError(f"无法重命名核心变量 '{old_name}'。")
        if not new_name.isidentifier(): raise ValueError(f"新名称 '{new_name}' 不是一个有效的标识符。")
        if new_name in self.get_variables(): raise ValueError(f"变量名 '{new_name}' 已存在。")

        try:
            with zarr.open(self.zarr_path, mode='a') as root:
                if old_name in root: root.move(old_name, new_name)
        except Exception as e: raise RuntimeError(f"重命名Zarr数组失败: {e}")

        conn = self.get_db_connection()
        try:
            cursor = conn.cursor(); cursor.execute("BEGIN TRANSACTION;")
            cursor.execute(f"SELECT key FROM {METADATA_TABLE_NAME} WHERE key LIKE ?", (f"{old_name}_global_%",))
            keys_to_update = [row[0] for row in cursor.fetchall()]
            updates = [(key.replace(f"{old_name}_global_", f"{new_name}_global_", 1), key) for key in keys_to_update]
            if updates: cursor.executemany(f"UPDATE {METADATA_TABLE_NAME} SET key = ? WHERE key = ?", updates)
            cursor.execute(f"UPDATE {VARIABLE_DEFINITIONS_TABLE_NAME} SET name = ? WHERE name = ?", (new_name, old_name))
            conn.commit()
        except Exception as e:
            conn.rollback()
            with zarr.open(self.zarr_path, mode='a') as root:
                if new_name in root: root.move(new_name, old_name)
            raise RuntimeError(f"数据库操作失败: {e}")
        finally: conn.close()

        self.refresh_schema_info(); self.load_global_stats()
        
    def save_global_stats(self, stats: Dict[str, float]):
        if not self.db_path: return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            data_to_insert = list(stats.items())
            cursor.executemany(f"INSERT OR REPLACE INTO {METADATA_TABLE_NAME} (key, value) VALUES (?, ?)", data_to_insert)
            conn.commit()
            conn.close()
            logger.info(f"成功将 {len(stats)} 条统计数据保存到数据库。")
            self.global_stats.update(stats)
        except Exception as e:
            logger.error(f"保存全局统计数据失败: {e}", exc_info=True)

    def load_global_stats(self):
        if not self.is_meta_db_ready(): return
        try:
            conn = self.get_db_connection()
            cursor = conn.execute(f"SELECT key, value FROM {METADATA_TABLE_NAME}")
            self.global_stats = dict(cursor.fetchall())
            conn.close()
            logger.info(f"从数据库加载了 {len(self.global_stats)} 条全局统计数据。")
        except Exception as e:
            logger.error(f"加载全局统计数据失败: {e}", exc_info=True)
            self.global_stats = {}

    def save_custom_definitions(self, definitions: List[str]):
        if not self.db_path: return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {CUSTOM_CONSTANTS_TABLE_NAME}")
            data_to_insert = [(d,) for d in definitions]
            if data_to_insert:
                cursor.executemany(f"INSERT INTO {CUSTOM_CONSTANTS_TABLE_NAME} (definition) VALUES (?)", data_to_insert)
            conn.commit()
            conn.close()
        except Exception as e: logger.error(f"保存自定义常量定义失败: {e}", exc_info=True)

    def load_custom_definitions(self) -> List[str]:
        if not self.is_meta_db_ready(): return []
        try:
            conn = self.get_db_connection()
            cursor = conn.execute(f"SELECT definition FROM {CUSTOM_CONSTANTS_TABLE_NAME} ORDER BY id")
            definitions = [row[0] for row in cursor.fetchall()]
            conn.close()
            return definitions
        except Exception as e:
            logger.error(f"加载自定义常量定义失败: {e}", exc_info=True)
            return []

    def delete_global_stats(self, stat_names: List[str]):
        if not self.db_path or not stat_names: return
        try:
            conn = self.get_db_connection()
            placeholders = ','.join('?' for _ in stat_names)
            conn.execute(f"DELETE FROM {METADATA_TABLE_NAME} WHERE key IN ({placeholders})", stat_names)
            conn.commit(); conn.close()
            for name in stat_names: self.global_stats.pop(name, None)
        except Exception as e: logger.error(f"删除全局统计数据失败: {e}", exc_info=True)

    def save_variable_definition(self, name: str, formula: str, type_str: str):
        if not self.db_path: return
        try:
            conn = self.get_db_connection()
            conn.execute(f"INSERT OR REPLACE INTO {VARIABLE_DEFINITIONS_TABLE_NAME} (name, formula, type) VALUES (?, ?, ?)", (name, formula, type_str))
            conn.commit(); conn.close()
        except Exception as e: logger.error(f"保存变量 '{name}' 的定义失败: {e}", exc_info=True)

    def load_variable_definitions(self) -> Dict[str, Dict[str, str]]:
        if not self.is_meta_db_ready(): return {}
        try:
            conn = self.get_db_connection()
            cursor = conn.execute(f"SELECT name, formula, type FROM {VARIABLE_DEFINITIONS_TABLE_NAME}")
            definitions = {row[0]: {'formula': row[1], 'type': row[2]} for row in cursor.fetchall()}
            conn.close()
            return definitions
        except Exception as e:
            logger.error(f"加载变量定义失败: {e}", exc_info=True)
            return {}

    def clear_global_stats(self):
        self.global_stats.clear(); self.custom_global_formulas.clear()