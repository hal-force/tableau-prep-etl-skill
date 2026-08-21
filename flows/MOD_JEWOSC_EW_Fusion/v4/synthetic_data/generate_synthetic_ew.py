#!/usr/bin/env python3
"""
Synthetic EW mission-data generator for the MOD JEWOSC fusion demo (v2).

Produces four CSVs that stand in for the CLASSIFIED-shaped data JEWOSC
actually fuses (emitter threat-library, Electronic Order of Battle
laydown, platform / mission-data association, and ELINT intercept
events). All parametric VALUES are NOTIONAL and fabricated for an
unclassified demonstration. NATO-style designations are used for
audience resonance but the parametrics behind them are invented and
must not be read as real emitter characteristics.

Scenario theatre: Baltic / NATO eastern flank.
Scale: rich (~25 emitters, ~40 sites, ~8 platforms, ~500 intercepts).
Determinism: fully seeded — rebuilds are byte-stable.

Run:
    python3 generate_synthetic_ew.py
Writes emitters.csv, eob_sites.csv, platforms.csv, intercepts.csv
next to this script.
"""
import csv
import math
import random
from pathlib import Path

SEED = 20260727
OUT = Path(__file__).resolve().parent

# Baltic / NATO eastern-flank scenario box (lat/lon bounds).
LAT_MIN, LAT_MAX = 53.5, 59.8
LON_MIN, LON_MAX = 18.0, 30.5

# BLUE own-ship reference for this scenario: a notional orbit point over
# the southern Baltic (kept unclassified; not a real basing location).
OWN_SHIP_LAT, OWN_SHIP_LON = 55.10, 18.30
OWN_SHIP_LABEL = "BLUE-ISR ORBIT ALPHA"


# --------------------------------------------------------------------------
# 1. EMITTER THREAT LIBRARY
# --------------------------------------------------------------------------
# Each record is one notional emitter "type" — the shape of a real
# mission-data-file threat entry. band/freq/PRI/PW/scan/ERP/modes/lethality.
# Designations are NATO-reporting-name style but the numbers are invented.
#
# columns:
#   emitter_id, nato_name, system_type, band, centre_freq_ghz,
#   pri_us, pw_us, scan_type, scan_period_s, erp_dbw, modulation,
#   modes, lethality, assoc_weapon, max_range_km, priority, notes
EMITTER_LIB = [
    # (nato_name, system_type, band, freq, pri, pw, scan_type, scan_s, erp, mod, modes, lethality, weapon, max_km, priority)
    ("BIG BIRD-N",     "EW/Surveillance",     "S",  2.9, 3000.0, 20.0, "circular",      12.0, 88.0, "pulse",        "search",                 "low",      "-",              350, 3),
    ("TALL RACK-N",    "EW/Acquisition",      "L",  1.3, 2200.0, 30.0, "circular",      10.0, 84.0, "pulse",        "search/acq",             "low",      "-",              300, 3),
    ("CLAM SHELL-N",   "Acquisition",         "C",  5.2,  900.0,  1.5, "raster",         6.0, 78.0, "pulse-doppler","acq",                    "medium",   "SA-N-long",      250, 4),
    ("GRAVE STONE-N",  "Engagement",          "X",  9.4,  250.0,  0.9, "track/monopulse",3.0, 72.0, "pulse-doppler","track/guidance",         "critical", "SA-N-long",      200, 8),
    ("TOMB STONE-N",   "Engagement",          "X",  9.6,  240.0,  0.8, "track/monopulse",3.0, 71.0, "pulse-doppler","track/guidance",         "critical", "SA-N-long",      200, 8),
    ("FLAP LID-N",     "Engagement",          "X", 10.1,  300.0,  0.7, "track",          2.5, 68.0, "pulse-doppler","track/guidance",         "critical", "SA-N-med",       150, 8),
    ("SNOW DRIFT-N",   "Acquisition",         "S",  3.3, 1100.0,  2.0, "circular",       8.0, 80.0, "pulse-doppler","acq",                    "medium",   "SA-N-med",       160, 5),
    ("GRILL PAN-N",    "Engagement",          "X",  9.9,  280.0,  0.8, "phased/track",   2.0, 70.0, "pulse-doppler","track/guidance",         "critical", "SA-N-med",       120, 8),
    ("HOT SHOT-N",     "Engagement",          "Ku",14.5,  180.0,  0.5, "track",          1.5, 62.0, "pulse-doppler","track/guidance",         "high",     "SHORAD",          40, 7),
    ("DOG EAR-N",      "Acquisition",         "F",  0.9, 1800.0, 25.0, "circular",       9.0, 76.0, "pulse",        "acq",                    "medium",   "SHORAD",          80, 5),
    ("SPOON REST-N",   "EW/Surveillance",     "A",  0.16,6000.0, 60.0, "circular",      15.0, 90.0, "pulse",        "search",                 "low",      "-",              400, 2),
    ("BOX SPRING-N",   "EW/Comms-jam",        "VHF",0.22,   0.0,  0.0, "-",              0.0, 85.0, "noise/barrage","jam",                    "high",     "-",              120, 6),
    ("RICH TON-N",     "EW/Comms-jam",        "UHF",0.42,   0.0,  0.0, "-",              0.0, 82.0, "spot/barrage", "jam",                    "high",     "-",              100, 6),
    ("FIRE DOME-N",    "Engagement",          "X",  9.2,  260.0,  0.9, "phased/track",   2.0, 69.0, "pulse-doppler","track/guidance",         "critical", "SA-N-med",       130, 8),
    ("CHEESE BRICK-N", "Fire-control",        "Ku",15.1,  150.0,  0.4, "track",          1.0, 58.0, "CW/pulse",     "guidance",               "high",     "naval-SAM",       35, 7),
    ("PALM FROND-N",   "Navigation",          "X",  9.4, 1000.0,  1.0, "circular",       4.0, 55.0, "pulse",        "nav",                    "none",     "-",               60, 1),
    ("SQUARE HEAD-N",  "IFF",                 "L",  1.03,2000.0,  1.0, "-",              0.0, 50.0, "pulse",        "iff",                    "none",     "-",               80, 1),
    ("BILL BOARD-N",   "EW/Surveillance",     "S",  2.7, 2800.0, 22.0, "circular",      11.0, 86.0, "pulse",        "search",                 "low",      "-",              320, 3),
    ("LOW BLOW-N",     "Engagement",          "G",  5.9,  320.0,  1.2, "track",          2.5, 66.0, "pulse",        "track/guidance",         "high",     "SA-N-legacy",    120, 7),
    ("STRAIGHT FLUSH-N","Engagement",         "H",  7.1,  350.0,  1.4, "track",          3.0, 65.0, "pulse",        "acq/track/guidance",     "high",     "SA-N-legacy",     90, 7),
    ("SIDE NET-N",     "Acquisition",         "E",  2.9, 1500.0, 18.0, "nodding",        7.0, 79.0, "pulse",        "height-find",            "low",      "-",              300, 3),
    ("SCRUM HALF-N",   "Engagement",          "Ku",14.8,  160.0,  0.4, "track",          1.2, 60.0, "pulse-doppler","track/guidance",         "high",     "SHORAD",          25, 7),
    ("KITE SCREECH-N", "Fire-control",        "X",  9.1,  240.0,  0.7, "track",          1.5, 64.0, "pulse",        "gun-fc",                 "medium",   "naval-gun",       35, 5),
    ("BAND STAND-N",   "Fire-control",        "X",  9.3,  220.0,  0.6, "track",          1.4, 63.0, "CW/pulse",     "ssm-guidance",           "high",     "naval-SSM",       50, 7),
    ("MUSHROOM-N",     "Airborne-intercept",  "X",  9.5,  200.0,  0.5, "track/scan",     2.0, 61.0, "pulse-doppler","ai-search/track",        "high",     "AAM",             90, 7),
]


def _emitter_id(i):
    return f"EMT-{i:03d}"


def write_emitters(rng):
    rows = []
    for i, e in enumerate(EMITTER_LIB, start=1):
        (nato, stype, band, freq, pri, pw, scan, scan_s, erp, mod, modes,
         leth, weapon, mx, prio) = e
        rows.append({
            "emitter_id": _emitter_id(i),
            "nato_name": nato,
            "system_type": stype,
            "band": band,
            "centre_freq_ghz": round(freq, 3),
            "pri_us": round(pri, 1),
            "pw_us": round(pw, 2),
            "scan_type": scan,
            "scan_period_s": round(scan_s, 1),
            "erp_dbw": round(erp, 1),
            "modulation": mod,
            "modes": modes,
            "lethality": leth,
            "assoc_weapon": weapon,
            "max_range_km": mx,
            "priority": prio,
            "notes": "NOTIONAL parametrics — unclassified demo; not real emitter data",
        })
    _write_csv("emitters.csv", rows)
    return rows


# --------------------------------------------------------------------------
# 2. ELECTRONIC ORDER OF BATTLE (LAYDOWN)
# --------------------------------------------------------------------------
# Where the emitters sit. ~40 sites across the Baltic box, each associated
# with an emitter type. Mix of RED (adversary) and a few BLUE/neutral.
# columns:
#   site_id, site_name, emitter_id, lat, lon, echelon, mobility,
#   affiliation, confidence, last_seen_days, status
SITE_PREFIXES = ["Kaliningrad", "Baltiysk", "Gvardeysk", "Chernyakhovsk",
                 "Sovetsk", "Chekhovo", "Primorsk", "Yantarny",
                 "Donskoye", "Pionersky", "Zelenogradsk", "Mamonovo"]
AFFIL = ["RED", "RED", "RED", "RED", "NEUTRAL", "BLUE"]


def write_eob_sites(rng, emitters, n=40):
    rows = []
    # Weight site placement toward a dense cluster (contested exclave feel)
    # plus scattered outliers.
    for i in range(1, n + 1):
        # 70% clustered around a hot zone, 30% scattered across the box.
        if rng.random() < 0.70:
            lat = rng.gauss(54.7, 0.35)
            lon = rng.gauss(20.5, 0.6)
        else:
            lat = rng.uniform(LAT_MIN, LAT_MAX)
            lon = rng.uniform(LON_MIN, LON_MAX)
        lat = max(LAT_MIN, min(LAT_MAX, lat))
        lon = max(LON_MIN, min(LON_MAX, lon))
        emitter = rng.choice(emitters)
        affil = rng.choice(AFFIL)
        # Mobile track/engagement radars are the interesting ones.
        mobility = "mobile" if emitter["system_type"] in (
            "Engagement", "Fire-control", "EW/Comms-jam") and rng.random() < 0.6 else "fixed"
        rows.append({
            "site_id": f"SITE-{i:03d}",
            "site_name": f"{rng.choice(SITE_PREFIXES)}-{rng.randint(1,9)}",
            "emitter_id": emitter["emitter_id"],
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "echelon": rng.choice(["battery", "battalion", "regiment", "site"]),
            "mobility": mobility,
            "affiliation": affil,
            "confidence": rng.choice(["confirmed", "confirmed", "probable", "possible"]),
            "last_seen_days": rng.choice([0, 0, 1, 2, 3, 5, 7, 14, 30]),
            "status": rng.choice(["active", "active", "active", "intermittent", "dormant"]),
        })
    _write_csv("eob_sites.csv", rows)
    return rows


# --------------------------------------------------------------------------
# 3. PLATFORMS / MISSION-DATA ASSOCIATION
# --------------------------------------------------------------------------
# BLUE airframes, their RWR/DAS fit, and which mission-data-file version
# they currently carry + reprogramming cycle. The "coverage_emitters" is a
# pipe-joined set of emitter_ids the current MDF recognises.
# columns:
#   platform_id, platform_type, role, rwr_das, mdf_version,
#   mdf_load_days_ago, reprogram_cycle_days, coverage_count, coverage_emitters
PLATFORMS = [
    ("Typhoon FGR4",   "multirole",   "Praetorian DASS"),
    ("F-35B",          "multirole",   "AN/ASQ-239 Barracuda"),
    ("P-8A Poseidon",  "MPA",         "AN/ALQ-240 ESM"),
    ("RC-135W Rivet Joint","SIGINT",  "integrated EWSP"),
    ("A400M Atlas",    "transport",   "DASS"),
    ("Merlin HM2",     "ASW-helo",    "helicopter DAS"),
    ("Protector RG1",  "UAS",         "DAS"),
    ("Wildcat HMA2",   "recce-helo",  "MANTIS DAS"),
]


def write_platforms(rng, emitters):
    rows = []
    all_ids = [e["emitter_id"] for e in emitters]
    for i, (ptype, role, das) in enumerate(PLATFORMS, start=1):
        # Each platform's MDF covers a random subset — deliberately NOT full,
        # so coverage-gap analysis has something to find.
        cov_n = rng.randint(14, 22)  # of 25 emitters
        coverage = sorted(rng.sample(all_ids, cov_n))
        rows.append({
            "platform_id": f"PLT-{i:02d}",
            "platform_type": ptype,
            "role": role,
            "rwr_das": das,
            "mdf_version": f"MDF-2026.{rng.randint(1,4)}.{rng.randint(0,9)}",
            "mdf_load_days_ago": rng.choice([2, 5, 9, 14, 21, 30, 45, 60]),
            "reprogram_cycle_days": rng.choice([30, 30, 45, 90]),
            "coverage_count": cov_n,
            "coverage_emitters": "|".join(coverage),
        })
    _write_csv("platforms.csv", rows)
    return rows


# --------------------------------------------------------------------------
# 4. ELINT INTERCEPT EVENTS
# --------------------------------------------------------------------------
# ~500 "cuts" — measured parametrics from ES receivers. Each intercept has
# measured RF/PRI/PW (noisy versions of a real emitter, OR a genuinely
# unknown/changed emitter). The measured params are what a threat-library
# match runs against. Deliberately includes:
#   - clean matches (params near a library emitter)
#   - ambiguous cuts (params between two library emitters)
#   - UNKNOWN / CHANGED cuts (no clean library match -> reprogramming trigger)
# columns:
#   intercept_id, detect_time_iso, lat, lon, band, meas_freq_ghz,
#   meas_pri_us, meas_pw_us, snr_db, bearing_deg_meas, sensor_id,
#   truth_emitter_id, truth_class
BASE_TIME = 1785000000  # fixed epoch seconds (deterministic; no Date.now)


def _iso(epoch):
    # deterministic ISO string without importing datetime.now
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def write_intercepts(rng, emitters, sites, n=500):
    rows = []
    # Pick a handful of "changed/unknown" emitter profiles that do NOT
    # correspond cleanly to any library entry — these are the reprogramming
    # triggers the fusion is meant to surface.
    for i in range(1, n + 1):
        t = BASE_TIME + i * rng.randint(30, 300)
        roll = rng.random()
        # location: near a real site most of the time
        site = rng.choice(sites)
        lat = site["lat"] + rng.gauss(0, 0.05)
        lon = site["lon"] + rng.gauss(0, 0.08)
        snr = round(rng.uniform(6, 28), 1)

        if roll < 0.70:
            # CLEAN cut: noisy measurement of the site's emitter
            emt = next(e for e in emitters if e["emitter_id"] == site["emitter_id"])
            freq = _jitter(rng, emt["centre_freq_ghz"], 0.02)
            pri = _jitter(rng, emt["pri_us"], 0.05)
            pw = _jitter(rng, emt["pw_us"], 0.08)
            truth_id = emt["emitter_id"]
            truth_class = "clean"
        elif roll < 0.88:
            # AMBIGUOUS cut: params drawn between two library emitters
            e1, e2 = rng.sample(emitters, 2)
            freq = round((e1["centre_freq_ghz"] + e2["centre_freq_ghz"]) / 2, 3)
            pri = round((e1["pri_us"] + e2["pri_us"]) / 2, 1)
            pw = round((e1["pw_us"] + e2["pw_us"]) / 2, 2)
            truth_id = ""  # no single truth
            truth_class = "ambiguous"
        else:
            # UNKNOWN / CHANGED: params deliberately off the library grid
            # (e.g. a frequency-agile or reprogrammed emitter) -> trigger.
            base = rng.choice(emitters)
            freq = round(base["centre_freq_ghz"] * rng.uniform(1.08, 1.25), 3)
            pri = round(max(50.0, base["pri_us"] * rng.uniform(0.5, 0.75)), 1) if base["pri_us"] else round(rng.uniform(80, 400), 1)
            pw = round(max(0.2, base["pw_us"] * rng.uniform(1.3, 1.8)), 2) if base["pw_us"] else round(rng.uniform(0.3, 2.0), 2)
            truth_id = ""
            truth_class = "unknown"

        band = _band_for_freq(freq)
        # measured bearing from own-ship to the intercept location
        bearing = _bearing_deg(OWN_SHIP_LAT, OWN_SHIP_LON, lat, lon)
        rows.append({
            "intercept_id": f"INT-{i:04d}",
            "detect_time_iso": _iso(t),
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "band": band,
            "meas_freq_ghz": freq,
            "meas_pri_us": pri,
            "meas_pw_us": pw,
            "snr_db": snr,
            "bearing_deg_meas": bearing,
            "sensor_id": rng.choice(["ES-01", "ES-02", "ES-03", "ES-AIR-1"]),
            "truth_emitter_id": truth_id,
            "truth_class": truth_class,
        })
    _write_csv("intercepts.csv", rows)
    return rows


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _jitter(rng, val, frac):
    if not val:
        return 0.0
    return round(val * (1 + rng.gauss(0, frac)), 3)


def _band_for_freq(f):
    # crude band mapping consistent with the library
    if f < 0.25: return "VHF"
    if f < 0.5:  return "UHF"
    if f < 1.0:  return "F"
    if f < 2.0:  return "L"
    if f < 4.0:  return "S"
    if f < 8.0:  return "C"
    if f < 12.0: return "X"
    if f < 18.0: return "Ku"
    return "K"


def _bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return round((math.degrees(math.atan2(y, x)) + 360) % 360, 1)


def _write_csv(name, rows):
    if not rows:
        return
    path = OUT / name
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}  ({len(rows)} rows, {len(rows[0])} cols)")


def main():
    rng = random.Random(SEED)
    emitters = write_emitters(rng)
    sites = write_eob_sites(rng, emitters, n=40)
    write_platforms(rng, emitters)
    write_intercepts(rng, emitters, sites, n=500)
    print("done — Baltic scenario, seed", SEED)


if __name__ == "__main__":
    main()
