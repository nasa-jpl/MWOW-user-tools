"""
Temporal collocation of sensors within MWOW L3 gridded data.

MWOW L3 files place all sensors on the same 0.125-degree grid, so spatial
collocation is inherent.  This module finds temporal matches: grid cells
where both a reference sensor (typically ASCAT-B/C) and a target sensor
have observations within a configurable time window.

The primary output is a structured array of matched observations suitable
for computing bias, standard deviation, joint histograms, and other
inter-sensor comparison statistics.
"""

import numpy as np
import xarray as xr


# Sensor ID mapping (matches MWOW v0.2 product convention)
SENSOR_IDS = {
    "ASCAT-B": 0,
    "ASCAT-C": 1,
    "EOS-6": 2,
    "HY-2B": 3,
    "HY-2C": 4,
    "SMAP": 5,
    "SWOT": 6,
    "COWVR": 7,
}

SENSOR_NAMES = {v: k for k, v in SENSOR_IDS.items()}


def find_collocations(ds, target_sensor, ref_sensors=("ASCAT-B", "ASCAT-C"),
                      max_dt_minutes=30, qi_max=None):
    """Find temporally collocated observations between sensors on the MWOW grid.

    For each grid cell where both the reference sensor(s) and the target sensor
    have valid wind_speed observations, pairs are formed by matching the closest
    reference observation in time (within the allowed window).

    Parameters
    ----------
    ds : xarray.Dataset
        An MWOW v0.2 dataset (as returned by :func:`mwow_tools.open_mwow_files`).
        Must have dimensions ``(orbit, latitude, longitude)`` and variables
        ``sensor_id``, ``time``, ``wind_speed``, ``wind_direction``,
        ``quality_indicator``.
    target_sensor : str or int
        Sensor to compare against the reference.  Either a name from
        :data:`SENSOR_IDS` (e.g. ``"HY-2B"``) or an integer sensor ID.
    ref_sensors : tuple of str or int, optional
        Reference sensor(s).  Default is ``("ASCAT-B", "ASCAT-C")`` combined.
    max_dt_minutes : float, optional
        Maximum allowed time difference in minutes (default 30).
    qi_max : int or None, optional
        If set, only include target observations with
        ``quality_indicator <= qi_max``.  Reference observations are not
        filtered (ASCAT QC is generally trusted).

    Returns
    -------
    dict
        Dictionary with arrays of equal length:

        - ``ref_speed`` : reference wind speed (m/s)
        - ``ref_direction`` : reference wind direction (deg)
        - ``target_speed`` : target sensor wind speed (m/s)
        - ``target_direction`` : target sensor wind direction (deg)
        - ``target_qi`` : target quality_indicator value
        - ``dt_minutes`` : time difference (target - ref) in minutes
        - ``lat`` : latitude of the grid cell
        - ``lon`` : longitude of the grid cell
        - ``time`` : reference observation time

    Notes
    -----
    This function loads data into memory in chunks by orbit pair.  For large
    datasets (many months), consider processing one file at a time and
    concatenating results.
    """
    # Resolve sensor names to IDs
    target_id = _resolve_sensor_id(target_sensor)
    ref_ids = [_resolve_sensor_id(s) for s in ref_sensors]

    # Identify orbits belonging to each group
    sensor_ids = ds.sensor_id.values
    ref_orbit_mask = np.array([sid in ref_ids for sid in sensor_ids])
    target_orbit_mask = np.array([sid == target_id for sid in sensor_ids])

    ref_orbit_indices = np.where(ref_orbit_mask)[0]
    target_orbit_indices = np.where(target_orbit_mask)[0]

    if len(ref_orbit_indices) == 0 or len(target_orbit_indices) == 0:
        return _empty_result()

    # Process orbit pairs to find collocations
    results = {k: [] for k in (
        "ref_speed", "ref_direction", "target_speed", "target_direction",
        "target_qi", "dt_minutes", "lat", "lon", "time")}

    max_dt_ns = np.timedelta64(int(max_dt_minutes * 60), "s")

    lat_vals = ds.latitude.values
    lon_vals = ds.longitude.values
    n_lon = len(lon_vals)

    # Pre-compute ASCAT valid cell indices (raveled) for each ref orbit.
    # ASCAT swaths are sparse (~5-10% of the grid), so working with indices
    # rather than full 2D masks is much faster.
    ref_data = []
    for r_orb in ref_orbit_indices:
        ref_spd = ds.wind_speed.values[r_orb]
        ref_time = ds.time.values[r_orb]
        valid = np.isfinite(ref_spd) & ~np.isnat(ref_time)
        raveled = np.where(valid.ravel())[0]
        ref_data.append({
            "spd": ref_spd,
            "dir": ds.wind_direction.values[r_orb],
            "time": ref_time,
            "raveled": raveled,
        })

    for t_orb in target_orbit_indices:
        # Load target orbit data
        target_spd = ds.wind_speed.values[t_orb]       # (lat, lon)
        target_dir = ds.wind_direction.values[t_orb]
        target_qi = ds.quality_indicator.values[t_orb]
        target_time = ds.time.values[t_orb]            # (lat, lon) datetime64

        # Mask for valid target cells
        target_valid = np.isfinite(target_spd) & ~np.isnat(target_time)
        if qi_max is not None:
            target_valid &= (target_qi <= qi_max)

        if not target_valid.any():
            continue

        # Raveled indices of valid target cells
        target_raveled = np.where(target_valid.ravel())[0]

        # For each reference orbit, find spatial overlap then temporal matches
        for rd in ref_data:
            # Intersect raveled indices — cells where both have valid data
            both_raveled = np.intersect1d(target_raveled, rd["raveled"],
                                          assume_unique=True)

            if len(both_raveled) == 0:
                continue

            # Convert back to 2D indices
            lat_idx = both_raveled // n_lon
            lon_idx = both_raveled % n_lon

            # Compute time difference only at overlapping cells
            dt = target_time[lat_idx, lon_idx] - rd["time"][lat_idx, lon_idx]
            within_window = np.abs(dt) <= max_dt_ns

            if not within_window.any():
                continue

            # Extract matched values
            lat_idx = lat_idx[within_window]
            lon_idx = lon_idx[within_window]
            dt_matched = dt[within_window]

            results["ref_speed"].append(rd["spd"][lat_idx, lon_idx])
            results["ref_direction"].append(rd["dir"][lat_idx, lon_idx])
            results["target_speed"].append(target_spd[lat_idx, lon_idx])
            results["target_direction"].append(target_dir[lat_idx, lon_idx])
            results["target_qi"].append(target_qi[lat_idx, lon_idx])
            results["dt_minutes"].append(
                dt_matched.astype("timedelta64[s]").astype(float) / 60.0)
            results["lat"].append(lat_vals[lat_idx])
            results["lon"].append(lon_vals[lon_idx])
            results["time"].append(rd["time"][lat_idx, lon_idx])

    # Concatenate all results
    return {k: np.concatenate(v) if v else np.array([], dtype=_dtype_for(k))
            for k, v in results.items()}


def collocate_files(file_paths, target_sensor, ref_sensors=("ASCAT-B", "ASCAT-C"),
                    max_dt_minutes=30, qi_max=None, chunks=None):
    """Run collocation across multiple MWOW files, processing one at a time.

    This is a convenience wrapper around :func:`find_collocations` that avoids
    loading all files into memory simultaneously.

    Parameters
    ----------
    file_paths : list of str
        Paths to MWOW L3 NetCDF files.
    target_sensor : str or int
        Target sensor name or ID.
    ref_sensors : tuple, optional
        Reference sensors (default ASCAT-B/C).
    max_dt_minutes : float, optional
        Maximum time difference in minutes (default 30).
    qi_max : int or None, optional
        Maximum quality_indicator for target observations.
    chunks : str or dict or None, optional
        Chunk spec for xarray. Default None loads eagerly (faster for
        single-file processing).

    Returns
    -------
    dict
        Same structure as :func:`find_collocations`, concatenated across files.
    """
    all_results = {k: [] for k in (
        "ref_speed", "ref_direction", "target_speed", "target_direction",
        "target_qi", "dt_minutes", "lat", "lon", "time")}

    for fpath in file_paths:
        ds = xr.open_dataset(fpath, chunks=chunks)
        result = find_collocations(
            ds, target_sensor, ref_sensors=ref_sensors,
            max_dt_minutes=max_dt_minutes, qi_max=qi_max)
        ds.close()

        for k, v in result.items():
            if len(v) > 0:
                all_results[k].append(v)

    return {k: np.concatenate(v) if v else np.array([], dtype=_dtype_for(k))
            for k, v in all_results.items()}


def collocate_files_multi(file_paths, target_sensors,
                          ref_sensors=("ASCAT-B", "ASCAT-C"),
                          max_dt_minutes=30, qi_max=None):
    """Collocate multiple target sensors in a single pass over the files.

    This is significantly faster than calling :func:`collocate_files`
    separately for each sensor, because each file is opened and its arrays
    loaded from disk only once (I/O dominates runtime over NFS).

    Parameters
    ----------
    file_paths : list of str
        Paths to MWOW L3 NetCDF files.
    target_sensors : list of str or int
        Target sensor names or IDs to collocate.
    ref_sensors : tuple, optional
        Reference sensors (default ASCAT-B/C).
    max_dt_minutes : float, optional
        Maximum time difference in minutes (default 30).
    qi_max : int or None, optional
        Maximum quality_indicator for target observations.

    Returns
    -------
    dict of dict
        Keyed by sensor name, each value is the same structure as
        :func:`find_collocations`.
    """
    # Resolve all sensor IDs upfront
    target_ids = {_resolve_sensor_id(s): s if isinstance(s, str)
                  else SENSOR_NAMES.get(s, str(s))
                  for s in target_sensors}
    ref_ids = [_resolve_sensor_id(s) for s in ref_sensors]

    # Initialize per-sensor result accumulators
    result_keys = ("ref_speed", "ref_direction", "target_speed",
                   "target_direction", "target_qi", "dt_minutes",
                   "lat", "lon", "time")
    all_results = {name: {k: [] for k in result_keys}
                   for name in target_ids.values()}

    max_dt_ns = np.timedelta64(int(max_dt_minutes * 60), "s")

    for fpath in file_paths:
        ds = xr.open_dataset(fpath)
        sensor_ids = ds.sensor_id.values
        lat_vals = ds.latitude.values
        lon_vals = ds.longitude.values
        n_lon = len(lon_vals)

        # Identify reference orbits
        ref_orbit_indices = [i for i, sid in enumerate(sensor_ids)
                             if sid in ref_ids]
        if not ref_orbit_indices:
            ds.close()
            continue

        # Load all arrays once (I/O is the bottleneck)
        wind_speed = ds.wind_speed.values
        wind_direction = ds.wind_direction.values
        quality_indicator = ds.quality_indicator.values
        time_arr = ds.time.values
        ds.close()

        # Pre-compute reference data
        ref_data = []
        for r_orb in ref_orbit_indices:
            ref_spd = wind_speed[r_orb]
            ref_time = time_arr[r_orb]
            valid = np.isfinite(ref_spd) & ~np.isnat(ref_time)
            raveled = np.where(valid.ravel())[0]
            if len(raveled) > 0:
                ref_data.append({
                    "spd": ref_spd,
                    "dir": wind_direction[r_orb],
                    "time": ref_time,
                    "raveled": raveled,
                })

        if not ref_data:
            continue

        # Process each target sensor using the already-loaded arrays
        for tid, tname in target_ids.items():
            target_orbit_indices = [i for i, sid in enumerate(sensor_ids)
                                    if sid == tid]
            if not target_orbit_indices:
                continue

            for t_orb in target_orbit_indices:
                target_spd = wind_speed[t_orb]
                target_dir = wind_direction[t_orb]
                target_qi = quality_indicator[t_orb]
                target_time = time_arr[t_orb]

                target_valid = np.isfinite(target_spd) & ~np.isnat(target_time)
                if qi_max is not None:
                    target_valid &= (target_qi <= qi_max)

                if not target_valid.any():
                    continue

                target_raveled = np.where(target_valid.ravel())[0]

                for rd in ref_data:
                    both_raveled = np.intersect1d(
                        target_raveled, rd["raveled"], assume_unique=True)
                    if len(both_raveled) == 0:
                        continue

                    lat_idx = both_raveled // n_lon
                    lon_idx = both_raveled % n_lon

                    dt = target_time[lat_idx, lon_idx] - rd["time"][lat_idx, lon_idx]
                    within_window = np.abs(dt) <= max_dt_ns

                    if not within_window.any():
                        continue

                    lat_idx = lat_idx[within_window]
                    lon_idx = lon_idx[within_window]
                    dt_matched = dt[within_window]

                    res = all_results[tname]
                    res["ref_speed"].append(rd["spd"][lat_idx, lon_idx])
                    res["ref_direction"].append(rd["dir"][lat_idx, lon_idx])
                    res["target_speed"].append(target_spd[lat_idx, lon_idx])
                    res["target_direction"].append(target_dir[lat_idx, lon_idx])
                    res["target_qi"].append(target_qi[lat_idx, lon_idx])
                    res["dt_minutes"].append(
                        dt_matched.astype("timedelta64[s]").astype(float) / 60.0)
                    res["lat"].append(lat_vals[lat_idx])
                    res["lon"].append(lon_vals[lon_idx])
                    res["time"].append(rd["time"][lat_idx, lon_idx])

    # Concatenate results per sensor
    return {name: {k: np.concatenate(v) if v else np.array([], dtype=_dtype_for(k))
                   for k, v in res.items()}
            for name, res in all_results.items()}


def _resolve_sensor_id(sensor):
    """Convert sensor name or ID to integer ID."""
    if isinstance(sensor, str):
        sensor_upper = sensor.upper()
        if sensor_upper not in SENSOR_IDS:
            raise ValueError(
                f"Unknown sensor '{sensor}'. "
                f"Valid names: {', '.join(SENSOR_IDS.keys())}")
        return SENSOR_IDS[sensor_upper]
    return int(sensor)


def _empty_result():
    """Return an empty collocation result dict."""
    return {
        "ref_speed": np.array([], dtype=np.float32),
        "ref_direction": np.array([], dtype=np.float32),
        "target_speed": np.array([], dtype=np.float32),
        "target_direction": np.array([], dtype=np.float32),
        "target_qi": np.array([], dtype=np.float32),
        "dt_minutes": np.array([], dtype=np.float64),
        "lat": np.array([], dtype=np.float32),
        "lon": np.array([], dtype=np.float32),
        "time": np.array([], dtype="datetime64[ns]"),
    }


def _dtype_for(key):
    """Return the appropriate dtype for a result key."""
    if key == "time":
        return "datetime64[ns]"
    elif key == "dt_minutes":
        return np.float64
    else:
        return np.float32
