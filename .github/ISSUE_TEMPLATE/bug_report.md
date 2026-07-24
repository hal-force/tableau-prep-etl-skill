---
name: Bug report
about: Report an error, incorrect output, or unexpected behavior
title: "[bug] "
labels: bug
---

## What happened

<!-- One or two sentences. What did you expect, what did you get? -->

## Repro

<!-- Smallest spec.json or command that reproduces the issue.
     DO NOT paste PATs, API keys, or `~/.tableau-prep-etl/server.json` contents. -->

```json
{
  "sources": [...],
  "outputs": [...]
}
```

Command:

```sh
python3 -m skill.scripts.run_loop --spec ...
```

## Environment

- OS + version:
- Python:
- TabPy version:
- Tableau Prep Builder version (if publishing):
- Skill version / commit:

## Logs

<!-- Attach or paste the tail of `runtime/<run_id>/log.txt` and any
     hyperd.log excerpts. Redact anything sensitive. -->
