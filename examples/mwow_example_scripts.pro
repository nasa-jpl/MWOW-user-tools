;+
; MWOW examples in IDL — time series, region extraction, and wind vector maps
;
; This script demonstrates:
;   1) Opening MWOW NetCDF files and stacking along orbit
;   2) Extracting a single lat/lon point time series
;   3) Matching a ship track to nearest MWOW observations
;   4) Selecting a geographic region and dropping empty orbits
;   5) Plotting results
;   6) Composite wind vector maps (speed + direction arrows)
;
; Supports both MWOW v0.1 and v0.2 file formats:
;   v0.2: wind_speed(orbit, latitude, longitude) in file
;         IDL NCDF_VARGET returns [lon, lat, orbit] (column-major reversal)
;   v0.1: wind_speed(longitude, latitude, time) in file
;         IDL NCDF_VARGET returns [time, lat, lon]
;         Transposed to [lon, lat, orbit] for a uniform interface.
;
; v0.1 files may contain duplicate orbits from double-ingested HY-2B/HY-2C
; granules.  Duplicates are removed when extracting point or region data.
;
; Usage:
;   IDL> .run mwow_example_scripts
;   IDL> mwow_example_main, '/path_to_mwow_files/'
;   IDL> mwow_plot_wind_map, '/path/*.nc', '2026-04-18', '2026-04-19'
;
; Requirements:
;   IDL 8.0+ (for NCDF routines and modern syntax)
;-


;; =========================================================================
;; Main entry point
;; =========================================================================
PRO mwow_example_main, folder

  IF N_ELEMENTS(folder) EQ 0 THEN folder = '/path_to_mwow_files/'

  ;; Find all NetCDF files
  paths = FILE_SEARCH(folder + '*.nc', COUNT=nfiles)
  IF nfiles EQ 0 THEN BEGIN
    PRINT, 'No .nc files found in: ' + folder
    RETURN
  ENDIF

  ;; --- Step 1: Open and stack files ---
  PRINT, '=== Opening MWOW files ==='
  DS = mwow_open_files(paths)
  PRINT, 'Loaded: ', STRTRIM(N_ELEMENTS(DS.longitude), 2), ' lon x ', $
         STRTRIM(N_ELEMENTS(DS.latitude), 2), ' lat x ', $
         STRTRIM(N_ELEMENTS(DS.orbit), 2), ' orbits'
  PRINT, 'File version: ', DS.version

  ;; --- Step 2: Point time series ---
  PRINT, ''
  PRINT, '=== Point time series at (-54, 90) ==='
  lat0 = -54.0
  lon0 = 90.0
  ds_point = mwow_select_point(DS, lat0, lon0)
  PRINT, 'Selected point: lat=', STRTRIM(ds_point.latitude[0], 2), $
         ' lon=', STRTRIM(ds_point.longitude[0], 2)
  PRINT, 'Valid orbits (after dedup): ', $
         STRTRIM(N_ELEMENTS(ds_point.wind_speed), 2)

  ;; Plot time series
  npts = N_ELEMENTS(ds_point.wind_speed)
  IF npts GT 0 THEN BEGIN
    w = WINDOW(DIMENSIONS=[1000, 350])
    p = SCATTERPLOT(ds_point.time_julian, $
                    ds_point.wind_speed, $
                    MAGNITUDE=FINDGEN(npts), $
                    SYMBOL='circle', /SYM_FILLED, $
                    XTITLE='Julian Date', $
                    YTITLE='Wind Speed [m/s]', $
                    TITLE='MWOW Wind Speed at (-54, 90)', /CURRENT)
  ENDIF

  ;; --- Step 3: Ship track matching ---
  PRINT, ''
  PRINT, '=== Ship track matching ==='
  ship_lat = [-38.1, -38.2, -38.3, -38.4, -38.5]
  ship_lon = [70.0, 70.1, 70.2, 70.3, 70.4]
  ;; Julian dates for 2026-03-21 19:35:36 + offsets
  ship_time_julian = JULDAY(3, 21, 2026, 19, 35, 36) + $
                     [0.0d, 1.0d/24, 2.0d/24, 27.0d/24, 48.0d/24]

  ds_ship = mwow_match_ship_track(DS, ship_lat, ship_lon, ship_time_julian)
  FOR i = 0, N_ELEMENTS(ds_ship.latitude) - 1 DO BEGIN
    PRINT, FORMAT='("  Point %d: lat=%7.2f lon=%7.2f ws=%5.1f")', $
           i, ds_ship.latitude[i], ds_ship.longitude[i], ds_ship.wind_speed[i]
  ENDFOR

  ;; --- Step 4: Regional subset ---
  PRINT, ''
  PRINT, '=== Regional subset around (-38, 70) ==='
  lat_center = -38.0
  lon_center = 70.0
  lat_size = 5.0
  lon_size = 5.0

  ds_region = mwow_select_region(DS, lat_center, lon_center, lat_size, lon_size)
  n_orbits = N_ELEMENTS(ds_region.orbit)
  PRINT, 'Region: ', STRTRIM(N_ELEMENTS(ds_region.longitude), 2), ' lon x ', $
         STRTRIM(N_ELEMENTS(ds_region.latitude), 2), ' lat x ', $
         STRTRIM(n_orbits, 2), ' orbits (after dedup + drop empty)'

  ;; --- Step 5: Plot first orbit of region ---
  IF n_orbits GT 0 THEN BEGIN
    ;; Data is [lon, lat, orbit]; select first orbit
    slice = REFORM(ds_region.wind_speed[*, *, 0])  ; [lon, lat]
    w2 = WINDOW(DIMENSIONS=[900, 600])
    ;; IMAGE expects data as [x-pixels, y-pixels]
    im = IMAGE(slice, $
               ds_region.longitude, ds_region.latitude, $
               RGB_TABLE=74, $
               TITLE='MWOW Wind Speed - Orbit ' + $
                     STRTRIM(ds_region.orbit[0], 2), $
               XTITLE='Longitude [deg]', $
               YTITLE='Latitude [deg]', /CURRENT)
    cb = COLORBAR(TARGET=im, TITLE='Wind Speed [m/s]')
  ENDIF

  PRINT, ''
  PRINT, 'Done.'
END


;; =========================================================================
;; Open one or more MWOW NetCDF files and stack along orbit dimension.
;; Returns all data in [lon, lat, orbit] convention (IDL column-major).
;; =========================================================================
FUNCTION mwow_open_files, paths

  nfiles = N_ELEMENTS(paths)

  ;; Detect version from first file
  version = mwow_detect_version(paths[0])

  ;; Read coordinate arrays from first file
  ncid = NCDF_OPEN(paths[0], /NOWRITE)
  varid_lat = NCDF_VARID(ncid, 'latitude')
  varid_lon = NCDF_VARID(ncid, 'longitude')
  NCDF_VARGET, ncid, varid_lat, latitude
  NCDF_VARGET, ncid, varid_lon, longitude
  NCDF_CLOSE, ncid

  latitude = DOUBLE(latitude)
  longitude = DOUBLE(longitude)

  ;; Stack wind_speed, wind_direction, time, and sensor_id across files
  wind_speed_all = !NULL
  wind_dir_all = !NULL
  time_all = !NULL
  sensor_id_all = !NULL

  FOR k = 0, nfiles - 1 DO BEGIN
    mwow_read_one_file, paths[k], version, wind_speed, time_julian, $
        wind_direction, sensor_id

    ;; Concatenate along orbit dimension (dim index 2 for [lon, lat, orbit])
    IF k EQ 0 THEN BEGIN
      wind_speed_all = wind_speed
      wind_dir_all = wind_direction
      time_all = time_julian
      sensor_id_all = sensor_id
    ENDIF ELSE BEGIN
      wind_speed_all = [[[wind_speed_all]], [[wind_speed]]]
      wind_dir_all = [[[wind_dir_all]], [[wind_direction]]]
      time_all = [[[time_all]], [[time_julian]]]
      sensor_id_all = [sensor_id_all, sensor_id]
    ENDELSE
  ENDFOR

  n_orbit = (SIZE(wind_speed_all, /DIMENSIONS))[2]

  DS = {latitude: latitude, $
        longitude: longitude, $
        wind_speed: wind_speed_all, $       ; [lon, lat, orbit]
        wind_direction: wind_dir_all, $     ; [lon, lat, orbit]
        time_julian: time_all, $            ; [lon, lat, orbit]
        sensor_id: sensor_id_all, $         ; [orbit]
        orbit: LINDGEN(n_orbit) + 1L, $
        version: version}

  RETURN, DS
END


;; =========================================================================
;; Detect file version from global attributes or dimension names.
;; =========================================================================
FUNCTION mwow_detect_version, filepath

  ncid = NCDF_OPEN(filepath, /NOWRITE)
  info = NCDF_INQUIRE(ncid)

  ;; Try reading version_id attribute
  FOR i = 0, info.ngatts - 1 DO BEGIN
    attname = NCDF_ATTNAME(ncid, /GLOBAL, i)
    IF STRLOWCASE(attname) EQ 'version_id' THEN BEGIN
      NCDF_ATTGET, ncid, /GLOBAL, attname, version_bytes
      NCDF_CLOSE, ncid
      RETURN, STRING(version_bytes)
    ENDIF
  ENDFOR

  ;; Fallback: check if 'orbit' dimension exists
  FOR i = 0, info.ndims - 1 DO BEGIN
    NCDF_DIMINQ, ncid, i, dimname, dimsize
    IF STRLOWCASE(dimname) EQ 'orbit' THEN BEGIN
      NCDF_CLOSE, ncid
      RETURN, '0.2'
    ENDIF
  ENDFOR

  NCDF_CLOSE, ncid
  RETURN, '0.1'
END


;; =========================================================================
;; Read one file and return data in [lon, lat, orbit] convention.
;; =========================================================================
PRO mwow_read_one_file, filepath, version, wind_speed, time_julian, $
    wind_direction, sensor_id

  ncid = NCDF_OPEN(filepath, /NOWRITE)

  varid_ws = NCDF_VARID(ncid, 'wind_speed')
  varid_t = NCDF_VARID(ncid, 'time')
  NCDF_VARGET, ncid, varid_ws, ws_raw
  NCDF_VARGET, ncid, varid_t, time_raw
  time_julian = mwow_decode_cf_time(ncid, varid_t, time_raw)

  ;; Read wind_direction if available
  varid_wd = NCDF_VARID(ncid, 'wind_direction')
  IF varid_wd GE 0 THEN BEGIN
    NCDF_VARGET, ncid, varid_wd, wd_raw
  ENDIF ELSE BEGIN
    wd_raw = MAKE_ARRAY(SIZE(ws_raw, /DIMENSIONS), VALUE=!VALUES.F_NAN)
  ENDELSE

  ;; Read sensor_id if available
  varid_sid = NCDF_VARID(ncid, 'sensor_id')
  IF varid_sid GE 0 THEN BEGIN
    NCDF_VARGET, ncid, varid_sid, sid_raw
    sid_raw = FIX(sid_raw)
  ENDIF ELSE BEGIN
    sid_raw = !NULL
  ENDELSE

  NCDF_CLOSE, ncid

  ;; Replace fill values with NaN
  bad = WHERE(ws_raw GT 9.9e35, nbad)
  IF nbad GT 0 THEN ws_raw[bad] = !VALUES.F_NAN
  bad_t = WHERE(time_julian GT 9.9e35, nbad_t)
  IF nbad_t GT 0 THEN time_julian[bad_t] = !VALUES.D_NAN
  bad_wd = WHERE(wd_raw GT 9.9e35, nbad_wd)
  IF nbad_wd GT 0 THEN wd_raw[bad_wd] = !VALUES.F_NAN

  ws_raw = DOUBLE(ws_raw)
  wd_raw = DOUBLE(wd_raw)

  IF STRMID(version, 0, 3) EQ '0.1' THEN BEGIN
    ;; v0.1: IDL NCDF_VARGET returns [time, lat, lon] (reversed from ncdump)
    ;; Transpose to [lon, lat, time] = [lon, lat, orbit]
    wind_speed = TRANSPOSE(ws_raw, [2, 1, 0])
    time_julian = TRANSPOSE(time_julian, [2, 1, 0])
    wind_direction = TRANSPOSE(wd_raw, [2, 1, 0])
    ;; sensor_id in v0.1 is 3D — extract per-orbit from center cell
    IF sid_raw NE !NULL THEN BEGIN
      sid_raw = TRANSPOSE(sid_raw, [2, 1, 0])
      dims = SIZE(sid_raw, /DIMENSIONS)
      n_orb = dims[2]
      sensor_id = INTARR(n_orb) - 1
      FOR k = 0, n_orb - 1 DO BEGIN
        slice = REFORM(sid_raw[*, *, k])
        valid = WHERE(slice GE 0 AND slice LE 7, nv)
        IF nv GT 0 THEN sensor_id[k] = slice[valid[0]]
      ENDFOR
    ENDIF ELSE BEGIN
      dims = SIZE(ws_raw, /DIMENSIONS)
      sensor_id = INTARR(dims[0]) - 1
    ENDELSE
  ENDIF ELSE BEGIN
    ;; v0.2: IDL NCDF_VARGET returns [lon, lat, orbit] (reversed from ncdump)
    ;; Already in the correct convention
    wind_speed = ws_raw
    wind_direction = wd_raw
    ;; sensor_id in v0.2 is 1D per orbit
    IF sid_raw NE !NULL THEN BEGIN
      sensor_id = sid_raw
    ENDIF ELSE BEGIN
      dims = SIZE(ws_raw, /DIMENSIONS)
      sensor_id = INTARR(dims[2]) - 1
    ENDELSE
  ENDELSE
END


;; =========================================================================
;; Decode CF-convention time variable to Julian dates.
;; =========================================================================
FUNCTION mwow_decode_cf_time, ncid, varid, time_raw

  ;; Read the 'units' attribute
  NCDF_ATTGET, ncid, varid, 'units', units_bytes
  units = STRING(units_bytes)

  ;; Parse "seconds since YYYY-MM-DD HH:MM:SS.S"
  parts = STREGEX(units, '^([a-z]+) since (.+)$', /EXTRACT, /SUBEXPR)
  IF N_ELEMENTS(parts) LT 3 THEN MESSAGE, 'Unsupported time units: ' + units

  unit_name = STRLOWCASE(parts[1])
  ref_string = STRTRIM(parts[2], 2)

  ;; Strip trailing timezone
  ref_string = (STRSPLIT(ref_string, ' UTC', /EXTRACT, /REGEX))[0]
  ref_string = (STRSPLIT(ref_string, ' GMT', /EXTRACT, /REGEX))[0]

  ;; Parse date components
  date_parts = STRSPLIT(ref_string, '-T: ', /EXTRACT)
  year  = FIX(date_parts[0])
  month = FIX(date_parts[1])
  day   = FIX(date_parts[2])
  hour  = 0 & minute = 0 & second = 0.0d
  IF N_ELEMENTS(date_parts) GE 4 THEN hour   = FIX(date_parts[3])
  IF N_ELEMENTS(date_parts) GE 5 THEN minute = FIX(date_parts[4])
  IF N_ELEMENTS(date_parts) GE 6 THEN second = DOUBLE(date_parts[5])

  ref_julian = JULDAY(month, day, year, hour, minute, second)

  ;; Convert raw values to Julian date offset
  time_raw = DOUBLE(time_raw)
  CASE unit_name OF
    'seconds': scale = 1.0d / 86400.0d
    'second':  scale = 1.0d / 86400.0d
    'minutes': scale = 1.0d / 1440.0d
    'minute':  scale = 1.0d / 1440.0d
    'hours':   scale = 1.0d / 24.0d
    'hour':    scale = 1.0d / 24.0d
    'days':    scale = 1.0d
    'day':     scale = 1.0d
    ELSE: MESSAGE, 'Unsupported CF time unit: ' + unit_name
  ENDCASE

  RETURN, ref_julian + time_raw * scale
END


;; =========================================================================
;; Extract single lat/lon point across all orbits (with deduplication).
;; =========================================================================
FUNCTION mwow_select_point, DS, lat0, lon0

  ;; Find nearest grid indices
  dummy = MIN(ABS(DS.latitude - lat0), ilat)
  dummy = MIN(ABS(DS.longitude - lon0), ilon)

  n_orbit = N_ELEMENTS(DS.orbit)

  ;; Data is [lon, lat, orbit] — select one lon, one lat, all orbits
  ws = REFORM(DS.wind_speed[ilon, ilat, *])
  tvec = REFORM(DS.time_julian[ilon, ilat, *])

  ;; Keep only valid (non-NaN) orbits
  valid = WHERE(FINITE(ws) AND FINITE(tvec), nvalid)
  IF nvalid EQ 0 THEN BEGIN
    RETURN, {latitude: [DS.latitude[ilat]], longitude: [DS.longitude[ilon]], $
             orbit: [], wind_speed: [], time_julian: []}
  ENDIF
  ws = ws[valid]
  tvec = tvec[valid]

  ;; Deduplicate orbits with identical time and wind_speed
  keep = mwow_deduplicate(tvec, ws)
  ws = ws[keep]
  tvec = tvec[keep]
  nkeep = N_ELEMENTS(ws)

  ds_point = {latitude: REPLICATE(DS.latitude[ilat], nkeep), $
              longitude: REPLICATE(DS.longitude[ilon], nkeep), $
              orbit: LINDGEN(nkeep) + 1L, $
              wind_speed: ws, $
              time_julian: tvec}

  RETURN, ds_point
END


;; =========================================================================
;; Match ship track points to nearest MWOW observations.
;; =========================================================================
FUNCTION mwow_match_ship_track, DS, ship_lat, ship_lon, ship_time_julian

  n = N_ELEMENTS(ship_lat)

  out_lat = DBLARR(n) + !VALUES.D_NAN
  out_lon = DBLARR(n) + !VALUES.D_NAN
  out_ws  = DBLARR(n) + !VALUES.D_NAN
  out_time = DBLARR(n) + !VALUES.D_NAN
  out_orbit = LONARR(n)

  FOR i = 0, n - 1 DO BEGIN
    dummy = MIN(ABS(DS.latitude - ship_lat[i]), ilat)
    dummy = MIN(ABS(DS.longitude - ship_lon[i]), ilon)

    ;; Data is [lon, lat, orbit]
    tvec = REFORM(DS.time_julian[ilon, ilat, *])
    wsvec = REFORM(DS.wind_speed[ilon, ilat, *])

    valid = WHERE(FINITE(tvec) AND FINITE(wsvec), nvalid)
    IF nvalid EQ 0 THEN CONTINUE

    ;; Deduplicate
    tvec_v = tvec[valid]
    wsvec_v = wsvec[valid]
    keep = mwow_deduplicate(tvec_v, wsvec_v)
    tvec_v = tvec_v[keep]
    wsvec_v = wsvec_v[keep]

    ;; Find orbit with time closest to ship time
    dt = ABS(tvec_v - ship_time_julian[i])
    dummy = MIN(dt, jmin)

    out_lat[i] = DS.latitude[ilat]
    out_lon[i] = DS.longitude[ilon]
    out_ws[i] = wsvec_v[jmin]
    out_time[i] = tvec_v[jmin]
    out_orbit[i] = jmin + 1L
  ENDFOR

  ds_ship = {latitude: out_lat, $
             longitude: out_lon, $
             wind_speed: out_ws, $
             time_julian: out_time, $
             orbit: out_orbit}

  RETURN, ds_ship
END


;; =========================================================================
;; Select a geographic region, drop empty and duplicate orbits.
;; =========================================================================
FUNCTION mwow_select_region, DS, lat_center, lon_center, lat_size, lon_size

  ;; Find indices within the region
  ilat = WHERE(DS.latitude GE (lat_center - lat_size) AND $
               DS.latitude LE (lat_center + lat_size), nlat)
  ilon = WHERE(DS.longitude GE (lon_center - lon_size) AND $
               DS.longitude LE (lon_center + lon_size), nlon)

  IF nlat EQ 0 OR nlon EQ 0 THEN BEGIN
    PRINT, 'WARNING: No grid points in selected region.'
    RETURN, {latitude: [], longitude: [], wind_speed: [], $
             time_julian: [], orbit: []}
  ENDIF

  ;; Data is [lon, lat, orbit] — subset lon and lat ranges
  wind_speed = DS.wind_speed[ilon[0]:ilon[-1], ilat[0]:ilat[-1], *]
  time_data = DS.time_julian[ilon[0]:ilon[-1], ilat[0]:ilat[-1], *]

  dims = SIZE(wind_speed, /DIMENSIONS)
  n_orbit = dims[2]

  ;; Drop orbits that are entirely NaN
  valid_orbit = BYTARR(n_orbit)
  FOR k = 0, n_orbit - 1 DO BEGIN
    slice = wind_speed[*, *, k]
    IF TOTAL(FINITE(slice)) GT 0 THEN valid_orbit[k] = 1B
  ENDFOR

  keep_valid = WHERE(valid_orbit, nkeep)
  IF nkeep EQ 0 THEN BEGIN
    PRINT, 'WARNING: All orbits are empty in selected region.'
    RETURN, {latitude: DS.latitude[ilat], longitude: DS.longitude[ilon], $
             wind_speed: [], time_julian: [], orbit: []}
  ENDIF

  wind_speed = wind_speed[*, *, keep_valid]
  time_data = time_data[*, *, keep_valid]
  orbits_kept = DS.orbit[keep_valid]

  ;; Deduplicate using center point as reference
  IF nkeep GT 1 THEN BEGIN
    dims2 = SIZE(wind_speed, /DIMENSIONS)
    clat = dims2[1] / 2
    clon = dims2[0] / 2
    ref_t = REFORM(time_data[clon, clat, *])
    ref_ws = REFORM(wind_speed[clon, clat, *])
    keep_dedup = mwow_deduplicate(ref_t, ref_ws)
    wind_speed = wind_speed[*, *, keep_dedup]
    time_data = time_data[*, *, keep_dedup]
    orbits_kept = orbits_kept[keep_dedup]
  ENDIF

  ds_region = {latitude: DS.latitude[ilat], $
               longitude: DS.longitude[ilon], $
               wind_speed: wind_speed, $
               time_julian: time_data, $
               orbit: orbits_kept}

  RETURN, ds_region
END


;; =========================================================================
;; Deduplicate orbits with identical time and wind_speed values.
;; Returns indices of orbits to keep.
;;
;; In MWOW v0.1, duplicate orbits arise from double-ingested HY-2B/HY-2C
;; granules, producing multiple time slots with identical measurements.
;; =========================================================================
FUNCTION mwow_deduplicate, time_arr, ws_arr

  n = N_ELEMENTS(time_arr)
  IF n EQ 0 THEN RETURN, []

  keep = BYTARR(n) + 1B  ; start with all kept

  FOR i = 1, n - 1 DO BEGIN
    IF ~keep[i] THEN CONTINUE
    FOR j = 0, i - 1 DO BEGIN
      IF ~keep[j] THEN CONTINUE
      ;; Skip if either is NaN
      IF ~FINITE(time_arr[i]) OR ~FINITE(time_arr[j]) THEN CONTINUE
      IF ~FINITE(ws_arr[i]) OR ~FINITE(ws_arr[j]) THEN CONTINUE
      ;; Duplicate if time within 1 second and wind_speed within 0.001 m/s
      ;; (1 second = 1/86400 of a Julian day)
      IF ABS(time_arr[i] - time_arr[j]) LT (1.0d / 86400.0d) AND $
         ABS(ws_arr[i] - ws_arr[j]) LT 0.001d THEN BEGIN
        keep[i] = 0B
        BREAK
      ENDIF
    ENDFOR
  ENDFOR

  RETURN, WHERE(keep)
END


;; =========================================================================
;; Parse an ISO-8601 date string to a Julian date.
;; Accepts: 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS', 'YYYY-MM-DD HH:MM:SS'
;; =========================================================================
FUNCTION mwow_parse_datetime, dt_string

  s = STRTRIM(dt_string, 2)

  ;; Split on T or space to separate date and time
  parts = STRSPLIT(s, 'T ', /EXTRACT)
  date_str = parts[0]
  time_str = (N_ELEMENTS(parts) GE 2) ? parts[1] : '00:00:00'

  ;; Parse date
  date_parts = STRSPLIT(date_str, '-', /EXTRACT)
  year  = FIX(date_parts[0])
  month = FIX(date_parts[1])
  day   = FIX(date_parts[2])

  ;; Parse time
  time_parts = STRSPLIT(time_str, ':', /EXTRACT)
  hour   = FIX(time_parts[0])
  minute = (N_ELEMENTS(time_parts) GE 2) ? FIX(time_parts[1]) : 0
  second = (N_ELEMENTS(time_parts) GE 3) ? DOUBLE(time_parts[2]) : 0.0d

  RETURN, JULDAY(month, day, year, hour, minute, second)
END


;; =========================================================================
;; Return a 256x3 BYTE array reproducing MATLAB's "jet" colormap.
;; =========================================================================
FUNCTION mwow_jet_ct

  n = 256
  r = BYTARR(n)
  g = BYTARR(n)
  b = BYTARR(n)

  ;; Jet colormap: dark blue -> blue -> cyan -> green -> yellow -> red -> dark red
  ;; Defined via piecewise linear interpolation of R, G, B channels.
  FOR i = 0, n - 1 DO BEGIN
    x = FLOAT(i) / (n - 1)  ; 0.0 to 1.0

    ;; Red channel
    IF x LT 0.375 THEN BEGIN
      r[i] = 0B
    ENDIF ELSE IF x LT 0.625 THEN BEGIN
      r[i] = BYTE(255 * (x - 0.375) / 0.25)
    ENDIF ELSE IF x LT 0.875 THEN BEGIN
      r[i] = 255B
    ENDIF ELSE BEGIN
      r[i] = BYTE(255 * (1.0 - (x - 0.875) / 0.25 * 0.5))
    ENDELSE

    ;; Green channel
    IF x LT 0.125 THEN BEGIN
      g[i] = 0B
    ENDIF ELSE IF x LT 0.375 THEN BEGIN
      g[i] = BYTE(255 * (x - 0.125) / 0.25)
    ENDIF ELSE IF x LT 0.625 THEN BEGIN
      g[i] = 255B
    ENDIF ELSE IF x LT 0.875 THEN BEGIN
      g[i] = BYTE(255 * (1.0 - (x - 0.625) / 0.25))
    ENDIF ELSE BEGIN
      g[i] = 0B
    ENDELSE

    ;; Blue channel
    IF x LT 0.125 THEN BEGIN
      b[i] = BYTE(128 + 127 * (x / 0.125))
    ENDIF ELSE IF x LT 0.375 THEN BEGIN
      b[i] = 255B
    ENDIF ELSE IF x LT 0.625 THEN BEGIN
      b[i] = BYTE(255 * (1.0 - (x - 0.375) / 0.25))
    ENDIF ELSE BEGIN
      b[i] = 0B
    ENDELSE
  ENDFOR

  RETURN, [[r], [g], [b]]
END


;; =========================================================================
;; Plot a composite wind vector map from MWOW data.
;;
;; Usage:
;;   mwow_plot_wind_map, '/data/mwow/2026/04/*.nc', $
;;       '2026-04-18T00:00:00', '2026-04-18T23:59:59'
;;
;;   mwow_plot_wind_map, '/data/mwow/', $
;;       JULDAY(4,18,2026,0,0,0), JULDAY(4,18,2026,23,59,59), $
;;       LAT_RANGE=[-60,-30], LON_RANGE=[60,120], $
;;       SENSOR_ID=0, METHOD='mean'
;;
;; Parameters:
;;   path        - File glob pattern or directory path
;;   start_time  - Start of time range (Julian date or ISO string)
;;   end_time    - End of time range (Julian date or ISO string)
;;
;; Keywords:
;;   LAT_RANGE        - [min, max] latitude bounds (default: [-90, 90])
;;   LON_RANGE        - [min, max] longitude bounds (default: [-180, 180])
;;   SPEED_RANGE      - [min, max] colorbar range in m/s (default: [0, 25])
;;   ARROW_SUBSAMPLE  - Subsampling factor for arrows (default: auto)
;;   OUTPUT_FILE      - Save to file (PNG or PS, detected by extension)
;;   TITLE            - Plot title (default: auto-generated)
;;   WINDOW_SIZE      - [width, height] in pixels (default: [1200, 700])
;;   METHOD           - 'last' (default) or 'mean' composite
;;   SENSOR_ID        - Filter to this sensor (0-7), default: all
;; =========================================================================
PRO mwow_plot_wind_map, path, start_time, end_time, $
    LAT_RANGE=lat_range, LON_RANGE=lon_range, $
    SPEED_RANGE=speed_range, ARROW_SUBSAMPLE=arrow_subsample, $
    OUTPUT_FILE=output_file, TITLE=title_in, $
    WINDOW_SIZE=window_size, METHOD=method, SENSOR_ID=sensor_id_filter

  ;; --- Defaults ---
  IF ~KEYWORD_SET(lat_range) THEN lat_range = [-90.0, 90.0]
  IF ~KEYWORD_SET(lon_range) THEN lon_range = [-180.0, 180.0]
  IF ~KEYWORD_SET(speed_range) THEN speed_range = [0.0, 25.0]
  IF ~KEYWORD_SET(window_size) THEN window_size = [1200, 700]
  IF ~KEYWORD_SET(method) THEN method = 'last'

  ;; --- Find files ---
  IF STRPOS(path, '*') GE 0 OR STRPOS(path, '?') GE 0 THEN BEGIN
    paths = FILE_SEARCH(path, COUNT=nfiles)
  ENDIF ELSE BEGIN
    ;; Treat as directory
    search_dir = path
    IF STRMID(search_dir, 0, 1, /REVERSE_OFFSET) NE '/' THEN $
      search_dir = search_dir + '/'
    paths = FILE_SEARCH(search_dir + '*.nc', COUNT=nfiles)
  ENDELSE

  IF nfiles EQ 0 THEN BEGIN
    PRINT, 'ERROR: No .nc files found for: ' + path
    RETURN
  ENDIF
  PRINT, 'Found ', STRTRIM(nfiles, 2), ' files'

  ;; --- Parse time range ---
  IF SIZE(start_time, /TYPE) EQ 7 THEN BEGIN
    start_julian = mwow_parse_datetime(start_time)
  ENDIF ELSE BEGIN
    start_julian = DOUBLE(start_time)
  ENDELSE

  IF SIZE(end_time, /TYPE) EQ 7 THEN BEGIN
    end_julian = mwow_parse_datetime(end_time)
  ENDIF ELSE BEGIN
    end_julian = DOUBLE(end_time)
  ENDELSE

  ;; --- Open and stack files ---
  PRINT, 'Loading data...'
  DS = mwow_open_files(paths)
  PRINT, 'Loaded: ', STRTRIM(N_ELEMENTS(DS.orbit), 2), ' orbits'

  ;; --- Filter by time range ---
  dims = SIZE(DS.wind_speed, /DIMENSIONS)
  nlon = dims[0]
  nlat = dims[1]
  n_orbit = dims[2]

  ;; Compute representative time per orbit (median of valid times)
  orbit_times = DBLARR(n_orbit) + !VALUES.D_NAN
  FOR k = 0, n_orbit - 1 DO BEGIN
    tvec = REFORM(DS.time_julian[*, *, k])
    valid = WHERE(FINITE(tvec), nv)
    IF nv GT 0 THEN orbit_times[k] = MEDIAN(tvec[valid])
  ENDFOR

  ;; Keep orbits within time range
  time_mask = FINITE(orbit_times) AND $
              (orbit_times GE start_julian) AND $
              (orbit_times LE end_julian)

  ;; Apply sensor filter if specified
  IF N_ELEMENTS(sensor_id_filter) GT 0 THEN BEGIN
    time_mask = time_mask AND (DS.sensor_id EQ sensor_id_filter)
  ENDIF

  keep_orbits = WHERE(time_mask, n_keep)
  IF n_keep EQ 0 THEN BEGIN
    PRINT, 'ERROR: No orbits within the specified time range.'
    RETURN
  ENDIF
  PRINT, 'Orbits in time range: ', STRTRIM(n_keep, 2)

  ;; Sort kept orbits by time
  sort_idx = SORT(orbit_times[keep_orbits])
  keep_orbits = keep_orbits[sort_idx]

  ;; --- Composite into 2D ---
  speed_map = DBLARR(nlon, nlat) + !VALUES.D_NAN
  dir_map = DBLARR(nlon, nlat) + !VALUES.D_NAN

  IF STRLOWCASE(method) EQ 'mean' THEN BEGIN
    ;; Vector-average: accumulate u, v components
    u_sum = DBLARR(nlon, nlat)
    v_sum = DBLARR(nlon, nlat)
    count = LONARR(nlon, nlat)

    FOR ki = 0, n_keep - 1 DO BEGIN
      k = keep_orbits[ki]
      ws = REFORM(DS.wind_speed[*, *, k])
      wd = REFORM(DS.wind_direction[*, *, k])
      valid = WHERE(FINITE(ws) AND FINITE(wd), nv)
      IF nv GT 0 THEN BEGIN
        wd_rad = wd[valid] * !DTOR
        u_sum[valid] = u_sum[valid] + ws[valid] * SIN(wd_rad)
        v_sum[valid] = v_sum[valid] + ws[valid] * COS(wd_rad)
        count[valid] = count[valid] + 1L
      ENDIF
    ENDFOR

    has_data = WHERE(count GT 0, n_has)
    IF n_has GT 0 THEN BEGIN
      u_mean = u_sum[has_data] / count[has_data]
      v_mean = v_sum[has_data] / count[has_data]
      speed_map[has_data] = SQRT(u_mean^2 + v_mean^2)
      dir_map[has_data] = (ATAN(u_mean, v_mean) * !RADEG + 360.0d) MOD 360.0d
    ENDIF

  ENDIF ELSE BEGIN
    ;; 'last' method: iterate in time order, overwrite with last valid
    FOR ki = 0, n_keep - 1 DO BEGIN
      k = keep_orbits[ki]
      ws = REFORM(DS.wind_speed[*, *, k])
      wd = REFORM(DS.wind_direction[*, *, k])
      valid = WHERE(FINITE(ws), nv)
      IF nv GT 0 THEN speed_map[valid] = ws[valid]
      valid_d = WHERE(FINITE(wd), nvd)
      IF nvd GT 0 THEN dir_map[valid_d] = wd[valid_d]
    ENDFOR
  ENDELSE

  ;; --- Subset to lat/lon range ---
  ilat = WHERE(DS.latitude GE lat_range[0] AND $
               DS.latitude LE lat_range[1], nlat_sub)
  ilon = WHERE(DS.longitude GE lon_range[0] AND $
               DS.longitude LE lon_range[1], nlon_sub)

  IF nlat_sub EQ 0 OR nlon_sub EQ 0 THEN BEGIN
    PRINT, 'ERROR: No grid points in the specified lat/lon range.'
    RETURN
  ENDIF

  lats = DS.latitude[ilat]
  lons = DS.longitude[ilon]
  speed_sub = speed_map[ilon[0]:ilon[-1], ilat[0]:ilat[-1]]
  dir_sub = dir_map[ilon[0]:ilon[-1], ilat[0]:ilat[-1]]

  ;; --- Compute arrow subsample ---
  IF ~KEYWORD_SET(arrow_subsample) THEN BEGIN
    arrow_subsample = MAX([1, nlon_sub / 20])
  ENDIF

  ;; Subsample for arrows: unit-length vectors showing direction only
  lon_idx = LINDGEN(nlon_sub / arrow_subsample) * arrow_subsample
  lat_idx = LINDGEN(nlat_sub / arrow_subsample) * arrow_subsample
  lon_arr = lons[lon_idx]
  lat_arr = lats[lat_idx]
  n_arlon = N_ELEMENTS(lon_idx)
  n_arlat = N_ELEMENTS(lat_idx)

  u_arrows = DBLARR(n_arlon, n_arlat) + !VALUES.D_NAN
  v_arrows = DBLARR(n_arlon, n_arlat) + !VALUES.D_NAN

  FOR j = 0, n_arlat - 1 DO BEGIN
    FOR i = 0, n_arlon - 1 DO BEGIN
      spd = speed_sub[lon_idx[i], lat_idx[j]]
      dir = dir_sub[lon_idx[i], lat_idx[j]]
      IF FINITE(spd) AND FINITE(dir) THEN BEGIN
        dir_rad = dir * !DTOR
        u_arrows[i, j] = SIN(dir_rad)
        v_arrows[i, j] = COS(dir_rad)
      ENDIF
    ENDFOR
  ENDFOR

  ;; --- Build title ---
  IF KEYWORD_SET(title_in) THEN BEGIN
    plot_title = title_in
  ENDIF ELSE BEGIN
    CALDAT, start_julian, sm, sd, sy, sh, smi
    CALDAT, end_julian, em, ed, ey, eh, emi
    plot_title = STRING(FORMAT='("MWOW Wind Vectors  %04d-%02d-%02d %02d:%02d to %04d-%02d-%02d %02d:%02d")', $
        sy, sm, sd, sh, smi, ey, em, ed, eh, emi)
    IF N_ELEMENTS(sensor_id_filter) GT 0 THEN BEGIN
      sensor_names = ['ASCAT-B', 'ASCAT-C', 'EOS-6', 'HY-2B', $
                      'HY-2C', 'SMAP', 'SWOT', 'COWVR']
      IF sensor_id_filter GE 0 AND sensor_id_filter LE 7 THEN $
        plot_title = plot_title + ' (' + sensor_names[sensor_id_filter] + ')'
    ENDIF
  ENDELSE

  ;; --- Get jet colormap ---
  jet_ct = mwow_jet_ct()

  ;; --- Plot ---
  PRINT, 'Plotting map...'
  w = WINDOW(DIMENSIONS=window_size, BUFFER=(KEYWORD_SET(output_file)))

  ;; Create map
  m = MAP('Equidistant Cylindrical', $
      LIMIT=[lat_range[0], lon_range[0], lat_range[1], lon_range[1]], $
      TITLE=plot_title, $
      /CURRENT)

  ;; Grey land fill
  mc_land = MAPCONTINENTS(/FILL_BACKGROUND, FILL_COLOR='light gray')

  ;; Wind speed image overlay
  im = IMAGE(speed_sub, lons, lats, $
      RGB_TABLE=jet_ct, $
      MIN_VALUE=speed_range[0], MAX_VALUE=speed_range[1], $
      GRID_UNITS=2, $
      TRANSPARENCY=0, $
      /OVERPLOT)

  ;; Coastlines on top
  mc_coast = MAPCONTINENTS(COLOR='black', THICK=1.0)

  ;; Wind direction arrows (black)
  vec = VECTOR(u_arrows, v_arrows, lon_arr, lat_arr, $
      /OVERPLOT, $
      AUTO_COLOR=0, $
      COLOR='black', $
      THICK=1.0, $
      HEAD_SIZE=0.3, $
      LENGTH_SCALE=2.0, $
      HEAD_INDENT=0.4)

  ;; Colorbar
  cb = COLORBAR(TARGET=im, $
      TITLE='Wind Speed [m/s]', $
      POSITION=[0.15, 0.06, 0.85, 0.09])

  ;; --- Save if requested ---
  IF KEYWORD_SET(output_file) THEN BEGIN
    w.Save, output_file
    PRINT, 'Saved: ' + output_file
    w.Close
  ENDIF

  PRINT, 'Done.'
END
