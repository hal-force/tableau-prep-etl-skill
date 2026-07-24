# docker/

Optional docker-compose stack for local development. The native macOS
recipe in the top-level README is still the primary path — this exists
so a Linux contributor can get TabPy + the skill's Python env running
without touching their host Python.

## What you get

- `tabpy` service — unauth TabPy on `127.0.0.1:9099`, matching the
  loopback-only recipe in `skill/reference/tabpy_setup.md`. Runs as a
  non-root user; `TABPY_EVALUATE_TIMEOUT=600` for slow script nodes.
- `skill` service — Python 3.11 with `requirements.txt` installed and
  the repo bind-mounted at `/workspace`. Use for spec validation,
  tests, `generate_flow`, `run_loop --skip-cli` — anything that
  doesn't need the (macOS-only) Tableau Prep CLI binary.

## Not included, and why

- **No Tableau Prep CLI.** Proprietary macOS-only binary. Any workflow
  that needs `--skip-cli` off has to run on a Mac host.
- **No production TabPy.** This image ships zero auth config. Your
  production TabPy needs a pwdfile — set that up on a real host, not
  in this container.
- **No creds.** `LLM_GATEWAY_URL`/`_KEY` etc. come from the host env
  or a `.env` file next to `docker-compose.yml`. Nothing is baked into
  the images.

## Quickstart

```sh
# From the repo root:
docker compose -f docker/docker-compose.yml up -d tabpy
curl http://localhost:9099/info                            # sanity check

docker compose -f docker/docker-compose.yml run --rm skill \
    python3 -m pytest -q skill/tests                        # 118 tests

docker compose -f docker/docker-compose.yml run --rm skill \
    python3 -m skill.scripts.generate_flow \
        --spec flows/fed_outlays/v1/spec.json \
        --out-dir /tmp/build --flow-name fed_outlays

docker compose -f docker/docker-compose.yml down            # tear down
```

## Ports + security posture

The TabPy container's `9099` is published to `127.0.0.1:9099` on the
host — NOT `0.0.0.0`. Anyone on your LAN who could hit the host's
external interface cannot reach TabPy. Inside the docker network,
the `skill` service reaches TabPy at `tabpy:9099` via docker's DNS.

If your host is a shared dev box, treat the loopback binding as a
must-keep. If it's your personal laptop, it's still a good default.
