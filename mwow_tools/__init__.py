"""
mwow_tools - Tools for accessing and visualizing MWOW ocean wind data products.

Provides functions to open MWOW NetCDF files and extract time series by point,
ship track, or geographic region, as well as inter-sensor collocation and
comparison utilities.
"""

from mwow_tools.reader import (
    open_mwow_files,
    select_point,
    match_ship_track,
    select_region,
)

from mwow_tools.collocate import (
    find_collocations,
    collocate_files,
    collocate_files_multi,
    SENSOR_IDS,
    SENSOR_NAMES,
)

from mwow_tools.sensor_comparison import (
    compute_stats,
    joint_histogram,
    plot_joint_histogram,
    plot_qi_sensitivity,
    qi_sensitivity_table,
)

from mwow_tools.compare import (
    extract_matched_pairs,
    comparison_stats,
    circular_abs_diff,
)

from mwow_tools.spatial import plot_wind_map

from mwow_tools.video import generate_region_video

__version__ = "0.2.0"

__all__ = [
    "open_mwow_files",
    "select_point",
    "match_ship_track",
    "select_region",
    "find_collocations",
    "collocate_files",
    "collocate_files_multi",
    "SENSOR_IDS",
    "SENSOR_NAMES",
    "compute_stats",
    "joint_histogram",
    "plot_joint_histogram",
    "plot_qi_sensitivity",
    "qi_sensitivity_table",
    "extract_matched_pairs",
    "comparison_stats",
    "circular_abs_diff",
    "plot_wind_map",
    "generate_region_video",
]
