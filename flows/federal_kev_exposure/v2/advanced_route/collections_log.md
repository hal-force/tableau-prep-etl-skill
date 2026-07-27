# Collections log — Federal KEV exposure

## Pass 1 — internal scan (2026-07-24)

- CISA KEV (score 96) — F1/F2/F3
- Fed Workforce (55) — F4 capacity proxy (dashboard join)
- NVD CVEs (41) — not required (KEV is the exploit subset)

## Pass 1 — external acquisition

- CISA KEV catalog JSON (public, keyless).
- BLS CES series pulled by the existing Fed Workforce flow — join
  at dashboard time.

## Pass 1 — indicator status

| Id | Status | Notes |
|---|---|---|
| F1.1 | GREEN | days_to_due derived |
| F1.2 | GREEN | overdue_flag derived |
| F1.3 | GREEN | exploit_sla_days derived |
| F2.1 | GREEN | knownRansomwareCampaignUse |
| F2.2 | GREEN | cwe_list from list_join |
| F3.1 | GREEN | trend_analysis stats |
| F3.2 | GREEN | trend_analysis stats |
| F4.1 | GREEN | Dashboard-time join |
| F5.1 | **RED** | Per-agency inventory not publicly available |

## Pass 2 — F5 gap-fill attempt

Tried:

1. CDM (Continuous Diagnostics and Mitigation) — per-agency
   inventory lives inside each agency's CDM. Not publicly exposed.
2. vulnrichment repo — provides SSVC / CISA enrichment metadata,
   not per-agency deployment.
3. FedRAMP marketplace — tells you which cloud services are
   authorized, not which specific products each agency runs.

Decision: DECLARE AS GAP. Reframe the DS to be an UPPER-BOUND
exposure ranking at the vendorProject/product level, with the F4
workforce capacity proxy layered on for triage.

## Pass 3 — n/a

## Final status

8 GREEN + 1 RED declared.

## Gap declaration (verbatim for DS description)

```
This data source addresses the question "Which KEV entries pose the
highest risk to federal-civilian agencies?" via 8 GREEN indicators
+ 1 RED (declared gap).

Scope:
- All active CISA KEV catalog entries with computed SLA pressure
  (days_to_due, overdue_flag, exploit_sla_days), ransomware-use
  flag, and CWE weakness classes.
- Federal workforce is joined at dashboard time from 'Fed Workforce'
  as a capacity proxy — larger workforce implies more sprawl to
  patch, not per-agency CVE presence.
- BOD 22-01 SLA scope is FCEB (Federal Civilian Executive Branch)
  only; DoD and IC have separate obligations.

RED indicator (declared gap):
- F5.1 Per-agency CVE inventory. This lives inside each agency's
  CDM (Continuous Diagnostics and Mitigation) system and is NOT
  publicly available. Effect on the answer: every ranking here is
  an UPPER-BOUND estimate at the vendorProject/product level, NOT
  a targeted per-agency assessment. A vulnerability in a product
  that no federal agency actually runs will still appear in this
  DS with a high SLA pressure score.

To fill this gap: partnership with CISA / CDM data access, or an
agency-specific SBOM feed. Neither is available via approved
external hosts as of the current scan.
```
