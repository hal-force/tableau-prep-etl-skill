# Skill runner image — everything a spec.json -> flow.tfl build needs
# EXCEPT the Tableau Prep CLI binary, which is macOS-only and can't be
# containerised. Use this image for `generate_flow` / `run_loop --skip-cli`
# style operations, connector cache seeding, and CI-style spec validation.
#
# amd64 pin: `tableauhyperapi` publishes wheels for linux/amd64 only —
# no aarch64 build. On Apple Silicon hosts docker will run this under
# Rosetta emulation. Slower to build (one-time cost) but users get the
# full skill including Hyper reads/writes.
FROM --platform=linux/amd64 python:3.11-slim

# Build tools for the few wheels that don't publish arm64 binaries.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Two-step deps: system reqs first (cache-friendly), skill code last.
# pytest / Faker are dev-time deps — pinned here so a fresh container
# can immediately run the test suite. Faker is also declared optional
# in requirements.txt so the archive path can use it; we install it
# eagerly here to keep the image self-contained.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt pytest

# Non-root runtime user with a real HOME so the connector cache lands
# somewhere writable.
RUN useradd --create-home --shell /bin/bash skill
USER skill
ENV HOME=/home/skill
ENV PYTHONPATH=/workspace
# Point the connector cache at a per-user location inside HOME so it
# survives container restarts if HOME is a volume.
ENV TABLEAU_PREP_ETL_CONNECTOR_CACHE=/home/skill/.tableau-prep-etl/connectors

# The compose file bind-mounts the repo into /workspace so edits from
# the host land inside instantly. No COPY of the source tree here.

CMD ["python3", "-m", "skill.scripts.spec_validation", "--help"]
