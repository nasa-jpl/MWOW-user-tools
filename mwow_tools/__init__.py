"""
mwow_tools - Tools for accessing and visualizing MWOW ocean wind data products.

Provides functions to open MWOW NetCDF files and extract time series by point,
ship track, or geographic region.
"""

from mwow_tools.reader import (
    open_mwow_files,
    select_point,
    match_ship_track,
    select_region,
)

__version__ = "0.1.0"

__all__ = [
    "open_mwow_files",
    "select_point",
    "match_ship_track",
    "select_region",
]
