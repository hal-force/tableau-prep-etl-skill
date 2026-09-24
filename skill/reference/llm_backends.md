# LLM backends for script nodes (the actually-working recipe)

The skill's own LLM calls — intake (`scripts/intake.py`), the QA
reviewer, and the Phase 11 metadata writer (`scripts/metadata_writer.py`)
— all go through **one** transport: an OpenAI-compatible gateway,
`POST <url>/chat/completions`, answer read from
`choices[0].message.content`. That is the default and covers every
built-in phase.

Some flows need an LLM **inside a script node** — per-row extraction,
classification, or enrichment that runs on TabPy for every input row
(the DNFSB Resident-Inspector reference flow does exactly this: it
sends each weekly report's full text to an LLM and gets back long-form
safety entities). This page is the recipe for those script-node LLM
calls: the two backend shapes, the reasoning-model trap that silently
returns nothing, and the concurrency pattern that turns an 11-minute
run into a 3-minute one. All of it was proven on the DNFSB Cohere arm;
none of it is wired into a shipped template yet — treat it as the
pattern to copy when you author an LLM extractor node.

## Two backend shapes

### OpenAI-compatible gateway (default)

```python
body = {
    "model": model,
    "messages": [{"role": "system", "content": sys},
                 {"role": "user", "content": user}],
    "temperature": 0,
    "max_tokens": 4000,
    "response_format": {"type": "json_object"},   # JSON mode
}
# answer:
content = resp["choices"][0]["message"]["content"]   # a STRING
```

Config: `LLM_GATEWAY_URL` / `LLM_GATEWAY_KEY` / `LLM_GATEWAY_MODEL`
(see SKILL.md → Configuration). This is what `intake.py` and
`metadata_writer.py` already do.

### Cohere Chat API v2 (alternate)

Same idea, three wire differences that will bite you if you assume the
OpenAI shape:

```python
# endpoint + auth
url = "https://api.cohere.com/v2/chat"
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

body = {
    "model": model,                               # e.g. "command-a-03-2025"
    "messages": [{"role": "system", "content": sys},
                 {"role": "user", "content": user}],
    "temperature": 0,
    "max_tokens": 4000,
    "response_format": {"type": "json_object"},
}

# answer: content is a LIST OF BLOCKS, not a string.
blocks = resp["message"]["content"]               # list
text = "".join(b["text"] for b in blocks if b.get("type") == "text")
```

The three differences from the gateway shape:

1. Answer lives at `message.content` (not `choices[0].message.content`).
2. `message.content` is a **list of typed blocks**, not a string. Text
   is only in blocks where `type == "text"`. Concatenate those; ignore
   the rest.
3. Reasoning models prepend a `{"type": "thinking", ...}` block before
   the text block — which leads directly to the trap below.

## The reasoning-model thinking-budget trap

**Symptom:** calls take 30–60s, `finish_reason == "MAX_TOKENS"`, the
text block is empty, and the node emits **0 rows**. Looks like the
model "failed" or the prompt is wrong. It isn't — the model spent the
entire `max_tokens` budget *thinking* and never got to the answer.

This hits **reasoning models only**: Cohere `command-a-plus-*` and any
`*-reasoning` model emit an internal `thinking` block. Left unbounded,
reasoning consumes all of `max_tokens` before a single answer token is
produced.

**Fix — bound the thinking budget AND give the answer headroom:**

```python
def _is_reasoning_model(model):
    m = (model or "").lower()
    return "reasoning" in m or "command-a-plus" in m

if THINKING_TOKENS > 0 and _is_reasoning_model(model):
    body["thinking"] = {"type": "enabled", "token_budget": THINKING_TOKENS}
    # max_tokens must cover the budget PLUS room for the actual answer:
    body["max_tokens"] = max(body["max_tokens"], THINKING_TOKENS + 2000)
```

Two things that will waste an afternoon if you don't know them:

- `"thinking": {"type": "disabled"}` returns **HTTP 422** on these
  models — you can't turn reasoning off, only bound it. Omit the key
  entirely for non-reasoning models; set it (enabled + budget) for
  reasoning ones. That's what `_is_reasoning_model()` gates.
- The `max_tokens >= token_budget + 2000` guard is load-bearing. Set
  the budget without raising `max_tokens` and you've just re-created
  the original starvation with extra steps.

**Empirical (one DNFSB weekly report, `command-a-plus-05-2026`):**

| thinking budget | call time | items returned |
|---|---|---|
| unbounded       | ~60s      | 0 (MAX_TOKENS, empty text) |
| 1200            | ~13s      | 15 |
| 800             | ~8s       | 17 |

## Latency is output-bound, not reasoning-bound

Do **not** reach for a non-reasoning model expecting it to be faster
per call. It isn't. Regular Command A (`command-a-03-2025`,
non-reasoning) measured **~11.6s/call** vs **~13s/call** for the
budget-bounded A+ — a wash. Per-call latency is dominated by
*output-token generation*, not by reasoning. Model choice is a
quality/vocabulary decision, not a speed lever.

(Quality note from the DNFSB corpus, if you're choosing: Command A's
free-text themes mapped to the controlled issue-type vocabulary at
~94%, cleaner than A+'s more granular themes — so the faster-to-map,
cheaper model was also the better downstream fit. Champion GPT arm
produced ~4.6 themes/report, Command A ~2.8, A+ ~3.8. Measure on your
own corpus before switching.)

## The real speed lever: per-row concurrency

LLM calls over rows are **independent and I/O-bound** — the ideal case
for a bounded thread pool. A sequential loop pays `n × latency`; a pool
of `w` workers pays `~ceil(n/w) × latency`.

**Empirical (DNFSB full run, 1,298 reports):** sequential ≈ 11 min;
6 workers ≈ 3 min. On an 8-report demo slice: 29s wall = 3.6s/report
vs ~12s/report sequential.

Pattern that works cleanly inside a TabPy script node:

```python
import concurrent.futures, threading

CONCURRENCY = max(1, int(os.environ.get("COHERE_CONCURRENCY", "6")))
_LOG_LOCK = threading.Lock()          # logging from worker threads must be serialized

def extract(df):
    tasks = [(i, row) for i, row in enumerate(rows) if row["full_text"].strip()]
    workers = min(CONCURRENCY, len(tasks)) or 1
    results = {}                       # keyed by original index i

    def _work(task):
        i, row = task
        # ... one LLM call; on 429, sleep-and-retry with backoff ...
        return {"i": i, "rows": [...], "n_items": n, "err": None}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_work, t) for t in tasks]
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            results[r["i"]] = r
            # increment ok/failed counters BEFORE building any progress
            # tail — doing it after is a classic off-by-one in the log.

    # reassemble in INPUT order — as_completed returns out of order:
    out_rows = []
    for i in sorted(results):
        out_rows.extend(results[i]["rows"])
    return pd.DataFrame(out_rows, columns=OUT_COLS)
```

Rules that keep it correct and polite:

- **Reassemble by index.** `as_completed` yields futures in completion
  order, not submission order. Collect into a dict keyed by the
  original row index and re-sort, or the output row order is
  nondeterministic across runs.
- **Serialize logging** behind a lock — interleaved `print`/log lines
  from worker threads are otherwise unreadable, and any shared counter
  updated from workers is a race. Increment counters *before* you
  render a progress line (incrementing after produces an off-by-one).
- **Retry 429 with backoff** inside `_work`; don't let one rate-limit
  kill the batch.
- **Trial / free keys: drop `CONCURRENCY` to 1 or 2.** Their per-minute
  caps are low and 6 parallel calls will spend the run in backoff.
  Production keys handle 6 comfortably.
- **Bound the pool** — `min(CONCURRENCY, len(tasks))`. Never spawn a
  thread per row.

## Config discovery for script-node keys (read at call time)

A TabPy script node does **not** inherit the shell that launched
Builder's GUI (see `tabpy_setup.md` → "API keys for script nodes").
So resolve the key **at call time**, env first then a chmod-600 config
file — never bake it into the `.tfl` and never pass it on argv:

```python
def _cohere_key():
    k = os.environ.get("COHERE_API_KEY", "").strip()
    if k:
        return k
    cfg = os.path.expanduser("~/.tableau-prep-etl/config.json")
    if os.path.exists(cfg):
        with open(cfg) as fh:
            return (json.load(fh).get("cohere") or {}).get("api_key", "")
    return ""
```

The Cohere block lives **alongside** the existing gateway block in the
same `~/.tableau-prep-etl/config.json` (chmod 600) — the gateway keys
stay at the top level; add a sibling `cohere` object:

```json
{
  "url": "https://<gateway>/chat/completions",
  "key": "<gateway-token>",
  "model": "claude-sonnet-4-6",
  "cohere": { "api_key": "<cohere-key>", "model": "command-a-03-2025" }
}
```

Reading at call time means **no TabPy restart** is needed after you add
or rotate the key — unlike shell env vars, which the daemon only reads
at launch (that restart requirement is the `tabpy_setup.md` "Restart
TabPy after adding a source-credential env var" case). A config-file
key sidesteps it entirely.

## Environment knobs (DNFSB Cohere arm)

| Var | Default | Purpose |
|---|---|---|
| `COHERE_API_KEY` | — | key (env beats config file) |
| `COHERE_MODEL` | `command-a-03-2025` | model id |
| `COHERE_CONCURRENCY` (or `DNFSB_LLM_CONCURRENCY`) | `6` | worker pool size |
| `COHERE_MAX_TOKENS` (or `DNFSB_LLM_MAX_TOKENS`) | `4000` | answer budget |
| `COHERE_THINKING_TOKENS` | `1024` | reasoning budget (reasoning models only) |

## Past failure modes (codified to prevent repeat)

- **Reasoning model returns 0 items, `finish=MAX_TOKENS`, empty text**
  → reasoning ate the whole budget. Set `thinking.token_budget` AND
  `max_tokens >= budget + 2000`. `thinking:disabled` is a 422, not an
  option.
- **Parsing Cohere like OpenAI** → `message.content` is a list of
  blocks, not `choices[0].message.content` and not a string. Join the
  `type == "text"` blocks.
- **Switching to a non-reasoning model "to go faster"** → per-call
  latency is output-bound; the switch is a wash. Concurrency is the
  lever (11 min → 3 min on 1,298 rows).
- **Nondeterministic output row order** → `as_completed` completes out
  of order; reassemble rows by the original input index.
- **Trial key spends the run in 429 backoff** → lower `CONCURRENCY` to
  1–2 on trial/free keys.
