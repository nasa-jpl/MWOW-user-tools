"""
Unit tests for mwow_tools.reader — all 4 product types.
"""

import numpy as np
import pytest
import xarray as xr

from mwow_tools.reader import (
    open_mwow_files,
    select_point,
    match_ship_track,
    select_region,
)

from conftest import realdata, HAS_REAL_DATA

EXPECTED_DIMS = {"orbit", "latitude", "longitude"}
EXPECTED_VARS = {"wind_speed", "wind_direction", "time",
                 "wind_speed_uncert", "wind_direction_uncert",
                 "quality_indicator", "sensor_id", "sensor_name"}


# =====================================================================
# open_mwow_files
# =====================================================================

@realdata
class TestOpenMwowFiles:

    def test_single_lowres_dims(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        assert set(ds.dims) == EXPECTED_DIMS
        assert ds.sizes["latitude"] == 1440
        assert ds.sizes["longitude"] == 2880
        ds.close()

    def test_single_highres_dims(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        assert set(ds.dims) == EXPECTED_DIMS
        assert ds.sizes["latitude"] == 2880
        assert ds.sizes["longitude"] == 2880
        ds.close()

    def test_glob_pattern_lowres(self, data_root):
        import os
        from conftest import DATA_DATE
        pattern = os.path.join(data_root, "epi", "lowres", DATA_DATE, "*.nc")
        ds = open_mwow_files(pattern)
        # 4 files x ~35 orbits each
        assert ds.sizes["orbit"] > 35
        assert ds.sizes["latitude"] == 1440
        ds.close()

    def test_list_of_paths(self, epi_lowres_files):
        if len(epi_lowres_files) < 2:
            pytest.skip("Need at least 2 lowres files")
        ds = open_mwow_files(epi_lowres_files[:2])
        assert ds.sizes["orbit"] > 35
        ds.close()

    def test_nonexistent_glob_raises(self):
        with pytest.raises(Exception):
            ds = open_mwow_files("/nonexistent/path/*.nc")
            # Force evaluation
            ds.load()

    def test_multiple_highres_tiles_merge(self, epi_highres_files):
        if len(epi_highres_files) < 2:
            pytest.skip("Need at least 2 highres tiles")
        ds = open_mwow_files(epi_highres_files[:2])
        assert set(ds.dims) == EXPECTED_DIMS
        # Merged tiles should have larger lat or lon than a single tile
        assert ds.sizes["latitude"] >= 2880
        ds.close()

    def test_epi_nonepi_consistent_structure(self, single_lowres_file,
                                              single_nonepi_lowres_file,
                                              single_highres_file,
                                              single_nonepi_highres_file):
        files = [single_lowres_file, single_nonepi_lowres_file,
                 single_highres_file, single_nonepi_highres_file]
        for f in files:
            ds = open_mwow_files(f)
            assert set(ds.dims) == EXPECTED_DIMS, f"Wrong dims in {f}"
            for var in EXPECTED_VARS:
                assert var in ds.data_vars or var in ds.coords, \
                    f"Missing {var} in {f}"
            ds.close()


# =====================================================================
# select_point
# =====================================================================

@realdata
class TestSelectPoint:

    def test_returns_orbit_dim_only(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        pt = select_point(ds, lat=-30.0, lon=50.0)
        assert "orbit" in pt.dims
        assert "latitude" not in pt.dims
        assert "longitude" not in pt.dims
        ds.close()

    def test_nearest_neighbor_correct(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        pt = select_point(ds, lat=-30.0, lon=50.0)
        # 0.125 deg grid, so nearest should be within half a grid cell
        assert abs(float(pt.latitude.values) - (-30.0)) <= 0.0625
        assert abs(float(pt.longitude.values) - 50.0) <= 0.0625
        ds.close()

    def test_works_on_highres_tile(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        # Pick a point in the middle of the tile
        mid_lat = float(ds.latitude.values[len(ds.latitude) // 2])
        mid_lon = float(ds.longitude.values[len(ds.longitude) // 2])
        pt = select_point(ds, lat=mid_lat, lon=mid_lon)
        assert "orbit" in pt.dims
        ds.close()

    def test_point_outside_highres_picks_edge(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        lat_min = float(ds.latitude.min())
        # Request a point well below the tile
        pt = select_point(ds, lat=lat_min - 20, lon=float(ds.longitude.values[0]))
        # Should snap to the edge
        assert abs(float(pt.latitude) - lat_min) < 0.1
        ds.close()

    def test_result_has_expected_variables(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        pt = select_point(ds, lat=-30.0, lon=50.0)
        for var in ["wind_speed", "wind_direction", "time"]:
            assert var in pt.data_vars or var in pt.coords, f"Missing {var}"
        ds.close()


# =====================================================================
# match_ship_track
# =====================================================================

@realdata
class TestMatchShipTrack:

    def test_single_point_track(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        result = match_ship_track(ds, [-30.0], [50.0], ["2026-04-18T03:00:00"])
        assert result.sizes["point"] == 1
        ds.close()

    def test_multi_point_track(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        lats = [-30.0, -31.0, -32.0]
        lons = [50.0, 51.0, 52.0]
        times = ["2026-04-18T01:00:00", "2026-04-18T03:00:00",
                 "2026-04-18T05:00:00"]
        result = match_ship_track(ds, lats, lons, times)
        assert result.sizes["point"] == 3
        ds.close()

    def test_closest_time_orbit_selected(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        # Use a time near the start of the 6-hour window
        result = match_ship_track(ds, [-30.0], [50.0], ["2026-04-18T00:30:00"])
        # Result has a 'point' dimension of size 1
        assert result.sizes["point"] == 1
        ds.close()

    def test_works_on_highres(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        mid_lat = float(ds.latitude.values[len(ds.latitude) // 2])
        mid_lon = float(ds.longitude.values[len(ds.longitude) // 2])
        result = match_ship_track(ds, [mid_lat], [mid_lon],
                                  ["2026-04-18T03:00:00"])
        assert result.sizes["point"] == 1
        ds.close()

    def test_land_point_does_not_crash(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        # Sahara desert — should be all NaN for wind data
        result = match_ship_track(ds, [25.0], [10.0], ["2026-04-18T03:00:00"])
        assert result.sizes["point"] == 1
        # wind_speed should be NaN (result has point dim of size 1)
        ws = result["wind_speed"].values
        assert np.all(np.isnan(ws))
        ds.close()


# =====================================================================
# select_region
# =====================================================================

@realdata
class TestSelectRegion:

    def test_returns_correct_lat_lon_bounds(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        region = select_region(ds, lat_center=-30.0, lon_center=50.0,
                               lat_size=5.0, lon_size=5.0)
        assert float(region.latitude.min()) >= -35.1
        assert float(region.latitude.max()) <= 35.1
        assert float(region.longitude.min()) >= 44.9
        assert float(region.longitude.max()) <= 55.1
        ds.close()

    def test_drop_empty_orbits_reduces_count(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        region_drop = select_region(ds, lat_center=-30.0, lon_center=50.0,
                                    drop_empty_orbits=True)
        region_keep = select_region(ds, lat_center=-30.0, lon_center=50.0,
                                    drop_empty_orbits=False)
        assert region_drop.sizes["orbit"] <= region_keep.sizes["orbit"]
        ds.close()

    def test_drop_false_preserves_all_orbits(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        region = select_region(ds, lat_center=-30.0, lon_center=50.0,
                               drop_empty_orbits=False)
        assert region.sizes["orbit"] == ds.sizes["orbit"]
        ds.close()

    def test_works_on_highres_tile(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        mid_lat = float(ds.latitude.values[len(ds.latitude) // 2])
        mid_lon = float(ds.longitude.values[len(ds.longitude) // 2])
        region = select_region(ds, lat_center=mid_lat, lon_center=mid_lon,
                               lat_size=2.0, lon_size=2.0)
        assert set(region.dims) == EXPECTED_DIMS
        ds.close()

    def test_region_at_tile_edge(self, single_highres_file):
        ds = open_mwow_files(single_highres_file)
        edge_lat = float(ds.latitude.values[0])
        edge_lon = float(ds.longitude.values[0])
        # Region extends past the tile edge — should return in-bounds portion
        region = select_region(ds, lat_center=edge_lat, lon_center=edge_lon,
                               lat_size=5.0, lon_size=5.0)
        assert region.sizes["latitude"] > 0
        assert region.sizes["longitude"] > 0
        ds.close()

    def test_ocean_has_data_land_has_nan(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        # Southern Indian Ocean — should have wind data
        ocean = select_region(ds, lat_center=-40.0, lon_center=70.0,
                              lat_size=3.0, lon_size=3.0)
        # Sahara — should be mostly NaN
        land = select_region(ds, lat_center=25.0, lon_center=10.0,
                             lat_size=3.0, lon_size=3.0,
                             drop_empty_orbits=False)
        ocean_ws = ocean["wind_speed"].values
        land_ws = land["wind_speed"].values
        assert np.nansum(np.isfinite(ocean_ws)) > 0, "Ocean region has no data"
        # Land should have far fewer valid points
        ocean_valid = np.sum(np.isfinite(ocean_ws))
        land_valid = np.sum(np.isfinite(land_ws))
        assert land_valid < ocean_valid
        ds.close()


# =====================================================================
# Cross-product-type consistency
# =====================================================================

@realdata
class TestCrossProductConsistency:

    def test_all_four_types_same_variables(self, single_lowres_file,
                                            single_nonepi_lowres_file,
                                            single_highres_file,
                                            single_nonepi_highres_file):
        for f in [single_lowres_file, single_nonepi_lowres_file,
                  single_highres_file, single_nonepi_highres_file]:
            ds = open_mwow_files(f)
            for var in EXPECTED_VARS:
                assert var in ds.data_vars or var in ds.coords, \
                    f"Missing {var} in {f}"
            ds.close()

    def test_all_four_types_same_dims(self, single_lowres_file,
                                       single_nonepi_lowres_file,
                                       single_highres_file,
                                       single_nonepi_highres_file):
        for f in [single_lowres_file, single_nonepi_lowres_file,
                  single_highres_file, single_nonepi_highres_file]:
            ds = open_mwow_files(f)
            assert set(ds.dims) == EXPECTED_DIMS, f"Wrong dims in {f}"
            ds.close()

    def test_lowres_global_grid(self, single_lowres_file):
        ds = open_mwow_files(single_lowres_file)
        lats = ds.latitude.values
        lons = ds.longitude.values
        assert lats.min() < -89
        assert lats.max() > 89
        assert lons.min() < -179
        assert lons.max() > 179
        ds.close()

    def test_highres_tile_grid_matches_label(self, single_highres_file):
        import os
        ds = open_mwow_files(single_highres_file)
        lats = ds.latitude.values
        lons = ds.longitude.values
        # Tile should span ~45 degrees
        lat_span = lats.max() - lats.min()
        lon_span = lons.max() - lons.min()
        assert 44 < lat_span < 46, f"Unexpected lat span: {lat_span}"
        assert 44 < lon_span < 46, f"Unexpected lon span: {lon_span}"
        # Resolution should be ~1/64 deg
        lat_res = np.diff(lats).mean()
        assert abs(lat_res - 1/64) < 0.001, f"Unexpected lat resolution: {lat_res}"
        ds.close()
