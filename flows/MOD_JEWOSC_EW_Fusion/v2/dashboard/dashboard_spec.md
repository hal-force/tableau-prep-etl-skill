# MOD JEWOSC EW Fusion — operator dashboard specification (v2)

Versioned dashboard artifact for the JEWOSC demonstration. This is the
F6/F7/F8 deliverable referenced by the advanced-route collections plan:
it specifies the five operator constructs, the calculations, the
interaction model, the colour ramp, and the mandatory synthetic-data
footer, so JEWOSC can reproduce the surface from the published data
source (`MOD JEWOSC EW Fusion`, project `Prep Agent / 31 - MOD JEWOSC
EW Fusion Demo`).

The skill produces the published data source; the workbook (`.twb`) is
a Tableau Desktop artifact built on top of it. This spec is the
build-sheet for that workbook.

## Design principle — decision-first, not data-first

An EW operator asks, in order: **What is the highest threat right now?
Where is it relative to me? What is it (emitter / RF signature)?** The
layout answers top-to-bottom, left-to-right, so the eye lands on the
alert before the detail (indicator F7.1).

```
+---------------------------------------------------------------------+
|  STATUS STRIP (KPIs)  Critical:2  Engage:5  Track:11 ... Closest:14nm|
+-----------------------------------+---------------------------------+
|                                   |                                 |
|   TACTICAL GEO (centre)           |   PPI POLAR (bearing / range)   |
|   map, own-ship * at RAF Odiham,  |   own-ship at origin, N-up      |
|   tracks coloured by threat_band, |   range rings @ 50/100/150 nm   |
|   sized by rx_dbm                 |   operator-native scope view    |
|                                   |                                 |
+-----------------------------------+---------------------------------+
|  PRIORITISED TRACK LIST           |  RF CHARACTERISATION            |
|  sortable: threat, range, rx_dbm  |  freq x PRI scatter, by band    |
|  callsign / emitter / band / mode |  de-interleave panel            |
|  -> selecting drives the maps     |                                 |
+-----------------------------------+---------------------------------+
|  FOOTER (mandatory): synthetic / notional disclaimer (F8.1)         |
+---------------------------------------------------------------------+
```

## Worksheets

### WS1 — Status strip (KPI band)  [F7.1]
Five big-number tiles, one per `threat_band` in escalation order
(Non-hostile -> Search -> Track -> Engage -> Critical), each showing
`COUNTD([icao24])` filtered to that band. Plus two tiles:
`MIN([range_nm])` over rows with threat_rank >= Search ("nearest
active"), and `MAX([erp_dbw])` ("hottest emitter"). This is the glance
layer.

### WS2 — Tactical geo (centrepiece)  [F6.2]
- Map. `longitude` / `latitude` as generated lat/lon.
- Colour: `threat_band` (manual escalation palette below).
- Size: `rx_dbm` (received power at own-ship; bigger = hotter/closer).
- Detail: `icao24`; Shape: custom per `emitter_class` if desired.
- Own-ship layer: a second marks layer at fixed (51.3762, -1.3086),
  star shape, labelled `own_ship_label`.
- Tooltip: callsign, emitter_class, primary_emitter, mode,
  range_nm / bearing_deg / aspect_deg, rx_dbm, fusion_confidence,
  and (after F3.1 build) em_environment_band / hf_propagation_note.

### WS3 — PPI polar (the standout construct)  [F6.1]
Own-ship at origin; bearing = clock angle (N-up, clockwise);
range = radius. Reads like an EW scope, not a BI chart.

Calcs:
```
// N-up, clockwise: 0 deg = up (North), 90 deg = right (East)
PPI_X = [range_nm] * COS(RADIANS(90 - [bearing_deg]))
PPI_Y = [range_nm] * SIN(RADIANS(90 - [bearing_deg]))
```
- `PPI_X` on Columns, `PPI_Y` on Rows, both continuous -> scatter.
- Fix both axes to a symmetric fixed range (e.g. -250..250 nm) so the
  scope stays circular regardless of the current snapshot.
- Range rings: reference lines / background circle image at 50/100/150 nm.
- Own-ship mark at (0,0). Same colour/size encoding as WS2.

### WS4 — Prioritised track list (triage worklist)  [F7.1]
Text table sorted by `threat_rank` DESC then `range_nm` ASC. Columns:
callsign, emitter_class, primary_emitter, rf_band, mode, range_nm,
bearing_deg, rx_dbm, fusion_confidence. This worksheet is the SOURCE of
the dashboard filter action.

Calc:
```
threat_rank =
  CASE [threat_band]
    WHEN "Critical"    THEN 5
    WHEN "Engage"      THEN 4
    WHEN "Track"       THEN 3
    WHEN "Search"      THEN 2
    WHEN "Non-hostile" THEN 1
    ELSE 0
  END
```

### WS5 — RF characterisation (de-interleave panel)  [F6.2]
Scatter of `centre_freq_ghz` (X) x `pri_us` (Y); colour by `rf_band`,
shape by `mode`, size by `pw_us`. This is how an analyst separates
emitter families — clusters in freq/PRI space. Log-scale the PRI axis
(spans 0 -> ~2500 us). Filter out `centre_freq_ghz = 0` (passive/silent
rows collapse to the origin) or route them to a small "passive/silent"
callout.

## Interactions  [F7.1]
- **Track-list -> maps** (filter action, on Select from WS4): highlights
  the selected track on WS2 + WS3. The core operator loop.
- **Threat floor** parameter (`threat_rank` >= N slider): de-clutter to
  "Track and above". Applied as a filter across WS2-WS5.
- **Geo/PPI -> track list** (highlight action): rubber-band an area,
  list narrows.
- **Quick filters**: `emitter_class`, `rf_band` (compact multi-select);
  `fusion_confidence` continuous filter default >= 0.3 so
  low-confidence fusions can be suppressed (honest handling of the
  notional data).

## Colour — semantic escalation ramp (dark ops theme)
Dark canvas (~#0d1117). Manual palette assigned to the DISCRETE
`threat_band` so the order is fixed regardless of snapshot contents:

| threat_band | hex |
|---|---|
| Non-hostile | #3a7d5d (muted slate-green) |
| Search      | #e8d44d (yellow) |
| Track       | #f08a24 (amber) |
| Engage      | #e03131 (red) |
| Critical    | #ff2d95 (magenta / white-hot) |

## Mandatory footer (F8.1) — verbatim
> Emitter parametrics, RF bands, threat bands and confidence values are
> NOTIONAL and ILLUSTRATIVE — a decision surface to be inspected and
> retuned, not operational doctrine. The Electronic Order of Battle is
> synthetic; no classified reference material is used. Track data:
> OpenSky Network ADS-B (public). EM-environment: NOAA SWPC space-weather.

This footer is non-negotiable for the JEWOSC audience: undeclared
synthetic data would sink the evaluation faster than a modest feature
set. The same disclaimer is carried in the published DS description so
it reaches the site catalog as well as the dashboard surface.

## Fields this dashboard depends on
All present in the v1/v2 fused output (verified against
`v1/sample_output/*.sample.csv`): threat_band, range_nm, bearing_deg,
aspect_deg, rx_dbm, erp_dbw, centre_freq_ghz, pri_us, pw_us, rf_band,
mode, emitter_class, primary_emitter, fusion_confidence, icao24,
callsign, latitude, longitude, own_ship_label.

Added by the F3.1 build-task (not yet in the sample): em_environment_band,
space_wx_r, space_wx_s, space_wx_g, hf_propagation_note. Until that
build-task lands, WS2's tooltip simply omits the environment lines and
an optional 6th "EM environment" tile on the status strip is deferred.
