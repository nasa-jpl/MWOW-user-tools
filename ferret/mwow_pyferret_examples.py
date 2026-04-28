#!/usr/bin/env python
"""
pyFerret examples for MWOW data products.

This script demonstrates five workflows:
  1. Load a single-point time series (T axis — time-based subsetting)
  2. Load and browse a geographic sub-region (T axis)
  3. Load a full dataset for orbit browsing (Z axis)
  4. Ad-hoc Ferret analysis commands
  5. Matplotlib plotting (RECOMMENDED — works in all environments)

Requirements:
  conda env create -f environment.yml
  conda activate mwow-user-tools
  pip install -e .

NOTE on plotting:
  pyferret 7.6.5 on conda-forge (the only py310 build as of April 2026)
  has a fatal Fortran runtime error that crashes any plot/shade command.
  The bug is a missing comma in ppl/symlib/getsym.F line 95.

    Bug: https://github.com/NOAA-PMEL/PyFerret/issues/145
    Fix (pending merge): https://github.com/NOAA-PMEL/PyFerret/pull/149

  Use the mpl_plot_* functions (Example 5) for plotting until a fixed
  build is available.  The native Ferret plot commands (Examples 1-3)
  will work if you build pyferret from source with PR #149 applied, or
  use a NOAA-distributed build with an older gfortran runtime.

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
    mpl_plot_timeseries,
    mpl_plot_region,
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

    # ---------------------------------------------------------------
    # Example 5: Matplotlib plotting (RECOMMENDED)
    # ---------------------------------------------------------------
    # The mpl_plot_* functions extract data from Ferret variables and
    # plot with matplotlib.  They work regardless of the getsym.F bug
    # in pyferret 7.6.5.  This is the recommended plotting approach
    # for Python+pyferret users.
    print("\n=== Example 5: Matplotlib plotting (recommended) ===")

    # Point time series — uses data already loaded in Example 1
    mpl_plot_timeseries("MWOW_WIND_SPEED_POINT",
                        output="mwow_mpl_timeseries.png",
                        title="MWOW Wind Speed at (-54, 90)",
                        vmax=30)

    # Region shade — uses data already loaded in Example 2
    mpl_plot_region("MWOW_WIND_SPEED_REGION", orbit=1,
                    output="mwow_mpl_region_pass1.png",
                    title="MWOW Region (-38, 70) – Pass 1")

    # Multiple orbits
    mpl_plot_region("MWOW_WIND_SPEED_REGION", orbit=2,
                    output="mwow_mpl_region_pass2.png",
                    title="MWOW Region (-38, 70) – Pass 2")

    print("\nDone. Close the Ferret window or call pyferret.stop() to exit.")


if __name__ == "__main__":
    main()
