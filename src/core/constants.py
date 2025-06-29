#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目共享常量与枚举
"""
from enum import Enum

class VectorPlotType(Enum):
    """矢量图的绘图类型"""
    STREAMLINE = "流线图 (Streamline)"
    QUIVER = "矢量图 (Quiver)"

    @classmethod
    def from_str(cls, s: str):
        for item in cls:
            if item.value == s:
                return item
        return cls.STREAMLINE # 默认值

class StreamlineColor(Enum):
    """流线图的着色依据"""
    MAGNITUDE = "速度大小"
    U_COMPONENT = "U分量"
    V_COMPONENT = "V分量"
    BLACK = "黑色"

    @classmethod
    def from_str(cls, s: str):
        for item in cls:
            if item.value == s:
                return item
        return cls.MAGNITUDE # 默认值

class PickerMode(Enum):
    """颜色拾取器的模式"""
    VMIN = "vmin"
    VMAX = "vmax"