"""Generate AOML demo storm-tracking videos."""
import sys
import glob
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from mwow_tools import generate_track_video

DATA_ROOT = '/u/tsali-z0/fore/mwow_v0.2_fwd/nonepi/lowres'
TRACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_files(start_date, end_date):
    dates = pd.date_range(start_date, end_date, freq='D')
    paths = []
    for d in dates:
        day_dir = os.path.join(DATA_ROOT, f'{d.year:04d}/{d.month:02d}/{d.day:02d}')
        paths.extend(sorted(glob.glob(os.path.join(day_dir, '*.nc'))))
    print(f'  Found {len(paths)} files for {start_date} to {end_date}')
    return paths


def gen_melissa_video():
    print('=== Storm Video: Hurricane Melissa (Oct 21-31) ===')
    files = get_files('2025-10-21', '2025-10-31')
    track = os.path.join(TRACK_DIR, 'melissa_2025_track.csv')

    video = generate_track_video(
        files, track=track, region_size=5.0,
        output_dir=OUT_DIR, output_name='melissa_storm_tracking.mp4',
        speedup=14400, fps=10, dpi=150,
        speed_range=(0, 30), qi_max=2,
        title='Hurricane Melissa (2025)',
        show_track=True, track_color='magenta',
        timestamp_date_color='navy',
    )
    print(f'  Result: {video}')


def gen_erin_video():
    print('=== Storm Video: Hurricane Erin (Aug 11-22) ===')
    files = get_files('2025-08-11', '2025-08-22')
    track = os.path.join(TRACK_DIR, 'erin_2025_track.csv')

    video = generate_track_video(
        files, track=track, region_size=5.0,
        output_dir=OUT_DIR, output_name='erin_storm_tracking.mp4',
        speedup=14400, fps=10, dpi=150,
        speed_range=(0, 30), qi_max=2,
        title='Hurricane Erin (2025)',
        show_track=True, track_color='magenta',
        timestamp_date_color='navy',
    )
    print(f'  Result: {video}')


def gen_humberto_video():
    print('=== Storm Video: Hurricane Humberto (Sep 24 - Oct 1) ===')
    files = get_files('2025-09-24', '2025-10-01')
    track = os.path.join(TRACK_DIR, 'humberto_2025_track.csv')

    video = generate_track_video(
        files, track=track, region_size=5.0,
        output_dir=OUT_DIR, output_name='humberto_storm_tracking.mp4',
        speedup=14400, fps=10, dpi=150,
        speed_range=(0, 30), qi_max=2,
        title='Hurricane Humberto (2025)',
        show_track=True, track_color='magenta',
        timestamp_date_color='navy',
    )
    print(f'  Result: {video}')


if __name__ == '__main__':
    storm = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if storm == 'melissa' or storm == 'all':
        gen_melissa_video()
    if storm == 'erin' or storm == 'all':
        gen_erin_video()
    if storm == 'humberto' or storm == 'all':
        gen_humberto_video()
