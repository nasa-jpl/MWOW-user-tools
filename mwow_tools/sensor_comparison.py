"""
Sensor comparison statistics and plots for MWOW inter-sensor validation.

Provides functions to compute and plot 2D joint histograms of wind speed
(and direction), bias/standard deviation statistics, and quality indicator
sensitivity analysis.  Designed to work with collocation results from
:mod:`mwow_tools.collocate`.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm


def compute_stats(ref_speed, target_speed):
    """Compute bias and standard deviation of speed differences.

    Parameters
    ----------
    ref_speed : array-like
        Reference sensor wind speeds (m/s).
    target_speed : array-like
        Target sensor wind speeds (m/s).

    Returns
    -------
    dict
        Keys: ``bias`` (mean of target - ref), ``std`` (std of target - ref),
        ``rmse``, ``count``, ``correlation``.
    """
    ref_speed = np.asarray(ref_speed, dtype=float)
    target_speed = np.asarray(target_speed, dtype=float)
    diff = target_speed - ref_speed
    valid = np.isfinite(diff)
    diff = diff[valid]

    if len(diff) == 0:
        return {"bias": np.nan, "std": np.nan, "rmse": np.nan,
                "count": 0, "correlation": np.nan}

    bias = np.mean(diff)
    std = np.std(diff)
    rmse = np.sqrt(np.mean(diff ** 2))
    corr = np.corrcoef(ref_speed[valid], target_speed[valid])[0, 1]

    return {"bias": bias, "std": std, "rmse": rmse,
            "count": len(diff), "correlation": corr}


def joint_histogram(ref_speed, target_speed, bins=60, speed_range=(0, 30)):
    """Compute a 2D joint histogram of reference vs target wind speed.

    Parameters
    ----------
    ref_speed : array-like
        Reference sensor wind speeds (m/s).
    target_speed : array-like
        Target sensor wind speeds (m/s).
    bins : int, optional
        Number of bins along each axis (default 60).
    speed_range : tuple of float, optional
        (min, max) speed range for both axes (default (0, 30)).

    Returns
    -------
    dict
        Keys: ``counts`` (2D array, shape bins x bins),
        ``xedges``, ``yedges`` (bin edge arrays),
        ``stats`` (output of :func:`compute_stats`).
    """
    ref_speed = np.asarray(ref_speed, dtype=float)
    target_speed = np.asarray(target_speed, dtype=float)

    valid = np.isfinite(ref_speed) & np.isfinite(target_speed)
    ref_speed = ref_speed[valid]
    target_speed = target_speed[valid]

    counts, xedges, yedges = np.histogram2d(
        ref_speed, target_speed,
        bins=bins, range=[speed_range, speed_range])

    stats = compute_stats(ref_speed, target_speed)

    return {"counts": counts, "xedges": xedges, "yedges": yedges,
            "stats": stats}


def plot_joint_histogram(ref_speed, target_speed, target_name,
                         ref_name="ASCAT", bins=60, speed_range=(0, 30),
                         cmap="viridis", ax=None, save_path=None,
                         title=None, figsize=(7, 6)):
    """Plot a 2D joint histogram of wind speed with statistics annotation.

    Parameters
    ----------
    ref_speed : array-like
        Reference sensor wind speeds (m/s).
    target_speed : array-like
        Target sensor wind speeds (m/s).
    target_name : str
        Name of the target sensor (for labels).
    ref_name : str, optional
        Name of the reference sensor (default "ASCAT").
    bins : int, optional
        Number of bins per axis (default 60).
    speed_range : tuple, optional
        (min, max) speed range (default (0, 30)).
    cmap : str, optional
        Colormap name (default "viridis").
    ax : matplotlib.axes.Axes or None, optional
        Axes to plot on.  If None, a new figure is created.
    save_path : str or None, optional
        If provided, save the figure to this path.
    title : str or None, optional
        Custom title.  If None, auto-generated with bias/std.
    figsize : tuple, optional
        Figure size if creating a new figure (default (7, 6)).

    Returns
    -------
    matplotlib.axes.Axes
        The axes with the plot.
    """
    hist = joint_histogram(ref_speed, target_speed, bins=bins,
                           speed_range=speed_range)
    stats = hist["stats"]

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    counts = hist["counts"].T  # transpose so x=ref, y=target
    counts_masked = np.ma.masked_where(counts == 0, counts)

    max_count = counts.max()
    if max_count > 0:
        im = ax.pcolormesh(
            hist["xedges"], hist["yedges"], counts_masked,
            cmap=cmap, norm=LogNorm(vmin=1, vmax=max_count))
    else:
        im = ax.pcolormesh(
            hist["xedges"], hist["yedges"], counts_masked,
            cmap=cmap)

    # 1:1 reference line
    ax.plot(speed_range, speed_range, "k--", linewidth=1, alpha=0.7)

    ax.set_xlabel(f"{ref_name} Wind Speed [m/s]")
    ax.set_ylabel(f"{target_name} Wind Speed [m/s]")
    ax.set_xlim(speed_range)
    ax.set_ylim(speed_range)
    ax.set_aspect("equal")

    if title is None:
        title = (f"{target_name} vs {ref_name}  |  "
                 f"Bias: {stats['bias']:.2f} m/s  "
                 f"Std: {stats['std']:.2f} m/s  "
                 f"N={stats['count']:,}")
    ax.set_title(title)

    fig.colorbar(im, ax=ax, label="Count")

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return ax


def plot_qi_sensitivity(collocation_result, target_name, ref_name="ASCAT",
                        qi_levels=(0, 1, 2), bins=60, speed_range=(0, 30),
                        cmap="viridis", save_path=None, figsize=(18, 5)):
    """Plot joint histograms at multiple QI thresholds side by side.

    Parameters
    ----------
    collocation_result : dict
        Output of :func:`mwow_tools.collocate.find_collocations` (must
        include ``target_qi`` field).
    target_name : str
        Name of the target sensor.
    ref_name : str, optional
        Reference sensor name (default "ASCAT").
    qi_levels : tuple of int, optional
        QI thresholds to plot.  Each panel shows data with
        ``quality_indicator <= level`` (default (0, 1, 2)).
    bins : int, optional
        Bins per axis (default 60).
    speed_range : tuple, optional
        Speed range (default (0, 30)).
    cmap : str, optional
        Colormap (default "viridis").
    save_path : str or None, optional
        If provided, save the figure.
    figsize : tuple, optional
        Figure size (default (18, 5)).

    Returns
    -------
    matplotlib.figure.Figure
        The figure with QI sensitivity panels.
    """
    n_panels = len(qi_levels)
    fig, axes = plt.subplots(1, n_panels, figsize=figsize)
    if n_panels == 1:
        axes = [axes]

    ref_spd = collocation_result["ref_speed"]
    tgt_spd = collocation_result["target_speed"]
    tgt_qi = collocation_result["target_qi"]

    for ax, qi_thresh in zip(axes, qi_levels):
        mask = tgt_qi <= qi_thresh
        panel_title = (f"{target_name} vs {ref_name}  |  QI <= {qi_thresh}")

        if mask.sum() > 0:
            plot_joint_histogram(
                ref_spd[mask], tgt_spd[mask], target_name,
                ref_name=ref_name, bins=bins, speed_range=speed_range,
                cmap=cmap, ax=ax,
                title=None)
            # Override title with QI info
            stats = compute_stats(ref_spd[mask], tgt_spd[mask])
            ax.set_title(f"{panel_title}\n"
                         f"Bias: {stats['bias']:.2f}  "
                         f"Std: {stats['std']:.2f}  "
                         f"N={stats['count']:,}")
        else:
            ax.set_title(f"{panel_title}\nNo data")
            ax.text(0.5, 0.5, "No collocations", transform=ax.transAxes,
                    ha="center", va="center")

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def qi_sensitivity_table(collocation_result, target_name,
                         qi_levels=(0, 1, 2)):
    """Compute bias/std at multiple QI thresholds as a summary table.

    Parameters
    ----------
    collocation_result : dict
        Output of :func:`mwow_tools.collocate.find_collocations`.
    target_name : str
        Sensor name (for labeling).
    qi_levels : tuple of int, optional
        QI thresholds (default (0, 1, 2)).

    Returns
    -------
    list of dict
        One entry per QI level with keys: ``sensor``, ``qi_max``,
        ``bias``, ``std``, ``rmse``, ``count``, ``correlation``.
    """
    ref_spd = collocation_result["ref_speed"]
    tgt_spd = collocation_result["target_speed"]
    tgt_qi = collocation_result["target_qi"]

    rows = []
    for qi_thresh in qi_levels:
        mask = tgt_qi <= qi_thresh
        if mask.sum() > 0:
            stats = compute_stats(ref_spd[mask], tgt_spd[mask])
        else:
            stats = {"bias": np.nan, "std": np.nan, "rmse": np.nan,
                     "count": 0, "correlation": np.nan}
        rows.append({"sensor": target_name, "qi_max": qi_thresh, **stats})

    return rows
