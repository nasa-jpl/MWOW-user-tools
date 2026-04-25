#!/usr/bin/env python
"""
pyFerret examples for MWOW data products.

This script demonstrates four workflows:
  1. Load a single-point time series (T axis — time-based subsetting)
  2. Load and browse a geographic sub-region (T axis)
  3. Load a full dataset for orbit browsing (Z axis)
  4. Ad-hoc Ferret analysis commands

Requirements:
  conda env create -f environment.yml
  conda activate mwow-user-tools
  pip install -e .

Usage:
  python mwow_pyferret_examples.py            (uses placeholder paths)
  python mwow_pyferret_examples.py /data/*.nc  (your files)
"""

import sys
import pyferret
from mwow_ferret import (
    load_mwow,
    load_mwow_point,
    load_mwow_point_z,
    load_mwow_region,
    load_mwow_region_z,
    plot_timeseries,
    plot_region_orbit,
)


def main():
    # Default to placeholder; override with command-line arg
    paths = sys.argv[1] if len(sys.argv) > 1 else "/path_to_mwow_data/*.nc"

    # Initialize pyFerret
    pyferret.start(quiet=True)

    # ---------------------------------------------------------------
    # Example 1: Single-point time series (T axis)
    # ---------------------------------------------------------------
    print("\n=== Example 1: Point time series (T axis) ===")
    load_mwow_point(paths, lat=-54, lon=90)

    # Plot — x-axis is real time
    pyferret.run('plot/title="MWOW Wind Speed at (-54, 90)"'
                 '/vlimits=0:30/symbol=17 MWOW_WIND_SPEED_POINT')

    # Subset by time range
    pyferret.run('list MWOW_WIND_SPEED_POINT'
                 '[T="18-APR-2026 00:00":"18-APR-2026 06:00"]')

    # Uncomment to save:
    # pyferret.run('frame/file="mwow_timeseries.png"')

    # ---------------------------------------------------------------
    # Example 2: Regional subset (T axis)
    # ---------------------------------------------------------------
    print("\n=== Example 2: Regional subset (T axis) ===")
    load_mwow_region(paths, lat_center=-38, lon_center=70,
                     lat_size=5, lon_size=5)

    # Browse passes — L= selects by time index
    pyferret.run('shade/l=1/palette=viridis'
                 '/title="MWOW Region – Pass 1" MWOW_WIND_SPEED_REGION')

    # Subset by time
    pyferret.run('shade/palette=viridis MWOW_WIND_SPEED_REGION'
                 '[T="18-APR-2026 00:00":"18-APR-2026 03:00"]')

    # If the time-spread warning fires, use the Z variant:
    # load_mwow_region_z(paths, lat_center=-38, lon_center=70)
    # pyferret.run('shade/k=1 MWOW_WIND_SPEED_REGION_Z')

    # ---------------------------------------------------------------
    # Example 3: Full dataset (Z axis)
    # ---------------------------------------------------------------
    print("\n=== Example 3: Full dataset, Z axis ===")
    load_mwow(paths, var="wind_speed")

    # Z axis — browse orbits with /K=
    pyferret.run('shade/k=1/palette=viridis'
                 '/title="MWOW Wind Speed – Orbit 1" MWOW_WIND_SPEED')
    pyferret.run('go land_detail')

    # ---------------------------------------------------------------
    # Example 4: Ad-hoc Ferret analysis
    # ---------------------------------------------------------------
    print("\n=== Example 4: Ad-hoc analysis ===")

    # Statistics for one orbit
    pyferret.run('stat MWOW_WIND_SPEED[k=1]')

    # Histogram
    pyferret.run('plot/title="Wind Speed Histogram"/vlabel="Count" '
                 'frequency_histogram(MWOW_WIND_SPEED[k=1], 0, 30, 1)')

    # Difference between two orbits
    pyferret.run('let orbit_diff = MWOW_WIND_SPEED[k=2]'
                 ' - MWOW_WIND_SPEED[k=1]')
    pyferret.run('shade/palette=blue_orange'
                 '/title="Orbit 2 minus Orbit 1" orbit_diff')

    print("\nDone. Close the Ferret window or call pyferret.stop() to exit.")


if __name__ == "__main__":
    main()
