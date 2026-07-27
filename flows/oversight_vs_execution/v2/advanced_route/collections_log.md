# Collections log — Oversight vs execution

## Pass 1 — internal scan (2026-07-24)

- Fed Register Actions (78) — F1 oversight proxy
- FedReg DoD (66) — F1 DoD subset
- DoD Award Detail (71) — F2 execution
- USASpending SLED Grants (68) — F2 execution

## Pass 1 — external acquisition

Re-pull Federal Register API for a broader 18mo window across ALL
executive agencies (not just DoD) so the resulting DS can be
sliced by agency in Tableau.

## Pass 1 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | Fed Reg count per agency |
| F1.2 | GREEN | Rule vs notice |
| F2.1 | GREEN | Dashboard-time |
| F2.2 | GREEN | Dashboard-time |
| F3.1 | GREEN | Tableau calc |
| F3.2 | GREEN | Tableau calc |
| F4.1 | **RED** | Congressional interest not on-site |

## Pass 2 — F4 gap-fill

Tried:

1. Congress.gov API — bill and member data available; no
   structured "agency oversight intensity" per-agency metric.
2. CRS reports — not indexed via any approved external host.

Decision: GRACEFUL DEGRADE. Reframe the DS as 'Fed Register
oversight signal vs execution volume' and clearly note that
Congressional pressure that hasn't materialized as a Fed Register
action is INVISIBLE in this view.

## Final status

6 GREEN + 1 RED (graceful degrade).

## Gap declaration (verbatim for DS description)

```
This DS surfaces Federal Register document velocity as an OVERSIGHT
PROXY across federal executive-branch agencies (18mo window). Use
in Tableau by joining to 'DoD Award Detail' + 'USASpending SLED
Grants' by month + agency for the execution side.

RED indicator (declared gap):
- F4.1 Congressional interest. Congress.gov API has bill / member
  data but no structured 'agency oversight intensity' metric per
  agency. CRS reports are not indexed via any approved external
  host. Effect on the answer: Congressional hearing pressure or
  investigative work that hasn't yet materialized as a Fed Register
  action is INVISIBLE in this view. This flow degrades gracefully
  by using Fed Register alone as the oversight proxy.

Divergence patterns from this DS are QUESTION-RAISERS, not
answers. Programs under oversight often SHOULD keep executing
(oversight is a process, not a stop). Analyst triage required.
```
