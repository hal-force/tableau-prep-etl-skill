# SAT brief — Federal KEV exposure (RED-path demo)

## Step 1.1 — Question decomposition

Original:
> "Which federal agencies are most exposed to known-exploited
> vulnerabilities in their tech stack, given the current KEV catalog,
> upcoming BOD 22-01 SLA dates, and workforce load?"

Refined:
> **Across the CISA KEV catalog's active entries, which
> vendorProject / product combinations are highest-risk for
> federal-civilian agencies given (a) days-remaining on the BOD
> 22-01 SLA due date, (b) knownRansomwareCampaignUse, (c) CWE
> weakness class, and (d) the FCEB agency's workforce load as a
> capacity proxy — noting explicitly that per-agency CVE
> inventory data is NOT public and must be declared as a RED gap?**

## Step 1.2 — Key Assumptions Check

- ⚠ **This is the canonical RED-path demo.** The right answer to
  the question requires per-agency CVE inventory (which agency runs
  which product/version). That data does NOT exist publicly — it
  lives in each agency's CDM (Continuous Diagnostics and
  Mitigation) system. We CANNOT get it from an approved external
  host. Declared as RED and the answer is reframed accordingly.
- **Reframed answer:** rank vendorProject / product combinations
  by their SLA + ransomware + CWE risk, then surface aggregate
  federal workforce as a capacity indicator (large-workforce
  agencies face more sprawl / more infra to patch).
- **"Federal exposure" without per-agency inventory is a
  UPPER-BOUND estimate**, not a targeted assessment.
- KEV catalog is the authoritative external ground truth for
  exploited CVEs; refresh: at least daily on CISA's side.
- BOD 22-01 SLA due dates apply to FCEB agencies only (executive
  civilian branch); DoD and IC have separate obligations.

## Step 1.3 — Factors

- **F1. Exploit SLA pressure.** Days remaining until dueDate from
  today; overdue counts.
- **F2. Weaponization intensity.** knownRansomwareCampaignUse
  ("Known" vs "Unknown"), CWE class severity.
- **F3. Catalog velocity.** Rate of new KEV additions in the last
  30/90 days per vendorProject.
- **F4. Workforce load (capacity proxy).** Federal civilian
  employment counts from BLS CES.
- **F5. Per-agency CVE inventory.** RED — not available.

## Step 1.4 — Indicators

| Id | Factor | Indicator | Window |
|---|---|---|---|
| F1.1 | F1 | days_to_due (dueDate - today) | current |
| F1.2 | F1 | overdue_flag (dueDate < today) | current |
| F1.3 | F1 | exploit_sla_days (dueDate - dateAdded) | current |
| F2.1 | F2 | knownRansomwareCampaignUse boolean | current |
| F2.2 | F2 | cwe_list top class | current |
| F3.1 | F3 | 30d new-KEV count per vendorProject | 30d |
| F3.2 | F3 | 90d rolling KEV additions per vendorProject | 90d |
| F4.1 | F4 | Federal civilian employment (BLS CES) | latest month |
| F5.1 | F5 | (RED — declared as gap) | — |

## Acceptance criteria

- KEV catalog: ≥1000 total entries, ≥90% populated on dueDate.
- BLS CES: series returns non-empty for CES9091000001 (Federal
  civilian) within the last 60 days.

## Out-of-scope

- Per-agency inventory (RED gap).
- CVSS scores / EPSS enrichment (separate DS if needed later).
- IC and DoD-specific patching (BOD 22-01 is FCEB-scope).
- Real-time exploit-attempt telemetry.

## What "good" looks like

Two DSes on Cloud:

- **Federal KEV Exposure Detail** — one row per KEV entry with
  F1/F2/F3 indicators + tooltip. Explicitly notes RED F5 gap in the
  description.
- **Federal KEV Exposure Stats** — long-form vendor rollup for
  trend / anomaly views.
