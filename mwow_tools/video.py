"""
Regional wind field video generation from MWOW L3 data.

Produces time-lapse animations showing orbit-by-orbit wind observations
over a geographic region, with frame dwell times proportional to real
inter-observation intervals.
"""

import os
import subprocess
import tempfile

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
import cartopy.crs as ccrs
import cartopy.feature as cfeature

from mwow_tools.reader import open_mwow_files, select_region
from mwow_tools.collocate import SENSOR_NAMES


# Custom colormap: black → dark blue → blue → cyan → green → yellow → orange → red
_MWOW_JET_COLORS = [
    (0.00, (0.0, 0.0, 0.0)),
    (0.15, (0.0, 0.0, 0.5)),
    (0.30, (0.0, 0.0, 1.0)),
    (0.40, (0.0, 1.0, 1.0)),
    (0.55, (0.0, 1.0, 0.0)),
    (0.70, (1.0, 1.0, 0.0)),
    (0.85, (1.0, 0.5, 0.0)),
    (1.00, (1.0, 0.0, 0.0)),
]

MWOW_JET_CMAP = LinearSegmentedColormap.from_list(
    "mwow_jet",
    [(pos, col) for pos, col in _MWOW_JET_COLORS])


def generate_region_video(file_paths, region, output_dir=".",
                          output_name="region_video.mp4",
                          speedup=3600, fps=10, dpi=150,
                          speed_range=(0, 25), cmap=None,
                          utc_offset=0, qi_max=1,
                          title=None, arrow_subsample=None,
                          timestamp_pos=None, timestamp_fontsize=None,
                          timestamp_date_color=None):
    """Generate a video of orbit passes over a geographic region.

    Each frame shows one orbit's wind speed field with coastlines,
    lat/lon gridlines, and wind direction arrows.  The dwell time of each
    frame is proportional to the real elapsed time until the next observation,
    so temporal gaps are visually represented.

    Parameters
    ----------
    file_paths : list of str
        Paths to MWOW L3 NetCDF files.
    region : dict
        Region specification with keys ``lat_center``, ``lon_center``,
        ``lat_size``, ``lon_size`` (as used by
        :func:`mwow_tools.select_region`).
    output_dir : str, optional
        Directory for the output video (default ".").
    output_name : str, optional
        Output filename (default "region_video.mp4").
    speedup : float, optional
        Seconds of real time per second of video (default 3600 = 1 hour
        per video second).
    fps : int, optional
        Video frame rate (default 10).
    dpi : int, optional
        Figure DPI for frames (default 150).
    speed_range : tuple, optional
        (vmin, vmax) for the wind speed colorbar in m/s (default (0, 25)).
    cmap : str or Colormap or None, optional
        Colormap for wind speed.  If None, uses the built-in mwow_jet
        (black → blue → cyan → green → yellow → orange → red).
    utc_offset : int, optional
        Hours offset from UTC for the local time clock overlay (default 0).
    qi_max : int or None, optional
        Maximum quality_indicator to display (default 1).  Set to None
        to show all data.
    title : str or None, optional
        Title for the video frames.  If None, auto-generated from region.
    arrow_subsample : int or None, optional
        Subsample factor for wind direction arrows.  If None, auto-computed
        to give ~12 arrows across the plot.
    timestamp_pos : tuple or None, optional
        (x, y) position in axes coordinates for the timestamp.
        Default (0.02, 0.98) = top-left.
    timestamp_fontsize : int or None, optional
        Font size for the timestamp (default 9).
    timestamp_date_color : str or None, optional
        If set, the date portion (YYYY-MM-DD) is rendered in this color
        and the time portion in black, both without a background box.

    Returns
    -------
    str or None
        Path to the output video file, or None if no data/encoding failed.
    """
    if cmap is None:
        cmap = MWOW_JET_CMAP

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_name)

    # Load and subset data
    print("  Loading region data...")
    ds = open_mwow_files(file_paths)
    ds_region = select_region(
        ds, region["lat_center"], region["lon_center"],
        lat_size=region["lat_size"], lon_size=region["lon_size"],
        drop_empty_orbits=True)

    n_orbits = ds_region.sizes["orbit"]
    print(f"  Orbits with data in region: {n_orbits}")

    if n_orbits == 0:
        print("  WARNING: No orbits with data in region, skipping video.")
        return None

    # Compute data eagerly for frame generation
    print("  Loading wind speed, direction, and time data...")
    wind_speed = ds_region.wind_speed.values      # (orbit, lat, lon)
    wind_dir = ds_region.wind_direction.values    # (orbit, lat, lon)
    qi = ds_region.quality_indicator.values
    time_data = ds_region.time.values             # (orbit, lat, lon)
    sensor_ids = ds_region.sensor_id.values       # (orbit,)
    lats = ds_region.latitude.values
    lons = ds_region.longitude.values

    # Apply QI filter
    if qi_max is not None:
        mask = qi <= qi_max
        wind_speed = np.where(mask, wind_speed, np.nan)
        wind_dir = np.where(mask, wind_dir, np.nan)

    # Compute arrow subsample factor
    n_lon_cells = len(lons)
    if arrow_subsample is None:
        arrow_subsample = max(1, n_lon_cells // 12)

    # Get representative time per orbit (median of valid times)
    orbit_times = []
    for i in range(n_orbits):
        valid_times = time_data[i][~np.isnat(time_data[i])]
        if len(valid_times) > 0:
            median_ns = int(np.median(valid_times.astype("int64")))
            orbit_times.append(np.datetime64(median_ns, "ns"))
        else:
            orbit_times.append(np.datetime64("NaT"))
    orbit_times = np.array(orbit_times)

    # Sort by time, excluding NaT (empty orbits with no observations)
    valid_time_mask = ~np.isnat(orbit_times)
    valid_indices = np.where(valid_time_mask)[0]
    sort_order = np.argsort(orbit_times[valid_indices])
    valid_indices = valid_indices[sort_order]

    if len(valid_indices) == 0:
        print("  WARNING: No orbits with valid time data, skipping video.")
        return None

    # Compute frame durations based on inter-observation time
    frame_durations = []
    min_frame_duration = 1.0 / fps
    for i in range(len(valid_indices)):
        if i < len(valid_indices) - 1:
            dt_real = (orbit_times[valid_indices[i + 1]] -
                       orbit_times[valid_indices[i]])
            dt_seconds = dt_real / np.timedelta64(1, "s")
            video_seconds = max(dt_seconds / speedup, min_frame_duration)
        else:
            video_seconds = min_frame_duration * 3
        frame_durations.append(video_seconds)

    # Generate frames
    if title is None:
        lat_s = region["lat_center"] - region["lat_size"]
        lat_n = region["lat_center"] + region["lat_size"]
        lon_w = region["lon_center"] - region["lon_size"]
        lon_e = region["lon_center"] + region["lon_size"]
        title = (f"Wind Speed — "
                 f"{abs(lat_s):.0f}{'N' if lat_s >= 0 else 'S'} to "
                 f"{abs(lat_n):.0f}{'N' if lat_n >= 0 else 'S'}, "
                 f"{abs(lon_w):.0f}{'W' if lon_w < 0 else 'E'} to "
                 f"{abs(lon_e):.0f}{'W' if lon_e < 0 else 'E'}")

    print(f"  Generating {len(valid_indices)} frames...")
    tmpdir = tempfile.mkdtemp(prefix="mwow_video_")
    frame_paths = []
    frame_repeat_counts = []

    norm = Normalize(vmin=speed_range[0], vmax=speed_range[1])
    projection = ccrs.PlateCarree()

    # Precompute subsampled coordinate grids for arrows
    lon_sub = lons[::arrow_subsample]
    lat_sub = lats[::arrow_subsample]
    lon_mesh, lat_mesh = np.meshgrid(lon_sub, lat_sub)

    for frame_num, orb_idx in enumerate(valid_indices):
        fig, ax = plt.subplots(figsize=(8, 6),
                               subplot_kw={"projection": projection})

        ax.set_extent([lons[0], lons[-1], lats[0], lats[-1]], crs=projection)

        # Land and coastlines
        ax.add_feature(cfeature.LAND, facecolor="lightgray", zorder=1)
        ax.coastlines(resolution="10m", linewidth=0.8, zorder=3)

        # Wind speed pcolormesh
        spd = wind_speed[orb_idx]
        im = ax.pcolormesh(
            lons, lats, spd,
            cmap=cmap, norm=norm, shading="nearest",
            transform=projection, zorder=2)

        # Wind direction arrows (subsampled)
        spd_sub = spd[::arrow_subsample, ::arrow_subsample]
        dir_sub = wind_dir[orb_idx, ::arrow_subsample, ::arrow_subsample]

        # Direction-to: u = speed * sin(dir), v = speed * cos(dir)
        dir_rad = np.deg2rad(dir_sub)
        u = np.sin(dir_rad)
        v = np.cos(dir_rad)

        # Only plot arrows where we have valid speed data
        arrow_mask = np.isfinite(spd_sub) & np.isfinite(dir_sub)
        u_plot = np.where(arrow_mask, u, np.nan)
        v_plot = np.where(arrow_mask, v, np.nan)

        ax.quiver(lon_mesh, lat_mesh, u_plot, v_plot,
                  scale=25, width=0.003, headwidth=3, headlength=4,
                  color="white", alpha=0.8, transform=projection, zorder=4)

        # Lat/lon gridlines
        gl = ax.gridlines(draw_labels=True, linewidth=0.5, color="gray",
                          alpha=0.5, linestyle="--", zorder=5)
        gl.top_labels = False
        gl.right_labels = False

        # Colorbar
        fig.colorbar(im, ax=ax, label="Wind Speed [m/s]", shrink=0.8, pad=0.08)

        # Sensor name annotation
        sid = sensor_ids[orb_idx]
        if not np.isfinite(sid):
            print(f"  ERROR: Orbit {orb_idx} has valid time data but NaN "
                  f"sensor_id. This indicates a corrupt or malformed file — "
                  f"all orbits with observations should have a sensor_id.")
            sensor_name = "Unknown"
        else:
            sensor_name = SENSOR_NAMES.get(int(sid), f"ID={sid:.0f}")
        ax.set_title(f"{title}\n{sensor_name}", fontsize=10)

        # Local time clock overlay
        t = orbit_times[orb_idx]
        if not np.isnat(t):
            local_time = t + np.timedelta64(utc_offset, "h")
            time_str = str(local_time)[:16].replace("T", " ")
            tz_label = f"UTC{utc_offset:+d}" if utc_offset != 0 else "UTC"
            ts_x, ts_y = timestamp_pos or (0.02, 0.98)
            ts_fs = timestamp_fontsize or 9

            if timestamp_date_color:
                date_part = time_str[:10]
                time_part = f" {time_str[11:]} {tz_label}"
                txt_date = ax.text(
                    ts_x, ts_y, date_part,
                    transform=ax.transAxes, fontsize=ts_fs,
                    fontweight="bold", color=timestamp_date_color,
                    verticalalignment="top", zorder=6)
                fig.canvas.draw()
                bb = txt_date.get_window_extent(
                    renderer=fig.canvas.get_renderer())
                bb_ax = bb.transformed(ax.transAxes.inverted())
                ax.text(bb_ax.x1, ts_y, time_part,
                        transform=ax.transAxes, fontsize=ts_fs,
                        fontweight="bold", color="black",
                        verticalalignment="top", zorder=6)
            else:
                ax.text(ts_x, ts_y, f"{time_str} {tz_label}",
                        transform=ax.transAxes, fontsize=ts_fs,
                        verticalalignment="top",
                        bbox=dict(boxstyle="round", facecolor="white",
                                  alpha=0.8),
                        zorder=6)

        frame_path = os.path.join(tmpdir, f"frame_{frame_num:05d}.png")
        fig.savefig(frame_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        frame_paths.append(frame_path)

        # How many times to repeat this frame for proper timing
        n_repeats = max(1, int(round(frame_durations[frame_num] * fps)))
        frame_repeat_counts.append(n_repeats)

        if frame_num % 50 == 0 and frame_num > 0:
            print(f"    Frame {frame_num}/{len(valid_indices)}")

    # Create concat file for ffmpeg with frame durations
    concat_path = os.path.join(tmpdir, "concat.txt")
    with open(concat_path, "w") as f:
        for fpath, n_rep in zip(frame_paths, frame_repeat_counts):
            duration = n_rep / fps
            f.write(f"file '{fpath}'\n")
            f.write(f"duration {duration:.4f}\n")
        # ffmpeg needs the last file repeated
        f.write(f"file '{frame_paths[-1]}'\n")

    # Encode video
    print("  Encoding video with ffmpeg...")
    vf = f"fps={fps},pad=ceil(iw/2)*2:ceil(ih/2)*2"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_path,
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "23",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: ffmpeg failed:\n{result.stderr[:500]}")
        print(f"  Frames preserved in: {tmpdir}")
        return None

    # Clean up temp frames
    for fpath in frame_paths:
        os.unlink(fpath)
    os.unlink(concat_path)
    os.rmdir(tmpdir)

    print(f"  Video saved: {output_path}")
    return output_path


def generate_track_video(file_paths, track, region_size=10.0,
                         lat_size=None, lon_size=None,
                         output_dir=".", output_name="track_video.mp4",
                         speedup=3600, fps=10, dpi=150,
                         speed_range=(0, 25), cmap=None,
                         utc_offset=0, qi_max=1,
                         title=None, arrow_subsample=None,
                         show_track=True, track_color="magenta",
                         timestamp_pos=None, timestamp_fontsize=None,
                         timestamp_date_color=None):
    """Generate a video where the map center follows a track.

    The track can represent a storm, a ship, or any moving point of
    interest.  Each frame is centered on the interpolated track position
    at the observation time.

    Parameters
    ----------
    file_paths : list of str
        Paths to MWOW L3 NetCDF files.
    track : str, dict, or pandas.DataFrame
        Track data.  Accepts:
        - A path to a CSV file with columns ``latitude``, ``longitude``,
          ``time`` (requires pandas).
        - A dict with keys ``"latitude"``, ``"longitude"``, ``"time"``
          containing array-like values.
        - A pandas DataFrame with those columns.
    region_size : float, optional
        Half-width of the map region in degrees (default 10.0, giving a
        20-degree box).  Used for both lat and lon unless overridden by
        ``lat_size`` / ``lon_size``.
    lat_size : float or None, optional
        Half-width in latitude (degrees).  Overrides ``region_size`` for
        the latitude dimension if set.
    lon_size : float or None, optional
        Half-width in longitude (degrees).  Overrides ``region_size`` for
        the longitude dimension if set.
    output_dir : str, optional
        Directory for the output video (default ".").
    output_name : str, optional
        Output filename (default "track_video.mp4").
    speedup : float, optional
        Seconds of real time per second of video (default 3600).
    fps : int, optional
        Video frame rate (default 10).
    dpi : int, optional
        Figure DPI for frames (default 150).
    speed_range : tuple, optional
        (vmin, vmax) for wind speed colorbar in m/s (default (0, 25)).
    cmap : str or Colormap or None, optional
        Colormap for wind speed (default: mwow_jet).
    utc_offset : int, optional
        Hours offset from UTC for the time overlay (default 0).
    qi_max : int or None, optional
        Maximum quality_indicator to display (default 1).
    title : str or None, optional
        Title for the video frames.
    arrow_subsample : int or None, optional
        Subsample factor for wind direction arrows.
    show_track : bool, optional
        Overlay the track line on each frame (default True).
    track_color : str, optional
        Color for the track overlay (default "magenta").
    timestamp_pos : tuple or None, optional
        (x, y) position in axes coordinates for the timestamp.
    timestamp_fontsize : int or None, optional
        Font size for the timestamp.
    timestamp_date_color : str or None, optional
        If set, renders the date in this color and time in black.

    Returns
    -------
    str or None
        Path to the output video file, or None if no data/encoding failed.
    """
    if cmap is None:
        cmap = MWOW_JET_CMAP

    # Resolve lat/lon half-widths
    half_lat = lat_size if lat_size is not None else region_size
    half_lon = lon_size if lon_size is not None else region_size

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_name)

    # Parse track data
    track_lat, track_lon, track_time = _parse_track(track)
    track_epoch = track_time.astype("datetime64[s]").astype("float64")

    # Load dataset lazily
    print("  Loading dataset (lazy)...")
    ds = open_mwow_files(file_paths)

    # Get orbit start times for sorting and filtering
    orbit_start_time = ds.orbit_start_time.values
    n_orbits_total = len(orbit_start_time)

    # Filter to orbits within the track time range (± 6 hours)
    margin = np.timedelta64(6, "h")
    track_start = track_time[0] - margin
    track_end = track_time[-1] + margin

    valid_mask = (~np.isnat(orbit_start_time)
                  & (orbit_start_time >= track_start)
                  & (orbit_start_time <= track_end))
    valid_indices = np.where(valid_mask)[0]

    if len(valid_indices) == 0:
        print("  WARNING: No orbits within track time range, skipping video.")
        return None

    # Sort by time
    sort_order = np.argsort(orbit_start_time[valid_indices])
    valid_indices = valid_indices[sort_order]
    orbit_times = orbit_start_time[valid_indices]

    print(f"  Orbits within track period: {len(valid_indices)}")

    # Generate frames (durations computed after, based on rendered frames only)
    min_frame_duration = 1.0 / fps
    print(f"  Processing {len(valid_indices)} candidate orbits...")
    tmpdir = tempfile.mkdtemp(prefix="mwow_storm_video_")
    frame_paths = []
    frame_times = []

    norm = Normalize(vmin=speed_range[0], vmax=speed_range[1])
    projection = ccrs.PlateCarree()

    actual_frame_num = 0
    for seq_num, orb_idx in enumerate(valid_indices):
        t = orbit_times[seq_num]
        t_epoch = t.astype("datetime64[s]").astype("float64")

        # Interpolate track to get storm center
        center_lat = np.interp(t_epoch, track_epoch, track_lat)
        center_lon = np.interp(t_epoch, track_epoch, track_lon)

        # Map extent
        lat_s = center_lat - half_lat
        lat_n = center_lat + half_lat
        lon_w = center_lon - half_lon
        lon_e = center_lon + half_lon

        # Load just this orbit's regional slice
        ds_slice = ds.sel(
            latitude=slice(lat_s, lat_n),
            longitude=slice(lon_w, lon_e)
        ).isel(orbit=orb_idx).compute()

        lats = ds_slice.latitude.values
        lons = ds_slice.longitude.values

        if len(lats) == 0 or len(lons) == 0:
            continue

        wind_speed = ds_slice.wind_speed.values
        wind_dir = ds_slice.wind_direction.values
        qi = ds_slice.quality_indicator.values

        # Apply QI filter
        if qi_max is not None:
            mask = qi <= qi_max
            wind_speed = np.where(mask, wind_speed, np.nan)
            wind_dir = np.where(mask, wind_dir, np.nan)

        # Skip orbits with no valid data within 1° of track center
        lat_near = np.abs(lats - center_lat) <= 1.0
        lon_near = np.abs(lons - center_lon) <= 1.0
        near_center = wind_speed[np.ix_(lat_near, lon_near)]
        if not np.any(np.isfinite(near_center)):
            continue

        # Compute arrow subsample
        n_lon_cells = len(lons)
        sub = arrow_subsample if arrow_subsample else max(1, n_lon_cells // 12)

        # Render frame
        fig, ax = plt.subplots(figsize=(8, 6),
                               subplot_kw={"projection": projection})

        ax.set_extent([lon_w, lon_e, lat_s, lat_n], crs=projection)
        ax.add_feature(cfeature.LAND, facecolor="lightgray", zorder=1)

        lat_span = lat_n - lat_s
        coast_res = "110m" if lat_span > 60 else "50m" if lat_span > 15 else "10m"
        ax.coastlines(resolution=coast_res, linewidth=0.8, zorder=3)

        im = ax.pcolormesh(
            lons, lats, wind_speed,
            cmap=cmap, norm=norm, shading="nearest",
            transform=projection, zorder=2)

        # Wind direction arrows
        lon_sub = lons[::sub]
        lat_sub = lats[::sub]
        lon_mesh, lat_mesh = np.meshgrid(lon_sub, lat_sub)

        spd_sub = wind_speed[::sub, ::sub]
        dir_sub = wind_dir[::sub, ::sub]
        dir_rad = np.deg2rad(dir_sub)
        u = np.sin(dir_rad)
        v = np.cos(dir_rad)

        arrow_mask = np.isfinite(spd_sub) & np.isfinite(dir_sub)
        u_plot = np.where(arrow_mask, u, np.nan)
        v_plot = np.where(arrow_mask, v, np.nan)

        ax.quiver(lon_mesh, lat_mesh, u_plot, v_plot,
                  scale=25, width=0.003, headwidth=3, headlength=4,
                  color="white", alpha=0.8, transform=projection, zorder=4)

        # Track overlay
        if show_track:
            # Past track up to current time
            past_mask = track_time <= t
            if np.any(past_mask):
                ax.plot(track_lon[past_mask], track_lat[past_mask],
                        color=track_color, linewidth=2, marker="o",
                        markersize=3, transform=projection, zorder=6)
            # Current position marker
            ax.plot(center_lon, center_lat, marker="X", markersize=10,
                    color=track_color, markeredgecolor="white",
                    markeredgewidth=1, transform=projection, zorder=7)

        # Gridlines
        gl = ax.gridlines(draw_labels=True, linewidth=0.5, color="gray",
                          alpha=0.5, linestyle="--", zorder=5)
        gl.top_labels = False
        gl.right_labels = False

        # Colorbar
        fig.colorbar(im, ax=ax, label="Wind Speed [m/s]", shrink=0.8, pad=0.08)

        # Sensor name
        sid = ds_slice.sensor_id.values
        if np.isfinite(sid):
            sensor_name = SENSOR_NAMES.get(int(sid), f"ID={sid:.0f}")
        else:
            sensor_name = "Unknown"

        frame_title = title or "Storm Tracking"
        ax.set_title(frame_title, fontsize=10)

        # Timestamp with sensor name, yellow background box
        if not np.isnat(t):
            local_time = t + np.timedelta64(utc_offset, "h")
            time_str = str(local_time)[:16].replace("T", " ")
            tz_label = f"UTC{utc_offset:+d}" if utc_offset != 0 else "UTC"
            ts_x, ts_y = timestamp_pos or (0.02, 0.98)
            ts_fs = timestamp_fontsize or 11

            stamp_text = f"{sensor_name}  {time_str} {tz_label}"
            ts_bbox = dict(boxstyle="round,pad=0.3", facecolor="yellow",
                           edgecolor="black", alpha=0.9)

            if timestamp_date_color:
                date_part = f"{sensor_name}  {time_str[:10]}"
                time_part = f" {time_str[11:]} {tz_label}"
                txt_date = ax.text(
                    ts_x, ts_y, date_part,
                    transform=ax.transAxes, fontsize=ts_fs,
                    fontweight="bold", color=timestamp_date_color,
                    verticalalignment="top",
                    bbox=ts_bbox, zorder=8)
                fig.canvas.draw()
                bb = txt_date.get_window_extent(
                    renderer=fig.canvas.get_renderer())
                bb_ax = bb.transformed(ax.transAxes.inverted())
                ax.text(bb_ax.x1 + 0.005, ts_y, time_part,
                        transform=ax.transAxes, fontsize=ts_fs,
                        fontweight="bold", color="black",
                        verticalalignment="top",
                        bbox=dict(boxstyle="round,pad=0.3",
                                  facecolor="yellow", edgecolor="none",
                                  alpha=0.9),
                        zorder=8)
            else:
                ax.text(ts_x, ts_y, stamp_text,
                        transform=ax.transAxes, fontsize=ts_fs,
                        fontweight="bold",
                        verticalalignment="top",
                        bbox=ts_bbox, zorder=8)

        frame_path = os.path.join(tmpdir, f"frame_{actual_frame_num:05d}.png")
        fig.savefig(frame_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        frame_paths.append(frame_path)
        frame_times.append(t)
        actual_frame_num += 1

        if actual_frame_num % 50 == 0:
            print(f"    Rendered {actual_frame_num} frames "
                  f"({seq_num + 1}/{len(valid_indices)} orbits processed)")

    if len(frame_paths) == 0:
        print("  WARNING: No frames generated, skipping video.")
        return None

    print(f"  Rendered {len(frame_paths)} frames from "
          f"{len(valid_indices)} candidate orbits")

    # Compute frame durations from actual rendered frame times
    frame_times = np.array(frame_times)
    concat_path = os.path.join(tmpdir, "concat.txt")
    with open(concat_path, "w") as f:
        for i, fpath in enumerate(frame_paths):
            if i < len(frame_paths) - 1:
                dt_real = frame_times[i + 1] - frame_times[i]
                dt_seconds = dt_real / np.timedelta64(1, "s")
                duration = max(dt_seconds / speedup, min_frame_duration)
            else:
                duration = min_frame_duration * 3
            f.write(f"file '{fpath}'\n")
            f.write(f"duration {duration:.4f}\n")
        f.write(f"file '{frame_paths[-1]}'\n")

    # Encode video
    print("  Encoding video with ffmpeg...")
    vf = f"fps={fps},pad=ceil(iw/2)*2:ceil(ih/2)*2"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_path,
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "23",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: ffmpeg failed:\n{result.stderr[:500]}")
        print(f"  Frames preserved in: {tmpdir}")
        return None

    # Clean up
    for fpath in frame_paths:
        os.unlink(fpath)
    os.unlink(concat_path)
    os.rmdir(tmpdir)

    print(f"  Video saved: {output_path}")
    return output_path


def _parse_track(track):
    """Parse track input into (lat, lon, time) numpy arrays."""
    if isinstance(track, str):
        import pandas as pd
        df = pd.read_csv(track, parse_dates=["time"])
        return (df["latitude"].values.astype(float),
                df["longitude"].values.astype(float),
                df["time"].values.astype("datetime64[ns]"))
    elif isinstance(track, dict):
        return (np.asarray(track["latitude"], dtype=float),
                np.asarray(track["longitude"], dtype=float),
                np.asarray(track["time"], dtype="datetime64[ns]"))
    else:
        # Assume pandas DataFrame
        return (track["latitude"].values.astype(float),
                track["longitude"].values.astype(float),
                track["time"].values.astype("datetime64[ns]"))


# Backwards-compatible alias
generate_storm_video = generate_track_video
