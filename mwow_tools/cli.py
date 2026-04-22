"""
Command-line interface for mwow_tools.

Usage examples::

    mwow-tools timeseries /data/mwow/*.nc --lat -54 --lon 90
    mwow-tools ship-track /data/mwow/*.nc --track ship.csv
    mwow-tools region /data/mwow/*.nc --lat -38 --lon 70 --size 5
"""

import argparse
import sys

import numpy as np


def _add_common_args(parser):
    parser.add_argument(
        "files", nargs="+",
        help="MWOW NetCDF file(s) or glob pattern",
    )
    parser.add_argument(
        "--no-plot", action="store_true",
        help="Suppress the plot (print summary to stdout instead)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Save plot to this file instead of displaying interactively",
    )


def cmd_timeseries(args):
    """Extract and plot a time series at a single point."""
    from mwow_tools import open_mwow_files, select_point
    import matplotlib.pyplot as plt

    ds = open_mwow_files(args.files)
    ds_point = select_point(ds, args.lat, args.lon)

    if args.no_plot:
        computed = ds_point.compute()
        for i in range(computed.sizes["orbit"]):
            t = computed.time.values[i]
            ws = computed.wind_speed.values[i]
            print(f"orbit {i:3d}  time={t}  wind_speed={ws:.2f}")
        return

    plt.figure(figsize=(12, 4))
    plt.scatter(ds_point.time, ds_point.wind_speed, c=np.arange(ds_point.sizes["orbit"]))
    plt.xlabel("Time of Observation [UTC]")
    plt.ylabel("Wind Speed [m/s]")
    plt.colorbar(label="Orbit Pass Number")
    plt.title(f"MWOW Wind Speed at ({args.lat}, {args.lon})")
    plt.grid(True)
    plt.tight_layout()
    if args.output:
        plt.savefig(args.output, dpi=150)
    else:
        plt.show()


def cmd_ship_track(args):
    """Match a ship track CSV to MWOW observations."""
    import pandas as pd
    from mwow_tools import open_mwow_files, match_ship_track
    import matplotlib.pyplot as plt

    track = pd.read_csv(args.track)
    required = {"latitude", "longitude", "time"}
    if not required.issubset(track.columns):
        sys.exit(
            f"CSV must have columns {required}; found {set(track.columns)}"
        )

    ds = open_mwow_files(args.files)
    ds_ship = match_ship_track(
        ds,
        track["latitude"].values,
        track["longitude"].values,
        track["time"].values,
    )

    if args.no_plot:
        computed = ds_ship.compute()
        for i in range(computed.sizes["point"]):
            print(
                f"point {i:3d}  "
                f"lat={computed.latitude.values[i]:.2f}  "
                f"lon={computed.longitude.values[i]:.2f}  "
                f"time={computed.time.values[i]}  "
                f"wind_speed={computed.wind_speed.values[i]:.2f}"
            )
        return

    plt.figure(figsize=(12, 6))
    sc = plt.scatter(
        ds_ship.longitude, ds_ship.latitude,
        c=ds_ship.wind_speed, s=60,
    )
    for lon, lat, t in zip(
        ds_ship.longitude.values,
        ds_ship.latitude.values,
        ds_ship.time.values,
    ):
        label = np.datetime_as_string(t, unit="s")
        plt.text(lon, lat, f" {label}", fontsize=8, ha="left", va="bottom")
    plt.xlabel("Longitude [deg]")
    plt.ylabel("Latitude [deg]")
    plt.colorbar(sc, label="Wind Speed [m/s]")
    plt.title("MWOW Wind Speed Along Ship Track")
    plt.grid(True)
    plt.tight_layout()
    if args.output:
        plt.savefig(args.output, dpi=150)
    else:
        plt.show()


def cmd_region(args):
    """Select and plot a geographic region."""
    from mwow_tools import open_mwow_files, select_region
    import matplotlib.pyplot as plt

    ds = open_mwow_files(args.files)
    ds_region = select_region(
        ds, args.lat, args.lon,
        lat_size=args.size, lon_size=args.size,
    )

    n_orbits = ds_region.sizes["orbit"]
    if n_orbits == 0:
        sys.exit("No orbits with data in the selected region.")

    if args.no_plot:
        print(f"Region: lat=[{args.lat - args.size}, {args.lat + args.size}], "
              f"lon=[{args.lon - args.size}, {args.lon + args.size}]")
        print(f"Orbits with data: {n_orbits}")
        return

    fig, axes = plt.subplots(n_orbits, 1, figsize=(10, 4 * n_orbits), squeeze=False)
    for i in range(n_orbits):
        ax = axes[i, 0]
        ds_region.wind_speed[..., i].T.plot(ax=ax)
        ax.set_aspect("equal")
        ax.set_title(f"Orbit {i}")
    plt.tight_layout()
    if args.output:
        plt.savefig(args.output, dpi=150)
    else:
        plt.show()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mwow-tools",
        description="Access and plot MWOW ocean wind data products.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- timeseries --
    ts = sub.add_parser(
        "timeseries",
        help="Extract a wind-speed time series at a single lat/lon point",
    )
    _add_common_args(ts)
    ts.add_argument("--lat", type=float, required=True, help="Latitude (degrees)")
    ts.add_argument("--lon", type=float, required=True, help="Longitude (degrees)")
    ts.set_defaults(func=cmd_timeseries)

    # -- ship-track --
    st = sub.add_parser(
        "ship-track",
        help="Match a moving-platform track to MWOW data",
    )
    _add_common_args(st)
    st.add_argument(
        "--track", required=True,
        help="CSV file with columns: latitude, longitude, time",
    )
    st.set_defaults(func=cmd_ship_track)

    # -- region --
    rg = sub.add_parser(
        "region",
        help="Select and plot a geographic region across orbits",
    )
    _add_common_args(rg)
    rg.add_argument("--lat", type=float, required=True, help="Center latitude (degrees)")
    rg.add_argument("--lon", type=float, required=True, help="Center longitude (degrees)")
    rg.add_argument(
        "--size", type=float, default=5.0,
        help="Half-width of the region in degrees (default: 5)",
    )
    rg.set_defaults(func=cmd_region)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
