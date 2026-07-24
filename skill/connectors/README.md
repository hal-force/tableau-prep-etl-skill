# Connector registry

Connectors built by the skill are cached here so subsequent runs that
match the same source signature can reuse the rendered Python step
(and its known-good defaults) instead of re-rendering from the
template.

## How keys are derived

`key = sha1("<source.type>|<host>|<auth>|<format>")[:16]`

Where `host` is the URL's hostname for `rest_api` / `graphql_api` /
`pki_endpoint` / `web_crawl` sources, the absolute folder path for
`local_folder`, and the connector class for `native_connector`.

This means any two specs with the same source type pointing at the
same host with the same auth method + format will hit the same cache
entry. Different URL paths under the same host still share the
connector — the skill records the best-known parameters from prior
runs and merges them in.

## On-disk shape

The **live** cache is per-user, outside the repo:

```
~/.tableau-prep-etl/connectors/
├── index.json                          # the per-user registry
└── <key>/
    ├── manifest.json                   # source signature, last_used_at, hit count
    ├── connector.py                    # rendered Python step (cached)
    └── defaults.json                   # spec.sources[*].extra defaults
                                        # (timeout_s, retries, headers, etc.)
```

Override with `TABLEAU_PREP_ETL_CONNECTOR_CACHE=/path` (useful for CI
or ephemeral runs). The `skill/connectors/index.json` shipped in this
repo is a **seed registry** — copied into the per-user directory on
first use, then never touched again.

## Lifecycle

- **Lookup**: `connector_registry.lookup(source) → CachedConnector | None`
- **Store**: after a successful render, `connector_registry.store(source, rendered_path, defaults)`
- **Promote**: when a run produces a measurably better connector
  (higher accuracy, fewer retries), `connector_registry.promote(...)`
  replaces the cached version. Old version is kept as `connector.v<N>.py`.

## What this is NOT

- Not a place to store **credentials**. The cached `.py` reads
  `os.environ` at runtime — the secret never enters the cache.
- Not a place to store **data**. Connector definitions only.
- Not auto-shared. Each user/repo has their own cache. To share a
  curated connector, promote it into `skill/templates/` as a real
  template variant.
