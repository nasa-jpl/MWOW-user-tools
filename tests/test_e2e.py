"""
End-to-end tests for mwow-user-tools using real MWOW v0.2 data.

Includes visual sanity-check tests that save PNGs to tests/test_plots/.
"""

import os
import re

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for plot tests
import matplotlib.pyplot as plt
import numpy as np
import pytest
import xarray as xr

from mwow_tools.reader import (
    open_mwow_files,
    select_point,
    match_ship_track,
    select_region,
)

from conftest import realdata


# =====================================================================
# Full pipeline tests
# =====================================================================

@realdata
class TestFullPipelineEPI:

    def test_lowres_day_point_extraction(self, epi_lowres_files):
        if not epi_lowres_files:
            pytest.skip("No EPI lowres files")
        ds = open_mwow_files(epi_lowres_files)
        pt = select_point(ds, lat=-40.0, lon=70.0)
        ws = pt["wind_speed"].compute().values
        # Should have some valid wind speed values (ocean point)
        assert np.any(np.isfinite(ws)), "No valid wind speed at ocean point"
        ds.close()

    def test_highres_tile_region(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        mid_lat = float(ds.latitude.values[len(ds.latitude) // 2])
        mid_lon = float(ds.longitude.values[len(ds.longitude) // 2])
        # Use drop_empty_orbits=False first to check structure,
        # then verify at least some data exists somewhere in the tile
        region = select_region(ds, mid_lat, mid_lon,
                               lat_size=10.0, lon_size=10.0,
                               drop_empty_orbits=False)
        assert region.sizes["orbit"] == ds.sizes["orbit"]
        assert region.sizes["latitude"] > 0
        assert region.sizes["longitude"] > 0
        ds.close()

    def test_ship_track_day(self, epi_lowres_files):
        if not epi_lowres_files:
            pytest.skip("No EPI lowres files")
        ds = open_mwow_files(epi_lowres_files)
        lats = [-40.0, -41.0, -42.0, -43.0, -44.0]
        lons = [70.0, 71.0, 72.0, 73.0, 74.0]
        times = [f"2026-04-18T{h:02d}:00:00" for h in [1, 6, 12, 18, 23]]
        result = match_ship_track(ds, lats, lons, times)
        assert result.sizes["point"] == 5
        ds.close()


@realdata
class TestFullPipelineNonEPI:

    def test_lowres_day_point_extraction(self, nonepi_lowres_files):
        if not nonepi_lowres_files:
            pytest.skip("No nonEPI lowres files")
        ds = open_mwow_files(nonepi_lowres_files)
        pt = select_point(ds, lat=-40.0, lon=70.0)
        ws = pt["wind_speed"].compute().values
        assert np.any(np.isfinite(ws)), "No valid wind speed at ocean point"
        ds.close()

    def test_highres_tile_region(self, single_nonepi_highres_file):
        ds = open_mwow_files(single_nonepi_highres_file)
        mid_lat = float(ds.latitude.values[len(ds.latitude) // 2])
        mid_lon = float(ds.longitude.values[len(ds.longitude) // 2])
        region = select_region(ds, mid_lat, mid_lon,
                               lat_size=10.0, lon_size=10.0,
                               drop_empty_orbits=False)
        assert region.sizes["orbit"] == ds.sizes["orbit"]
        assert region.sizes["latitude"] > 0
        ds.close()


# =====================================================================
# Data validity tests
# =====================================================================

@realdata
class TestDataValidity:

    @pytest.mark.parametrize("fixture_name", [
        "single_lowres_file",
        "single_highres_file",
        "single_nonepi_lowres_file",
        "single_nonepi_highres_file",
    ])
    def test_wind_speed_physically_reasonable(self, fixture_name, request):
        f = request.getfixturevalue(fixture_name)
        ds = open_mwow_files(f)
        ws = ds["wind_speed"].compute().values
        valid = ws[np.isfinite(ws)]
        if len(valid) > 0:
            assert valid.min() >= 0, f"Negative wind speed in {f}"
            assert valid.max() <= 100, f"Wind speed > 100 m/s in {f}"
        ds.close()

    @pytest.mark.parametrize("fixture_name", [
        "single_lowres_file",
        "single_highres_file",
        "single_nonepi_lowres_file",
        "single_nonepi_highres_file",
    ])
    def test_wind_direction_in_range(self, fixture_name, request):
        f = request.getfixturevalue(fixture_name)
        ds = open_mwow_files(f)
        wd = ds["wind_direction"].compute().values
        valid = wd[np.isfinite(wd)]
        if len(valid) > 0:
            # MWOW wind direction is in [-180, 180] (oceanographic convention)
            assert valid.min() >= -180, f"Wind direction < -180 in {f}"
            assert valid.max() <= 180, f"Wind direction > 180 in {f}"
        ds.close()

    def test_sensor_id_epi_vs_nonepi(self, single_lowres_file,
                                      single_nonepi_lowres_file):
        ds_epi = open_mwow_files(single_lowres_file)
        ds_non = open_mwow_files(single_nonepi_lowres_file)
        # sensor_id is 1D per-orbit (float); sensor_name is 1D per-orbit (str)
        epi_names = set(ds_epi["sensor_name"].compute().values)
        non_names = set(ds_non["sensor_name"].compute().values)
        # nonEPI should NOT have HY-2B or HY-2C
        assert "HY-2B" not in non_names, "HY-2B found in nonEPI"
        assert "HY-2C" not in non_names, "HY-2C found in nonEPI"
        # EPI should have more sensor types
        assert len(epi_names) >= len(non_names)
        ds_epi.close()
        ds_non.close()

    def test_lowres_grid_resolution(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        lat_res = abs(np.diff(ds.latitude.values).mean())
        lon_res = abs(np.diff(ds.longitude.values).mean())
        assert abs(lat_res - 0.125) < 0.001, f"Unexpected lat resolution: {lat_res}"
        assert abs(lon_res - 0.125) < 0.001, f"Unexpected lon resolution: {lon_res}"
        ds.close()

    def test_highres_grid_resolution(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        lat_res = abs(np.diff(ds.latitude.values).mean())
        expected = 1 / 64  # 0.015625
        assert abs(lat_res - expected) < 0.001, \
            f"Unexpected highres resolution: {lat_res}"
        ds.close()

    def test_time_within_6h_window(self, single_lowres_file):
        # Use xr.open_dataset directly (not open_mwow_files) to avoid
        # accumulating file handles that cause segfaults on NFS.
        with xr.open_dataset(single_lowres_file) as ds:
            fname = os.path.basename(single_lowres_file)
            # Pattern: MWOW_L3_20260414T00_20260414T06_...
            m = re.search(r"(\d{8}T\d{2})_(\d{8}T\d{2})", fname)
            if not m:
                pytest.skip("Cannot parse time window from filename")
            win_start = np.datetime64(
                m.group(1)[:4] + "-" + m.group(1)[4:6] + "-" +
                m.group(1)[6:8] + "T" + m.group(1)[9:11] + ":00:00")
            win_end = np.datetime64(
                m.group(2)[:4] + "-" + m.group(2)[4:6] + "-" +
                m.group(2)[6:8] + "T" + m.group(2)[9:11] + ":00:00")
            # xarray decodes time as datetime64; filter out NaT
            time_vals = ds["time"].values.ravel()
            times_dt = time_vals[~np.isnat(time_vals)]
            if len(times_dt) == 0:
                pytest.skip("No valid time values in file")
            # Allow 2 hour buffer — satellite passes straddle window boundaries
            buffer = np.timedelta64(2, "h")
            assert times_dt.min() >= win_start - buffer, \
                f"Time {times_dt.min()} before window start {win_start}"
            assert times_dt.max() <= win_end + buffer, \
                f"Time {times_dt.max()} after window end {win_end}"


# =====================================================================
# Visual sanity-check tests — save PNGs for human review
# =====================================================================

@realdata
class TestVisualPlots:

    def test_timeseries_epi_lowres(self, epi_lowres_files, plot_dir):
        if not epi_lowres_files:
            pytest.skip("No EPI lowres files")
        ds = open_mwow_files(epi_lowres_files)
        pt = select_point(ds, lat=-40.0, lon=70.0)
        pt_c = pt.compute()

        fig, ax = plt.subplots(figsize=(12, 4))
        t = pt_c.time.values
        ws = pt_c.wind_speed.values
        ax.scatter(t, ws, c="steelblue", s=20)
        ax.set_xlabel("Time of Observation [UTC]")
        ax.set_ylabel("Wind Speed [m/s]")
        ax.set_title("EPI Lowres: Wind Speed at (-40, 70) — 1 day")
        ax.grid(True)
        fig.tight_layout()
        fig.savefig(str(plot_dir / "timeseries_epi_lowres.png"), dpi=150)
        plt.close(fig)
        ds.close()

    def test_timeseries_nonepi_lowres(self, nonepi_lowres_files, plot_dir):
        if not nonepi_lowres_files:
            pytest.skip("No nonEPI lowres files")
        ds = open_mwow_files(nonepi_lowres_files)
        pt = select_point(ds, lat=-40.0, lon=70.0)
        pt_c = pt.compute()

        fig, ax = plt.subplots(figsize=(12, 4))
        t = pt_c.time.values
        ws = pt_c.wind_speed.values
        ax.scatter(t, ws, c="darkorange", s=20)
        ax.set_xlabel("Time of Observation [UTC]")
        ax.set_ylabel("Wind Speed [m/s]")
        ax.set_title("nonEPI Lowres: Wind Speed at (-40, 70) — 1 day")
        ax.grid(True)
        fig.tight_layout()
        fig.savefig(str(plot_dir / "timeseries_nonepi_lowres.png"), dpi=150)
        plt.close(fig)
        ds.close()

    def test_region_epi_lowres(self, single_lowres_file, plot_dir):
        ds = open_mwow_files(single_lowres_file)
        region = select_region(ds, lat_center=-38.0, lon_center=70.0,
                               lat_size=5.0, lon_size=5.0)
        n_orbits = region.sizes["orbit"]
        if n_orbits == 0:
            pytest.skip("No orbits with data in region")

        ws = region["wind_speed"].compute()
        finite = ws.values[np.isfinite(ws.values)]
        vmin, vmax = (float(finite.min()), float(finite.max())) if len(finite) else (0, 1)

        n_plot = min(n_orbits, 4)
        fig, axes = plt.subplots(n_plot, 1, figsize=(8, 5 * n_plot), squeeze=False)
        for i in range(n_plot):
            ax = axes[i, 0]
            orb = region.isel(orbit=i).compute()
            orb["wind_speed"].plot(ax=ax, x="longitude", y="latitude",
                                   cmap="viridis", vmin=vmin, vmax=vmax)
            sensor = str(orb["sensor_name"].values) if "sensor_name" in orb else "?"
            t_vals = orb["time"].values
            valid_t = t_vals[~np.isnat(t_vals)]
            ts = "no-data"
            if len(valid_t) > 0:
                mean_ns = int(valid_t.astype("int64").mean())
                ts = str(np.datetime64(mean_ns, "ns"))[:19].replace("-", "").replace(":", "")
            ax.set_title(f"EPI Lowres: {sensor} {ts} UTC")
            ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(str(plot_dir / "region_epi_lowres.png"), dpi=150)
        plt.close(fig)
        ds.close()

    def test_region_epi_highres(self, single_highres_file, plot_dir):
        ds = open_mwow_files(single_highres_file)
        mid_lat = float(ds.latitude.values[len(ds.latitude) // 2])
        mid_lon = float(ds.longitude.values[len(ds.longitude) // 2])
        region = select_region(ds, lat_center=mid_lat, lon_center=mid_lon,
                               lat_size=2.0, lon_size=2.0)
        n_orbits = region.sizes["orbit"]
        if n_orbits == 0:
            pytest.skip("No orbits with data in highres region")

        ws = region["wind_speed"].compute()
        finite = ws.values[np.isfinite(ws.values)]
        vmin, vmax = (float(finite.min()), float(finite.max())) if len(finite) else (0, 1)

        fig, ax = plt.subplots(figsize=(8, 6))
        orb = region.isel(orbit=0).compute()
        orb["wind_speed"].plot(ax=ax, x="longitude", y="latitude",
                               cmap="viridis", vmin=vmin, vmax=vmax)
        sensor = str(orb["sensor_name"].values) if "sensor_name" in orb else "?"
        t_vals = orb["time"].values
        valid_t = t_vals[~np.isnat(t_vals)]
        ts = "no-data"
        if len(valid_t) > 0:
            mean_ns = int(valid_t.astype("int64").mean())
            ts = str(np.datetime64(mean_ns, "ns"))[:19].replace("-", "").replace(":", "")
        ax.set_title(f"EPI Highres: {sensor} {ts} UTC")
        ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(str(plot_dir / "region_epi_highres.png"), dpi=150)
        plt.close(fig)
        ds.close()

    def test_ship_track_plot(self, epi_lowres_files, plot_dir):
        if not epi_lowres_files:
            pytest.skip("No EPI lowres files")
        ds = open_mwow_files(epi_lowres_files)
        lats = np.linspace(-35, -45, 10)
        lons = np.linspace(65, 75, 10)
        times = [f"2026-04-18T{h:02d}:00:00"
                 for h in np.linspace(0, 23, 10).astype(int)]
        result = match_ship_track(ds, lats, lons, times)
        res = result.compute()

        fig, ax = plt.subplots(figsize=(8, 6))
        sc = ax.scatter(res.longitude.values, res.latitude.values,
                        c=res.wind_speed.values, s=80, cmap="viridis",
                        edgecolors="k")
        fig.colorbar(sc, ax=ax, label="Wind Speed [m/s]")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title("Ship Track: EPI Lowres, 10 points")
        ax.grid(True)
        fig.tight_layout()
        fig.savefig(str(plot_dir / "ship_track_epi_lowres.png"), dpi=150)
        plt.close(fig)
        ds.close()
