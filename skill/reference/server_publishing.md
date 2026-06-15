# Tableau Server publishing (v2 placeholder)

Server publishing is **not implemented in v1** of this skill. The skill
produces a working `.tfl` that can be:

- Opened in Tableau Prep Builder and run interactively.
- Run headlessly via `tableau-prep-cli -t flow.tfl`.
- Manually published via Tableau Prep Builder's "Publish to Tableau
  Server" menu, or via the Tableau Server REST API.

## What v2 will add

A `--publish` flag on `scripts/run_loop.py` that:

1. Authenticates to Tableau Server via Personal Access Token (PAT).
2. Selects the target site + project.
3. Uploads the `.tfl` via `POST /api/<api-version>/sites/<site-id>/flows`
   (multipart with the `.tfl` payload + connection metadata).
4. Returns the published flow URL + Conductor schedule (if requested).

## Required environment variables (v2)

```sh
export TABLEAU_SERVER_URL='https://<server>/'
export TABLEAU_SERVER_PAT_NAME='<PAT name>'
export TABLEAU_SERVER_PAT_SECRET='<PAT secret>'
export TABLEAU_SERVER_SITE='<site contentUrl, or "" for default site>'
export TABLEAU_SERVER_PROJECT='<project name or id>'
```

## Reference (for the v2 implementer)

- Tableau Server REST API: https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api.htm
- Flow publish endpoint: `POST /api/<api-version>/sites/<site-id>/flows`
- Authentication via PAT: `POST /api/<api-version>/auth/signin` with
  `<personalAccessTokenName>` + `<personalAccessTokenSecret>`.
- Multipart upload: `Content-Type: multipart/mixed; boundary=...`,
  with one part being the `<tsRequest>` XML metadata and a second part
  being the `.tfl` payload.

## Why deferred

1. The v1 `.tfl` shape is still iterating; locking down the upload
   format is premature.
2. A misconfigured PAT could push a bad flow into a production site —
   the deploy path needs explicit per-run confirmation, dry-run mode,
   and rollback support, which is meaningful design work.
3. Most users we've seen prefer reviewing the `.tfl` in Builder before
   publishing manually anyway.

When ready, the work is well-scoped: ~1 day to author `scripts/deploy.py`
and the auth/multipart helpers in `tflb_lib.publishing` (new submodule),
plus a verification run against a test site.
