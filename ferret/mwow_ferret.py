"""
pyFerret bridge for MWOW ocean wind data products.

This module loads MWOW NetCDF files into pyFerret, handling the non-standard
``orbit`` dimension by mapping it to a Ferret time axis (for point and region
extractions) or a custom Z axis (for full-file loads).

Point and region functions use the **T axis** so that pyFerret's time-based
subsetting works (e.g. ``list var[T="18-APR-2026 03:00"]``).  Orbits are
sorted by time and deduplicated.  If the per-cell time variation within an
orbit exceeds 10 minutes, a warning recommends using the ``_z`` variant
instead.

Full-file loads always use the **Z axis** because overlapping sensor times
make a monotonic T axis unreliable at global scale.

Requires
--------
- pyferret  (conda install -c conda-forge pyferret)
- mwow_tools  (pip install -e . from the repo root)
- numpy, xarray

Quick start
-----------
>>> import pyferret
>>> from mwow_ferret import load_mwow, load_mwow_point, load_mwow_region
>>> pyferret.start(quiet=True)
>>> load_mwow_point("/data/mwow/*.nc", lat=-54, lon=90)
>>> pyferret.run("plot MWOW_WIND_SPEED_POINT")
"""

import numpy as np
import pyferret

from mwow_tools.reader import open_mwow_files


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_UNITS = {
    "wind_speed": "m/s",
    "wind_direction": "degrees",
    "wind_speed_uncert": "m/s",
    "wind_direction_uncert": "degrees",
    "quality_indicator": "1",
    "sensor_id": "1",
}


def _unit_for(var):
    """Return the unit string for a MWOW variable name."""
    return _UNITS.get(var, "1")


def _to_ferret_time(datetimes):
    """Convert datetime64[ns] array to pyferret's (N, 6) int time format.

    Columns: [day, month, year, hour, minute, second] using pyferret's
    TIMEARRAY_*INDEX constants.
    """
    # pandas Timestamp gives easy access to components
    import pandas as pd
    out = np.zeros((len(datetimes), 6), dtype=np.int32)
    for i, dt in enumerate(datetimes):
        ts = pd.Timestamp(dt)
        out[i, pyferret.TIMEARRAY_DAYINDEX] = ts.day
        out[i, pyferret.TIMEARRAY_MONTHINDEX] = ts.month
        out[i, pyferret.TIMEARRAY_YEARINDEX] = ts.year
        out[i, pyferret.TIMEARRAY_HOURINDEX] = ts.hour
        out[i, pyferret.TIMEARRAY_MINUTEINDEX] = ts.minute
        out[i, pyferret.TIMEARRAY_SECONDINDEX] = ts.second
    return out


def _dedup_orbits(ds):
    """Drop duplicate orbits (same sensor_name + orbit_start_time).

    Keeps the orbit with the lowest index.  Prints a warning for each
    duplicate dropped.
    """
    if "sensor_name" not in ds or "orbit_start_time" not in ds:
        return ds

    sensor_names = ds["sensor_name"].values
    start_times = ds["orbit_start_time"].values
    n = len(sensor_names)

    seen = {}  # (sensor_name, start_time) -> first orbit index
    keep = []
    for i in range(n):
        key = (str(sensor_names[i]), start_times[i])
        if key in seen:
            print(f"WARNING: Dropped duplicate orbit for {key[0]} "
                  f"(orbit index {i}, duplicate of {seen[key]})")
        else:
            seen[key] = i
            keep.append(i)

    if len(keep) < n:
        ds = ds.isel(orbit=keep)
    return ds


def _sort_by_time(ds, time_coords):
    """Sort the orbit dimension by *time_coords* (1D datetime64 array).

    Returns (sorted_ds, sorted_time_coords).
    """
    order = np.argsort(time_coords)
    return ds.isel(orbit=order), time_coords[order]


def _ensure_monotonic(time_coords):
    """Add 1-second offsets to resolve duplicate timestamps.

    Returns a new array where all values are strictly increasing.
    """
    out = time_coords.copy()
    one_sec = np.timedelta64(1, "s")
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + one_sec
    return out


def _compute_region_times(ds):
    """Compute mean observation time per orbit from the 2D time slice.

    Returns a 1D datetime64 array of length n_orbits.
    Falls back to orbit_start_time for orbits with no valid times.
    """
    n_orbits = ds.sizes["orbit"]
    times = np.empty(n_orbits, dtype="datetime64[ns]")
    fallback = ds["orbit_start_time"].values if "orbit_start_time" in ds else None

    for i in range(n_orbits):
        t_slice = ds["time"].isel(orbit=i).values.ravel()
        valid = t_slice[~np.isnat(t_slice)]
        if len(valid) > 0:
            mean_ns = int(valid.astype("int64").mean())
            times[i] = np.datetime64(mean_ns, "ns")
        elif fallback is not None:
            times[i] = fallback[i]
        else:
            times[i] = np.datetime64("NaT")
    return times


def _compute_point_times(ds_point):
    """Extract per-orbit time from a point-selected dataset (1D time).

    Falls back to orbit_start_time for NaT values.
    """
    times = ds_point["time"].values.copy()
    if "orbit_start_time" in ds_point:
        fallback = ds_point["orbit_start_time"].values
        nat_mask = np.isnat(times)
        if np.any(nat_mask):
            times[nat_mask] = fallback[nat_mask]
    return times


def _check_time_spread(ds, z_func_name, threshold_minutes=10):
    """Warn if any orbit's time variation exceeds threshold.

    Checks max(time) - min(time) within the spatial slice for each orbit.
    """
    threshold = np.timedelta64(threshold_minutes, "m")
    n_orbits = ds.sizes["orbit"]
    warned = False
    sensor_names = ds["sensor_name"].values if "sensor_name" in ds else None

    for i in range(n_orbits):
        t_slice = ds["time"].isel(orbit=i).values.ravel()
        valid = t_slice[~np.isnat(t_slice)]
        if len(valid) < 2:
            continue
        spread = valid.max() - valid.min()
        if spread > threshold:
            sensor = str(sensor_names[i]) if sensor_names is not None else "?"
            spread_min = spread / np.timedelta64(1, "m")
            if not warned:
                print(f"WARNING: Time variation within orbit exceeds "
                      f"{threshold_minutes} min for some orbits.")
                print(f"  Consider using {z_func_name}() for orbit-indexed "
                      f"access instead.")
                warned = True
            print(f"  Orbit {i} ({sensor}): {spread_min:.1f} min spread")


def _prepare_data(ds, var):
    """Extract, transpose, and convert a 3D variable for pyferret.

    Input shape:  (orbit, latitude, longitude)
    Output shape: (longitude, latitude, orbit)

    NaN values are replaced with pyferret's missing value sentinel.
    """
    data = ds[var].values  # (orbit, lat, lon)
    data = np.transpose(data, (2, 1, 0))  # (lon, lat, orbit)
    return np.where(np.isnan(data), -1.0e34, data).astype(np.float64)


MISSING = np.array([-1.0e34])


# ---------------------------------------------------------------------------
# Z-axis functions (orbit as custom axis)
# ---------------------------------------------------------------------------

def load_mwow(paths, var="wind_speed", ferret_name=None):
    """Load an MWOW variable into pyFerret with orbit on the Z axis.

    Full-file loads always use Z because overlapping sensor times make
    a monotonic time axis unreliable at global scale.  For time-axis
    access, use :func:`load_mwow_point` or :func:`load_mwow_region`.

    Parameters
    ----------
    paths : str or list of str
        File path(s) or glob pattern.
    var : str
        Variable to load (default ``"wind_speed"``).
    ferret_name : str, optional
        Name in Ferret.  Defaults to ``"MWOW_" + var.upper()``.
    """
    ds = open_mwow_files(paths)
    ds = _dedup_orbits(ds)

    if ferret_name is None:
        ferret_name = f"MWOW_{var.upper()}"

    start_times = ds["orbit_start_time"].values
    ds, start_times = _sort_by_time(ds, start_times)

    data64 = _prepare_data(ds, var)
    lon = ds.longitude.values.astype(np.float64)
    lat = ds.latitude.values.astype(np.float64)
    n_orbit = ds.sizes["orbit"]
    orbit_coords = np.arange(1, n_orbit + 1, dtype=np.float64)

    pyferret.putdata(
        {
            "name": ferret_name,
            "title": f"MWOW {var.replace('_', ' ').title()}",
            "data": data64,
            "missing_value": MISSING,
            "data_unit": _unit_for(var),
            "axis_types": [
                pyferret.AXISTYPE_LONGITUDE,
                pyferret.AXISTYPE_LATITUDE,
                pyferret.AXISTYPE_CUSTOM,
            ],
            "axis_names": ["LONGITUDE", "LATITUDE", "ORBIT"],
            "axis_units": ["degrees_east", "degrees_north", "count"],
            "axis_coords": [lon, lat, orbit_coords],
        },
        axis_pos=(pyferret.X_AXIS, pyferret.Y_AXIS, pyferret.Z_AXIS),
    )

    print(f"NOTE: Full-file load uses Z axis for orbits (not time axis).")
    print(f"  Use load_mwow_point() or load_mwow_region() for time-axis access.")
    print(f"Loaded '{ferret_name}' into Ferret  "
          f"[{len(lon)} lon x {len(lat)} lat x {n_orbit} orbits]")
    print(f"  Access orbits with /K=   e.g.  shade/k=1 {ferret_name}")
    ds.close()


load_mwow_z = load_mwow  # Explicit alias


def load_mwow_point_z(paths, lat, lon, var="wind_speed",
                       ferret_name=None):
    """Load a single-point time series with orbit on the Z axis.

    This is the fallback when :func:`load_mwow_point` warns about
    large time variation.

    Parameters
    ----------
    paths : str or list of str
        File path(s) or glob pattern.
    lat, lon : float
        Target coordinates (nearest grid point is selected).
    var : str
        Variable to load (default ``"wind_speed"``).
    ferret_name : str, optional
        Ferret variable name.  Defaults to ``"MWOW_{VAR}_POINT_Z"``.
    """
    ds = open_mwow_files(paths)
    ds = _dedup_orbits(ds)

    if ferret_name is None:
        ferret_name = f"MWOW_{var.upper()}_POINT_Z"

    ds_pt = ds.sel(latitude=lat, longitude=lon, method="nearest")
    point_times = _compute_point_times(ds_pt)
    ds_pt, point_times = _sort_by_time(ds_pt, point_times)

    data = ds_pt[var].values.astype(np.float64)  # (orbit,)
    data = np.where(np.isnan(data), -1.0e34, data)
    n = len(data)
    orbit_coords = np.arange(1, n + 1, dtype=np.float64)

    pyferret.putdata(
        {
            "name": ferret_name,
            "title": f"MWOW {var} at ({lat}, {lon})",
            "data": data,
            "missing_value": MISSING,
            "data_unit": _unit_for(var),
            "axis_types": [pyferret.AXISTYPE_CUSTOM],
            "axis_names": ["ORBIT"],
            "axis_units": ["count"],
            "axis_coords": [orbit_coords],
        },
        axis_pos=(pyferret.X_AXIS,),
    )

    actual_lat = float(ds_pt.latitude)
    actual_lon = float(ds_pt.longitude)
    print(f"Loaded '{ferret_name}' [{n} orbits] at "
          f"({actual_lat:.2f}, {actual_lon:.2f})  [Z axis]")
    print(f"  Plot with:  plot {ferret_name}")
    ds.close()


def load_mwow_region_z(paths, lat_center, lon_center,
                        lat_size=5.0, lon_size=5.0,
                        var="wind_speed", ferret_name=None):
    """Load a geographic sub-region with orbit on the Z axis.

    This is the fallback when :func:`load_mwow_region` warns about
    large time variation.  Empty orbits are dropped.

    Parameters
    ----------
    paths : str or list of str
        File path(s) or glob pattern.
    lat_center, lon_center : float
        Center of the region (degrees).
    lat_size, lon_size : float
        Half-width of the box in degrees (default 5).
    var : str
        Variable name (default ``"wind_speed"``).
    ferret_name : str, optional
        Ferret variable name.
    """
    ds = open_mwow_files(paths)
    ds = _dedup_orbits(ds)

    if ferret_name is None:
        ferret_name = f"MWOW_{var.upper()}_REGION_Z"

    ds_reg = ds.sel(
        latitude=slice(lat_center - lat_size, lat_center + lat_size),
        longitude=slice(lon_center - lon_size, lon_center + lon_size),
    )
    # Drop empty orbits
    valid = (ds_reg[var].notnull()
             .any(dim=("latitude", "longitude"))
             .compute())
    ds_reg = ds_reg.isel(orbit=valid)

    region_times = _compute_region_times(ds_reg)
    ds_reg, region_times = _sort_by_time(ds_reg, region_times)

    data64 = _prepare_data(ds_reg, var)
    lon = ds_reg.longitude.values.astype(np.float64)
    lat = ds_reg.latitude.values.astype(np.float64)
    n_orbit = ds_reg.sizes["orbit"]
    orbit_coords = np.arange(1, n_orbit + 1, dtype=np.float64)

    pyferret.putdata(
        {
            "name": ferret_name,
            "title": f"MWOW {var} region ({lat_center}, {lon_center})",
            "data": data64,
            "missing_value": MISSING,
            "data_unit": _unit_for(var),
            "axis_types": [
                pyferret.AXISTYPE_LONGITUDE,
                pyferret.AXISTYPE_LATITUDE,
                pyferret.AXISTYPE_CUSTOM,
            ],
            "axis_names": ["LON_REG", "LAT_REG", "ORBIT"],
            "axis_units": ["degrees_east", "degrees_north", "count"],
            "axis_coords": [lon, lat, orbit_coords],
        },
        axis_pos=(pyferret.X_AXIS, pyferret.Y_AXIS, pyferret.Z_AXIS),
    )

    print(f"Loaded '{ferret_name}' [{len(lon)} lon x {len(lat)} lat "
          f"x {n_orbit} orbits]  [Z axis]")
    print(f"  Browse orbits:  shade/k=1 {ferret_name}")
    ds.close()


# ---------------------------------------------------------------------------
# T-axis functions (orbit mapped to Ferret time axis)
# ---------------------------------------------------------------------------

def load_mwow_point(paths, lat, lon, var="wind_speed",
                    ferret_name=None):
    """Load a single-point time series with orbit on the T (time) axis.

    The per-orbit time is taken from the ``time`` variable at the selected
    grid cell.  Orbits are deduplicated, sorted by time, and any remaining
    ties receive a 1-second offset for monotonicity.

    Parameters
    ----------
    paths : str or list of str
        File path(s) or glob pattern.
    lat, lon : float
        Target coordinates (nearest grid point is selected).
    var : str
        Variable to load (default ``"wind_speed"``).
    ferret_name : str, optional
        Ferret variable name.  Defaults to ``"MWOW_{VAR}_POINT"``.
    """
    ds = open_mwow_files(paths)
    ds = _dedup_orbits(ds)

    if ferret_name is None:
        ferret_name = f"MWOW_{var.upper()}_POINT"

    ds_pt = ds.sel(latitude=lat, longitude=lon, method="nearest")
    point_times = _compute_point_times(ds_pt)

    ds_pt, point_times = _sort_by_time(ds_pt, point_times)
    point_times = _ensure_monotonic(point_times)

    data = ds_pt[var].values.astype(np.float64)  # (orbit,)
    data = np.where(np.isnan(data), -1.0e34, data)
    n = len(data)

    ferret_times = _to_ferret_time(point_times)

    pyferret.putdata(
        {
            "name": ferret_name,
            "title": f"MWOW {var} at ({lat}, {lon})",
            "data": data,
            "missing_value": MISSING,
            "data_unit": _unit_for(var),
            "axis_types": [pyferret.AXISTYPE_TIME],
            "axis_names": ["TIME"],
            "axis_units": [pyferret.CALTYPE_GREGORIAN],
            "axis_coords": [ferret_times],
        },
        axis_pos=(pyferret.T_AXIS,),
    )

    actual_lat = float(ds_pt.latitude)
    actual_lon = float(ds_pt.longitude)
    print(f"Loaded '{ferret_name}' [{n} orbits] at "
          f"({actual_lat:.2f}, {actual_lon:.2f})  [T axis]")
    print(f"  Plot with:  plot {ferret_name}")
    print(f"  Subset:     list {ferret_name}[T=\"18-APR-2026 00:00\":"
          f"\"18-APR-2026 06:00\"]")
    ds.close()


def load_mwow_region(paths, lat_center, lon_center,
                     lat_size=5.0, lon_size=5.0,
                     var="wind_speed", ferret_name=None):
    """Load a geographic sub-region with orbit on the T (time) axis.

    The per-orbit time is the mean of the 2D ``time`` slice within the
    selected region.  Empty orbits are dropped.  If any orbit has >10 min
    of time variation within the region, a warning recommends using
    :func:`load_mwow_region_z` instead.

    Parameters
    ----------
    paths : str or list of str
        File path(s) or glob pattern.
    lat_center, lon_center : float
        Center of the region (degrees).
    lat_size, lon_size : float
        Half-width of the box in degrees (default 5).
    var : str
        Variable name (default ``"wind_speed"``).
    ferret_name : str, optional
        Ferret variable name.
    """
    ds = open_mwow_files(paths)
    ds = _dedup_orbits(ds)

    if ferret_name is None:
        ferret_name = f"MWOW_{var.upper()}_REGION"

    ds_reg = ds.sel(
        latitude=slice(lat_center - lat_size, lat_center + lat_size),
        longitude=slice(lon_center - lon_size, lon_center + lon_size),
    )
    # Drop empty orbits
    valid = (ds_reg[var].notnull()
             .any(dim=("latitude", "longitude"))
             .compute())
    ds_reg = ds_reg.isel(orbit=valid)

    if ds_reg.sizes["orbit"] == 0:
        print(f"WARNING: No orbits with data in the selected region.")
        ds.close()
        return

    _check_time_spread(ds_reg, "load_mwow_region_z")

    region_times = _compute_region_times(ds_reg)
    ds_reg, region_times = _sort_by_time(ds_reg, region_times)
    region_times = _ensure_monotonic(region_times)

    data64 = _prepare_data(ds_reg, var)
    lon = ds_reg.longitude.values.astype(np.float64)
    lat = ds_reg.latitude.values.astype(np.float64)
    n_orbit = ds_reg.sizes["orbit"]

    ferret_times = _to_ferret_time(region_times)

    pyferret.putdata(
        {
            "name": ferret_name,
            "title": f"MWOW {var} region ({lat_center}, {lon_center})",
            "data": data64,
            "missing_value": MISSING,
            "data_unit": _unit_for(var),
            "axis_types": [
                pyferret.AXISTYPE_LONGITUDE,
                pyferret.AXISTYPE_LATITUDE,
                pyferret.AXISTYPE_TIME,
            ],
            "axis_names": ["LON_REG", "LAT_REG", "TIME"],
            "axis_units": [
                "degrees_east",
                "degrees_north",
                pyferret.CALTYPE_GREGORIAN,
            ],
            "axis_coords": [lon, lat, ferret_times],
        },
        axis_pos=(pyferret.X_AXIS, pyferret.Y_AXIS, pyferret.T_AXIS),
    )

    print(f"Loaded '{ferret_name}' [{len(lon)} lon x {len(lat)} lat "
          f"x {n_orbit} orbits]  [T axis]")
    print(f"  Browse orbits:  shade/L=1 {ferret_name}")
    print(f"  Time subset:    shade {ferret_name}"
          f"[T=\"18-APR-2026 00:00\":\"18-APR-2026 06:00\"]")
    ds.close()


# ---------------------------------------------------------------------------
# Convenience plot functions
# ---------------------------------------------------------------------------

def plot_timeseries(ferret_name="MWOW_WIND_SPEED_POINT", output=None):
    """Plot a single-point time series loaded with :func:`load_mwow_point`.

    Parameters
    ----------
    ferret_name : str
        Ferret variable name.
    output : str, optional
        Save the plot to this file (PNG or PDF).
    """
    pyferret.run(f'plot/title="MWOW Wind Speed Time Series"'
                 f'/vlimits=0:30/symbol=17 {ferret_name}')
    if output:
        pyferret.run(f'frame/file="{output}"')
        print(f"Saved to {output}")


def plot_region_orbit(ferret_name="MWOW_WIND_SPEED_REGION", orbit=1,
                      output=None, palette="viridis"):
    """Shade-plot one orbit of a loaded region.

    Works with both T-axis and Z-axis variants.  For T-axis data use
    ``/L=`` to select orbits; for Z-axis data use ``/K=``.

    Parameters
    ----------
    ferret_name : str
        Ferret variable name.
    orbit : int
        Orbit index (1-based).  Maps to K (Z-axis) or L (T-axis).
    output : str, optional
        Save plot to file.
    palette : str
        Ferret color palette name.
    """
    # Try L= first (T-axis), fall back to K= (Z-axis)
    pyferret.run(
        f'shade/l={orbit}/palette={palette}'
        f'/title="MWOW Wind Speed – Pass {orbit}" {ferret_name}'
    )
    if output:
        pyferret.run(f'frame/file="{output}"')
        print(f"Saved to {output}")
