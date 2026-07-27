# embassy_threat_monitor_v2 — v2

**Request:** v2 of the Embassy Threat Monitor. Same upstream feed (GDELT 1.0 every 3 hours), same 60-post US diplomatic roster, same 50mi/90d windows and 5-band risk scoring. Adds the GDELT free-text-ish columns the v1 flow already pulled but didn't surface: Actor1Name, Actor2Name, ActionGeo_FullName, EventCode (leaf taxonomy + human label), and a composed one-sentence event_summary (Actor1Name + verb + Actor2Name @ ActionGeo_FullName on YYYY-MM-DD) so each row reads as a sentence. The per-post roll-up also gains top_event_summary + top_event_source_url so an analyst sees *why* a post is rated where it is without drilling. GDELT 1.0 has no narrative description field; this is the most natural-language surface available short of switching to the GKG feed.

## Sources

- **REST API** (`csv_index_then_zip`): http://data.gdeltproject.org/events/index.html

## Transformations

- **embassy_threat_join**: Spatial-joins GDELT events to a curated US diplomatic-post roster (50mi haversine). Same scoring as v1 (severity, proximity, recency, US-actor, composite). v2 additions: actor1_name, actor2_name, action_geo_fullname, event_code, event_full_name (human verb for the leaf CAMEO code), and event_summary — a composed one-sentence narrative per row.
- **embassy_risk_summary**: Per-post weighted threat-score roll-up over a 7-day window with the same 5-band classification as v1 (CRITICAL / HIGH / ELEVATED / GUARDED / LOW). v2 additions: top_event_summary (sentence describing the top-severity recent event at this post) and top_event_source_url (the news link backing that event).

## Outputs

- `Embassy Threat Events v2` (published data source on Tableau Server, project `Embassy Threat Monitor v2`)
- `Embassy Risk Summary v2` (published data source on Tableau Server, project `Embassy Threat Monitor v2`)

## Refresh cadence

`every_3_hours`
Prior versions: `v1`

## Sample output

- `sample_output/Embassy Risk Summary v2.hyper`
- `sample_output/Embassy Threat Events v2.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/embassy_threat_monitor_v2/v2/spec.json \
    --flow-name embassy_threat_monitor_v2
```

