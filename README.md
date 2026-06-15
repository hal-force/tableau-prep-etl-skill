# tableau-prep-etl-skill

A Claude Code skill that takes a natural-language ETL request and
produces a tested, refined Tableau Prep `.tfl` file with closed-loop
refinement.

## What's in the box

```
tableau-prep-etl-skill/
├── tflb_lib/                 # domain-agnostic .tfl JSON mutation library
│   ├── nodes.py              # make_script_node, make_join_node, …
│   ├── inputs.py             # rewire_input_to_local_excel
│   ├── topology.py           # prune_nodes_by_name, rewrite_script_paths, add_branch
│   └── builder.py            # build() top-level read/mutate/write
│
└── skill/                    # the Claude Code skill
    ├── SKILL.md              # frontmatter + workflow spec
    ├── scripts/              # intake, source_planner, generate_flow, run_loop, etc.
    ├── templates/            # Jinja templates for connector / api_caller / crawler / etc.
    └── reference/            # tfl_format, tabpy_setup, server_publishing, examples
```

## Install (local)

```sh
git clone https://github.com/hal-force/tableau-prep-etl-skill.git
cd tableau-prep-etl-skill
ln -s "$PWD/skill" ~/.claude/skills/tableau-prep-etl
```

The symlink lets Claude Code discover the skill while the canonical
source stays in this repo for version control.

## Configuration

Required env vars:

```sh
export LLM_GATEWAY_URL='https://your-gateway/chat/completions'
export LLM_GATEWAY_KEY='<your bearer token>'
export LLM_GATEWAY_MODEL='claude-sonnet-4-6'  # production default
```

Optional:

```sh
export CORPUS_DIR='/path/to/your/inputs'
export OUTPUTS_DIR='/path/to/your/outputs'
export TABLEAU_PREP_CLI='/Applications/Tableau Prep Builder (Apple silicon) 2026.1.app/Contents/scripts/tableau-prep-cli'
```

System dependencies:

- TabPy running on `localhost:9099` — see `skill/reference/tabpy_setup.md`.
- `tesseract` and `poppler` if any source involves PDF OCR
  (`brew install tesseract poppler`).

## Use

In Claude Code:

```
/tableau-prep-etl <your request>
```

Examples:

- "Process this folder of PDFs and extract Standard Form 1034 fields."
- "Pull GDELT events for the US daily into a Hyper extract."
- "Crawl news about <topic> ongoingly. Topic should be configurable
  from the dashboard."
- "Get parcel data from my ArcGIS server (PKI auth) and load into Tableau."

The skill walks through intake → planning → flow generation → eval rig
synthesis → bounded refinement loop → final report.

## Companion: invoice extraction example

The repo at `hal-force/tableau_prep_agentic_AI_document_extraction`
contains the full worked example this skill generalizes — the SF1034
invoice extraction pipeline. That repo's `auto_refine/` framework is
the prototype; this repo's `skill/` is the productized version.

## v2 roadmap

- `--publish` flag → push the produced `.tfl` to Tableau Server via
  REST API (PAT auth, multipart upload).
- Conductor schedule wiring for sources with `refresh_cadence` set.
- Cross-flow dependency management (output of flow A as input to B).

See `skill/reference/server_publishing.md` for the v2 design.
