"""
Behavior tests for the WHS CX, listing-crawler, PDF-text and entity-extract
templates.

Each template is rendered the way `generate_flow._render_templates` renders
it (StrictUndefined + the `pyrepr` filter), `ast.parse`d, then exec'd with
stub `prep_*` helpers. Network, browser, OCR and spaCy are replaced with
in-process fakes, so nothing here needs TabPy, Chromium or a model.
"""
from __future__ import annotations

import ast
import asyncio
import sys
import types
from pathlib import Path

import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from skill.scripts.intake import Source, Spec, Transformation
from skill.scripts.source_planner import plan_sources


TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def _render(name: str, **tvars) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=False, undefined=StrictUndefined)
    env.filters["pyrepr"] = repr
    src = env.get_template(name).render(**tvars)
    ast.parse(src)
    return src


def _load(name: str, **tvars) -> dict:
    ns = {
        "__name__": "rendered_" + name.split(".")[0],
        "prep_string": lambda: ["string"],
        "prep_int": lambda: ["int"],
        "prep_decimal": lambda: ["decimal"],
    }
    exec(compile(_render(name, **tvars), name, "exec"), ns)
    return ns


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------

class _Resp:
    def __init__(self, status, body=b""):
        self.status = status
        self.ok = 200 <= status < 300
        self._body = body

    async def body(self):
        return self._body


class _FakePlaywright:
    """Stands in for async_playwright() and every object hanging off it
    (browser, context, page, request context). `pages` / `gets` map a URL
    to a list of scripted (status, html|bytes) responses, consumed in order;
    the last one repeats."""

    def __init__(self, pages=None, gets=None):
        self.pages = pages or {}
        self.gets = gets or {}
        self.goto_calls = []
        self.get_calls = []
        self._html = ""

    def _next(self, table, url):
        seq = table[url]
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def chromium(self):
        return self

    @property
    def request(self):
        return self

    async def launch(self, **kw):
        return self

    async def new_context(self, **kw):
        return self

    async def new_page(self):
        return self

    async def add_init_script(self, js):
        pass

    async def wait_for_timeout(self, ms):
        pass

    async def close(self):
        pass

    async def goto(self, url, **kw):
        self.goto_calls.append(url)
        status, self._html = self._next(self.pages, url) if url in self.pages else (200, "")
        return _Resp(status)

    async def content(self):
        return self._html

    async def get(self, url, **kw):
        self.get_calls.append(url)
        status, body = self._next(self.gets, url)
        return _Resp(status, body)


def _install_playwright(monkeypatch, fake):
    api = types.ModuleType("playwright.async_api")
    api.async_playwright = fake
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", api)


class _Ent:
    def __init__(self, text, start, label="PERSON"):
        self.text, self.start_char, self.end_char, self.label_ = text, start, start + len(text), label


class _FakeNLP:
    """spaCy stand-in: tags every occurrence of NAMES as PERSON and records
    how it was called."""
    NAMES = ("John Doe",)

    def __init__(self):
        self.pipe_calls = []
        self.call_count = 0

    def __call__(self, text):
        self.call_count += 1
        return self._doc(text)

    def pipe(self, texts, batch_size=None):
        texts = list(texts)
        self.pipe_calls.append(texts)
        return (self._doc(t) for t in texts)

    def _doc(self, text):
        ents = [_Ent(n, text.index(n)) for n in self.NAMES if n in text]
        return types.SimpleNamespace(ents=ents)


# ---------------------------------------------------------------------
# WHS CX core
# ---------------------------------------------------------------------

_WHS_HEADER = ["SubmissionID", "SubmissionDate", "AllComponents", "@15276", "@15278",
               "@15405", "@15375", "@15277", "InternalvsExternal", "NoServicesUsed",
               "@15268", "@15269", "@15281"]
#                          CSAT    NPS    WHS comment
_WHS_ROWS = {
    "p1.csv": [["S1", "14-Aug-24", "", "", "", "", "", "", "2", "1",
                "5", "11", "Mr. Smith was great, email a@b.com"],
               ["S2", "14-Aug-24", "", "", "", "", "", "", "2", "",
                "", "3", ""]],
    "p2.csv": [["S3", "14-Aug-25", "", "", "", "", "", "", "1", "2",
                "4.00", "9", "slow"],
               ["S4", "14-Aug-25", "", "", "", "", "", "", "1", "1",
                "2", "", "John Doe helped"]],
}


@pytest.fixture
def whs_inputs(tmp_path):
    import csv
    for fname, rows in _WHS_ROWS.items():
        with open(tmp_path / fname, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(_WHS_HEADER)
            w.writerows(rows)
    (tmp_path / "codebook.csv").write_text("a,b,c,d,e,f,g,h\n")
    return tmp_path


def _whs(variant, inputs_dir, use_ner=False, **over):
    tvars = dict(variant=variant, inputs_dir=str(inputs_dir),
                 period_files={"FY24": "p1.csv", "FY25": "p2.csv"},
                 codebook_file="codebook.csv", current_period="FY25",
                 prior_period="FY24", use_ner=use_ner)
    tvars.update(over)
    return _load(f"whs_{variant}.py.j2", **tvars)


TRIGGER = pd.DataFrame({"folder": ["RUN-1"]})


def test_whs_kpi_long_skips_blank_responses(whs_inputs):
    out = _whs("kpi_long", whs_inputs)["transform"](TRIGGER)
    # 4 respondents x (CSAT, NPS) minus S2's blank CSAT and S4's blank NPS.
    assert len(out) == 6
    assert out["ResponseValue"].notna().all()
    assert set(zip(out["SubmissionID"], out["KPI"])) == {
        ("S1", "CSAT"), ("S1", "NPS"), ("S2", "NPS"),
        ("S3", "CSAT"), ("S3", "NPS"), ("S4", "CSAT"),
    }
    assert (out["IsResponded"] == 1).all()


def test_whs_config_strings_survive_quotes_and_backslashes():
    # A trailing backslash broke the old r"..." literal; a quote broke "...".
    odd_dir = 'C:\\data\\it"s\\'
    ns = _whs("kpi_long", odd_dir,
              codebook_file='code"book.csv', current_period='FY"25', prior_period="FY'24")
    assert ns["INPUTS_DIR"] == odd_dir
    assert ns["CODEBOOK_FILE"] == 'code"book.csv'
    assert ns["CURRENT_PERIOD"] == 'FY"25'
    assert ns["PRIOR_PERIOD"] == "FY'24"
    assert ns["VARIANT"] == "kpi_long"


def test_whs_ner_fails_closed_when_model_missing(whs_inputs, monkeypatch):
    monkeypatch.setitem(sys.modules, "spacy", None)  # `import spacy` -> ImportError
    ns = _whs("comments", whs_inputs, use_ner=True)
    with pytest.raises(RuntimeError, match="en_core_web_sm"):
        ns["transform"](TRIGGER)


def test_whs_ner_errors_are_not_swallowed(whs_inputs):
    ns = _whs("comments", whs_inputs, use_ner=True)

    class Boom(_FakeNLP):
        def pipe(self, texts, batch_size=None):
            raise ValueError("ner exploded")

    ns["_NLP_CACHE"]["nlp"] = Boom()
    with pytest.raises(ValueError, match="ner exploded"):
        ns["transform"](TRIGGER)


def test_whs_comments_batch_ner_and_redact(whs_inputs):
    ns = _whs("comments", whs_inputs, use_ner=True)
    nlp = _FakeNLP()
    ns["_NLP_CACHE"]["nlp"] = nlp
    out = ns["transform"](TRIGGER).set_index("SubmissionID")
    assert len(nlp.pipe_calls) == 1 and nlp.call_count == 0  # one batched pass
    assert len(nlp.pipe_calls[0]) == 3
    assert out.at["S1", "CommentText"] == "[NAME] was great, email [EMAIL]"
    assert out.at["S1", "RedactionCount"] == 2
    assert out.at["S4", "CommentText"] == "[NAME] helped"
    assert out.at["S4", "RedactionCount"] == 1
    assert out.at["S3", "Sentiment"] == "Negative"


def test_whs_comments_regex_only_when_ner_off(whs_inputs, monkeypatch):
    monkeypatch.setitem(sys.modules, "spacy", None)  # must not even be imported
    out = _whs("comments", whs_inputs, use_ner=False)["transform"](TRIGGER).set_index("SubmissionID")
    assert out.at["S4", "CommentText"] == "John Doe helped"
    assert out.at["S1", "RedactionCount"] == 2


def test_whs_summary_reuses_upstream_kpi_long(whs_inputs, tmp_path):
    kpi_long = _whs("kpi_long", whs_inputs)["transform"](TRIGGER)
    rebuilt = _whs("summary", whs_inputs)["transform"](TRIGGER)
    # Point the reuse node at a directory with no files: it must not read them.
    reused = _whs("summary", tmp_path / "missing")["transform"](kpi_long)
    pd.testing.assert_frame_equal(reused.reset_index(drop=True), rebuilt.reset_index(drop=True))
    csat = reused[(reused.Directorate == "WHS") & (reused.KPI == "CSAT")].set_index("FY_Q")
    assert csat.at["FY24", "Score"] == 100.0
    assert csat.at["FY25", "Score"] == 50.0
    assert csat.at["FY25", "YoY_Delta"] == -50.0


def test_planner_hangs_whs_summary_off_kpi_long(tmp_path):
    spec = Spec(
        request="whs",
        sources=[Source(type="local_csv", path=str(tmp_path / "trigger.csv"), name="Trigger")],
        transformations=[Transformation(kind="whs_cx", args={
            "inputs_dir": str(tmp_path), "period_files": {"FY25": "p.csv"},
            "kpi_long_name": "KPI Long", "summary_name": "Summary"})],
    )
    plan = plan_sources(spec, outputs_dir=tmp_path)
    parents = {t.name: t.parent for t in plan.transforms if t.template.startswith("whs_")}
    assert parents["Summary"] == "KPI Long"
    assert parents["KPI Long"] == "@input"
    names = [t.name for t in plan.transforms]
    assert names.index("KPI Long") < names.index("Summary")


# ---------------------------------------------------------------------
# PDF text extract
# ---------------------------------------------------------------------

_PDF_VARS = dict(base_url="https://www.dnfsb.gov/list", pdf_url_col="pdf_url",
                 domains_allowlist=["dnfsb.gov"], browser_channel="chrome",
                 nav_timeout_ms=1000, request_timeout_ms=1000, settle_ms=0,
                 max_ocr_pages=8, ocr_dpi=100, max_text_chars=0,
                 catalog_schema={"doc_id": "string", "pdf_url": "string"})


def _pdf(**over):
    tvars = dict(_PDF_VARS)
    tvars.update(over)
    return _load("pdf_text_extract.py.j2", **tvars)


def test_pdf_refuses_empty_allowlist():
    with pytest.raises(RuntimeError, match="DOMAINS_ALLOWLIST is empty"):
        _pdf(domains_allowlist=[])


def test_planner_rejects_pdf_extract_without_allowlist(tmp_path):
    spec = Spec(request="pdf", sources=[Source(type="local_csv", path=str(tmp_path / "c.csv"))],
                transformations=[Transformation(kind="pdf_text_extract", args={})])
    with pytest.raises(ValueError, match="domains_allowlist"):
        plan_sources(spec, outputs_dir=tmp_path)


@pytest.fixture
def fake_ocr(monkeypatch):
    """Fake pdf2image (a doc of `total` pages) + pytesseract + pdfplumber."""
    state = types.SimpleNamespace(total=20, digital=None, convert_calls=[])

    def convert_from_bytes(_b, dpi=None, first_page=None, last_page=None):
        state.convert_calls.append((first_page, last_page))
        return ["p%d" % p for p in range(first_page, min(last_page, state.total) + 1)]

    class _Doc:
        def __enter__(self):
            digital = state.digital or [""] * state.total
            self.pages = [types.SimpleNamespace(extract_text=lambda t=t: t) for t in digital]
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setitem(sys.modules, "pdf2image",
                        types.SimpleNamespace(convert_from_bytes=convert_from_bytes))
    monkeypatch.setitem(sys.modules, "pytesseract",
                        types.SimpleNamespace(image_to_string=lambda img: "ocr-" + img))
    monkeypatch.setitem(sys.modules, "pdfplumber", types.SimpleNamespace(open=lambda _f: _Doc()))
    return state


def test_pdf_ocr_only_rasterizes_capped_pages(fake_ocr):
    ns = _pdf()
    # Scanned 20-page doc: OCR the first 8, flag the result partial.
    text, pages, method = ns["_extract"](b"%PDF")
    assert fake_ocr.convert_calls == [(1, 8)]
    assert text.split("\n") == ["ocr-p%d" % p for p in range(1, 9)]
    assert (pages, method) == (20, "ocr_partial")


def test_pdf_ocr_mixed_doc_targets_empty_pages_only(fake_ocr):
    ns = _pdf()
    fake_ocr.total = 12
    fake_ocr.digital = ["digital"] * 12
    fake_ocr.digital[2] = fake_ocr.digital[4] = fake_ocr.digital[10] = ""
    text, pages, method = ns["_extract"](b"%PDF")
    # Page index 10 is past the cap: not rasterized, result marked partial.
    assert fake_ocr.convert_calls == [(3, 5)]
    assert text.endswith("ocr-p3\nocr-p5")
    assert (pages, method) == (12, "mixed_partial")


def test_pdf_small_scanned_doc_is_not_partial(fake_ocr):
    fake_ocr.total = 3
    text, pages, method = _pdf()["_extract"](b"%PDF")
    assert (pages, method) == (3, "ocr")
    assert fake_ocr.convert_calls == [(1, 8)]


def test_pdf_fetch_retries_waf_and_server_errors(monkeypatch):
    pdf = b"%PDF-1.7 body"
    u = "https://www.dnfsb.gov/files/%s.pdf"
    fake = _FakePlaywright(gets={
        u % "403": [(403, b""), (200, pdf)],
        u % "429": [(429, b""), (200, pdf)],
        u % "500": [(500, b""), (503, b"")],
        u % "html": [(200, b"<html>challenge</html>")],
        u % "404": [(404, b""), (200, pdf)],
    })
    _install_playwright(monkeypatch, fake)
    ns = _pdf()
    handled = []
    out = asyncio.run(ns["_fetch"](list(fake.gets) + ["https://evil.example/x.pdf", ""],
                                   lambda b: handled.append(b) or "parsed"))
    assert out[u % "403"] == ("ok", "parsed", len(pdf), 200)
    assert out[u % "429"][0] == "ok"
    assert out[u % "500"][0] == "http_503"
    assert out[u % "html"][0] == "not_pdf"
    assert out[u % "404"][0] == "http_404"           # not retried
    assert fake.get_calls.count(u % "404") == 1
    assert out["https://evil.example/x.pdf"][0] == "blocked_host"
    assert out[""][0] == "no_pdf_url"
    assert handled == [pdf, pdf]


def test_pdf_extract_entrypoint_extracts_per_url(monkeypatch):
    pdf = b"%PDF-1.7 0123456789"
    url = "https://www.dnfsb.gov/files/a.pdf"
    fake = _FakePlaywright(gets={url: [(200, pdf)]})
    _install_playwright(monkeypatch, fake)
    ns = _pdf()
    ns["_extract"] = lambda body: ("hello", 2, "pdfplumber")
    out = ns["extract_pdf_text"](pd.DataFrame({"doc_id": ["a", "a2"], "pdf_url": [url, url]}))
    assert fake.get_calls == [url]                    # deduped
    assert list(out["full_text"]) == ["hello", "hello"]
    assert list(out["fetch_bytes"]) == [len(pdf)] * 2
    assert list(out["fetch_status"]) == ["ok", "ok"]


# ---------------------------------------------------------------------
# Listing crawler
# ---------------------------------------------------------------------

BASE = "https://www.dnfsb.gov/documents/reports"
_CRAWL_VARS = dict(base_url=BASE, page_param="page", per_page=1, max_reports=3,
                   max_reports_env="TEST_MAX_REPORTS", domains_allowlist=["dnfsb.gov"],
                   title_split_token=" Week Ending ", collection_label="RI Weekly",
                   browser_channel="chrome", nav_timeout_ms=1000, settle_ms=0,
                   catalog_schema={"doc_id": "string", "site": "string", "week_ending": "string",
                                   "pdf_url": "string", "listing_page": "int",
                                   "crawl_status": "string"})
_PAD = "<!-- " + "x" * 3000 + " -->"


def _listing(*ids):
    arts = "".join(
        f'<article><h2><a href="/r/{i}">Site {i} Week Ending August 14, 2026</a></h2>'
        f'<a href="/files/{i}.pdf">PDF</a></article>' for i in ids)
    return f"<html><body>{arts}{_PAD}</body></html>"


_BLOCKED = "<html>Access Denied. Reference #18.abc</html>"
_EMPTY_PAGE = f'<html><script src="https://cdn.akamai.example/x.js"></script>{_PAD}</html>'


def _crawler(monkeypatch, env=None):
    if env is None:
        monkeypatch.delenv("TEST_MAX_REPORTS", raising=False)
    else:
        monkeypatch.setenv("TEST_MAX_REPORTS", env)
    return _load("dnfsb_crawler.py.j2", **_CRAWL_VARS)


@pytest.mark.parametrize("env, expected", [(None, 3), ("", 3), ("  ", 3), (" 7 ", 7)])
def test_crawler_max_reports_env(monkeypatch, env, expected):
    assert _crawler(monkeypatch, env)["MAX_REPORTS"] == expected


@pytest.mark.parametrize("env, msg", [("abc", "not an integer"), ("2.5", "not an integer"),
                                      ("0", ">= 1"), ("-4", ">= 1")])
def test_crawler_max_reports_env_rejects_bad_values(monkeypatch, env, msg):
    with pytest.raises(RuntimeError, match=msg):
        _crawler(monkeypatch, env)


def test_crawler_block_on_later_page_raises(monkeypatch):
    ns = _crawler(monkeypatch)
    fake = _FakePlaywright(pages={BASE: [(200, _listing("a"))],
                                  BASE + "?page=1": [(200, _BLOCKED)]})
    _install_playwright(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="blocked on page 1 .* after 1 reports"):
        ns["crawl"](TRIGGER)
    assert fake.goto_calls.count(BASE + "?page=1") == 2  # one reload before giving up


def test_crawler_recovers_when_reload_clears_block(monkeypatch):
    ns = _crawler(monkeypatch)
    fake = _FakePlaywright(pages={BASE: [(200, _listing("a"))],
                                  BASE + "?page=1": [(403, _BLOCKED), (200, _listing("b"))],
                                  BASE + "?page=2": [(200, _listing("c"))]})
    _install_playwright(monkeypatch, fake)
    out = ns["crawl"](TRIGGER)
    assert list(out["doc_id"]) == ["a", "b", "c"]


def test_crawler_genuine_end_of_results_stops_quietly(monkeypatch):
    # The empty page mentions the CDN vendor in a script src; that alone
    # must not read as a block.
    ns = _crawler(monkeypatch)
    fake = _FakePlaywright(pages={BASE: [(200, _listing("a"))],
                                  BASE + "?page=1": [(200, _EMPTY_PAGE)]})
    _install_playwright(monkeypatch, fake)
    out = ns["crawl"](TRIGGER)
    assert list(out["doc_id"]) == ["a"]
    assert fake.goto_calls.count(BASE + "?page=1") == 1


def test_crawler_first_page_block_keeps_gui_hint(monkeypatch):
    ns = _crawler(monkeypatch)
    _install_playwright(monkeypatch, _FakePlaywright(pages={BASE: [(403, _BLOCKED)]}))
    with pytest.raises(RuntimeError, match="interactive GUI"):
        ns["crawl"](TRIGGER)


# ---------------------------------------------------------------------
# Entity extract
# ---------------------------------------------------------------------

_EE_VARS = dict(text_col="CommentText", id_col="SubmissionID", spacy_model="en_core_web_sm",
                entity_labels=[], passthrough=[["SubmissionID", "string"], ["FY_Q", "string"],
                                               ["SentimentScore", "decimal"], ["N", "int"]])


def test_entity_extract_raises_when_model_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "spacy", None)
    ns = _load("entity_extract.py.j2", **_EE_VARS)
    with pytest.raises(RuntimeError, match="en_core_web_sm"):
        ns["extract"](pd.DataFrame({"SubmissionID": ["S1"], "CommentText": ["John Doe"]}))


def test_entity_extract_empty_frame_matches_schema():
    ns = _load("entity_extract.py.j2", **_EE_VARS)
    out = ns["extract"](pd.DataFrame())
    assert len(out) == 0
    assert list(out.columns) == list(ns["get_output_schema"]().columns)
    dt = out.dtypes.astype(str).to_dict()
    assert dt["StartChar"] == dt["EndChar"] == dt["N"] == "int64"
    assert dt["SentimentScore"] == "float64"
    assert dt["EntityText"] == dt["FY_Q"] == dt["SubmissionID"] == "object"


def test_entity_extract_runs_with_model():
    ns = _load("entity_extract.py.j2", **_EE_VARS)
    ns["_NLP_CACHE"]["nlp"] = _FakeNLP()
    out = ns["extract"](pd.DataFrame({"SubmissionID": ["S1", "S2"], "FY_Q": ["FY25", "FY25"],
                                      "SentimentScore": [1, 0], "N": [3, 4],
                                      "CommentText": ["Ask John Doe", "nothing here"]}))
    assert list(out["EntityText"]) == ["John Doe"]
    assert (out.at[0, "StartChar"], out.at[0, "EndChar"]) == (4, 12)
