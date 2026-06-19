# TabPy setup (the actually-working recipe)

prep-cli runs Python script nodes via TabPy. Three things must be
true for the skill's flows to execute:

1. TabPy is reachable from prep-cli on a port that prep-cli's
   `pythonSupport.json` points at.
2. TabPy's evaluate timeout is high enough for the work the script
   does (default 30s is too low for graph_analyzer on big graphs).
3. TabPy's Python interpreter has every module the rendered scripts
   import.

This page is the unblock-recipe. For background on the GUI-vs-CLI
auth file split, see the gotchas memory.

## The recipe — unauth TabPy on :9099

prep-cli v2025.3 / 2026.1 cannot reliably pass basic-auth credentials
to TabPy on macOS. Even with a valid `pythonSupport.json` at the
CLI's `Command Line Repository/Credentials/`, the JAR's REST-mode
config fails to populate `BasicAuthConfiguration.password` and every
script node errors with "BasicAuthConfiguration.getPassword() is null".

The working pattern: launch a SECOND TabPy on `:9099` with auth
disabled, point Prep at it.

```sh
cat > /tmp/tabpy_smoke.conf <<'EOF'
[TabPy]
TABPY_PORT = 9099
TABPY_EVALUATE_ENABLE = true
TABPY_EVALUATE_TIMEOUT = 600
EOF

/Library/Frameworks/Python.framework/Versions/3.13/bin/tabpy \
    --config=/tmp/tabpy_smoke.conf --disable-auth-warning &

# Verify
curl -s http://localhost:9099/info | python3 -m json.tool | head
```

Then update `Command Line Repository/Credentials/pythonSupport.json` to:

```json
{"host":"localhost","port":"9099","username":"","password":"","requireSsl":"no","sslCertificate":""}
```

(Path: `~/Documents/My Tableau Prep Repository/Command Line Repository/Credentials/pythonSupport.json` on macOS.)

After this swap, prep-cli runs script-node flows end-to-end. Any
previous auth-required TabPy on a different port can keep running
for Builder GUI work — they're independent.

## TABPY_EVALUATE_TIMEOUT = 600 is load-bearing

The default 30-second TabPy script timeout is too short for two
common cases the skill produces:

- `graph_analyzer.py.j2` running on graphs with ≥10k edges
  (eigenvector + Fruchterman-Reingold layout takes minutes).
- `api_caller.py.j2` doing paginated ArcGIS pulls of 5k+ features
  (the network round-trips alone push past 30s).

Symptom when you forget: prep-cli reports
`"Unable to connect to the Tableau Python (TabPy) server localhost
on port 9099"` even though `curl /info` succeeds. That's TabPy
returning HTTP 408 from its `/evaluate` handler; prep-cli surfaces
it as a connection error.

Fix: include `TABPY_EVALUATE_TIMEOUT = 600` in the conf above and
restart TabPy.

## Required Python modules in TabPy's interpreter

TabPy uses *its own* Python interpreter — NOT the project `.venv`.
If a script imports a library and falls back silently when missing,
the CLI run will silently produce different numbers than the
standalone harness.

Install with TabPy's pip, not `.venv`'s pip:

```sh
/Library/Frameworks/Python.framework/Versions/3.13/bin/pip install \
  pandas networkx rapidfuzz \
  PyPDF2 pdfplumber pdf2image pytesseract \
  python-dateutil openai certifi tableauserverclient tableauhyperapi
```

Audit:

```sh
/Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python -c "
for m in ('rapidfuzz','dateutil','pdfplumber','pdf2image','pytesseract',
          'pandas','PyPDF2','openai','networkx','certifi',
          'tableauserverclient','tableauhyperapi'):
    try: __import__(m); print(f'{m}: ok')
    except ImportError as e: print(f'{m}: MISSING ({e})')"
```

## Restart TabPy after any install

TabPy caches modules in its sys.modules; new installs don't take
effect until the daemon restarts.

```sh
pkill -f "tabpy.*tabpy_smoke.conf"
sleep 2
/Library/Frameworks/Python.framework/Versions/3.13/bin/tabpy \
    --config=/tmp/tabpy_smoke.conf --disable-auth-warning &
```

## Builder GUI vs CLI — separate credentials files

Tableau Prep Builder's GUI reads
`~/Documents/My Tableau Prep Repository/Credentials/pythonSupport.json`.

prep-cli reads
`~/Documents/My Tableau Prep Repository/Command Line Repository/Credentials/pythonSupport.json`.

These are **separate files**. The GUI can have a working TabPy
config while the CLI is broken (and vice versa). When the GUI
errors with "BasicAuthConfiguration.getPassword() is null", fix
the GUI side via *Help → Settings and Performance → Manage
Analytics Extension Connection* — don't hand-edit the JSON; the
GUI re-saves it cleanly on connection-test success.

For the CLI side, hand-edit the JSON above to point at the unauth
:9099 instance.

## Past failure modes (codified to prevent repeat)

- **SSL via system trust store fails on macOS Python.org distros**
  → use `certifi.where()` in `_ssl_ctx()`. The api_caller template
  already does this.
- **TabPy can't `json.dumps(pd.Timestamp)`** → emit datetime
  columns as ISO 8601 strings. The api_caller template does this
  for ArcGIS date fields; trend_features and eoc_fire_metrics
  call `_coerce_to_declared_schema` at the end of every script
  to enforce wire types.
- **`get_output_schema` must match real columns** → INPUT_SCHEMA
  is threaded through every template; the planner builds it from
  the post-cast schema (`_input_schema_after_casts`).
- **Validators that drop input columns** → all script templates
  pd.concat passthrough cols + validator outputs.

See `feedback_tabpy_script_gotchas.md` for the full incident log.
