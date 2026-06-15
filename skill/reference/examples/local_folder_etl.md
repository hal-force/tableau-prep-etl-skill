# Example: Local folder ETL (the SF1034 invoice case)

User request:

> Process this folder of PDF invoice portfolios and extract Standard Form 1034
> fields. Each portfolio contains an SF1034 form and one or more invoice PDFs.

## Spec produced by `intake.py`

```json
{
  "sources": [{
    "type": "local_folder",
    "path": "/path/to/your/invoices",
    "format": "pdf_portfolio"
  }],
  "transformations": [
    {"kind": "form_widget_extract", "schema": "SF1034"},
    {"kind": "llm_extract_fallback", "schema": "SF1034"},
    {"kind": "ocr_for_image_pdfs"}
  ],
  "outputs": [
    {"kind": "hyper", "name": "production_records.hyper"},
    {"kind": "hyper", "name": "qa_suggestion_inbox.hyper"},
    {"kind": "hyper", "name": "statistical_anomalies.hyper"}
  ],
  "qa_tier": "llm",
  "eval_strategy": "extract_from_source",
  "deployment": "local"
}
```

## Strategy chosen by `source_planner.py`

- **Source acquisition**: folder-listing input (`.v1.LoadCsv` reading a
  side `.xlsx` whose single column points at the folder), then a
  per-file Script step that walks each PDF.
- **Eval strategy**: `extract_from_source`. The PDFs themselves contain
  the SF1034 widgets, which carry the certifier-typed expected values
  as AcroForm field `/V` values. We treat those as ground truth.
- **QA tier**: `llm`. Adds the QA reviewer + Statistical Analyst nodes.

## Output

- `flow.tfl` with 22 nodes (10 Hyper outputs).
- Refinement loop runs 1 iteration if accuracy ≥ 0.85, else proposes a
  v2 of the form-widget agent.
- Final mean: ~0.91 sf1034_truth, ~0.88 form_widget_agreement on a
  22-portfolio corpus.

## Files generated

```
runtime/<run_id>/
├── spec.json
├── flow.tfl
├── scripts/
│   ├── form_widget_extractor.py     # rendered from connectors/pdf_form.j2
│   ├── llm_extractor.py              # rendered from api_caller.py.j2 + SF1034 prompt
│   ├── ocr_preprocessor.py           # rendered from connectors/pdf_ocr.j2
│   ├── qa_reviewer.py                # rendered from qa_reviewer.py.j2
│   └── statistical_analyst.py        # rendered from statistical_analyst.py.j2
├── outputs/                          # .hyper files
└── report.md                         # final attention list + suggestions
```

## Why this is the canonical example

The invoice case in the parent `auto_refine/` repo is the worked
prototype this skill generalizes. Running the skill on this exact
request reproduces the framework hand-built in `auto_refine/` —
serving as the strongest regression check for the skill's correctness.
