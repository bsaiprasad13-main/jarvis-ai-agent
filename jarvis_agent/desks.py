"""The agent spec: who the brief is for, its sections, and the desks that write them.

Everything here comes from jarvis.config.json, so a new agent (a different
reader, different sections, different sources) is a config change, not a
code change. Each desk is its own agent with a written contract: which sources
it owns, which sections it writes, and what "done" means for it. The harness
checks the contract in code.
"""
import json
import os
from dataclasses import dataclass

from .config import ROOT

with open(os.path.join(ROOT, "jarvis.config.json"), encoding="utf-8") as _f:
    SPEC = json.load(_f)

READER = SPEC["reader"]
TEST_QUESTION = SPEC["test_question"]
SECTION_TITLES = {k: v["title"] for k, v in SPEC["sections"].items()}
SECTION_BRIEFS = {k: v["brief"] for k, v in SPEC["sections"].items()}


@dataclass(frozen=True)
class Desk:
    key: str            # "global" / "india"
    title: str
    prefix: str         # item ids look like g12 / i7
    sources: tuple
    sections: tuple
    min_read: int       # picks that must be read in full (page fetched, with text) before a draft can pass
    max_items: int = 8
    min_items: int = 3  # aim; fewer is allowed only with an honest "quiet" note


DESKS = tuple(Desk(d["key"], d["title"], d["prefix"], tuple(d["sources"]), tuple(d["sections"]), d["min_read"],
                   d.get("max_items", 8), d.get("min_items", 3)) for d in SPEC["desks"])
GLOBAL, INDIA = DESKS[0], DESKS[1]
