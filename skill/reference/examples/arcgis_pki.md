# Example: ArcGIS server with PKI authentication

User request:

> Get parcel data from my ArcGIS server. It's behind PKI — we authenticate
> with a client cert.

## Spec produced by `intake.py`

```json
{
  "sources": [{
    "type": "pki_endpoint",
    "name": "ArcGIS Parcels",
    "url": "https://arcgis.internal.example.com/server/rest/services/Parcels/MapServer/0/query",
    "format": "esri_feature_service_json",
    "auth": "client_cert",
    "extra": {
      "cert_path_env": "ARCGIS_CLIENT_CERT_PATH",
      "cert_key_env": "ARCGIS_CLIENT_KEY_PATH",
      "timeout_s": 90
    }
  }],
  "transformations": [],
  "outputs": [{"kind": "hyper", "name": "parcels"}],
  "qa_tier": "deterministic",
  "eval_strategy": "sample_validation",
  "deployment": "local"
}
```

> **Schema note.** The cert-path env-var names are `extra` keys on a
> `pki_endpoint` source, not top-level source keys (top-level unknown
> keys fail validation). The `pki_connector.py.j2` template flattens
> the feature-service geometry and returns a flat DataFrame itself —
> there is no `flatten_geometry` / `select_columns` transform kind, so
> `transformations` stays empty and column pruning happens downstream
> (in Tableau or via `.tds` hiding).

## Strategy chosen by `source_planner.py`

- **Source acquisition**: `templates/pki_connector.py.j2` rendered with
  the ArcGIS REST query URL + PKI cert paths from env vars. The
  template handles paginated `resultRecordCount` cursoring,
  `f=json` response parsing, and retries on 401.
- **Eval strategy**: `sample_validation`. The skill confirms the user's
  cert works, pulls 50 features, asks the user to confirm the schema +
  representative rows.
- **QA tier**: `deterministic`. Validators check OBJECTID uniqueness
  and PARCEL_ID format if a regex is supplied.

## Important caveats

The user must:

1. Set `ARCGIS_CLIENT_CERT_PATH` and `ARCGIS_CLIENT_KEY_PATH` env vars
   to actual cert paths the Tableau Prep Python interpreter can read.
2. Ensure the cert is loaded by TabPy's Python (the same env vars must
   be set in TabPy's launch environment, not just the skill's shell).
3. Ensure the Tableau Server / Prep Builder runtime trusts the
   ArcGIS server's CA chain.

The skill flags these in the "Plan + Confirm" phase before touching
any cert files.

## Why a Python step instead of the native ArcGIS connector

Tableau Prep ships an ArcGIS connector but it doesn't support
client-cert auth — only OAuth and basic auth. PKI endpoints require
a Python-side request via `requests` with `cert=(crt, key)`, which
the native connector can't express. The skill detects this case
during the planning phase and falls back to the Python template.
