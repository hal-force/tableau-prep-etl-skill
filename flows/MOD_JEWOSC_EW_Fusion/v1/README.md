# MOD JEWOSC EW Fusion — v1

**Request:** Prototype an Electronic Warfare fusion demonstration for the UK Ministry of Defence Joint Electronic Warfare Operational Support Cell (JEWOSC). Pull a live snapshot of civil ADS-B state vectors over UK & NW Europe (lat 48-61, lon -8 to 8) from OpenSky Network as an unclassified proxy for a cooperative-track feed. Fuse each row with a synthetic Electronic Order of Battle library keyed on airframe class (fighter / awacs / isr / transport / rotary / drone / unknown) to derive representative RF parametrics (band, centre frequency, PRI, PW, ERP) and a notional operating mode. Compute range/bearing/aspect from an own-ship reference (RAF Odiham, 51.3762N, -1.3086E) and Friis-model received signal power at own-ship (dBm). Assign a categorical threat_band (Non-hostile / Search / Track / Engage / Critical) that presents in an operational context. All emitter parametrics are notional; the EOB library is synthetic and illustrative — no classified reference material is used. Publish to 'Prep Agent / 31 - MOD JEWOSC EW Fusion Demo' on Tableau Server. Intended audience: JEWOSC analysts evaluating Tableau against complex Defence EW datasets, data-fusion workflows, and operator-facing visualisation.

## Sources

- **REST API** (`json`): https://opensky-network.org/api/states/all?lamin=48&lamax=61&lomin=-8&lomax=8

## Transformations

- **ew_fusion**: Fuses ADS-B state vectors with a synthetic Electronic Order of Battle library keyed on airframe class. Adds emitter class, primary emitter, RF band, centre frequency (GHz), PRI (us), PW (us), ERP (dBW), notional mode, own-ship range/bearing/aspect, Friis-model received power (dBm) at own-ship, and a categorical threat_band (Non-hostile / Search / Track / Engage / Critical). Emitter parametrics are notional and illustrative — no classified source. Own-ship reference: RAF Odiham (51.3762N, -1.3086E).

## Outputs

- `MOD JEWOSC EW Fusion` (published data source on Tableau Server, project `31 - MOD JEWOSC EW Fusion Demo`)

## Refresh cadence

`hourly`

## Sample output

- `sample_output/MOD JEWOSC EW Fusion.sample.csv`

Synthesized 5-row sample (real schema, fabricated values).
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/MOD_JEWOSC_EW_Fusion/v1/spec.json \
    --flow-name MOD_JEWOSC_EW_Fusion
```

