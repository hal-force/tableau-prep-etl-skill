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

## Security notice — read before deploying

TabPy is a Python-eval server. **Anything that can reach the
TabPy port can execute arbitrary code as the user running TabPy.**
The recipes below default to `localhost`-only bind so the port is
not reachable from the network. Do NOT expose TabPy on `0.0.0.0`
or a shared interface without adding authentication, TLS, and (at
minimum) a firewall rule. For any multi-user or production setup,
follow the official TabPy security guidance
(<https://tableau.github.io/TabPy/docs/server-config.html>) —
enable basic auth over TLS, or restrict access to a trusted proxy.

## The recipe — local-only TabPy on :9099

prep-cli v2025.3 / 2026.1 cannot reliably pass basic-auth credentials
to TabPy on macOS. Even with a valid `pythonSupport.json` at the
CLI's `Command Line Repository/Credentials/`, the JAR's REST-mode
config fails to populate `BasicAuthConfiguration.password` and every
script node errors with "BasicAuthConfiguration.getPassword() is null".

The working pattern: launch a **loopback-only** TabPy on `:9099`
with auth disabled, and point Prep at it. Loopback binding means
the port is not reachable from other machines on your network — it
answers only to `localhost` on the same host.

```sh
cat > /tmp/tabpy_smoke.conf <<'EOF'
[TabPy]
TABPY_PORT = 9099
TABPY_BIND_IP = 127.0.0.1
TABPY_EVALUATE_ENABLE = true
TABPY_EVALUATE_TIMEOUT = 600
EOF

# Use whichever tabpy is on PATH — no hard-coded interpreter path.
"$(which tabpy)" \
    --config=/tmp/tabpy_smoke.conf --disable-auth-warning &

# Verify it responds on loopback but NOT on the LAN interface.
curl -s http://localhost:9099/info | python3 -m json.tool | head
# Should FAIL (connection refused) — confirms external-facing bind is off:
# curl -s http://$(ipconfig getifaddr en0):9099/info
```

Then update `Command Line Repository/Credentials/pythonSupport.json` to:

```json
{"host":"localhost","port":"9099","username":"","password":"","requireSsl":"no","sslCertificate":""}
```

(Path: `~/Documents/My Tableau Prep Repository/Command Line Repository/Credentials/pythonSupport.json` on macOS.)

After this swap, prep-cli runs script-node flows end-to-end. Any
previous auth-required TabPy on a different port can keep running
for Builder GUI work — they're independent.

> **Why `TABPY_BIND_IP = 127.0.0.1`?** TabPy's default binds to
> `0.0.0.0`, which listens on every network interface. On a laptop
> connected to a public Wi-Fi network, that means anyone on the
> same network can send code to `/evaluate` and it will execute
> as your user. Loopback binding closes that hole cheaply.

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

Install with TabPy's pip, not `.venv`'s pip. Use whichever pip
matches the `tabpy` you launched:

```sh
"$(dirname "$(which tabpy)")/pip" install \
  pandas networkx rapidfuzz \
  PyPDF2 pdfplumber pdf2image pytesseract \
  python-dateutil openai certifi tableauserverclient tableauhyperapi
```

Audit:

```sh
python3 -c "
for m in ('rapidfuzz','dateutil','pdfplumber','pdf2image','pytesseract',
          'pandas','PyPDF2','openai','networkx','certifi',
          'tableauserverclient','tableauhyperapi'):
    try: __import__(m); print(f'{m}: ok')
    except ImportError as e: print(f'{m}: MISSING ({e})')"
```

(Run this against the same interpreter that TabPy uses — `ps eww`
on the TabPy PID will show its executable.)

## Restart TabPy after any install

TabPy caches modules in its sys.modules; new installs don't take
effect until the daemon restarts.

```sh
pkill -f "tabpy.*tabpy_smoke.conf"
sleep 2
"$(which tabpy)" \
    --config=/tmp/tabpy_smoke.conf --disable-auth-warning &
```

## Restart TabPy after adding a source-credential env var

The daemon inherits its process environment **at launch time only**.
Adding a new keychain-mapped variable to `~/.tableau-prep-etl/load_env.sh`
(e.g. `EIA_API_KEY`, `ACLED_API_KEY`) does not retroactively update
a long-lived TabPy. run_loop's Popen inherits env from prep-cli,
which inherits from the daemon — not from your current shell — so
`os.environ.get('EIA_API_KEY')` inside a script node returns empty
even though `printenv` in your shell shows the value.

Symptom: rendered script raises `RuntimeError: query_key auth
requires env var $EIA_API_KEY to be set` (or the equivalent for
whatever var you added). Verify daemon env before restarting:

```sh
lsof -i :9099                                          # note PID
ps eww -p <PID> | tr ' ' '\n' | grep EIA_API_KEY       # (empty = daemon lacks the var)
```

Fix — kill, source, relaunch (in one command so the env is fresh):

```sh
pkill -f "tabpy.*tabpy_smoke.conf" ; sleep 2
bash -c '
  source ~/.tableau-prep-etl/load_env.sh
  nohup "$(which tabpy)" \
      --config=/tmp/tabpy_smoke.conf --disable-auth-warning \
      > /tmp/tabpy_smoke.log 2>&1 &
'
```

Re-confirm with `ps eww -p <new-PID> | tr ' ' '\n' | grep <VAR>`.
The `RuntimeError: <VAR> not set` disappears on the next run.

## API keys for script nodes: read a config file at call time

The section above is the *CLI* path — a daemon launched from a shell
that sourced `load_env.sh`. **Builder's GUI TabPy is worse:** it's a
long-lived process started by the desktop app, so it inherits the GUI
launch environment, not your terminal's. A script node that does
`os.environ.get("COHERE_API_KEY")` gets an empty string even though
your shell has the value, and there's no shell to re-source — so the
restart dance above doesn't even apply.

The robust pattern for any key a script node needs (LLM keys, external
API keys) is to resolve it **at call time**, env first then a
chmod-600 config file:

```python
def _key(env_name, cfg_section):
    v = os.environ.get(env_name, "").strip()
    if v:
        return v
    cfg = os.path.expanduser("~/.tableau-prep-etl/config.json")
    if os.path.exists(cfg):
        with open(cfg) as fh:
            return (json.load(fh).get(cfg_section) or {}).get("api_key", "")
    return ""
```

Because the file is read on every call, **rotating or adding a key
needs no TabPy restart** — it takes effect on the next Run Flow. This
is the one case that escapes the "restart the daemon after adding a
var" rule above: a config-file key has no daemon-launch-time capture to
go stale. Keep the key out of the `.tfl` and off argv; the config file
(chmod 600, outside the repo) is the store. See
`reference/llm_backends.md` for the full LLM-key discovery recipe.

## Prep run fails with "Wait for cache write operation has terminated"

**Symptom:** a Run Flow (usually in Builder, sometimes CLI) aborts with
`Wait for cache write operation has terminated due to a failed write`.
It reads like a script-node crash, so the instinct is to debug the
Python. **It isn't a script error.** It's Prep's own connector/extract
cache failing to persist a partial result — most often left behind by a
*previously cancelled* run, occasionally a genuinely full disk.

Fix, in order:

1. **Check free disk first** (`df -h`) — rule out the boring cause. If
   the disk has room (the DNFSB incident had 530 GB free), it's stale
   cache, not space.
2. **Restart Tableau Prep Builder** — this alone clears the in-memory
   cache lock most of the time.
3. **Clear the on-disk connector/extract cache** if a restart isn't
   enough, then re-run.

Do not start rewriting the script node over this error — none of the
above touches your code, and a clean re-run after a Builder restart is
the expected outcome.

## Pre-warm TabPy's DNS resolver before Socrata/AWS pulls

macOS 15's `getaddrinfo` intermittently returns "nodename nor servname
provided" for Socrata FedRAMP hosts (`data.cdc.gov`, `chronicdata.cdc.gov`,
`data.sfgov.org`, `data.wa.gov`, etc.) — even with `--force-ipv4` and
the `_dns_warmup()` monkey-patch in `api_caller.py.j2`. The shell's
Python resolver may succeed at the same moment TabPy's daemon Python
still fails, because they carry independent DNS state.

Symptom: `curl https://data.wa.gov/...` works; the flow's api_caller
script raises `socket.gaierror: [Errno 8] nodename nor servname
provided`. Rerunning the same TFL immediately without changing
anything eventually succeeds — that's TabPy's resolver being cold.

Fix — POST to TabPy's `/evaluate` endpoint with a script that shells
out to `dscacheutil` in the daemon's own process context:

```sh
curl -s -X POST http://localhost:9099/evaluate \
    -H "Content-Type: application/json" \
    -d '{"data":{"_arg1":"data.wa.gov"},"script":"
import subprocess, socket
subprocess.run([\"/usr/bin/dscacheutil\",\"-q\",\"host\",\"-a\",\"name\",_arg1], check=False)
return socket.getaddrinfo(_arg1, 443, socket.AF_INET)[0][4][0]"}'
```

Do this once after launching TabPy and once before each large pull
against a new host. The daemon's `sys.modules['socket']` caches
successful lookups per-host.

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

For the CLI side, hand-edit the JSON above to point at the loopback
:9099 instance.

## Template render conventions

These are codified template-author rules. Violating them silently
breaks runs (sometimes only on certain spec shapes), so the rules
matter even when most templates currently obey them.

### Use the `pyrepr` Jinja filter, not `tojson`

`generate_flow.py` registers a custom filter:

```python
env.filters["pyrepr"] = repr
```

Use `| pyrepr` for every dict/list/scalar interpolation that lands
inside a Python literal:

```python
INPUT_SCHEMA: dict = {{ input_schema | pyrepr if input_schema is defined else '{}' }}
CAMEO_ROOTS    = {{ cameo_root_codes | pyrepr }}
```

`| tojson` emits JSON's `true`/`false`/`null`, which are syntax errors
in Python. The breakage is silent until a spec carries a bool or a
None default.

### No `from __future__ import annotations` and no PEP 585 subscripts at module level

Tableau Prep injects a preamble (the `prep_int()`/`prep_string()`
helpers) into every script node before sending to TabPy. The preamble
breaks both:

- `from __future__ import annotations` is no longer the first
  statement → `SyntaxError`.
- `INPUT_SCHEMA: dict[str, str]` at module scope evaluates `dict[...]`
  immediately, which fails without the future import.

Use plain `dict` / `list` (no subscripts) at module level. Function
bodies and lazy annotations are fine.

### `get_output_schema()` must return a DataFrame

Prep calls the script's `get_output_schema()` global to learn the
node's output columns. Return a `pd.DataFrame` whose values are the
injected `prep_*()` helpers — not a plain `dict` of them, which crashes
the TabPy call:

```python
def get_output_schema():
    return pd.DataFrame({
        "unit_id":   prep_string(),   # noqa: F821  (injected by Prep)
        "staffed":   prep_decimal(),  # noqa: F821
        "breach":    prep_decimal(),  # noqa: F821  0/1 flag
    })
```

The helpers only exist inside Prep's preamble, so `# noqa: F821` keeps
linters quiet and the function must never be called standalone. For
yes/no fields, emit `0`/`1` and declare `prep_decimal()` rather than
relying on a boolean helper — `prep_string` and `prep_decimal` are the
ones proven across the example flows.

### Shared modules across script nodes

When several script nodes import one shared helper module (the
one-scenario/N-views pattern in `examples/synthetic_multiview.md`), the
flow directory is not on TabPy's `sys.path`, and `__file__` may not be
defined in the node's scope. Insert the directory with a guarded
fallback before the import:

```python
_FLOW_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() \
    else "/abs/path/to/flow_dir"
if _FLOW_DIR not in sys.path:
    sys.path.insert(0, _FLOW_DIR)
import scenario_core  # noqa: E402
```

**Restart TabPy after editing a shared module.** TabPy keeps imported
modules in `sys.modules` for the life of its process, so a re-run picks
up edits to the node script itself but *not* to the module it imports.
Observed: a text fix in the shared module passed the standalone harness,
prep-cli then reported "Finished running the flow successfully", and the
Hyper still held the old string. After restarting TabPy, re-run and read
a changed value back out of the produced Hyper to confirm.

### Sibling-output routing via `output.source`

When two outputs need to consume different transformations off a
shared upstream tail (the Embassy Threat Monitor pattern), set
`output.source` on each output to the **node name string** of the
transformation whose output it should consume (the transform's
`args.name`, not a dict):

```json
"outputs": [
  {"kind": "published_data_source", "name": "Threat Events", "source": "Embassy Threat Join"},
  {"kind": "published_data_source", "name": "Risk Summary",  "source": "Embassy Risk Summary"}
]
```

`generate_flow.py` connects each output edge to the named node's id
rather than the linear flow tail. `output.source` is a plain string —
a dict form raises `TypeError: unhashable type: 'dict'`. Linear flows
omit `output.source` and inherit the tail.

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
