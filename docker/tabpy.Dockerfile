# TabPy sidecar for tableau-prep-etl-skill dev/demo.
#
# What this image is FOR:
#   - Running TabPy locally so Prep Builder / prep-cli on the host can
#     hit script nodes without polluting the host Python.
#   - Getting a new contributor to `curl http://localhost:9099/info`
#     with two commands (`docker compose up tabpy`).
#
# What this image is NOT for:
#   - Production. Production TabPy needs the auth config
#     (`~/Documents/Python/TabPy/tabpy.conf` + pwdfile). This image
#     ships the loopback-only unauth :9099 recipe that Claude uses
#     for local dev only.
#
# Pin to a stable slim base. TabPy pulls in numpy/pandas which take
# a while to build wheels on ARM; the -slim tag avoids the heaviest
# system libs but has wheels for most transitive deps.
FROM python:3.11-slim

# TabPy's own runtime deps (numpy/pandas/scikit — needed even if the
# user's script nodes don't call them, because TabPy imports numpy at
# server startup). Plus the skill's api_caller runtime deps so a script
# node that renders a spec-authored api_caller.py can just work.
RUN pip install --no-cache-dir \
        tabpy \
        pandas \
        certifi \
        requests \
        PyPDF2 \
        pdfplumber

# Non-root runtime user. TabPy doesn't need root and never should have it.
RUN useradd --create-home --shell /bin/bash tabpy
USER tabpy
WORKDIR /home/tabpy

# Config file. Bind loopback + long evaluate timeout to match the
# recipe in skill/reference/tabpy_setup.md.
RUN printf '%s\n' \
    '[TabPy]' \
    'TABPY_PORT = 9099' \
    'TABPY_BIND_IP = 0.0.0.0' \
    'TABPY_EVALUATE_TIMEOUT = 600' \
    > /home/tabpy/tabpy.conf

# NOTE on TABPY_BIND_IP inside a container: TabPy has to listen on
# 0.0.0.0 for docker's port mapping to reach the process from the
# host. The security perimeter comes from docker compose's port
# mapping — we only expose 127.0.0.1:9099 on the host. Setting
# BIND_IP=127.0.0.1 here would make the port unreachable from outside
# the container's own loopback, defeating the purpose.

EXPOSE 9099

CMD ["tabpy", "--config=/home/tabpy/tabpy.conf"]
