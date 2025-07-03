#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pandas as pd
import logging
import sqlite3
from typing import Optional, List, Dict, Any, Generator, Tuple
from collections import OrderedDict
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

DB_FILENAME = "_intervis_data.db"
METADATA_TABLE_NAME = "intervis_metadata"
CUSTOM_CONSTANTS_TABLE_NAME = "intervis_custom_constants"
VARIABLE_DEFINITIONS_TABLE_NAME = "intervis_variable_definitions" # 新增

class DataManager(QObject):
    """
    负责数据库的连接、查询和数据缓存。
    """
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_directory: Optional[str] = None
        self.db_path: Optional[str] = None
        
        self.cache: OrderedDict[int, pd.DataFrame] = OrderedDict()
        self.cache_max_size = 100
        
        self._variables: Optional[List[str]] = None
        self._frame_count: Optional[int] = None
        self._sorted_time_values: Optional[List] = None
        
        self.time_variable: str = "frame_index" # Default time variable
        
        self.global_stats: Dict[str, float] = {}
        self.custom_global_formulas: Dict[str, str] = {}
        
        self.global_filter_clause: str = ""

    def setup_project_directory(self, directory: str) -> bool:
        """设置项目目录并检查数据库状态。"""
        self.project_directory = directory
        self.db_path = os.path.join(self.project_directory, DB_FILENAME)
        
        if not os.path.isdir(self.project_directory):
            msg = f"项目目录不存在: {self.project_directory}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            return False
        
        self.clear_all()
        logger.info(f"项目目录已设置为: {self.project_directory}")
        return True

    def is_database_ready(self) -> bool:
        """检查数据库文件是否存在且有效。"""
        if self.db_path and os.path.exists(self.db_path):
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='timeseries_data';")
                if cursor.fetchone() is None:
                    conn.close(); return False
                conn.close(); return True
            except sqlite3.DatabaseError:
                logger.warning(f"数据库文件 {self.db_path} 已损坏或无效。")
                return False
        return False
        
    def get_db_connection(self) -> sqlite3.Connection:
        """返回一个新的数据库连接。调用者负责关闭连接。"""
        if not self.db_path: raise ConnectionError("数据库路径未设置。")
        return sqlite3.connect(self.db_path, timeout=15)
    
    def create_database_tables(self, conn: sqlite3.Connection):
        """创建所有必需的表，如果它们不存在的话。"""
        cursor = conn.cursor()
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {METADATA_TABLE_NAME} (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        );
        """)
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {CUSTOM_CONSTANTS_TABLE_NAME} (
            id INTEGER PRIMARY KEY,
            definition TEXT NOT NULL UNIQUE
        );
        """)
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {VARIABLE_DEFINITIONS_TABLE_NAME} (
            name TEXT PRIMARY KEY,
            formula TEXT NOT NULL,
            type TEXT NOT NULL
        );
        """)
        conn.commit()
        logger.info("数据库元数据、自定义常量和变量定义表已确认存在。")

    def post_import_setup(self):
        """导入完成后，强制重新加载元数据。"""
        self.refresh_schema_info()
        self.load_global_stats()
        time_candidates = self.get_time_candidates()
        if time_candidates:
            self.set_time_variable('frame_index' if 'frame_index' in time_candidates else time_candidates[0])
        logger.info("数据库设置完成。")

    def refresh_schema_info(self, include_id=False):
        """当数据库表结构发生变化时（如添加列），强制刷新元数据。"""
        self._variables = None
        self._frame_count = None
        self._sorted_time_values = None
        self.get_frame_count()
        logger.info("DataManager schema info has been refreshed.")

    def set_global_filter(self, filter_text: str):
        if not filter_text.strip():
            self.global_filter_clause = ""
            logger.info("全局过滤器已清除。")
            self.cache.clear()
            return
        
        test_query = f"SELECT 1 FROM timeseries_data WHERE {filter_text} LIMIT 1;"
        try:
            conn = self.get_db_connection()
            conn.execute(test_query)
            conn.close()
        except Exception as e:
            raise ValueError(f"过滤器语法无效: {e}")
            
        self.global_filter_clause = f"AND ({filter_text})"
        logger.info(f"全局过滤器已设置为: {self.global_filter_clause}")
        self.cache.clear()

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
        self.cache.clear()

    def _get_sorted_time_values(self) -> List:
        if self._sorted_time_values is None:
            if not self.is_database_ready(): return []
            try:
                conn = self.get_db_connection()
                query = f'SELECT DISTINCT "{self.time_variable}" FROM timeseries_data ORDER BY "{self.time_variable}" ASC;'
                df_times = pd.read_sql_query(query, conn)
                conn.close()
                self._sorted_time_values = df_times[self.time_variable].tolist()
            except Exception as e:
                logger.error(f"无法获取时间变量 '{self.time_variable}' 的唯一值: {e}")
                self._sorted_time_values = []
        return self._sorted_time_values

    def get_frame_data(self, frame_index: int, required_columns: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
        time_values = self._get_sorted_time_values()
        if not (0 <= frame_index < len(time_values)):
            return None

        time_value = time_values[frame_index]
        
        required_cols_tuple = tuple(sorted(required_columns)) if required_columns else None
        cache_key = (frame_index, self.global_filter_clause, self.time_variable, required_cols_tuple)

        if cache_key in self.cache:
            self.cache.move_to_end(cache_key)
            return self.cache[cache_key]

        try:
            conn = self.get_db_connection()
            db_vars = self.get_variables(include_id=True)
            
            if required_columns:
                core_cols = {'x', 'y', self.time_variable, 'id', 'frame_index'}
                cols_to_select_set = set(required_columns).union(core_cols)
                final_cols = [var for var in cols_to_select_set if var in db_vars]
                cols_to_select_str = ", ".join([f'"{var}"' for var in final_cols])
            else:
                cols_to_select_str = ", ".join([f'"{var}"' for var in db_vars])

            if not cols_to_select_str:
                logger.warning("按需加载的列计算结果为空，无法查询数据。")
                conn.close()
                return pd.DataFrame()

            query = f'SELECT {cols_to_select_str} FROM timeseries_data WHERE "{self.time_variable}" = ? {self.global_filter_clause}'
            
            data = pd.read_sql_query(query, conn, params=(time_value,))
            conn.close()

            self.cache[cache_key] = data
            self._enforce_cache_limit()
            return data
        except Exception as e:
            msg = f"从数据库加载帧 {frame_index} (时间值: {time_value}) 数据失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"加载帧 {frame_index} 失败 (可能由于过滤器语法错误)。\n错误: {e}")
            return None

    def get_time_averaged_data(self, start_frame: int, end_frame: int) -> Optional[pd.DataFrame]:
        time_values = self._get_sorted_time_values()
        if not (0 <= start_frame < len(time_values) and 0 <= end_frame < len(time_values) and start_frame <= end_frame):
            return None
            
        start_time = time_values[start_frame]
        end_time = time_values[end_frame]
        
        try:
            conn = self.get_db_connection()
            variables = self.get_variables()
            
            vars_to_avg = [var for var in variables if var not in ['x', 'y', self.time_variable, 'frame_index', 'id', 'source_file']]
            avg_cols = ", ".join([f'AVG("{var}") as "{var}"' for var in vars_to_avg])
            
            query = f"""
                SELECT x, y, {avg_cols}
                FROM timeseries_data
                WHERE "{self.time_variable}" BETWEEN ? AND ? {self.global_filter_clause}
                GROUP BY x, y
            """
            
            df = pd.read_sql_query(query, conn, params=(start_time, end_time))
            conn.close()
            return df
        except Exception as e:
            msg = f"计算时间平均场失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"时间平均计算失败 (可能由于过滤器语法错误)。\n错误: {e}")
            return None

    def get_timeseries_at_point(self, variable: str, point_coords: Tuple[float, float], tolerance: float) -> Optional[pd.DataFrame]:
        if variable not in self.get_variables():
            raise ValueError(f"变量 '{variable}' 不存在。")
        
        x, y = point_coords
        x_min, x_max = x - tolerance, x + tolerance
        y_min, y_max = y - tolerance, y + tolerance

        try:
            conn = self.get_db_connection()
            query = f"""
                SELECT "{self.time_variable}", AVG("{variable}") as "{variable}"
                FROM timeseries_data
                WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ? {self.global_filter_clause}
                GROUP BY "{self.time_variable}"
                ORDER BY "{self.time_variable}" ASC
            """
            df = pd.read_sql_query(query, conn, params=(x_min, x_max, y_min, y_max))
            conn.close()
            return df
        except Exception as e:
            msg = f"获取时间序列数据失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"时间序列查询失败。\n错误: {e}")
            return None

    def _enforce_cache_limit(self):
        while len(self.cache) > self.cache_max_size:
            self.cache.popitem(last=False)

    def set_cache_size(self, size: int):
        self.cache_max_size = max(1, size)
        self._enforce_cache_limit()
        logger.info(f"缓存大小已设置为: {self.cache_max_size}")

    def get_frame_count(self) -> int:
        if self._frame_count is None:
            self._frame_count = len(self._get_sorted_time_values())
        return self._frame_count

    def get_frame_info(self, i: int) -> Optional[Dict[str, Any]]: 
        time_values = self._get_sorted_time_values()
        if not (0 <= i < len(time_values)): return None
        return {'path': f'db_frame_{i}', 'timestamp': time_values[i]}

    def get_cache_info(self) -> Dict: return {'size': len(self.cache), 'max_size': self.cache_max_size}

    def get_database_info(self) -> Dict[str, Any]:
        return {
            "db_path": self.db_path,
            "is_ready": self.is_database_ready(),
            "frame_count": self.get_frame_count(),
            "variables": self.get_variables(),
            "global_filter": self.global_filter_clause
        }

    def get_variables(self, include_id: bool = False) -> List[str]:
        """
        [FIXED] 改进了缓存逻辑以正确处理 `include_id` 标志。
        它现在缓存完整列表，并根据请求进行过滤。
        """
        if self._variables is None:
            if not self.is_database_ready():
                self._variables = []
            else:
                try:
                    conn = self.get_db_connection()
                    cursor = conn.execute("PRAGMA table_info(timeseries_data);")
                    # 缓存从数据库中获得的完整、未经过滤的列名列表
                    self._variables = sorted([row[1] for row in cursor.fetchall()])
                    conn.close()
                except Exception as e:
                    logger.error(f"无法从数据库获取变量列表: {e}")
                    self._variables = []
        
        # 现在，根据请求从缓存的完整列表中过滤
        if not include_id:
            return [col for col in self._variables if col != 'id']
        else:
            return self._variables

    def get_time_candidates(self) -> List[str]:
        """获取可用作时间轴的变量列表 (所有数值型变量)。"""
        if not self.is_database_ready(): return []
        candidates = ['frame_index']
        all_vars = self.get_variables()
        for var in all_vars:
            if var != 'frame_index' and var != 'source_file' and var != 'id':
                candidates.append(var)
        return candidates

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
        if not self.is_database_ready(): return
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
            logger.info(f"成功将 {len(definitions)} 条自定义常量定义保存到数据库。")
        except Exception as e:
            logger.error(f"保存自定义常量定义失败: {e}", exc_info=True)

    def load_custom_definitions(self) -> List[str]:
        if not self.is_database_ready(): return []
        try:
            conn = self.get_db_connection()
            cursor = conn.execute(f"SELECT definition FROM {CUSTOM_CONSTANTS_TABLE_NAME} ORDER BY id")
            definitions = [row[0] for row in cursor.fetchall()]
            conn.close()
            logger.info(f"从数据库加载了 {len(definitions)} 条自定义常量定义。")
            return definitions
        except Exception as e:
            logger.error(f"加载自定义常量定义失败: {e}", exc_info=True)
            return []

    def delete_global_stats(self, stat_names: List[str]):
        if not self.db_path or not stat_names:
            return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in stat_names)
            query = f"DELETE FROM {METADATA_TABLE_NAME} WHERE key IN ({placeholders})"
            cursor.execute(query, stat_names)
            conn.commit()
            conn.close()
            logger.info(f"已从数据库中删除全局常量值: {stat_names}")
            for name in stat_names:
                self.global_stats.pop(name, None)
        except Exception as e:
            logger.error(f"删除全局统计数据失败: {e}", exc_info=True)

    def save_variable_definition(self, name: str, formula: str, type_str: str):
        if not self.db_path: return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT OR REPLACE INTO {VARIABLE_DEFINITIONS_TABLE_NAME} (name, formula, type) VALUES (?, ?, ?)",
                (name, formula, type_str)
            )
            conn.commit()
            conn.close()
            logger.info(f"已保存变量定义: {name} ({type_str})")
        except Exception as e:
            logger.error(f"保存变量 '{name}' 的定义失败: {e}", exc_info=True)

    def load_variable_definitions(self) -> Dict[str, Dict[str, str]]:
        if not self.is_database_ready(): return {}
        try:
            conn = self.get_db_connection()
            cursor = conn.execute(f"SELECT name, formula, type FROM {VARIABLE_DEFINITIONS_TABLE_NAME}")
            definitions = {row[0]: {'formula': row[1], 'type': row[2]} for row in cursor.fetchall()}
            conn.close()
            logger.info(f"从数据库加载了 {len(definitions)} 条变量定义。")
            return definitions
        except Exception as e:
            logger.error(f"加载变量定义失败: {e}", exc_info=True)
            return {}

    def clear_all(self):
        self._variables = None; self._frame_count = None; self._sorted_time_values = None
        self.time_variable = "frame_index"
        self.cache.clear(); self.clear_global_stats()
        self.global_filter_clause = ""
        logger.info("DataManager 状态已清除。")

    def clear_global_stats(self):
        self.global_stats.clear(); self.custom_global_formulas.clear()
        logger.info("内存中的全局统计数据已清除。")
        
    def delete_variable(self, var_name: str):
        core_vars = {'x', 'y', 'id', 'frame_index', 'source_file'}
        if var_name in core_vars:
            raise ValueError(f"无法删除核心变量 '{var_name}'。")

        conn = self.get_db_connection()
        try:
            logger.info(f"正在从 timeseries_data 表中删除列: {var_name}")
            conn.execute(f'ALTER TABLE timeseries_data DROP COLUMN "{var_name}";')

            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION;")

            stats_pattern_to_delete = f"{var_name}_global_%"
            logger.info(f"正在从 {METADATA_TABLE_NAME} 表中删除键匹配 '{stats_pattern_to_delete}' 的统计数据")
            cursor.execute(f"DELETE FROM {METADATA_TABLE_NAME} WHERE key LIKE ?", (stats_pattern_to_delete,))
            
            logger.info(f"正在删除变量 '{var_name}' 的定义")
            cursor.execute(f"DELETE FROM {VARIABLE_DEFINITIONS_TABLE_NAME} WHERE name = ?", (var_name,))
            
            conn.commit()
            logger.info(f"成功删除变量 '{var_name}' 及其关联数据。")

        except Exception as e:
            conn.rollback()
            logger.error(f"删除变量 '{var_name}' 失败: {e}", exc_info=True)
            raise RuntimeError(f"数据库操作失败: {e}")
        finally:
            conn.close()
        
        self.refresh_schema_info()
        self.load_global_stats()

    def rename_variable(self, old_name: str, new_name: str):
        core_vars = {'x', 'y', 'id', 'frame_index', 'source_file'}
        if old_name in core_vars:
            raise ValueError(f"无法重命名核心变量 '{old_name}'。")
        if not new_name.isidentifier():
            raise ValueError(f"新名称 '{new_name}' 不是一个有效的标识符。")
        if new_name in self.get_variables():
            raise ValueError(f"变量名 '{new_name}' 已存在。")

        conn = self.get_db_connection()
        try:
            logger.info(f"正在重命名列 '{old_name}' 为 '{new_name}'")
            conn.execute(f'ALTER TABLE timeseries_data RENAME COLUMN "{old_name}" TO "{new_name}";')

            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION;")
            
            stats_pattern = f"{old_name}_global_%"
            logger.info(f"正在更新匹配 '{stats_pattern}' 的统计数据键")
            cursor.execute(f"SELECT key FROM {METADATA_TABLE_NAME} WHERE key LIKE ?", (stats_pattern,))
            keys_to_update = [row[0] for row in cursor.fetchall()]
            
            updates = []
            for old_key in keys_to_update:
                new_key = old_key.replace(f"{old_name}_global_", f"{new_name}_global_", 1)
                updates.append((new_key, old_key))
            
            if updates:
                cursor.executemany(f"UPDATE {METADATA_TABLE_NAME} SET key = ? WHERE key = ?", updates)
                logger.info(f"已更新 {len(updates)} 个统计数据键。")

            logger.info(f"正在更新变量定义表中的 '{old_name}'")
            cursor.execute(f"UPDATE {VARIABLE_DEFINITIONS_TABLE_NAME} SET name = ? WHERE name = ?", (new_name, old_name))

            conn.commit()
            logger.info(f"成功重命名变量 '{old_name}' 为 '{new_name}'。")

        except Exception as e:
            conn.rollback()
            logger.error(f"重命名变量 '{old_name}' 失败: {e}", exc_info=True)
            raise RuntimeError(f"数据库操作失败: {e}")
        finally:
            conn.close()

        self.refresh_schema_info()
        self.load_global_stats()