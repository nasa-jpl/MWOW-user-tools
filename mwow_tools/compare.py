"""
Parallel inter-sensor comparison statistics for MWOW L3 data.

Computes speed bias, MAD, STD and direction MAD, RMS between a target
sensor and a reference sensor using latitude-chunked parallelism for
efficient I/O on NFS-mounted data.

Sensors are already co-located on the same 0.125-degree grid; only
temporal proximity (default 30 min) is required for a valid pair.
"""

import numpy as np
import xarray as xr
from multiprocessing import Pool


def _process_lat_chunk(args):
    """Process one latitude chunk of one file for matched pairs.

    Parameters
    ----------
    args : tuple
        (fpath, lat_start, lat_end, target_orbits, ref_orbits, max_dt_ns)

    Returns
    -------
    dict or None
        Keys: ref_speed, ref_direction, target_speed, target_direction,
        target_qi, lat, lon.  Values are 1-D arrays.
    """
    fpath, lat_start, lat_end, target_orbits, ref_orbits, max_dt_ns = args

    ds = xr.open_dataset(fpath)
    ws = ds.wind_speed[:, lat_start:lat_end, :].values
    wd = ds.wind_direction[:, lat_start:lat_end, :].values
    qi = ds.quality_indicator[:, lat_start:lat_end, :].values
    tm = ds.time[:, lat_start:lat_end, :].values
    lat_vals = ds.latitude.values[lat_start:lat_end]
    lon_vals = ds.longitude.values
    ds.close()

    accum = {k: [] for k in (
        "ref_speed", "ref_direction", "target_speed",
        "target_direction", "target_qi", "lat", "lon")}

    for t_orb in target_orbits:
        t_spd = ws[t_orb]
        t_dir = wd[t_orb]
        t_qi = qi[t_orb]
        t_time = tm[t_orb]
        t_valid = np.isfinite(t_spd) & ~np.isnat(t_time)

        if not t_valid.any():
            continue

        for r_orb in ref_orbits:
            r_spd = ws[r_orb]
            r_time = tm[r_orb]
            r_valid = np.isfinite(r_spd) & ~np.isnat(r_time)

            both_valid = t_valid & r_valid
            if not both_valid.any():
                continue

            dt = np.abs(t_time[both_valid] - r_time[both_valid])
            within_window = dt <= max_dt_ns

            if not within_window.any():
                continue

            bv_idx = np.where(both_valid)
            lat_idx = bv_idx[0][within_window]
            lon_idx = bv_idx[1][within_window]

            accum["ref_speed"].append(r_spd[lat_idx, lon_idx])
            accum["ref_direction"].append(wd[r_orb][lat_idx, lon_idx])
            accum["target_speed"].append(t_spd[lat_idx, lon_idx])
            accum["target_direction"].append(t_dir[lat_idx, lon_idx])
            accum["target_qi"].append(t_qi[lat_idx, lon_idx])
            accum["lat"].append(lat_vals[lat_idx])
            accum["lon"].append(lon_vals[lon_idx])

    concat = {}
    for k, v in accum.items():
        if v:
            concat[k] = np.concatenate(v)
    return concat if concat else None


def extract_matched_pairs(file_paths, target_sensor, ref_sensors,
                          max_dt_minutes=30, n_workers=48,
                          n_lat=1440):
    """Extract all time-matched observation pairs between two sensors.

    Uses latitude-chunked parallelism: each file is processed sequentially,
    but within each file the latitude dimension is split across workers.
    Each worker reads only its latitude slice from disk (via netCDF4
    hyperslab reads), keeping memory usage low.

    Parameters
    ----------
    file_paths : list of str
        Paths to MWOW L3 NetCDF files.
    target_sensor : str or int
        Target sensor name (e.g. "HY-2B") or integer ID.
    ref_sensors : str, int, or sequence thereof
        Reference sensor(s).  E.g. ("ASCAT-B", "ASCAT-C").
    max_dt_minutes : float, optional
        Maximum time difference in minutes (default 30).
    n_workers : int, optional
        Number of parallel workers (default 48).
    n_lat : int, optional
        Number of latitude rows in the grid (default 1440).

    Returns
    -------
    dict
        Arrays of matched observations:
        ref_speed, ref_direction, target_speed, target_direction,
        target_qi, lat, lon.
    """
    from mwow_tools.collocate import SENSOR_IDS, _resolve_sensor_id

    target_id = _resolve_sensor_id(target_sensor)
    if isinstance(ref_sensors, (str, int)):
        ref_sensors = [ref_sensors]
    ref_ids = set(_resolve_sensor_id(s) for s in ref_sensors)

    max_dt_ns = np.timedelta64(int(max_dt_minutes * 60), "s")
    chunk_size = max(1, n_lat // n_workers)

    result_keys = ("ref_speed", "ref_direction", "target_speed",
                   "target_direction", "target_qi", "lat", "lon")
    all_results = {k: [] for k in result_keys}

    for fpath in file_paths:
        ds = xr.open_dataset(fpath)
        sensor_ids = ds.sensor_id.values
        ds.close()

        target_orbits = [i for i, sid in enumerate(sensor_ids)
                         if np.isfinite(sid) and int(sid) == target_id]
        ref_orbits = [i for i, sid in enumerate(sensor_ids)
                      if np.isfinite(sid) and int(sid) in ref_ids]

        if not target_orbits or not ref_orbits:
            continue

        chunk_args = []
        for start in range(0, n_lat, chunk_size):
            end = min(start + chunk_size, n_lat)
            chunk_args.append((fpath, start, end, target_orbits,
                               ref_orbits, max_dt_ns))

        with Pool(n_workers) as pool:
            chunk_results = pool.map(_process_lat_chunk, chunk_args)

        for cres in chunk_results:
            if cres is not None:
                for k, v in cres.items():
                    all_results[k].append(v)

    return {k: np.concatenate(v) if v else np.array([], dtype=np.float32)
            for k, v in all_results.items()}


def circular_abs_diff(d1, d2):
    """Absolute circular difference in degrees, result in [0, 180]."""
    diff = np.abs(d1 - d2)
    return np.minimum(diff, 360.0 - diff)


def comparison_stats(pairs, qi_max=None, min_speed_for_dir=None,
                     lat_limit=None, bbox=None):
    """Compute wind comparison statistics from matched observation pairs.

    Speed stats (bias, MAD, STD) use all valid pairs.  Direction stats
    (MAD, RMS) additionally exclude pairs where either speed is below
    min_speed_for_dir, since low-wind directions are unreliable.

    Parameters
    ----------
    pairs : dict
        Output of :func:`extract_matched_pairs`.  Must contain:
        ref_speed, ref_direction, target_speed, target_direction,
        target_qi, lat, lon.
    qi_max : int or None, optional
        Maximum quality_indicator to include (default None = all).
    min_speed_for_dir : float or None, optional
        Exclude pairs where either speed < this value from direction
        stats only (default None = no speed filter for direction).
    lat_limit : float or None, optional
        Only include pairs where |lat| < lat_limit (default None).
    bbox : dict or None, optional
        Spatial bounding box with keys lat_min, lat_max, lon_min, lon_max.
        Only pairs within this box are included.  If None, no spatial
        restriction beyond lat_limit.

    Returns
    -------
    dict
        speed_bias : mean(target - ref) speed [m/s]
        speed_mad : median |target - ref| speed [m/s]
        speed_std : std(target - ref) speed [m/s]
        speed_n : number of pairs used for speed stats
        dir_mad : median absolute circular direction difference [deg]
        dir_rms : RMS of circular direction difference [deg]
        dir_n : number of pairs used for direction stats
    """
    empty = {"speed_bias": np.nan, "speed_mad": np.nan,
             "speed_std": np.nan, "speed_n": 0,
             "dir_mad": np.nan, "dir_rms": np.nan, "dir_n": 0}

    if len(pairs.get("ref_speed", [])) == 0:
        return empty

    # Base mask: QI, spatial, finite values
    mask = np.ones(len(pairs["ref_speed"]), dtype=bool)

    if qi_max is not None:
        mask &= pairs["target_qi"] <= qi_max

    if lat_limit is not None:
        mask &= np.abs(pairs["lat"]) < lat_limit

    if bbox is not None:
        mask &= (pairs["lat"] >= bbox["lat_min"])
        mask &= (pairs["lat"] <= bbox["lat_max"])
        mask &= (pairs["lon"] >= bbox["lon_min"])
        mask &= (pairs["lon"] <= bbox["lon_max"])

    # Speed stats: require finite speeds
    speed_mask = mask & np.isfinite(pairs["ref_speed"]) & np.isfinite(pairs["target_speed"])
    speed_n = int(speed_mask.sum())

    if speed_n > 0:
        ref_spd = pairs["ref_speed"][speed_mask]
        tgt_spd = pairs["target_speed"][speed_mask]
        speed_diff = tgt_spd - ref_spd
        speed_bias = float(np.mean(speed_diff))
        speed_mad = float(np.median(np.abs(speed_diff)))
        speed_std = float(np.std(speed_diff))
    else:
        speed_bias = speed_mad = speed_std = np.nan

    # Direction stats: additionally require finite directions and min speed
    dir_mask = speed_mask & np.isfinite(pairs["ref_direction"]) & np.isfinite(pairs["target_direction"])

    if min_speed_for_dir is not None:
        dir_mask &= (pairs["ref_speed"] >= min_speed_for_dir)
        dir_mask &= (pairs["target_speed"] >= min_speed_for_dir)

    dir_n = int(dir_mask.sum())

    if dir_n > 0:
        ref_dir = pairs["ref_direction"][dir_mask]
        tgt_dir = pairs["target_direction"][dir_mask]
        dir_diff = circular_abs_diff(tgt_dir, ref_dir)
        dir_mad = float(np.median(dir_diff))
        dir_rms = float(np.sqrt(np.mean(dir_diff**2)))
    else:
        dir_mad = dir_rms = np.nan

    return {
        "speed_bias": speed_bias,
        "speed_mad": speed_mad,
        "speed_std": speed_std,
        "speed_n": speed_n,
        "dir_mad": dir_mad,
        "dir_rms": dir_rms,
        "dir_n": dir_n,
    }
