# Worked examples

Each archived flow has a self-contained spec.json + flow.tfl + sample
Hyper output you can run cold.

| Flow | Source | Highlights |
|---|---|---|
| `flows/gdelt_global/v1/` | GDELT 1.0 events index | csv_index_then_zip + 115K rows/day |
| `flows/otf_grants/v1/` | otf.ca/open CSVs | 3-source multi-CSV join, bilingual headers, Latin-1 encoding |
| `flows/us_wildfires_eoc/v1/` | NIFC/WFIGS ArcGIS | EOC analyst metrics (size_class, growth_band, region_key) |
| `flows/us_grid_network/v1/` | HIFLD transmission lines | networkx centralities + Fruchterman-Reingold layout |
| `flows/fed_outlays/v1/` | Treasury Fiscal Data | JSON:API page[number]/page[size] paginated walk (3K rows) |
| `flows/fed_workforce/v1/` | BLS Public Data API | POST + JSON body, flatten inner records, derived obs_date |
| `flows/cisa_kev/v1/` | CISA KEV catalog | list_join + days_between (exploit SLA window) |
| `flows/fed_register_actions/v1/` | Federal Register API | list_first_field + days_since (regulatory case-mgmt) |
| `flows/fema_disasters/v1/` | OpenFEMA OData v2 | $top/$skip pagination + nested envelope |
| `flows/cms_deficiencies/v1/` | CMS Provider Data | 4xx-graceful pagination + page-size cap discovery |
| `flows/college_scorecard/v1/` | Dept of Ed bulk ZIP | csv_zip + per-column CSV_SCHEMA coercion |
| `flows/opensky_us/v1/` | OpenSky Network | json_array_columns positional projection (3.5K aircraft) |
| `flows/epa_aqs_ozone/v1/` | EPA AQS Data API | Drop Content-Type on bodyless GET (EPA strict-API fix) |
| `flows/usaspending_contracts/v1/` | USAspending.gov | json_page_in_body + has_next + dict_field flatten |
| `flows/russia_ukraine_attrition/v1/` | PetroIvaniuk dataset (GitHub) | Multi-source join + per-branch output routing; built via advanced collections route |
| `flows/embassy_threat_monitor_v2/v1/` | GDELT × US diplomatic-post roster | Haversine spatial join + weighted risk-bands + narrative event_summary. Every-3h cadence via publisher-cadence workaround. |
| `flows/doe_data_center_energy_monthly/v1/` | EIA Open Data v2 (retail-sales + state-profiles) | `auth: query_key` (`?api_key=…`) — first flow to exercise the new query-string auth path. Monthly. |
| `flows/doe_data_center_energy_hourly/v1/` | EIA Open Data v2 (RTO region-data) | Sub-daily hourly RTO demand pull (PJM/ERCOT/CAISO/MISO); every-6h refresh via publisher-cadence workaround. |
| `flows/dod_contracts/v1/` | USAspending.gov (DoD only) | Defense/NatSec collection slot 11 — DoD prime-contract awards, POST-body pagination. |
| `flows/nvd_cves/v1/` | NIST NVD CVE 2.0 | Slot 12 — dotted_path into CVSS metrics, days_since_published enrichment. |
| `flows/cisa_kev/v2/` | CISA Known Exploited Vulnerabilities | Slot 13 — flat JSON, days_between (dueDate SLA), all-string date schema fix. |
| `flows/fedreg_dod/v1/` | Federal Register DoD YTD | Slot 14 — list_first_field agency extraction. |
| `flows/usgs_earthquakes/v1/` | USGS significant_month GeoJSON | Slot 15 — 16 dotted_path extractions incl. geometry.coordinates.{0,1,2}; new `epoch_ms_iso` derived-col for `properties.time`. |
| `flows/tle_satellites/v1/` | tle.ivanstanojevic mirror | Slot 16 — pivoted from CelesTrak (TLS-fingerprint block); page-size=100 + page kind override. |
| `flows/gdelt_centcom/v1/` | GDELT 1.0 events (CENTCOM AOR) | Slot 17 — comma-list `country_filter` (20 codes: IR,IQ,SY,YE,AF,SA,QA,KW,BH,OM,AE,JO,LB,EG,PK,TJ,TM,UZ,KG,KZ). |
| `flows/noaa_swpc/v1/` | NOAA SWPC alerts feed | Slot 18 — 30d space-weather alerts, product_id family enrichment. |
| `flows/wb_mil_expenditure/v1/` | World Bank indicator API | Slot 19 — `json_records_path: "1"` (numeric index into 2-elem envelope); new `numeric_bin` for spend_band. |
| `flows/cneos_sentry/v1/` | NASA JPL CNEOS Sentry risk table | Slot 20 — pivoted from NEO browse (DEMO_KEY rate limit); Palermo scale binning + diameter_class. |
| `flows/UK_Police_London_Crime/v1/` | data.police.uk street-level crime | Slot 32 — poly-filtered Central London (Westminster/City/Southwark/Lambeth); dotted_path on nested `location`/`outcome_status`; `crime_month` substring-alias dodges the trend_features month clash. |
| `flows/UK_EA_Flood_Monitoring/v1/` | environment.data.gov.uk /flood-monitoring/id/measures | Slot 33 — 5.6k EA telemetry-station measurements; `numeric_bin` water-level bands, `map_values` parameter/qualifier normalization, `days_since` reading-freshness. |
| `flows/UK_Parliament_Written_Questions/v1/` | questions-statements-api.parliament.uk | Slot 34 — Commons + Lords written questions, `json_records_path: "results"` + dotted_path on `.value` wrapper; `days_between` answer latency + department_group map. |
| `flows/UK_NHS_ORD_Trusts/v1/` | directory.spineservices.nhs.uk (Spine ORD) | Slot 35 — active NHS Trusts (PrimaryRoleId RO197); `substring` postcode area/OrgId prefix; `map_values` postcode-area → England region. |
| `flows/UK_TfL_AccidentStats_2019/v1/` | api.tfl.gov.uk/AccidentStats/2019 | Slot 36 — full year 51k Greater London road-traffic accidents; new `list_length` derived-col for casualty/vehicle counts; `list_first_field` primary_vehicle_type; substring-hour + time_of_day_bucket map. |

The first 14 form a baseline; flows 1-10, 11-20 and 21-30 of the **Prep Agent demo
collection** are the thirty archived US flows. Slots 1-10 cover the
federal / open-government baseline; 11-20 cover defense and national
security (DoD contracts, CVEs, KEV, USGS, TLE catalog, GDELT CENTCOM,
SWPC, World Bank military expenditure, CNEOS Sentry); 21-30 cover
state, local, and education (BLS LAUS, USAspending SLED grants,
Boston 311, CMS nursing homes, HealthData.gov hospitals, ProPublica
nonprofits, FEC candidates, LA crime, CDC PLACES, WA EV registrations).
Slot 31 is the MOD JEWOSC EW fusion demonstration; slots 32-36 are the
UK Public Sector cohort (Police data.police.uk, Environment Agency
flood-monitoring, Parliament written questions, NHS ORD Trusts, TfL
AccidentStats 2019).

Reproduce any one with:

```sh
python3 -m skill.scripts.run_loop \
    --spec flows/<flow>/v1/spec.json \
    --flow-name <flow>
```
