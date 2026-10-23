"""
Codebook tests for the embassy threat-join template.

The rendered-script golden hash only proves the output didn't change; a
re-bless after any edit would accept a wrong CAMEO label. These tests pin
the labels against the CAMEO 1.1b3 codebook, including the ones corrected
in the advanced-route worked example (175, 176, 181, 133-138).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined


TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

_TVARS = dict(
    radius_miles=50, lookback_days=7, cameo_root_codes=["13", "14", "17", "18", "19", "20"],
    lat_col="ActionGeo_Lat", lon_col="ActionGeo_Long", date_col="SQLDATE",
    event_root_col="EventRootCode", event_code_col="EventCode",
    goldstein_col="GoldsteinScale", actor1_country_col="Actor1CountryCode",
    actor2_country_col="Actor2CountryCode", actor1_name_col="Actor1Name",
    actor2_name_col="Actor2Name", action_geo_full_col="ActionGeo_FullName",
    num_mentions_col="NumMentions", source_url_col="SOURCEURL", input_schema={},
)


@pytest.fixture(scope="module")
def ns():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=False, undefined=StrictUndefined)
    env.filters["pyrepr"] = repr
    src = env.get_template("embassy_threat_join.py.j2").render(**_TVARS)
    ast.parse(src)
    out = {"__name__": "rendered_embassy_threat_join",
           "prep_string": lambda: ["string"], "prep_int": lambda: ["int"],
           "prep_decimal": lambda: ["decimal"]}
    exec(compile(src, "embassy_threat_join.py", "exec"), out)
    return out


@pytest.mark.parametrize("code,label", [
    ("175", "used violent repression against"),
    ("176", "carried out a cyberattack on"),
    ("181", "abducted, hijacked or took hostage"),
    ("133", "threatened political dissent or protest against"),
    ("134", "threatened to halt negotiations with"),
    ("135", "threatened to halt mediation with"),
    ("136", "threatened to halt international involvement with"),
    ("137", "threatened repression against"),
    ("138", "threatened military force against"),
])
def test_codebook_labels(ns, code, label):
    assert ns["_CAMEO_EVENT_LABEL"][code] == label


@pytest.mark.parametrize("code,root,verb", [
    ("179", "17", "coerced"),
    ("199", "19", "used conventional force against"),
    ("209", "20", "used unconventional mass violence against"),
    ("", "18", "assaulted"),
    ("999", "99", "engaged with"),
])
def test_unknown_code_falls_back_to_a_root_verb(ns, code, root, verb):
    label = ns["_event_label"](code, root, ns["_CAMEO_SEVERITY"].get(root, (0, ""))[1])
    assert label == verb
    assert not label.endswith("eed")


def test_four_digit_leaf_falls_back_to_its_base(ns):
    assert ns["_event_label"]("1759", "17", "Coerce") == ns["_CAMEO_EVENT_LABEL"]["175"]
