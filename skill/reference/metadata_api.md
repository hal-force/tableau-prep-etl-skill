# Tableau Metadata API — what the skill uses

The skill talks to the Metadata API for two phases:

- **Phase 0 (INTERNAL scan)** — list published data sources on the
  site, score them against the user's request, return the top
  candidates so the user can pick one as an `internal_published_ds`
  source. (`skill/scripts/server_scan.py`)
- **Phase 11 (metadata writer)** — push DS-level + per-column
  descriptions back to the site after a successful publish.
  (`skill/scripts/metadata_writer.py`)

The Metadata API is GraphQL at `/api/metadata/graphql` on every
Tableau Server >= 2019.3 and on Tableau Cloud. We talk to it through
`tableauserverclient.Server.metadata.query()` so PAT auth and site
plumbing are handled by TSC.

## Auth

PAT only, via env vars (read at call time, never persisted):

```
TABLEAU_SERVER_URL          # e.g. https://prod-useast-a.online.tableau.com
TABLEAU_SERVER_PAT_NAME
TABLEAU_SERVER_PAT_SECRET
TABLEAU_SERVER_SITE         # site contentUrl ("" for default site on Server)
```

The signin handshake uses
`TSC.PersonalAccessTokenAuth(name, secret, site_id=site)`. PATs are
strongly preferred over user/password — they expire on a known
schedule and don't carry interactive privileges.

Discovery layered in front: see `scripts/server_creds.py`. Walks env
vars first, then macOS Keychain (`security find-generic-password`),
then Linux libsecret (`secret-tool`), then
`~/.tableau-prep-etl/server.json` (chmod 600 plaintext, local dev only).

## Queries we use

### List datasources (paginated)

```graphql
query ListPublishedDatasources($first: Int, $after: String) {
  publishedDatasourcesConnection(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      luid
      name
      description
      projectName
      hasExtracts
      isCertified
      certificationNote
      tags { name }
      owner { username name }
      createdAt
      updatedAt
      extractLastUpdateTime
    }
  }
}
```

We walk pages until `hasNextPage = false`, then score every node
locally (token-overlap on name/description/project/tags with a small
boost for certified DSs). No per-DS detail fetches happen during the
scan — those go through `inventory_datasource(luid)`.

### Per-DS field inventory

```graphql
query DatasourceInventory($luid: String!) {
  publishedDatasources(filter: { luid: $luid }) {
    luid
    name
    description
    projectName
    hasExtracts
    isCertified
    fields {
      __typename
      name
      description
      ... on ColumnField { dataType role aggregation }
      ... on CalculatedField { dataType role formula }
    }
  }
}
```

Used by the metadata writer to seed proposals against existing column
descriptions, and by future workflows that want to show the user a
column inventory before they pick the DS.

## Writes — important: Metadata API is read-only on Cloud

The Metadata API is **read-only on Tableau Cloud** as of 2026-06.
GraphiQL's "Docs" panel reports the Mutation root is empty;
historical mutations (`updateField`, `updateColumn`,
`updateColumnDescription`, `updateColumnField`,
`updateFieldDescription`, etc.) all return a generic
`Internal Server Error(s) while executing query` regardless of
auth scope or Data Management licensing. This is the canonical
Tableau-side behavior for Cloud — verified against
`prod-useast-a.online.tableau.com / usfederaldemos`. On older
Tableau Server builds (≤ 2022.x) the GraphQL mutations existed; on
modern Server they have been deprecated in favor of REST.

The skill therefore uses two **non-GraphQL** paths to apply
metadata writes:

### Update DS-level description

REST, not GraphQL — `PUT /api/{ver}/sites/{site}/datasources/{luid}`
with the standard `<datasource>` payload. We let TSC handle this via
`server.datasources.update(item)` after setting `item.description`.
Works on Cloud and Server.

### Update column descriptions — .tds round-trip

The supported write surface for column descriptions on Cloud is
download-modify-republish:

```
1. server.datasources.download(luid, include_extract=True)  → .tdsx
2. unzip; locate the .tds and Data/Extracts/*.hyper sidecar
3. for each (col, description):
     find <column name='[col]' ...> element OR create one with the
       inferred datatype/role/type
     replace any existing <desc> child with:
       <desc><formatted-text><run>DESCRIPTION</run></formatted-text></desc>
4. repack as .tdsx (preserve the .hyper sidecar verbatim)
5. server.datasources.publish(item, path, mode="Overwrite")
```

The DS LUID is **preserved** across the overwrite, so any
references / dashboards / connections stay valid. Implemented in
`metadata_writer._apply_column_descriptions_via_tds` (single
atomic round-trip — no per-field network call).

The .tds XML is well-defined: the column element shape is

```xml
<column caption='display_name' datatype='real' name='[internal_name]'
        role='measure' type='quantitative'>
  <desc><formatted-text><run>Description text.</run></formatted-text></desc>
</column>
```

Datatype values: `integer`, `real`, `string`, `date`, `datetime`,
`boolean`. Role: `measure` for numeric quantitative, `dimension`
for categorical. The skill's writer carries a `column_types` map
through from `run_loop._maybe_write_metadata` so newly-created
column elements get correct types; existing columns retain their
declared types and only the `<desc>` child is rewritten.

### Async indexing on Cloud

After a `mode="Overwrite"` republish, Cloud's Metadata API
reindexes asynchronously — readback queries (`fields { description }`)
may show stale data for several minutes (occasionally longer). The
.tds itself is authoritative; the descriptions appear in
`Data Details` in the browser as soon as the republish completes.

## Performance notes

- The Metadata API can time out at ~30s on broad introspection. We
  keep queries narrow (specific field selections, paginated lists).
- Large sites: pagination depth depends on the total DS count. The
  default `page_size = 100` is a reasonable balance for sites in the
  low-thousands of published DSs.
- Mutations should be idempotent. `updateField` with the same
  description is a no-op on the server side.

## Failure modes

- **No env vars** → `is_configured()` returns False; scan + metadata
  writer skip silently and the rest of the pipeline runs unaffected.
  The Phase 1a credentials gate emits platform-tailored suggestions
  before any phase that needs server access.
- **Bad PAT** → TSC raises during signin; the calling helper catches
  it and returns `{"status": "error", ...}` so the run still produces
  a `.tfl` locally.
- **Metadata API disabled on the site** → queries return
  `{"errors": [{"message": "Metadata API is not enabled..."}]}`. We
  surface the error message so the user can ask their site admin to
  enable it.
- **Insufficient PAT scopes** → `updateField` returns a permission
  error. The writer records the failure per-column but doesn't roll
  back — already-applied descriptions stay.

## CLI smoke tests

```bash
# Quick: are env vars set?
python3 -m skill.scripts.server_scan --check

# Full discovery (env -> Keychain -> secret-tool -> file):
python3 -m skill.scripts.server_creds --load

# Search: what's relevant to "customer spend"?
python3 -m skill.scripts.server_scan --search "customer spend" --top-k 5

# Inventory: full column list for one DS
python3 -m skill.scripts.server_scan --inventory <luid>

# Generate (don't apply) a description proposal for one output
python3 -m skill.scripts.metadata_writer \
    --spec runtime/specs/<flow>.json \
    --output-name <output_name> \
    --columns "col_a,col_b,col_c" \
    --review --run-dir /tmp/tpa-md-test
```
