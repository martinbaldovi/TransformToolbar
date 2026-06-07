# -*- coding: utf-8 -*-
"""
TransformToolbar – Manifold‑style transform toolbar for QGIS 4.0 (Qt6)
"""

from qgis.core import QgsApplication
from .plugin import TransformToolbar


def classFactory(iface):
    """Required plugin entry point."""
    return TransformToolbar(iface)
