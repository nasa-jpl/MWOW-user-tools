#!/usr/bin/env python
"""
pyFerret examples for MWOW data products.

This script demonstrates three workflows:
  1. Load a full MWOW dataset and shade-plot one orbit
  2. Extract and plot a single-point time series
  3. Load and browse a geographic sub-region

Requirements:
  conda install -c conda-forge pyferret numpy xarray netcdf4

Usage:
  python mwow_pyferret_examples.py            (uses placeholder paths)
  python mwow_pyferret_examples.py /data/*.nc  (your files)
"""

import sys
import pyferret
from mwow_ferret import (
    load_mwow,
    load_mwow_point,
    load_mwow_region,
    plot_timeseries,
    plot_region_orbit,
)


def main():
    # Default to placeholder; override with command-line arg
    paths = sys.argv[1] if len(sys.argv) > 1 else "/path_to_mwow_data/*.nc"

    # Initialize pyFerret
    pyferret.start(quiet=True)

    # ---------------------------------------------------------------
    # Example 1: Full dataset — shade one orbit
    # ---------------------------------------------------------------
    print("\n=== Example 1: Full dataset, single orbit ===")
    load_mwow(paths, var="wind_speed")

    # Plot orbit 1 (K=1)
    pyferret.run('shade/k=1/palette=viridis'
                 '/title="MWOW Wind Speed – Orbit 1" MWOW_WIND_SPEED')
    pyferret.run('go land_detail')
    # Uncomment to save:
    # pyferret.run('frame/file="mwow_orbit1.png"')

    # ---------------------------------------------------------------
    # Example 2: Single-point time series
    # ---------------------------------------------------------------
    print("\n=== Example 2: Point time series ===")
    load_mwow_point(paths, lat=-54, lon=90)
    plot_timeseries("MWOW_POINT")
    # Uncomment to save:
    # plot_timeseries("MWOW_POINT", output="mwow_timeseries.png")

    # ---------------------------------------------------------------
    # Example 3: Regional subset
    # ---------------------------------------------------------------
    print("\n=== Example 3: Regional subset ===")
    load_mwow_region(paths, lat_center=-38, lon_center=70,
                     lat_size=5, lon_size=5)

    # Browse individual orbits within the region
    plot_region_orbit("MWOW_WIND_SPEED_REGION", orbit=1)
    # Uncomment to save:
    # plot_region_orbit("MWOW_WIND_SPEED_REGION", orbit=1,
    #                   output="mwow_region_orbit1.png")

    # ---------------------------------------------------------------
    # Example 4: Direct Ferret commands on loaded data
    # ---------------------------------------------------------------
    print("\n=== Example 4: Ad-hoc Ferret commands ===")

    # Statistics
    pyferret.run('stat MWOW_WIND_SPEED[k=1]')

    # Histogram
    pyferret.run('plot/title="Wind Speed Histogram"/vlabel="Count" '
                 'frequency_histogram(MWOW_WIND_SPEED[k=1], 0, 30, 1)')

    # Difference between two orbits
    pyferret.run('let orbit_diff = MWOW_WIND_SPEED[k=2] - MWOW_WIND_SPEED[k=1]')
    pyferret.run('shade/palette=blue_orange/title="Orbit 2 minus Orbit 1" '
                 'orbit_diff')

    print("\nDone. Close the Ferret window or call pyferret.stop() to exit.")


if __name__ == "__main__":
    main()
