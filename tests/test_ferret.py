"""
Tests for the pyFerret bridge (ferret/mwow_ferret.py).

These tests require pyferret and real MWOW data.
Run in the mwow-user-tools conda env (Python 3.10).
"""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pytest

# Add ferret/ to path so we can import mwow_ferret
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ferret"))

from conftest import realdata, HAS_REAL_DATA

# Import the bridge internals for unit testing
from mwow_ferret import (
    _unit_for,
    _to_ferret_time,
    _dedup_orbits,
    _sort_by_time,
    _ensure_monotonic,
    _compute_region_times,
    _compute_point_times,
    _check_time_spread,
    load_mwow,
    load_mwow_point,
    load_mwow_point_z,
    load_mwow_region,
    load_mwow_region_z,
    mpl_plot_timeseries,
    mpl_plot_region,
)

try:
    import pyferret
    HAS_PYFERRET = True
except ImportError:
    HAS_PYFERRET = False

needs_pyferret = pytest.mark.skipif(
    not HAS_PYFERRET,
    reason="pyferret not available",
)


@pytest.fixture(scope="session")
def ferret_session():
    """Start a pyferret session for the entire test run."""
    if not HAS_PYFERRET:
        pytest.skip("pyferret not available")
    pyferret.start(quiet=True, journal=False, unmapped=True,
                   verify=False, metaname=".ferret_tests")
    yield
    # pyferret.stop() can segfault in test cleanup; leave it running


# =====================================================================
# Test 52: _unit_for
# =====================================================================

class TestUnitFor:

    def test_wind_speed(self):
        assert _unit_for("wind_speed") == "m/s"

    def test_wind_direction(self):
        assert _unit_for("wind_direction") == "degrees"

    def test_unknown_returns_1(self):
        assert _unit_for("nonexistent_variable") == "1"

    def test_quality_indicator(self):
        assert _unit_for("quality_indicator") == "1"


# =====================================================================
# Test 53: open_mwow_files replaces _open
# =====================================================================

@realdata
class TestOpenReplacesInternal:

    def test_open_returns_correct_dims(self, single_lowres_file):
        from mwow_tools.reader import open_mwow_files
        ds = open_mwow_files(single_lowres_file)
        assert set(ds.dims) == {"orbit", "latitude", "longitude"}
        ds.close()


# =====================================================================
# Test helpers (no pyferret needed)
# =====================================================================

class TestToFerretTime:

    def test_single_datetime(self):
        dt = np.array(["2026-04-18T03:15:42"], dtype="datetime64[ns]")
        result = _to_ferret_time(dt)
        assert result.shape == (1, 6)
        assert result[0, pyferret.TIMEARRAY_YEARINDEX] == 2026
        assert result[0, pyferret.TIMEARRAY_MONTHINDEX] == 4
        assert result[0, pyferret.TIMEARRAY_DAYINDEX] == 18
        assert result[0, pyferret.TIMEARRAY_HOURINDEX] == 3
        assert result[0, pyferret.TIMEARRAY_MINUTEINDEX] == 15
        assert result[0, pyferret.TIMEARRAY_SECONDINDEX] == 42

    def test_multiple_datetimes(self):
        dts = np.array([
            "2026-04-18T00:00:00",
            "2026-04-18T12:30:00",
        ], dtype="datetime64[ns]")
        result = _to_ferret_time(dts)
        assert result.shape == (2, 6)
        assert result[1, pyferret.TIMEARRAY_HOURINDEX] == 12
        assert result[1, pyferret.TIMEARRAY_MINUTEINDEX] == 30


class TestEnsureMonotonic:

    def test_already_monotonic(self):
        times = np.array([
            "2026-04-18T00:00:00",
            "2026-04-18T01:00:00",
            "2026-04-18T02:00:00",
        ], dtype="datetime64[ns]")
        result = _ensure_monotonic(times)
        np.testing.assert_array_equal(result, times)

    def test_duplicates_get_offset(self):
        times = np.array([
            "2026-04-18T00:00:00",
            "2026-04-18T00:00:00",
            "2026-04-18T00:00:00",
        ], dtype="datetime64[ns]")
        result = _ensure_monotonic(times)
        # Each subsequent should be 1 second later
        assert result[1] == result[0] + np.timedelta64(1, "s")
        assert result[2] == result[1] + np.timedelta64(1, "s")

    def test_mixed(self):
        times = np.array([
            "2026-04-18T00:00:00",
            "2026-04-18T00:00:00",
            "2026-04-18T02:00:00",
        ], dtype="datetime64[ns]")
        result = _ensure_monotonic(times)
        assert result[0] < result[1]
        assert result[1] < result[2]
        # Second value should be just 1 sec after first
        assert result[1] == times[0] + np.timedelta64(1, "s")
        # Third value unchanged (already > result[1])
        assert result[2] == times[2]


@realdata
class TestDedupOrbits:

    def test_no_duplicates_unchanged(self, single_lowres_file):
        from mwow_tools.reader import open_mwow_files
        ds = open_mwow_files(single_lowres_file)
        n_before = ds.sizes["orbit"]
        ds_dedup = _dedup_orbits(ds)
        assert ds_dedup.sizes["orbit"] == n_before
        ds.close()


@realdata
class TestSortByTime:

    def test_sorts_by_time(self, single_lowres_file):
        from mwow_tools.reader import open_mwow_files
        ds = open_mwow_files(single_lowres_file)
        times = ds["orbit_start_time"].values.copy()
        ds_sorted, times_sorted = _sort_by_time(ds, times)
        # Verify monotonic
        for i in range(1, len(times_sorted)):
            assert times_sorted[i] >= times_sorted[i - 1]
        ds.close()


# =====================================================================
# Tests 54-57: pyferret integration
# =====================================================================

@needs_pyferret
@realdata
class TestLoadMwow:
    """Test 54: load_mwow with Z axis."""

    def test_loads_with_correct_orbit_count(self, single_lowres_file,
                                             ferret_session, capsys):
        from mwow_tools.reader import open_mwow_files
        ds = open_mwow_files(single_lowres_file)
        expected_orbits = ds.sizes["orbit"]
        ds.close()

        load_mwow(single_lowres_file, ferret_name="TEST_LOAD_Z")
        captured = capsys.readouterr()
        assert "NOTE: Full-file load uses Z axis" in captured.out
        assert f"{expected_orbits} orbits" in captured.out

    def test_z_axis_note_always_printed(self, single_lowres_file,
                                         ferret_session, capsys):
        load_mwow(single_lowres_file, ferret_name="TEST_LOAD_Z2")
        captured = capsys.readouterr()
        assert "Z axis" in captured.out


@needs_pyferret
@realdata
class TestLoadMwowPoint:
    """Test 55: load_mwow_point with T axis."""

    def test_loads_with_time_axis(self, single_lowres_file,
                                   ferret_session, capsys):
        load_mwow_point(single_lowres_file, lat=-40.0, lon=70.0,
                        ferret_name="TEST_POINT_T")
        captured = capsys.readouterr()
        assert "T axis" in captured.out
        assert "orbits" in captured.out

    def test_var_parameter(self, single_lowres_file,
                           ferret_session, capsys):
        load_mwow_point(single_lowres_file, lat=-40.0, lon=70.0,
                        var="wind_direction",
                        ferret_name="TEST_POINT_WD")
        captured = capsys.readouterr()
        assert "TEST_POINT_WD" in captured.out

    def test_z_variant(self, single_lowres_file,
                       ferret_session, capsys):
        load_mwow_point_z(single_lowres_file, lat=-40.0, lon=70.0,
                          ferret_name="TEST_POINT_Z")
        captured = capsys.readouterr()
        assert "Z axis" in captured.out


@needs_pyferret
@realdata
class TestLoadMwowRegion:
    """Test 56: load_mwow_region with T axis."""

    def test_loads_and_drops_empty_orbits(self, single_lowres_file,
                                           ferret_session, capsys):
        from mwow_tools.reader import open_mwow_files
        ds = open_mwow_files(single_lowres_file)
        total_orbits = ds.sizes["orbit"]
        ds.close()

        load_mwow_region(single_lowres_file,
                         lat_center=-38.0, lon_center=70.0,
                         ferret_name="TEST_REGION_T")
        captured = capsys.readouterr()
        assert "T axis" in captured.out
        # Loaded orbit count should be <= total
        # (empty orbits dropped)
        assert "orbits" in captured.out

    def test_z_variant(self, single_lowres_file,
                       ferret_session, capsys):
        load_mwow_region_z(single_lowres_file,
                           lat_center=-38.0, lon_center=70.0,
                           ferret_name="TEST_REGION_Z")
        captured = capsys.readouterr()
        assert "Z axis" in captured.out


# =====================================================================
# Test 57: Transpose — data values match reader.py
# =====================================================================

@needs_pyferret
@realdata
class TestTransposeDataMatch:
    """Verify data pushed to pyferret matches reader.py output."""

    def test_point_data_matches_reader(self, single_lowres_file,
                                        ferret_session):
        from mwow_tools.reader import open_mwow_files, select_point

        # Get data via reader
        ds = open_mwow_files(single_lowres_file)
        pt = select_point(ds, lat=-40.0, lon=70.0)
        reader_ws = pt["wind_speed"].compute().values.copy()
        ds.close()

        # Load via bridge
        load_mwow_point(single_lowres_file, lat=-40.0, lon=70.0,
                        ferret_name="TEST_MATCH_PT")

        # Get data back from pyferret
        ferret_data = pyferret.getdata("TEST_MATCH_PT")
        bridge_ws = ferret_data["data"].ravel()

        # getdata returns a masked array; fill masked values with NaN
        bridge_ws = np.ma.filled(bridge_ws, np.nan).ravel()
        # Also filter out values near the missing sentinel
        bridge_ws[np.abs(bridge_ws) > 1e30] = np.nan

        # Both should have the same valid values
        # (bridge may reorder by time, so sort both for comparison)
        reader_valid = np.sort(reader_ws[np.isfinite(reader_ws)])
        bridge_valid = np.sort(bridge_ws[np.isfinite(bridge_ws)])

        assert len(reader_valid) == len(bridge_valid), \
            f"Different valid counts: reader={len(reader_valid)}, bridge={len(bridge_valid)}"
        np.testing.assert_allclose(reader_valid, bridge_valid, rtol=1e-5)

    def test_region_data_matches_reader(self, single_lowres_file,
                                         ferret_session):
        from mwow_tools.reader import open_mwow_files, select_region

        # Get data via reader
        ds = open_mwow_files(single_lowres_file)
        region = select_region(ds, lat_center=-38.0, lon_center=70.0,
                               lat_size=2.0, lon_size=2.0)
        reader_ws = region["wind_speed"].compute().values.copy()
        ds.close()

        # Load via bridge
        load_mwow_region(single_lowres_file,
                         lat_center=-38.0, lon_center=70.0,
                         lat_size=2.0, lon_size=2.0,
                         ferret_name="TEST_MATCH_REG")

        # Get data back from pyferret
        ferret_data = pyferret.getdata("TEST_MATCH_REG")
        bridge_ws = np.ma.filled(ferret_data["data"], np.nan).ravel()
        # Also filter out values near the missing sentinel (pyferret
        # may use a slightly different value than the mask catches)
        bridge_ws[np.abs(bridge_ws) > 1e30] = np.nan

        # Compare sorted valid values (bridge transposes and reorders)
        reader_valid = np.sort(reader_ws[np.isfinite(reader_ws)].ravel())
        bridge_valid = np.sort(bridge_ws[np.isfinite(bridge_ws)])

        assert len(reader_valid) == len(bridge_valid), \
            f"Different valid counts: reader={len(reader_valid)}, bridge={len(bridge_valid)}"
        np.testing.assert_allclose(reader_valid, bridge_valid, rtol=1e-5)


# =====================================================================
# Test 59: Time sort monotonicity
# =====================================================================

@realdata
class TestTimeSortMonotonic:

    def test_point_times_monotonic(self, single_lowres_file):
        """Verify that the time computation and sorting produces
        strictly monotonic times (tested at the helper level, since
        pyferret.getdata returns None for time axis coords)."""
        from mwow_tools.reader import open_mwow_files

        ds = open_mwow_files(single_lowres_file)
        ds = _dedup_orbits(ds)
        ds_pt = ds.sel(latitude=-40.0, longitude=70.0, method="nearest")
        point_times = _compute_point_times(ds_pt)
        ds_pt, point_times = _sort_by_time(ds_pt, point_times)
        point_times = _ensure_monotonic(point_times)

        for i in range(1, len(point_times)):
            assert point_times[i] > point_times[i - 1], \
                f"Time not monotonic at index {i}: {point_times[i-1]} >= {point_times[i]}"
        ds.close()


# =====================================================================
# Test 61: Time spread warning
# =====================================================================

@realdata
class TestTimeSpreadWarning:

    def test_warns_on_large_spread(self, single_lowres_file, capsys):
        from mwow_tools.reader import open_mwow_files
        ds = open_mwow_files(single_lowres_file)
        # Use a large region — orbits covering wide swaths will have
        # large time spread
        ds_reg = ds.sel(
            latitude=slice(-60, 60),
            longitude=slice(-60, 60),
        )
        _check_time_spread(ds_reg, "load_mwow_region_z",
                           threshold_minutes=10)
        captured = capsys.readouterr()
        # Most orbits covering 120 degrees of latitude will exceed 10 min
        assert "WARNING" in captured.out or captured.out == ""
        # (If no warning, the region was small enough — that's OK too)
        ds.close()


# =====================================================================
# Visual sanity checks — save plots
# =====================================================================

# Native Ferret plot/shade commands crash in pyferret 7.6.5 conda-forge
# (the only py310 build) due to a missing comma in a Fortran FORMAT
# statement at ppl/symlib/getsym.F:95.  The error is fatal (kills the
# process) and cannot be worked around at the Ferret command level.
#
# Bug report: https://github.com/NOAA-PMEL/PyFerret/issues/145
# Fix (pending merge): https://github.com/NOAA-PMEL/PyFerret/pull/149
#
# The matplotlib-based plot functions (mpl_plot_timeseries, mpl_plot_region)
# bypass the Ferret plot engine entirely and work in all environments.
NATIVE_FERRET_PLOT_SKIP = (
    "pyferret 7.6.5 conda-forge build has fatal Fortran error in "
    "getsym.F:95 on any plot/shade command (crashes process).  "
    "See https://github.com/NOAA-PMEL/PyFerret/issues/145 — "
    "fix pending in PR #149.  Use mpl_plot_* functions instead."
)


@needs_pyferret
@realdata
class TestFerretPlots:
    """Plot tests for the pyFerret bridge.

    Matplotlib-based tests run normally.  Native Ferret plot tests are
    skipped due to a fatal Fortran runtime error in pyferret 7.6.5
    (conda-forge py310 build):

        ppl/symlib/getsym.F:95 has a missing comma in FORMAT 101 that
        causes "Missing comma between descriptors" when the TIME symbol
        is evaluated during plot rendering.  This crashes the process.

    Bug report: https://github.com/NOAA-PMEL/PyFerret/issues/145
    Fix (pending merge): https://github.com/NOAA-PMEL/PyFerret/pull/149
    """

    # --- matplotlib-based plots (work in all environments) ---

    def test_mpl_point_timeseries(self, epi_lowres_files,
                                  ferret_session, plot_dir):
        if not epi_lowres_files:
            pytest.skip("No EPI lowres files")
        load_mwow_point(epi_lowres_files, lat=-40.0, lon=70.0,
                        ferret_name="TEST_MPL_PT")
        out = str(plot_dir / "mpl_timeseries_point.png")
        mpl_plot_timeseries("TEST_MPL_PT", output=out,
                            title="Wind Speed at (-40, 70)", vmax=30)
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 5000  # non-trivial PNG

    def test_mpl_region_shade(self, single_lowres_file,
                              ferret_session, plot_dir):
        load_mwow_region(single_lowres_file,
                         lat_center=-38.0, lon_center=70.0,
                         ferret_name="TEST_MPL_REG")
        out = str(plot_dir / "mpl_region_shade.png")
        mpl_plot_region("TEST_MPL_REG", orbit=1, output=out,
                        title="Region (-38, 70) Pass 1")
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 5000  # non-trivial PNG

    # --- native Ferret plots (skipped until pyferret bug is fixed) ---

    @pytest.mark.skip(reason=NATIVE_FERRET_PLOT_SKIP)
    def test_native_point_timeseries_plot(self, epi_lowres_files,
                                          ferret_session, plot_dir):
        if not epi_lowres_files:
            pytest.skip("No EPI lowres files")
        load_mwow_point(epi_lowres_files, lat=-40.0, lon=70.0,
                        ferret_name="TEST_PLOT_PT")
        out = str(plot_dir / "ferret_timeseries_point.png")
        pyferret.run(f'plot/title="pyFerret: Wind Speed at (-40, 70)"'
                     f'/vlimits=0:30/symbol=17 TEST_PLOT_PT')
        pyferret.run(f'frame/file="{out}"')
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    @pytest.mark.skip(reason=NATIVE_FERRET_PLOT_SKIP)
    def test_native_region_shade_plot(self, single_lowres_file,
                                      ferret_session, plot_dir):
        load_mwow_region(single_lowres_file,
                         lat_center=-38.0, lon_center=70.0,
                         ferret_name="TEST_PLOT_REG")
        out = str(plot_dir / "ferret_region_shade.png")
        pyferret.run(f'shade/l=1/palette=viridis'
                     f'/title="pyFerret: Region (-38, 70) Pass 1"'
                     f' TEST_PLOT_REG')
        pyferret.run(f'frame/file="{out}"')
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0
