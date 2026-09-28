"""Ajudantes de geometria compartilhados pelos modulos 2D."""

from __future__ import annotations

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry


def polygon_parts(geometry: BaseGeometry) -> list[Polygon]:
    """Poligonos de area positiva de uma geometria, seja ela simples ou multipla."""
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > 0 else []
    return [
        part
        for part in getattr(geometry, "geoms", [])
        if part.geom_type == "Polygon" and part.area > 0
    ]
