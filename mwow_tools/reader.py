"""
Core functions for reading and subsetting MWOW ocean wind data products.

MWOW files are CF-compliant NetCDF on a global 0.125-degree grid with an
``orbit`` dimension that indexes individual satellite passes within each
6-hourly accumulation window.
"""

import glob as _glob
import numpy as np
import xarray as xr


def open_mwow_files(paths, chunks="auto"):
    """Open one or more MWOW NetCDF files and return a lazily-loaded Dataset.

    For **lowres** files (same global grid, different time windows), files are
    concatenated along the ``orbit`` dimension.

    For **highres** tiles (different spatial grids, same time window), tiles are
    merged by coordinates into a single dataset covering the union of all tile
    regions.  Regions with no data are filled with NaN.

    The function auto-detects which strategy to use by comparing the latitude
    coordinates of the first two files.

    Parameters
    ----------
    paths : str or list of str
        A single file path, a list of paths, or a glob pattern
        (e.g. ``"/data/mwow/*.nc"``).
    chunks : str or dict, optional
        Chunk specification passed to :func:`xarray.open_mfdataset`.
        Default is ``"auto"`` (uses chunking embedded in the files).

    Returns
    -------
    xarray.Dataset
        Lazily-loaded dataset with dimensions ``(orbit, latitude, longitude)``.
    """
    if isinstance(paths, str):
        expanded = sorted(_glob.glob(paths))
        if not expanded:
            expanded = [paths]
        paths = expanded

    if len(paths) == 1:
        return xr.open_mfdataset(paths, chunks=chunks,
                                 combine="nested", concat_dim="orbit")

    # Peek at the first two files to decide merge strategy.
    with xr.open_dataset(paths[0]) as ds0, xr.open_dataset(paths[1]) as ds1:
        same_grid = (ds0.sizes["latitude"] == ds1.sizes["latitude"]
                     and ds0.sizes["longitude"] == ds1.sizes["longitude"]
                     and np.array_equal(ds0.latitude.values,
                                        ds1.latitude.values)
                     and np.array_equal(ds0.longitude.values,
                                        ds1.longitude.values))

    if same_grid:
        # Lowres files (or same-tile highres): concatenate along orbit.
        return xr.open_mfdataset(paths, chunks=chunks,
                                 combine="nested", concat_dim="orbit")
    else:
        # Highres tiles covering different regions: merge by coordinates.
        return xr.open_mfdataset(paths, chunks=chunks,
                                 combine="by_coords", join="outer")


def select_point(ds, lat, lon):
    """Extract all orbit data at the nearest grid point to a given coordinate.

    Parameters
    ----------
    ds : xarray.Dataset
        An MWOW dataset (as returned by :func:`open_mwow_files`).
    lat : float
        Target latitude in degrees (south is negative).
    lon : float
        Target longitude in degrees (west is negative).

    Returns
    -------
    xarray.Dataset
        Dataset reduced to a single lat/lon point, indexed by orbit.
    """
    return ds.sel(latitude=lat, longitude=lon, method="nearest")


def match_ship_track(ds, lats, lons, times):
    """Match a sequence of moving-platform positions to the nearest MWOW data.

    For each position, the nearest grid cell is selected and the orbit with
    the closest observation time is chosen.

    Parameters
    ----------
    ds : xarray.Dataset
        An MWOW dataset (as returned by :func:`open_mwow_files`).
    lats : array-like
        Latitudes of the platform track (degrees).
    lons : array-like
        Longitudes of the platform track (degrees).
    times : array-like
        Observation times of the platform track (datetime64 or strings
        parseable by NumPy).

    Returns
    -------
    xarray.Dataset
        Dataset with one entry per input position, containing the MWOW
        observation nearest in space and time.
    """
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    times = np.asarray(times, dtype="datetime64[ns]")

    point = xr.DataArray(np.arange(len(lats)), dims="point")
    lat_da = xr.DataArray(lats, dims="point", coords={"point": point})
    lon_da = xr.DataArray(lons, dims="point", coords={"point": point})
    time_da = xr.DataArray(times, dims="point", coords={"point": point})

    ds_ll = ds.sel(latitude=lat_da, longitude=lon_da, method="nearest")

    dt = abs(ds_ll["time"] - time_da)
    dt_filled = dt.fillna(np.timedelta64(99, "D"))
    orbit_idx = dt_filled.argmin(dim="orbit").compute()

    return ds_ll.isel(orbit=orbit_idx)


def select_region(ds, lat_center, lon_center, lat_size=5.0, lon_size=5.0,
                  drop_empty_orbits=True):
    """Select a geographic region and optionally drop orbits with no data.

    Parameters
    ----------
    ds : xarray.Dataset
        An MWOW dataset (as returned by :func:`open_mwow_files`).
    lat_center, lon_center : float
        Center of the region (degrees).
    lat_size, lon_size : float, optional
        Half-width of the region in degrees (default 5.0, giving a
        10-degree box).
    drop_empty_orbits : bool, optional
        If True (default), drop orbit slices that are entirely NaN within
        the region.

    Returns
    -------
    xarray.Dataset
        Subset of the input dataset covering the requested region.
    """
    ds_region = ds.sel(
        latitude=slice(lat_center - lat_size, lat_center + lat_size),
        longitude=slice(lon_center - lon_size, lon_center + lon_size),
    )

    if drop_empty_orbits:
        valid = (ds_region.wind_speed
                 .notnull()
                 .any(dim=("latitude", "longitude"))
                 .compute())
        ds_region = ds_region.isel(orbit=valid)

    return ds_region
