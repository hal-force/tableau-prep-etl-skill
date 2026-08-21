# MOD JEWOSC EW Fusion (v4) — Customer Overview

*Synthetic / notional demonstration — not operational, not classified. Every emitter parametric, EOB laydown, and ELINT intercept is fabricated for an unclassified capability demo. NATO-reporting-name-style designations are for audience resonance only.*

## Why it matters

Electronic Warfare Operational Support (EWOS) lives or dies on one loop: a sensor cuts an unknown signal, an analyst decides whether the threat library already knows it, and — if it doesn't — a **mission-data-file reprogramming** cycle updates the platforms that are blind to it. Today that loop is slow and manual because the pieces sit in separate systems: the intercept feed, the threat library, the Electronic Order of Battle (EOB), and each platform's coverage list. **v4 fuses all four into a single, queryable operational picture** and, critically, turns the reprogramming backlog from one conflated number into an actionable, cause-split workload the EWOS cell can triage in minutes.

## How it's built — agentically, start to finish

The entire artifact is produced by a natural-language request handed to an agentic Tableau Prep ETL skill. No hand-coding of the flow.

1. **Intake & plan.** The agent parses the request into a structured spec — sources, the fusion logic, the output data source, and the quality gate — and confirms the plan before touching anything.
2. **Honest modelling-vs-fusion split.** The agent recognises that correlating a measured cut to the library is a *nearest-neighbour* search (not an equality match), so it isolates **only that** into a Python step and expresses everything else — library, EOB, platform coverage — as **native, visible join nodes** on the canvas. The fusion is auditable, not buried in a black box.
3. **Generate, run, verify.** It renders the flow, executes it locally against a live Python service, and verifies the result against a deterministic gate: 500 intercepts resolve to **310 matched / 62 ambiguous / 128 unknown** — reproduced byte-for-byte across builds, proving the model is stable.
4. **Publish & document itself.** The agent publishes the data source and flow to Tableau Cloud, then writes **48 column-level descriptions and a full provenance disclaimer back onto the data source** so an analyst (or an NL/AI query layer) can ask questions in plain English and get grounded answers. It hides the three technical join-residue keys so the catalog stays clean, and archives a versioned, policy-safe snapshot (sample rows only — no bulk synthetic data leaves the environment).

The whole chain — plan → build → test → publish → document → archive — runs from one instruction, with human confirmation gates at the decisions that matter.

## The so-what

- **The reprogramming queue is now diagnosable, not just counted.** v4 splits the 128-cut backlog into **56 genuinely new emitters, 68 library-ambiguous signals, and 4 correlator misses** — three different workloads that demand three different responses. The cell stops treating a de-interleave problem like a new-threat problem.
- **A known weakness became a feature.** Rather than hiding the correlator's miscalibration, v4 surfaces it as a **truth-vs-call confusion matrix**: the 68 "ambiguous-but-dumped-to-unknown" cuts are visibly recoverable by tuning one gate — a concrete, defensible calibration story instead of a silent defect.
- **Contradictions surface automatically.** v4 flags **4 emitters assessed inactive by the Order of Battle yet actively being collected** — EOB-update triggers that would otherwise stay invisible across siloed systems.
- **Time is back on the table.** A data-typing fix restores real timestamps, unlocking "when is collection densest / are new signals clustering?" analysis that was previously impossible.
- **It's repeatable and governable.** Because the agent authors, tests, documents, and versions the flow itself, the same pattern scales to any fusion problem — with provenance, a quality gate, and an audit trail baked in, not bolted on.

**Bottom line:** v4 shows an agent taking a plain-English mission need and delivering a tested, self-documenting, fused intelligence product to the analyst's screen — compressing the EWOS decision loop while keeping every step transparent and auditable.
