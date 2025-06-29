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
        return sqlite3.connect(self.db_path, timeout=10)
    
    def create_database_tables(self, conn: sqlite3.Connection):
        """创建所有必需的表，如果它们不存在的话。"""
        cursor = conn.cursor()
        # Metadata table for storing global stats
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {METADATA_TABLE_NAME} (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        );
        """)
        # Custom constants definitions table
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {CUSTOM_CONSTANTS_TABLE_NAME} (
            id INTEGER PRIMARY KEY,
            definition TEXT NOT NULL UNIQUE
        );
        """)
        conn.commit()
        logger.info("数据库元数据和自定义常量表已确认存在。")

    def post_import_setup(self):
        """导入完成后，强制重新加载元数据。"""
        self.refresh_schema_info()
        self.load_global_stats() # Load stats from db
        logger.info("数据库设置完成。")

    def refresh_schema_info(self):
        """当数据库表结构发生变化时（如添加列），强制刷新元数据。"""
        self._variables = None; self._frame_count = None
        self.get_variables(); self.get_frame_count()
        logger.info("DataManager schema info has been refreshed.")

    def set_global_filter(self, filter_text: str):
        """设置并验证全局过滤器。"""
        if not filter_text.strip():
            self.global_filter_clause = ""
            logger.info("全局过滤器已清除。")
            return
        
        # 非常基础的验证，防止一些明显的错误
        if 'drop' in filter_text.lower() or 'delete' in filter_text.lower():
             raise ValueError("过滤器不允许包含 'DROP' 或 'DELETE'。")
        
        self.global_filter_clause = f"AND ({filter_text})"
        logger.info(f"全局过滤器已设置为: {self.global_filter_clause}")
        # 清空缓存，因为过滤条件已改变
        self.cache.clear()

    def get_frame_data(self, frame_index: int) -> Optional[pd.DataFrame]:
        # 缓存键现在必须包含过滤器，以避免混淆
        cache_key = (frame_index, self.global_filter_clause)
        if not (0 <= frame_index < self.get_frame_count()): return None
        if cache_key in self.cache:
            self.cache.move_to_end(cache_key)
            return self.cache[cache_key]
        
        try:
            conn = self.get_db_connection()
            all_known_vars = self.get_variables()
            if not all_known_vars: return pd.DataFrame()

            cols_to_select = ", ".join([f'"{var}"' for var in all_known_vars])
            query = f"SELECT {cols_to_select} FROM timeseries_data WHERE frame_index = ? {self.global_filter_clause}"
            
            data = pd.read_sql_query(query, conn, params=(frame_index,))
            conn.close()

            self.cache[cache_key] = data
            self._enforce_cache_limit()
            return data
        except Exception as e:
            msg = f"从数据库加载帧 {frame_index} 数据失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"加载帧 {frame_index} 失败 (可能由于过滤器语法错误)。\n错误: {e}")
            return None

    def get_time_averaged_data(self, start_frame: int, end_frame: int) -> Optional[pd.DataFrame]:
        """计算并返回指定时间范围内的平均场。"""
        try:
            conn = self.get_db_connection()
            variables = self.get_variables()
            avg_cols = ", ".join([f'AVG("{var}") as "{var}"' for var in variables])
            
            # 我们需要x和y坐标来构建网格，所以也对它们进行平均（虽然它们可能不随时间变化）
            query = f"""
                SELECT AVG(x) as x, AVG(y) as y, {avg_cols}
                FROM timeseries_data
                WHERE frame_index BETWEEN ? AND ? {self.global_filter_clause}
                GROUP BY x, y
            """
            
            df = pd.read_sql_query(query, conn, params=(start_frame, end_frame))
            conn.close()
            return df
        except Exception as e:
            msg = f"计算时间平均场失败: {e}"
            logger.error(msg, exc_info=True)
            self.error_occurred.emit(f"时间平均计算失败 (可能由于过滤器语法错误)。\n错误: {e}")
            return None

    def get_timeseries_at_point(self, variable: str, point_coords: Tuple[float, float], tolerance: float = 0.05) -> Optional[pd.DataFrame]:
        """使用'探针盒'方法获取一个点的时间序列数据。"""
        if variable not in self.get_variables():
            raise ValueError(f"变量 '{variable}' 不存在。")
        
        x, y = point_coords
        x_min, x_max = x * (1 - tolerance), x * (1 + tolerance)
        y_min, y_max = y * (1 - tolerance), y * (1 + tolerance)

        try:
            conn = self.get_db_connection()
            query = f"""
                SELECT timestamp, AVG("{variable}") as "{variable}"
                FROM timeseries_data
                WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ? {self.global_filter_clause}
                GROUP BY frame_index
                ORDER BY timestamp
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
            if not self.is_database_ready(): return 0
            try:
                conn = self.get_db_connection()
                result = conn.execute("SELECT MAX(frame_index) + 1 FROM timeseries_data;").fetchone()
                conn.close()
                self._frame_count = result[0] if result and result[0] is not None else 0
            except Exception: self._frame_count = 0
        return self._frame_count

    def get_frame_info(self, i: int) -> Optional[Dict[str, Any]]: 
        if not (0 <= i < self.get_frame_count()): return None
        try:
            conn = self.get_db_connection()
            ts = conn.execute("SELECT timestamp FROM timeseries_data WHERE frame_index = ? LIMIT 1;", (i,)).fetchone()
            conn.close()
            return {'path': f'db_frame_{i}', 'timestamp': ts[0] if ts else i}
        except Exception: return {'path': f'db_frame_{i}', 'timestamp': i}

    def get_cache_info(self) -> Dict: return {'size': len(self.cache), 'max_size': self.cache_max_size}

    def get_database_info(self) -> Dict[str, Any]:
        """返回数据库的概览信息。"""
        return {
            "db_path": self.db_path,
            "is_ready": self.is_database_ready(),
            "frame_count": self.get_frame_count(),
            "variables": self.get_variables(),
            "global_filter": self.global_filter_clause
        }

    def get_variables(self) -> List[str]:
        if self._variables is None:
            if not self.is_database_ready(): return []
            try:
                conn = self.get_db_connection()
                cursor = conn.execute("PRAGMA table_info(timeseries_data);")
                all_cols = [row[1] for row in cursor.fetchall()]
                conn.close()
                excluded_cols = {'id', 'frame_index', 'timestamp'}
                self._variables = sorted([col for col in all_cols if col not in excluded_cols])
            except Exception: self._variables = []
        return self._variables

    def save_global_stats(self, stats: Dict[str, float]):
        """将统计数据保存或更新到元数据表中。"""
        if not self.db_path: return
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            data_to_insert = list(stats.items())
            cursor.executemany(f"INSERT OR REPLACE INTO {METADATA_TABLE_NAME} (key, value) VALUES (?, ?)", data_to_insert)
            conn.commit()
            conn.close()
            logger.info(f"成功将 {len(stats)} 条统计数据保存到数据库。")
            # 更新内存中的副本
            self.global_stats.update(stats)
        except Exception as e:
            logger.error(f"保存全局统计数据失败: {e}", exc_info=True)

    def load_global_stats(self):
        """从数据库加载所有全局统计数据。"""
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
            cursor.execute(f"DELETE FROM {CUSTOM_CONSTANTS_TABLE_NAME}") # Clear old definitions
            data_to_insert = [(d,) for d in definitions]
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

    def clear_all(self):
        self._variables = None; self._frame_count = None
        self.cache.clear(); self.clear_global_stats()
        self.global_filter_clause = ""
        logger.info("DataManager 状态已清除。")

    def clear_global_stats(self):
        self.global_stats.clear(); self.custom_global_formulas.clear()
        logger.info("内存中的全局统计数据已清除。")