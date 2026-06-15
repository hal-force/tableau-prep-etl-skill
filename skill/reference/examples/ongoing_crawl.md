# Example: Ongoing topical web crawl with Crawl4AI

User request:

> I need to crawl news about <topic> on an ongoing basis. The topic should
> be configurable from a Tableau dashboard so analysts can change it
> without editing the flow.

## Spec produced by `intake.py`

```json
{
  "sources": [{
    "type": "web_crawl",
    "engine": "crawl4ai",
    "query_param_name": "Topic",
    "query_default": "AI safety",
    "max_results_per_run": 50,
    "domains_allowlist": ["bloomberg.com", "ft.com", "reuters.com"]
  }],
  "transformations": [
    {"kind": "extract_entities"},
    {"kind": "sentiment_score"},
    {"kind": "deduplicate_by_url"}
  ],
  "outputs": [
    {"kind": "hyper", "name": "topic_crawl_results.hyper"},
    {"kind": "hyper", "name": "crawl_audit.hyper"}
  ],
  "qa_tier": "llm",
  "eval_strategy": "synthesized",
  "deployment": "local"
}
```

## Strategy chosen by `source_planner.py`

- **Source acquisition**: `templates/crawler.py.j2` rendered with
  Crawl4AI as the crawl engine. The crawler reads the topic query
  from a Tableau Prep **parameter** (not a hardcoded constant),
  exposing it to the dashboard so analysts can change it without
  editing the flow.
- **Eval strategy**: `synthesized`. On the first run, the skill asks
  the LLM to generate a small expected-shape sample (≤20 records)
  matching the user's transformation spec, then validates the live
  crawl output against that shape. Lower fidelity than ground-truth
  extraction but appropriate for emergent web data.
- **QA tier**: `llm`. The QA reviewer flags shallow / low-quality
  crawl results; the Statistical Analyst tracks domain mix shifts
  across runs.

## Prep parameter wiring

The skill emits a `<parameter>` block in the flow's `parameters`
section:

```json
{
  "Topic": {
    "name": "Topic",
    "displayName": "Crawl Topic",
    "domain": {"type": "open"},
    "currentValue": "AI safety",
    "type": "string"
  }
}
```

The crawler script reads this via Tableau Prep's parameter-injection
mechanism (the parameter value is passed as an argument to the script's
entry function). When the analyst changes "Crawl Topic" in the Tableau
Server flow run dialog, the next run uses the new query.

## Known limitations

- Crawl4AI must be installed in TabPy's Python interpreter (`pip
  install crawl4ai`). The skill checks this in the "Plan + Confirm"
  phase and surfaces a clear install hint if missing.
- Rate-limited domains may need an allowlist (above) and per-domain
  throttling. v1 supports allowlist; throttling is a v2 feature.
- Crawl4AI's headless Chrome dep is heavy. For server-side runs the
  Tableau Prep Conductor host needs Chrome installed.
