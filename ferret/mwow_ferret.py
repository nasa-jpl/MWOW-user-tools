"""
pyFerret bridge for MWOW ocean wind data products.

This module loads MWOW NetCDF files into pyFerret, handling the non-standard
``orbit`` dimension by mapping it to a Ferret custom axis.  It can also
reshape the data so that orbit is mapped to the Ferret Z axis (for browsing
individual passes) or collapse it into a time axis (for time-series work).

Requires
--------
- pyferret  (conda install -c conda-forge pyferret)
- numpy
- xarray
- netCDF4

Quick start
-----------
>>> import pyferret
>>> from mwow_ferret import load_mwow, load_mwow_point, load_mwow_region
>>> pyferret.start(quiet=True)
>>> load_mwow("/data/mwow/MWOW_2026032*.nc")
>>> pyferret.run("shade/k=1 MWOW_WIND_SPEED")
"""

import glob as _glob

import numpy as np
import pyferret
import xarray as xr


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def load_mwow(paths, var="wind_speed", ferret_name=None):
    """Load an MWOW variable into pyFerret with orbit as the Z axis.

    The longitude and latitude dimensions are mapped to Ferret X and Y.
    The orbit dimension is mapped to Ferret Z as a custom axis, so
    individual passes can be accessed with ``/K=`` qualifiers, e.g.
    ``shade/k=1 MWOW_WIND_SPEED``.

    Parameters
    ----------
    paths : str or list of str
        File path(s) or glob pattern.
    var : str
        Variable to load (default ``"wind_speed"``).
    ferret_name : str, optional
        Name for the variable in Ferret.  Defaults to
        ``"MWOW_" + var.upper()``.
    """
    ds = _open(paths)

    if ferret_name is None:
        ferret_name = f"MWOW_{var.upper()}"

    data = ds[var].values  # shape: (lon, lat, orbit)
    data = np.transpose(data, (2, 1, 0))  # -> (orbit, lat, lon)

    lon = ds.longitude.values.astype(np.float64)
    lat = ds.latitude.values.astype(np.float64)
    n_orbit = data.shape[0]
    orbit_coords = np.arange(1, n_orbit + 1, dtype=np.float64)

    data64 = np.where(np.isnan(data), -1.0e34, data).astype(np.float64)

    datavar = {
        "name": ferret_name,
        "title": f"MWOW {var.replace('_', ' ').title()}",
        "data": data64,
        "missing_value": np.array([-1.0e34]),
        "data_unit": _unit_for(var),
        "axis_types": [
            pyferret.AXISTYPE_CUSTOM,
            pyferret.AXISTYPE_LATITUDE,
            pyferret.AXISTYPE_LONGITUDE,
        ],
        "axis_names": ["ORBIT", "LATITUDE", "LONGITUDE"],
        "axis_units": ["count", "degrees_north", "degrees_east"],
        "axis_coords": [orbit_coords, lat, lon],
    }

    pyferret.putdata(datavar, axis_pos=(
        pyferret.X_AXIS,
        pyferret.Y_AXIS,
        pyferret.Z_AXIS,
    ))

    print(f"Loaded '{ferret_name}' into Ferret  "
          f"[{len(lon)} lon x {len(lat)} lat x {n_orbit} orbits]")
    print(f"  Access orbits with /K=   e.g.  shade/k=1 {ferret_name}")


def load_mwow_point(paths, lat, lon, ferret_name="MWOW_POINT"):
    """Load a single-point time series into pyFerret.

    The orbit dimension is mapped to a custom Z axis so the series can
    be plotted with ``plot mwow_point``.

    Parameters
    ----------
    paths : str or list of str
        File path(s) or glob pattern.
    lat, lon : float
        Target coordinates (nearest grid point is selected).
    ferret_name : str
        Ferret variable name (default ``"MWOW_POINT"``).
    """
    ds = _open(paths)
    ds_pt = ds.sel(latitude=lat, longitude=lon, method="nearest")
    ws = ds_pt["wind_speed"].values.astype(np.float64)  # shape: (orbit,)

    n = len(ws)
    orbit_coords = np.arange(1, n + 1, dtype=np.float64)

    ws64 = np.where(np.isnan(ws), -1.0e34, ws)

    datavar = {
        "name": ferret_name,
        "title": f"Wind speed at ({lat}, {lon})",
        "data": ws64,
        "missing_value": np.array([-1.0e34]),
        "data_unit": "m/s",
        "axis_types": [pyferret.AXISTYPE_CUSTOM],
        "axis_names": ["ORBIT"],
        "axis_units": ["count"],
        "axis_coords": [orbit_coords],
    }

    pyferret.putdata(datavar, axis_pos=(pyferret.X_AXIS,))

    actual_lat = float(ds_pt.latitude)
    actual_lon = float(ds_pt.longitude)
    print(f"Loaded '{ferret_name}' [{n} orbits] at "
          f"({actual_lat:.2f}, {actual_lon:.2f})")
    print(f"  Plot with:  plot {ferret_name}")


def load_mwow_region(paths, lat_center, lon_center,
                     lat_size=5.0, lon_size=5.0,
                     var="wind_speed", ferret_name=None):
    """Load a geographic sub-region into pyFerret.

    Empty orbits (all NaN within the region) are dropped.

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
    ds = _open(paths)

    if ferret_name is None:
        ferret_name = f"MWOW_{var.upper()}_REGION"

    ds_reg = ds.sel(
        latitude=slice(lat_center - lat_size, lat_center + lat_size),
        longitude=slice(lon_center - lon_size, lon_center + lon_size),
    )
    valid = (ds_reg[var]
             .notnull()
             .any(dim=("latitude", "longitude"))
             .compute())
    ds_reg = ds_reg.isel(orbit=valid)

    data = ds_reg[var].values  # (lon, lat, orbit)
    data = np.transpose(data, (2, 1, 0))  # -> (orbit, lat, lon)

    lon = ds_reg.longitude.values.astype(np.float64)
    lat = ds_reg.latitude.values.astype(np.float64)
    n_orbit = data.shape[0]
    orbit_coords = np.arange(1, n_orbit + 1, dtype=np.float64)

    data64 = np.where(np.isnan(data), -1.0e34, data).astype(np.float64)

    datavar = {
        "name": ferret_name,
        "title": f"MWOW {var} region ({lat_center}, {lon_center})",
        "data": data64,
        "missing_value": np.array([-1.0e34]),
        "data_unit": _unit_for(var),
        "axis_types": [
            pyferret.AXISTYPE_CUSTOM,
            pyferret.AXISTYPE_LATITUDE,
            pyferret.AXISTYPE_LONGITUDE,
        ],
        "axis_names": ["ORBIT", "LAT_REG", "LON_REG"],
        "axis_units": ["count", "degrees_north", "degrees_east"],
        "axis_coords": [orbit_coords, lat, lon],
    }

    pyferret.putdata(datavar, axis_pos=(
        pyferret.X_AXIS,
        pyferret.Y_AXIS,
        pyferret.Z_AXIS,
    ))

    print(f"Loaded '{ferret_name}' [{len(lon)} lon x {len(lat)} lat "
          f"x {n_orbit} orbits]")
    print(f"  Browse orbits:  shade/k=1 {ferret_name}")


# ---------------------------------------------------------------------------
# Convenience: run common Ferret plot commands from Python
# ---------------------------------------------------------------------------

def plot_timeseries(ferret_name="MWOW_POINT", output=None):
    """Plot a single-point time series that was loaded with load_mwow_point.

    Parameters
    ----------
    ferret_name : str
        Ferret variable name.
    output : str, optional
        If given, save the plot to this file (PNG or PDF).
    """
    pyferret.run(f'plot/title="MWOW Wind Speed Time Series"'
                 f'/vlimits=0:30/symbol=17 {ferret_name}')
    if output:
        pyferret.run(f'frame/file="{output}"')
        print(f"Saved to {output}")


def plot_region_orbit(ferret_name="MWOW_WIND_SPEED_REGION", orbit=1,
                      output=None, palette="viridis"):
    """Shade-plot one orbit of a loaded region.

    Parameters
    ----------
    ferret_name : str
        Ferret variable name.
    orbit : int
        Orbit index (1-based, maps to Ferret K).
    output : str, optional
        Save plot to file.
    palette : str
        Ferret color palette name.
    """
    pyferret.run(
        f'shade/k={orbit}/palette={palette}'
        f'/title="MWOW Wind Speed – Orbit {orbit}" {ferret_name}'
    )
    if output:
        pyferret.run(f'frame/file="{output}"')
        print(f"Saved to {output}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _open(paths):
    if isinstance(paths, str):
        expanded = sorted(_glob.glob(paths))
        if not expanded:
            expanded = [paths]
        paths = expanded
    return xr.open_mfdataset(paths, chunks="auto")


_UNITS = {
    "wind_speed": "m/s",
    "wind_direction": "degrees",
    "wind_speed_uncert": "m/s",
    "wind_direction_uncert": "degrees",
    "quality_indicator": "1",
    "sensor_id": "1",
}


def _unit_for(var):
    return _UNITS.get(var, "1")
