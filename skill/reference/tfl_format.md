# .tfl reverse-engineering notes

## File format
A `.tfl` is a ZIP archive. Members observed:
- `flow` — JSON, the actual graph (nodes + edges + dataConnections)
- `displaySettings` — JSON, GUI layout (positions, viewport)
- `maestroMetadata` — JSON, version + bookkeeping
- `flowGraphThumbnail.svg` — preview image

We only need to author `flow`. `displaySettings` can be regenerated with default positions; `maestroMetadata` can be copied from the existing template.

## Top-level `flow` keys
`parameters`, `initialNodes`, `nodes`, `connections`, `dataConnections`,
`connectionIds`, `dataConnectionIds`, `nodeProperties`, `extensibility`,
`selection`, `majorVersion`, `minorVersion`, `documentId`, `obfuscatorId`.

## Edges
Edges are stored on the source node as `node['nextNodes']` (each entry has
`nextNodeId`). There is no global edge list to maintain.

## Node types we need
| `nodeType`                              | Role                      |
|-----------------------------------------|---------------------------|
| `.v1.LoadSql`                           | Input (folder/file load)  |
| `.v1.Container`                         | Logical group             |
| `.v2019_2_2.SuperExtensibilityNode`     | Python script step (TabPy)|
| `.v2018_2_3.SuperJoin`                  | Join                      |
| `.v1.WriteToHyper`                      | Output (.hyper)           |

## Python script node (the surface we mutate most)
A `SuperExtensibilityNode` wraps an inner `actionNode` of type
`.v2019_2_2.ExtensibilityNode`. The fields we care about:

```jsonc
{
  "setupParameters": {
    "scriptFilePath": "<absolute path to .py>"
  },
  "executionParameters": {
    "scriptFunctionName": "<entry function name>"
  },
  "externalServiceType": "pythonSupport"
}
```

Both `scriptFilePath` and `scriptFunctionName` are stable handles —
when we promote a new agent version we can swap the path and leave the
graph topology intact.

## Existing graph (current WIP)
```
Directory List → Invoice Directories ─┬─ LLM Extraction        → Cleanse ─┬─ Invoice Extraction (Hyper)
                                      ├─ Standard Forms        → SF Output → Join 1 ↑
                                      │                                     Cleanse ↗
                                      └─ Raw Invoice Text      → Invoice Text Extraction (Hyper)
                                       Standard Forms          → Standard Form Extraction (Hyper)
                                       Join 1 → Validate Test  → Stats → LLM Analyst
                                       Join 1 → LLM QA
```

Current script nodes point at the `*_test.py` variants:
- LLM Extraction → `02_LLM_Extraction/llm_extraction_optimized_test.py` :: `extract_invoices_llm_with_guidance`
- (similar pattern for the other extension nodes — to confirm per node when generator is built)

## Implications for the auto-refiner
1. **No need to open Prep Builder.** We can read & write `flow` JSON directly.
2. **Promotion = file path swap.** Versioned agent files (`agents/v3/llm_extraction.py`) can be promoted by editing one string in `setupParameters.scriptFilePath`.
3. **Topology changes are also safe** — add/remove nodes by editing `nodes` and the originating node's `nextNodes`. `displaySettings` can be regenerated.
4. **TabPy is required at runtime.** During the inner refinement loop we invoke the .py functions directly (faster, deterministic). The outer loop runs the .tfl via Tableau Prep CLI to verify the full pipeline.
