"""
Tests for the mwow-tools CLI.
"""

import os
import sys
from io import StringIO

import pytest

from mwow_tools.cli import main
from conftest import realdata


@realdata
class TestCLITimeseries:

    def test_no_plot_prints_orbit_lines(self, single_lowres_file, capsys):
        main(["timeseries", single_lowres_file,
              "--lat", "-30", "--lon", "50", "--no-plot"])
        captured = capsys.readouterr()
        assert "orbit" in captured.out
        assert "wind_speed" in captured.out

    def test_no_plot_highres(self, single_highres_file, capsys):
        import xarray as xr
        # Get a point inside the tile
        with xr.open_dataset(single_highres_file) as ds:
            mid_lat = float(ds.latitude.values[len(ds.latitude) // 2])
            mid_lon = float(ds.longitude.values[len(ds.longitude) // 2])
        main(["timeseries", single_highres_file,
              "--lat", str(mid_lat), "--lon", str(mid_lon), "--no-plot"])
        captured = capsys.readouterr()
        assert "orbit" in captured.out

    def test_output_saves_plot(self, single_lowres_file, plot_dir):
        out = str(plot_dir / "cli_timeseries_lowres.png")
        main(["timeseries", single_lowres_file,
              "--lat", "-30", "--lon", "50", "-o", out])
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0


@realdata
class TestCLIRegion:

    def test_no_plot_prints_summary(self, single_lowres_file, capsys):
        main(["region", single_lowres_file,
              "--lat", "-38", "--lon", "70", "--size", "5", "--no-plot"])
        captured = capsys.readouterr()
        assert "Region" in captured.out or "Orbits" in captured.out

    def test_output_saves_plot(self, single_lowres_file, plot_dir):
        out = str(plot_dir / "cli_region_lowres.png")
        main(["region", single_lowres_file,
              "--lat", "-38", "--lon", "70", "--size", "5", "-o", out])
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0


@realdata
class TestCLIShipTrack:

    def test_no_plot_with_csv(self, single_lowres_file, tmp_path, capsys):
        csv = tmp_path / "track.csv"
        csv.write_text(
            "latitude,longitude,time\n"
            "-30.0,50.0,2026-04-18T01:00:00\n"
            "-31.0,51.0,2026-04-18T03:00:00\n"
            "-32.0,52.0,2026-04-18T05:00:00\n"
        )
        main(["ship-track", single_lowres_file,
              "--track", str(csv), "--no-plot"])
        captured = capsys.readouterr()
        assert "point" in captured.out
        assert "wind_speed" in captured.out


@realdata
class TestCLIVarAndClim:

    def test_region_wind_u(self, single_lowres_file, plot_dir):
        out = str(plot_dir / "cli_region_wind_u.png")
        main(["region", single_lowres_file,
              "--lat", "-38", "--lon", "70", "--size", "5",
              "--var", "wind_u", "--vmin", "-15", "--vmax", "15",
              "-o", out])
        assert os.path.isfile(out)
        assert os.path.getsize(out) > 0

    def test_timeseries_wind_v_no_plot(self, single_lowres_file, capsys):
        main(["timeseries", single_lowres_file,
              "--lat", "-30", "--lon", "50", "--var", "wind_v", "--no-plot"])
        captured = capsys.readouterr()
        assert "wind_v" in captured.out

    def test_ship_track_wind_direction(self, single_lowres_file, tmp_path, capsys):
        csv = tmp_path / "track.csv"
        csv.write_text(
            "latitude,longitude,time\n"
            "-30.0,50.0,2026-04-18T01:00:00\n"
        )
        main(["ship-track", single_lowres_file,
              "--track", str(csv), "--var", "wind_direction", "--no-plot"])
        captured = capsys.readouterr()
        assert "wind_direction" in captured.out


class TestCLIErrorCases:

    def test_missing_lat_arg(self):
        with pytest.raises(SystemExit):
            main(["timeseries", "dummy.nc", "--lon", "50", "--no-plot"])

    def test_missing_command(self):
        with pytest.raises(SystemExit):
            main([])
