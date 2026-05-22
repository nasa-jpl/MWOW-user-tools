"""Generate all AOML hurricane demo outputs (figures + videos + comparison).

Usage:
    python gen_demo.py [all|figures|videos|comparison]
    python gen_demo.py [timeseries|windmap|shiptrack|coverage|videos|comparison]

Requires conda environment: mwow-user-tools
Data root: /u/tsali-z0/fore/mwow_v0.2_fwd/{nonepi,epi}/lowres/
"""
import sys
import glob
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from mwow_tools import (
    open_mwow_files, select_point, select_region, match_ship_track,
    plot_sensor_coverage, generate_track_video,
    collocate_files, plot_joint_histogram,
    SENSOR_NAMES,
)
from mwow_tools.video import MWOW_JET_CMAP
import cartopy.crs as ccrs
import cartopy.feature as cfeature

MS_TO_KT = 1.9438
DATA_ROOT = '/u/tsali-z0/fore/mwow_v0.2_fwd/nonepi/lowres'
EPI_ROOT = '/u/tsali-z0/fore/mwow_v0.2_fwd/epi/lowres'
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
TRACK_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def get_files(start_date, end_date, root=DATA_ROOT):
    dates = pd.date_range(start_date, end_date, freq='D')
    paths = []
    for d in dates:
        day_dir = os.path.join(root, f'{d.year:04d}/{d.month:02d}/{d.day:02d}')
        paths.extend(sorted(glob.glob(os.path.join(day_dir, '*.nc'))))
    print(f'  Found {len(paths)} files for {start_date} to {end_date}')
    return paths


# ─── FIGURES ──────────────────────────────────────────────────────────────────

def gen_timeseries():
    """Time series at NDBC 41049 with buoy data overlay (Hurricane Humberto)."""
    print('=== Time Series with Buoy (Humberto, NDBC 41049) ===')

    buoy_lat, buoy_lon = 27.505, -62.271
    files = get_files('2025-09-24', '2025-10-01')
    ds = open_mwow_files(files)
    ds_point = select_point(ds, lat=buoy_lat, lon=buoy_lon)

    times = ds_point.time.values
    speeds = ds_point.wind_speed.values * MS_TO_KT
    sensor_ids_arr = ds_point.sensor_id.values

    valid = np.isfinite(speeds) & ~np.isnat(times)
    t_valid = times[valid]
    s_valid = speeds[valid]
    sid_valid = sensor_ids_arr[valid]
    print(f'  MWOW observations: {valid.sum()}')

    buoy_path = os.path.join(TRACK_DIR, 'ndbc_41049_sep24_oct01_2025.csv')
    buoy = pd.read_csv(buoy_path, parse_dates=['time'])
    buoy_valid = buoy.dropna(subset=['wind_speed_ms'])
    print(f'  Buoy observations: {len(buoy_valid)}')

    sensor_colors = {0: "#1f77b4", 1: "#2ca02c", 2: "#ff7f0e", 5: "#9467bd", 6: "#17becf"}
    fig, ax = plt.subplots(figsize=(12, 4.5))

    buoy_hourly = buoy_valid.set_index('time').resample('1h').mean().dropna()
    ax.scatter(buoy_hourly.index, buoy_hourly['wind_speed_ms'].values * MS_TO_KT,
               marker='x', c='black', s=25, linewidths=1.2,
               label='NDBC 41049 (buoy)', zorder=3)

    for sid in np.unique(sid_valid[np.isfinite(sid_valid)]).astype(int):
        mask = np.isfinite(sid_valid) & (sid_valid.astype(float) == sid)
        ax.scatter(t_valid[mask], s_valid[mask],
                   c=sensor_colors.get(sid, "gray"), s=40,
                   label=f'MWOW {SENSOR_NAMES[sid]}', alpha=0.9,
                   edgecolors="none", zorder=4)

    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Wind Speed [kt]")
    ax.set_title(f"MWOW vs NDBC Buoy 41049 ({buoy_lat:.1f}°N, {abs(buoy_lon):.1f}°W)\n"
                 f"Hurricane Humberto Passage (Sep 24–Oct 1, 2025)")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'humberto_timeseries_v2.png'), dpi=150, bbox_inches="tight")
    plt.close('all')
    print('  Saved: humberto_timeseries_v2.png')


def gen_windmap():
    """Erin wind field — separate SMAP and EOS-6 single-orbit plots."""
    print('=== Wind Maps (Erin, Aug 16, separate SMAP + EOS-6) ===')

    track = pd.read_csv(os.path.join(TRACK_DIR, 'erin_2025_track.csv'), parse_dates=['time'])
    files = get_files('2025-08-16', '2025-08-16')
    ds = open_mwow_files(files)

    region = {'lat_center': 19.8, 'lon_center': -59.0, 'lat_size': 8.0, 'lon_size': 8.0}
    ds_region = select_region(ds, region['lat_center'], region['lon_center'],
                              lat_size=region['lat_size'], lon_size=region['lon_size'],
                              drop_empty_orbits=False)

    sensor_ids_arr = ds_region.sensor_id.values
    lats = ds_region.latitude.values
    lons = ds_region.longitude.values

    for sensor_id, sensor_label in [(2, 'EOS-6'), (5, 'SMAP')]:
        orbits = [i for i in range(len(sensor_ids_arr))
                  if np.isfinite(sensor_ids_arr[i]) and int(sensor_ids_arr[i]) == sensor_id]

        best_orb, best_max = None, 0
        for orb in orbits:
            ws = ds_region.wind_speed.values[orb]
            qi = ds_region.quality_indicator.values[orb]
            valid = np.isfinite(ws) & (qi <= 2)
            if valid.sum() > 0:
                mx = np.nanmax(ws[valid])
                if mx > best_max:
                    best_max = mx
                    best_orb = orb

        if best_orb is None:
            print(f'  No valid {sensor_label} data')
            continue

        ws = ds_region.wind_speed.values[best_orb]
        wd = ds_region.wind_direction.values[best_orb]
        qi = ds_region.quality_indicator.values[best_orb]
        valid = np.isfinite(ws) & (qi <= 2)
        max_speed_kt = np.nanmax(ws[valid]) * MS_TO_KT

        orb_times = ds_region.time.values[best_orb]
        valid_times = orb_times[~np.isnat(orb_times)]
        med_time = np.sort(valid_times)[len(valid_times) // 2]
        t_pd = pd.Timestamp(med_time)
        time_str = t_pd.strftime('%Y-%m-%d %H:%M UTC')

        nearby = track[(track.time >= t_pd - pd.Timedelta('3h')) &
                       (track.time <= t_pd + pd.Timedelta('3h'))]
        best_track_max = nearby['max_wind_kt'].max() if len(nearby) > 0 else np.nan

        ws_plot = np.where(valid, ws * MS_TO_KT, np.nan)
        wd_plot = np.where(valid, wd, np.nan)
        vmax = max(80, int(np.ceil(max_speed_kt / 10) * 10))

        projection = ccrs.PlateCarree()
        fig, ax = plt.subplots(figsize=(10, 7), subplot_kw={"projection": projection})
        ax.set_extent([lons[0], lons[-1], lats[0], lats[-1]], crs=projection)
        ax.add_feature(cfeature.LAND, facecolor="lightgray", zorder=1)
        ax.coastlines(resolution="50m", linewidth=0.8, zorder=3)

        norm = Normalize(vmin=0, vmax=vmax)
        im = ax.pcolormesh(lons, lats, ws_plot, cmap=MWOW_JET_CMAP, norm=norm,
                           shading="nearest", transform=projection, zorder=2)

        sub = max(1, len(lons) // 15)
        lon_sub = lons[::sub]
        lat_sub = lats[::sub]
        lon_mesh, lat_mesh = np.meshgrid(lon_sub, lat_sub)
        dir_sub = wd_plot[::sub, ::sub]
        spd_sub = ws_plot[::sub, ::sub]
        u = np.sin(np.deg2rad(dir_sub))
        v = np.cos(np.deg2rad(dir_sub))
        arrow_mask = np.isfinite(spd_sub) & np.isfinite(dir_sub)
        ax.quiver(lon_mesh, lat_mesh,
                  np.where(arrow_mask, u, np.nan),
                  np.where(arrow_mask, v, np.nan),
                  scale=25, width=0.003, headwidth=3, headlength=4,
                  color="white", alpha=0.8, transform=projection, zorder=4)

        gl = ax.gridlines(draw_labels=True, linewidth=0.5, color="gray",
                          alpha=0.5, linestyle="--", zorder=5)
        gl.top_labels = False
        gl.right_labels = False
        fig.colorbar(im, ax=ax, label="Wind Speed [kt]", shrink=0.8, pad=0.05)

        title_lines = [f"Hurricane Erin Wind Field — {sensor_label}",
                       f"{time_str}"]
        if not np.isnan(best_track_max):
            title_lines.append(f"Best Track Max: {best_track_max:.0f} kt | "
                               f"{sensor_label} Max: {max_speed_kt:.0f} kt")
        else:
            title_lines.append(f"{sensor_label} Max: {max_speed_kt:.0f} kt")
        ax.set_title("\n".join(title_lines), fontsize=11, fontweight="bold")

        out_name = f'erin_wind_{sensor_label.lower().replace("-", "")}.png'
        fig.savefig(os.path.join(OUT_DIR, out_name), dpi=150, bbox_inches="tight")
        plt.close('all')
        print(f'  {sensor_label}: time={time_str}, max={max_speed_kt:.0f} kt → {out_name}')


def gen_shiptrack():
    """Ship track: NOAA Pisces (Apr 7-8 2026), EPI data."""
    print('=== Ship Track (NOAA Pisces, Apr 7-8 2026, EPI MWOW) ===')

    ship_all = pd.read_csv(os.path.join(TRACK_DIR, 'noaa_pisces_apr2026.csv'),
                           parse_dates=['time'])
    ship = ship_all.iloc[25:32].reset_index(drop=True)
    ship_lats = ship['latitude'].values
    ship_lons = ship['longitude'].values
    ship_times = ship['time'].values
    ship_winds_kt = ship['wind_speed_ms'].values * MS_TO_KT

    print(f'  Using {len(ship)} positions: {ship.time.iloc[0]} to {ship.time.iloc[-1]}')

    files = get_files('2026-04-07', '2026-04-08', root=EPI_ROOT)
    ds = open_mwow_files(files)
    ds_matched = match_ship_track(ds, ship_lats, ship_lons, ship_times)

    speeds_kt = ds_matched.wind_speed.values * MS_TO_KT
    sids = ds_matched.sensor_id.values

    cmap = plt.cm.jet
    norm = Normalize(vmin=0, vmax=30)

    lat_min, lat_max = ship_lats.min() - 0.5, ship_lats.max() + 0.5
    lon_min, lon_max = ship_lons.min() - 0.5, ship_lons.max() + 0.5

    fig, ax = plt.subplots(figsize=(12, 6), subplot_kw={"projection": ccrs.PlateCarree()})
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND, facecolor="lightgray")
    ax.coastlines(resolution="10m", linewidth=0.8)
    gl = ax.gridlines(draw_labels=True, linewidth=0.5, alpha=0.5, linestyle="--")
    gl.top_labels = False
    gl.right_labels = False

    ax.plot(ship_lons, ship_lats, 'k--', linewidth=1.5, label="Vessel Track",
            transform=ccrs.PlateCarree())
    ax.scatter(ship_lons, ship_lats, c=ship_winds_kt, cmap=cmap,
               norm=norm, s=160, marker='s', edgecolors="black", linewidths=0.8,
               transform=ccrs.PlateCarree(), zorder=4, label="Ship anemometer")

    mwow_lons = ds_matched.longitude.values
    mwow_lats = ds_matched.latitude.values - 0.15
    sc_mwow = ax.scatter(mwow_lons, mwow_lats,
                         c=speeds_kt, cmap=cmap, norm=norm,
                         s=120, marker='o', edgecolors="black", linewidths=0.5,
                         transform=ccrs.PlateCarree(), zorder=5, label="MWOW satellite")

    for i in range(len(sids)):
        sid = sids[i]
        if np.isfinite(sid):
            sensor_name = SENSOR_NAMES.get(int(sid), f'ID={int(sid)}')
        else:
            sensor_name = '?'
        ax.text(mwow_lons[i], mwow_lats[i] - 0.1,
                sensor_name, fontsize=8, fontweight='bold',
                color='darkblue', ha='center', va='top',
                transform=ccrs.PlateCarree(), zorder=6)

    for i in range(len(ship_times)):
        t_str = pd.Timestamp(ship_times[i]).strftime('%b %d %H:%M')
        ax.text(ship_lons[i], ship_lats[i] + 0.12, t_str,
                fontsize=7, ha='center', va='bottom', color='gray',
                transform=ccrs.PlateCarree())

    fig.colorbar(sc_mwow, ax=ax, label="Wind Speed [kt]", shrink=0.7)
    ax.set_title("Ship Track Matching: NOAA Ship Pisces (WTDL)\n"
                 "Eastward Transit, April 7–8, 2026\n"
                 "Squares = ship anemometer, Circles = MWOW satellite",
                 fontsize=10)
    ax.legend(loc="lower right", fontsize=9)
    fig.savefig(os.path.join(OUT_DIR, 'pisces_ship_track.png'), dpi=150, bbox_inches="tight")
    plt.close('all')
    print('  Saved: pisces_ship_track.png')


def gen_coverage():
    """Sensor coverage as 2x2 six-hour panels (nonepi + epi)."""
    for root, suffix, title_prefix in [(DATA_ROOT, 'nonepi', 'Non-EPI'),
                                        (EPI_ROOT, 'epi', 'EPI')]:
        print(f'=== Coverage 6hr Panels ({title_prefix}) ===')
        region = {'lat_center': 19.5, 'lon_center': -58.0, 'lat_size': 10.0, 'lon_size': 12.0}
        day_dir = os.path.join(root, '2025/08/16')
        files = sorted(glob.glob(os.path.join(day_dir, '*.nc')))
        print(f'  Files: {len(files)}')

        fig, axes = plt.subplots(2, 2, figsize=(14, 10),
                                 subplot_kw={"projection": ccrs.PlateCarree()})
        time_labels = ['00-06 UTC', '06-12 UTC', '12-18 UTC', '18-00 UTC']

        for i, (f, ax, tlabel) in enumerate(zip(files, axes.flatten(), time_labels)):
            ds = open_mwow_files([f])
            plot_sensor_coverage(ds, region=region, qi_max=2,
                                 title=f'Aug 16, 2025  {tlabel}', ax=ax)

        fig.suptitle(f'{title_prefix} Sensor Coverage: Hurricane Erin (Aug 16, 2025)',
                     fontsize=13, fontweight='bold', y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        out_name = f'erin_coverage_6hr_{suffix}.png'
        fig.savefig(os.path.join(OUT_DIR, out_name), dpi=150, bbox_inches="tight")
        plt.close('all')
        print(f'  Saved: {out_name}')


# ─── VIDEOS ──────────────────────────────────────────────────────────────────

def gen_videos():
    """Generate storm-tracking videos for all three hurricanes."""
    storms = [
        ('melissa', 'Hurricane Melissa (2025)', '2025-10-21', '2025-10-31'),
        ('erin', 'Hurricane Erin (2025)', '2025-08-11', '2025-08-22'),
        ('humberto', 'Hurricane Humberto (2025)', '2025-09-24', '2025-10-01'),
    ]
    for name, title, start, end in storms:
        print(f'=== Storm Video: {title} ({start} to {end}) ===')
        files = get_files(start, end)
        track = os.path.join(TRACK_DIR, f'{name}_2025_track.csv')

        video = generate_track_video(
            files, track=track, region_size=5.0,
            output_dir=OUT_DIR, output_name=f'{name}_storm_tracking.mp4',
            speedup=14400, fps=10, dpi=150,
            speed_range=(0, 30), qi_max=2,
            title=title,
            show_track=True, track_color='magenta',
            timestamp_date_color='navy',
        )
        print(f'  Result: {video}')


# ─── COMPARISON ───────────────────────────────────────────────────────────────

def gen_comparison():
    """EOS-6 vs ASCAT joint histogram (tropical Atlantic, Sep 2025)."""
    print('=== Sensor Comparison: EOS-6 vs ASCAT (Sep 15-17, 2025) ===')

    files = get_files('2025-09-15', '2025-09-17')
    collocations = collocate_files(
        files,
        target_sensor="EOS-6",
        ref_sensors=("ASCAT-B", "ASCAT-C"),
        max_dt_minutes=30,
        qi_max=None,
    )
    print(f'  Collocated pairs: {len(collocations["ref_speed"])}')

    plot_joint_histogram(
        collocations["ref_speed"],
        collocations["target_speed"],
        target_name="EOS-6",
        ref_name="ASCAT",
        speed_range=(0, 25),
        save_path=os.path.join(OUT_DIR, "eos6_vs_ascat_histogram.png"),
        title="EOS-6 vs ASCAT (Sep 15–17, 2025)\nTropical Atlantic",
    )
    plt.close('all')
    print('  Saved: eos6_vs_ascat_histogram.png')


# ─── MAIN ─────────────────────────────────────────────────────────────────────

SECTIONS = {
    'timeseries': gen_timeseries,
    'windmap': gen_windmap,
    'shiptrack': gen_shiptrack,
    'coverage': gen_coverage,
    'videos': gen_videos,
    'comparison': gen_comparison,
}

if __name__ == '__main__':
    section = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if section == 'all':
        for name, func in SECTIONS.items():
            func()
    elif section == 'figures':
        gen_timeseries()
        gen_windmap()
        gen_shiptrack()
        gen_coverage()
    elif section in SECTIONS:
        SECTIONS[section]()
    else:
        print(f'Unknown section: {section}')
        print(f'Usage: python gen_demo.py [{"|".join(["all", "figures", "videos"] + list(SECTIONS.keys()))}]')
        sys.exit(1)
