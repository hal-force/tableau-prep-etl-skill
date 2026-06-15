"""
Intake: parse a natural-language ETL request into a structured spec.json.

Calls the LLM gateway with a system prompt that demands a strict JSON
schema. Returns a `Spec` dataclass + writes spec.json to runtime/<run_id>/.

If confidence on any required field is low, raises `IntakeIncomplete`
with a list of clarification prompts the orchestrator should ask the
user via Claude's AskUserQuestion before retrying.

Public entry point: `intake(request: str, run_dir: Path) -> Spec`
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
from urllib import error, request as urlrequest

# Bootstrap tflb_lib + auto_refine import path
from skill.scripts.lib import _REPO_ROOT  # noqa: F401


GATEWAY_URL = os.environ.get(
    "LLM_GATEWAY_URL",
    "https://your-gateway.example.com/chat/completions",
)
GATEWAY_KEY = os.environ.get("LLM_GATEWAY_KEY", "")
GATEWAY_MODEL = os.environ.get("LLM_GATEWAY_MODEL", "claude-sonnet-4-6")
GATEWAY_VERIFY_SSL = False


SOURCE_TYPES = (
    "local_folder", "native_connector", "rest_api", "graphql_api",
    "web_crawl", "pki_endpoint",
)
QA_TIERS = ("none", "deterministic", "llm")
EVAL_STRATEGIES = (
    "extract_from_source", "sample_validation", "synthesized",
    "user_supplied", "self_consistency",
)


@dataclass
class Source:
    type: str
    path: str = ""             # filesystem path for local_folder
    url: str = ""              # for rest_api / graphql_api / web_crawl / pki_endpoint
    format: str = ""
    auth: str = "none"         # none | basic | oauth | client_cert | api_key
    extra: dict = field(default_factory=dict)


@dataclass
class Transformation:
    kind: str
    args: dict = field(default_factory=dict)


@dataclass
class Output:
    kind: str           # hyper | csv | published_data_source
    name: str           # output filename or DS name
    path: str = ""


@dataclass
class Spec:
    request: str
    sources: list[Source] = field(default_factory=list)
    transformations: list[Transformation] = field(default_factory=list)
    outputs: list[Output] = field(default_factory=list)
    qa_tier: str = "deterministic"
    eval_strategy: str = "sample_validation"
    deployment: str = "local"
    confidence: float = 0.0   # 0–1, LLM's self-reported confidence
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class IntakeIncomplete(RuntimeError):
    """Raised when the LLM's confidence is too low or required fields are missing.
    `questions` is a list of clarification prompts to surface to the user.
    """

    def __init__(self, message: str, questions: list[str]):
        super().__init__(message)
        self.questions = questions


SYSTEM_PROMPT = """You are an intake parser for a Tableau Prep ETL skill.
Convert the user's natural-language request into a strict JSON object.

Return ONLY a JSON object matching this schema:

{
  "sources": [
    {
      "type": "local_folder|native_connector|rest_api|graphql_api|web_crawl|pki_endpoint",
      "path": "<filesystem path or empty>",
      "url": "<URL or empty>",
      "format": "<source format hint, e.g. 'csv', 'json', 'pdf_portfolio', 'esri_feature_service'>",
      "auth": "none|basic|oauth|client_cert|api_key",
      "extra": {}
    }
  ],
  "transformations": [
    {"kind": "<verb>", "args": {}}
  ],
  "outputs": [
    {"kind": "hyper|csv|published_data_source", "name": "<filename>", "path": ""}
  ],
  "qa_tier": "none|deterministic|llm",
  "eval_strategy": "extract_from_source|sample_validation|synthesized|user_supplied|self_consistency",
  "deployment": "local",
  "confidence": 0.0,
  "open_questions": ["clarifying question 1", "..."]
}

Rules:
- Pick `eval_strategy` based on the source: local_folder of structured docs
  (PDFs with form fields, JSON with schemas) → extract_from_source.
  rest_api / graphql_api with stable schemas → sample_validation.
  web_crawl → synthesized. native_connector → sample_validation.
  pki_endpoint → sample_validation.
- Pick `qa_tier` 'llm' only when the user explicitly asks for QA review or
  the source is unstructured (PDFs, web). Use 'deterministic' for clean
  structured sources. Use 'none' only when the user says they want it.
- `confidence` should be 0.95 if every required field is unambiguous in
  the user's request, lower otherwise. If < 0.7, populate `open_questions`
  with the missing pieces.
- DO NOT invent paths or URLs the user didn't supply. Use empty string
  for unknowns and lower confidence accordingly.
- DO NOT include explanation, markdown fences, or any text outside the JSON.
"""


def _ssl_ctx() -> Optional[ssl.SSLContext]:
    try:
        return ssl.create_default_context() if GATEWAY_VERIFY_SSL else ssl._create_unverified_context()
    except Exception:
        return None


def _llm_chat(user_msg: str, max_retries: int = 3) -> str:
    """Send a single-turn message; return assistant text. Raises on failure."""
    if not GATEWAY_KEY or "your-gateway.example.com" in GATEWAY_URL:
        raise RuntimeError(
            "LLM gateway not configured. Set LLM_GATEWAY_URL and LLM_GATEWAY_KEY "
            "environment variables before running the intake step."
        )
    payload = {
        "model": GATEWAY_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    ctx = _ssl_ctx()
    attempt = 0
    while True:
        req = urlrequest.Request(GATEWAY_URL, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {GATEWAY_KEY}")
        req.add_header("Content-Type", "application/json")
        try:
            with urlrequest.urlopen(req, timeout=120, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"no choices in gateway response: {str(data)[:200]}")
                return (choices[0].get("message") or {}).get("content") or ""
        except (error.HTTPError, error.URLError, TimeoutError) as e:
            if attempt < max_retries:
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"gateway call failed after {max_retries} retries: {e}")


def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


def _parse_json(raw: str) -> dict:
    s = _strip_fence(raw)
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        s = m.group(0)
    return json.loads(s)


def _validate_spec(spec_dict: dict) -> list[str]:
    """Return a list of validation errors. Empty list = valid."""
    errors: list[str] = []

    sources = spec_dict.get("sources") or []
    if not sources:
        errors.append("at least one source required")
    for i, s in enumerate(sources):
        if s.get("type") not in SOURCE_TYPES:
            errors.append(f"source[{i}].type must be one of {SOURCE_TYPES}")

    if spec_dict.get("qa_tier") not in QA_TIERS:
        errors.append(f"qa_tier must be one of {QA_TIERS}")
    if spec_dict.get("eval_strategy") not in EVAL_STRATEGIES:
        errors.append(f"eval_strategy must be one of {EVAL_STRATEGIES}")

    outputs = spec_dict.get("outputs") or []
    if not outputs:
        errors.append("at least one output required")

    return errors


def intake(request: str, run_dir: Path) -> Spec:
    """Parse a user request into a Spec. Writes spec.json to run_dir.

    Raises IntakeIncomplete if the LLM's confidence < 0.7. Caller should
    surface the open_questions to the user via AskUserQuestion and retry
    with the augmented request.
    """
    raw = _llm_chat(request)
    parsed = _parse_json(raw)

    errors = _validate_spec(parsed)
    if errors:
        raise IntakeIncomplete(
            f"intake validation failed: {'; '.join(errors)}",
            questions=parsed.get("open_questions") or [
                "Could you clarify the data source(s) and the desired output format?"
            ],
        )

    confidence = float(parsed.get("confidence") or 0.0)
    open_qs = parsed.get("open_questions") or []
    if confidence < 0.7:
        raise IntakeIncomplete(
            f"intake confidence {confidence:.2f} below 0.7 threshold",
            questions=open_qs or [
                "Could you provide more detail about the source location and format?"
            ],
        )

    spec = Spec(
        request=request,
        sources=[Source(**s) for s in parsed["sources"]],
        transformations=[Transformation(**t) for t in (parsed.get("transformations") or [])],
        outputs=[Output(**o) for o in parsed["outputs"]],
        qa_tier=parsed["qa_tier"],
        eval_strategy=parsed["eval_strategy"],
        deployment=parsed.get("deployment", "local"),
        confidence=confidence,
        open_questions=open_qs,
    )

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "spec.json").write_text(json.dumps(spec.to_dict(), indent=2))
    return spec


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("request", help="The user's ETL request (natural language)")
    ap.add_argument("--run-dir", required=True, help="Per-run scratch directory")
    args = ap.parse_args()
    try:
        spec = intake(args.request, Path(args.run_dir))
        print(json.dumps(spec.to_dict(), indent=2))
    except IntakeIncomplete as e:
        print(f"INTAKE INCOMPLETE: {e}", file=sys.stderr)
        for q in e.questions:
            print(f"  - {q}", file=sys.stderr)
        sys.exit(2)
