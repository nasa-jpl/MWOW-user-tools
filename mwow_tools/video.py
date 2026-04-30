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
from matplotlib.colors import Normalize

from mwow_tools.reader import open_mwow_files, select_region
from mwow_tools.collocate import SENSOR_NAMES


def generate_region_video(file_paths, region, output_dir=".",
                          output_name="region_video.mp4",
                          speedup=3600, fps=10, dpi=150,
                          speed_range=(0, 25), cmap="YlOrRd",
                          utc_offset=0, qi_max=0,
                          title=None):
    """Generate a video of orbit passes over a geographic region.

    Each frame shows one orbit's wind speed field.  The dwell time of each
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
    cmap : str, optional
        Colormap for wind speed (default "YlOrRd").
    utc_offset : int, optional
        Hours offset from UTC for the local time clock overlay (default 0).
    qi_max : int or None, optional
        Maximum quality_indicator to display (default 0).  Set to None
        to show all data.
    title : str or None, optional
        Title for the video frames.  If None, auto-generated from region.

    Returns
    -------
    str or None
        Path to the output video file, or None if no data/encoding failed.
    """
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
    print("  Loading wind speed and time data...")
    wind_speed = ds_region.wind_speed.values  # (orbit, lat, lon)
    qi = ds_region.quality_indicator.values
    time_data = ds_region.time.values         # (orbit, lat, lon)
    sensor_ids = ds_region.sensor_id.values   # (orbit,)
    lats = ds_region.latitude.values
    lons = ds_region.longitude.values

    # Apply QI filter
    if qi_max is not None:
        wind_speed = np.where(qi <= qi_max, wind_speed, np.nan)

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

    # Sort by time, excluding NaT
    valid_time_mask = ~np.isnat(orbit_times)
    valid_indices = np.where(valid_time_mask)[0]
    sort_order = np.argsort(orbit_times[valid_indices])
    valid_indices = valid_indices[sort_order]

    if len(valid_indices) == 0:
        print("  WARNING: No orbits with valid time data, skipping video.")
        return None

    # Compute frame durations based on inter-observation time
    frame_durations = []  # in seconds of video time
    min_frame_duration = 1.0 / fps  # at least one frame
    for i in range(len(valid_indices)):
        if i < len(valid_indices) - 1:
            dt_real = (orbit_times[valid_indices[i + 1]] -
                       orbit_times[valid_indices[i]])
            dt_seconds = dt_real / np.timedelta64(1, "s")
            video_seconds = max(dt_seconds / speedup, min_frame_duration)
        else:
            video_seconds = min_frame_duration * 3  # Linger on last frame
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

    for frame_num, orb_idx in enumerate(valid_indices):
        fig, ax = plt.subplots(figsize=(8, 6))

        spd = wind_speed[orb_idx]
        im = ax.pcolormesh(
            lons, lats, spd,
            cmap=cmap, norm=norm, shading="nearest")

        fig.colorbar(im, ax=ax, label="Wind Speed [m/s]", shrink=0.8)

        # Sensor name annotation
        sid = sensor_ids[orb_idx]
        sensor_name = SENSOR_NAMES.get(int(sid), f"ID={sid:.0f}") if \
            np.isfinite(sid) else "Unknown"
        ax.set_title(f"{title}\n{sensor_name}", fontsize=10)

        # Local time clock overlay
        t = orbit_times[orb_idx]
        if not np.isnat(t):
            local_time = t + np.timedelta64(utc_offset, "h")
            time_str = str(local_time)[:16].replace("T", " ")
            tz_label = f"UTC{utc_offset:+d}" if utc_offset != 0 else "UTC"
            ax.text(0.02, 0.98, f"{time_str} {tz_label}",
                    transform=ax.transAxes, fontsize=9,
                    verticalalignment="top",
                    bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_aspect("equal")

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
    # pad filter ensures dimensions are divisible by 2 (required by libx264)
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
        # Keep frames for debugging
        print(f"  Frames preserved in: {tmpdir}")
        return None

    # Clean up temp frames
    for fpath in frame_paths:
        os.unlink(fpath)
    os.unlink(concat_path)
    os.rmdir(tmpdir)

    print(f"  Video saved: {output_path}")
    return output_path
