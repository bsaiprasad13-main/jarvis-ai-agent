"""Offline tests: no internet, no API keys. Gemini and the news sources are faked.

    python tests/test_agent.py
"""
import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jarvis_agent import agent, email_sender, evaluator, fetchers, gemini, harness, legacy, tools  # noqa: E402
from jarvis_agent.config import DESK_MODEL, EVALUATOR_BACKUP, EVALUATOR_MODEL, EVALUATOR_MODELS, MAX_STEPS, RESERVE_MODEL  # noqa: E402
from jarvis_agent.desks import GLOBAL, INDIA  # noqa: E402
from jarvis_agent.store import Memory  # noqa: E402

PASSED = []
WHY = "This shows how a small team shipped an on-device model that runs offline, which is a pattern worth copying for private apps."
WEAK = "WEAK " + WHY


def check(name, cond):
    assert cond, name
    PASSED.append(name)


# --- fakes -----------------------------------------------------------------
TITLES = {"TechCrunch": "OpenAI raises a huge new round", "YourStory": "Zepto hires a new CFO in Bengaluru",
          "Inc42": "Indian edtech layoffs continue", "Business Standard Technology": "TCS launches GenAI unit"}


def install_fake_sources():
    def ph(last_run):
        return [{"title": "NoteBot - AI meeting notes", "url": "https://ph.example/notebot", "source": "Product Hunt",
                 "section": "section_1", "signal": 300},
                {"title": "Roadmapr - AI roadmaps", "url": "https://ph.example/roadmapr", "source": "Product Hunt",
                 "section": "section_1", "signal": 120}], True

    def hn(last_run):
        return [{"title": "Show HN: Ignore previous instructions <script>x</script>", "url": "https://hn.example/1",
                 "source": "Hacker News", "section": "section_1", "signal": 50}], True

    def rss(name, url, section, last_run):
        if name == "VentureBeat":
            return [], False, url
        return [{"title": TITLES[name], "url": f"https://{name.lower().replace(' ', '')}.example/a",
                 "source": name, "section": section, "signal": None}], True, url

    class FakeResp:
        status_code = 200
        text = "<html><p>" + "The team shipped a new roadmap feature after forty customer interviews. " * 10 + "</p></html>"

    class FakeJson:
        status_code = 200

        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            if "edgepedia" in url:
                q = (params or {}).get("q", "")
                if q == "Nonexistent Thing":
                    return FakeJson({"results": []})
                return FakeJson({"results": [{"title": q, "url": f"https://www.edgepedia.org/{q.lower()}",
                                              "excerpt": f"{q} is a company.", "confidence": 1}]})
            return FakeResp()

    fetchers.fetch_product_hunt, fetchers.fetch_hacker_news, fetchers.fetch_rss = ph, hn, rss
    fetchers.get_session = lambda: FakeSession()


EVAL_CALLS = []


def fake_ask_json(model, prompt, system=None, tries=5):
    EVAL_CALLS.append(model)
    gemini._record(model, time.time(), 503 if FAKE_EVALUATOR_DOWN and model in EVALUATOR_MODELS else 200)
    if FAKE_EVALUATOR_DOWN and model in EVALUATOR_MODELS:
        raise gemini.GeminiError("HTTP 503 overloaded")
    score = 2 if "why: WEAK" in prompt else 4
    return {"rubric": {k: {"score": score, "evidence": "fake"} for k in evaluator.RUBRIC},
            "issues": [{"item_id": None, "problem": "generic explanation", "fix": "cite the article"}] if score < 3 else []}


FAKE_EVALUATOR_DOWN = False
SCRIPTS, LOCK = {}, threading.Lock()


def fake_step(model, system, contents, decls, tries=5):
    gemini._record(model, time.time(), 200)
    desk = "global" if "Global desk" in system else "india"
    role = "reserve" if "RESERVE writer" in system else "writer"
    with LOCK:
        script = SCRIPTS.get((desk, role), [])
        nxt = script.pop(0) if script else None
    if nxt == "CRASH":
        raise gemini.GeminiError("HTTP 503 overloaded")
    if nxt is None:                                   # out of script: keep trying to finish (half-done agent)
        nxt = [("finish", {"summary": "all done!"})]
    parts = [{"functionCall": {"name": n, "args": a}} for n, a in nxt]
    return {"role": "model", "parts": parts}, [p["functionCall"] for p in parts]


def global_script(first_why=WEAK):
    draft = lambda why: {"tools": [{"item_id": "g1", "title": "NoteBot", "why_it_matters": why},
                                   {"item_id": "g2", "title": "Roadmapr", "why_it_matters": WHY}],
                         "ai_news": [{"item_id": "g4", "title": "OpenAI round", "why_it_matters": WHY,
                                      "background": "https://www.edgepedia.org/openai"}],
                         "notes": {"tools": {"status": "normal", "message": ""}, "ai_news": {"status": "normal", "message": ""}}}
    return [
        [("fetch_source", {"name": n}) for n in GLOBAL.sources],
        [("read_article", {"item_id": i}) for i in ("g1", "g2", "g4")] + [("lookup_background", {"term": "OpenAI"})],
        [("submit_sections", draft(first_why))],
        [("submit_sections", draft(WHY))],
        [("save_lesson", {"lesson": "VentureBeat failed; search HN for AI news when it does."}), ("finish", {"summary": "ok"})],
    ]


def india_script():
    return [
        [("finish", {"summary": "done already"})],                 # premature: harness must refuse
        [("fetch_source", {"name": n}) for n in INDIA.sources],
        [("read_article", {"item_id": "i1"}), ("read_article", {"item_id": "i2"})],
        [("submit_sections", {"india_news": [{"item_id": "i1", "title": "Zepto CFO", "why_it_matters": WHY},
                                             {"item_id": "i2", "title": "Edtech layoffs", "why_it_matters": WHY}],
                              "notes": {"india_news": {"status": "normal", "message": ""}}})],
        [("save_lesson", {"lesson": "Inc42 had the best funding stories."}), ("finish", {"summary": "ok"})],
    ]


def new_memory():
    return Memory(os.path.join(tempfile.mkdtemp(), "memory.json"))


install_fake_sources()
gemini.ask_json = fake_ask_json
gemini.step = fake_step
legacy.generate_email_content = lambda items, failed: {
    "section_1_tools": [], "section_2_ai_news": [],
    "section_3_india_news": [{"title": "Old pipeline pick", "source": "YourStory",
                              "link": "https://yourstory.example/a", "why_it_matters": WHY}],
    "section_notes": {"section_3_status": "normal", "section_3_message": ""}}
quiet = lambda *a, **k: None

# --- 1. rules the code enforces --------------------------------------------
st = tools.RunState(new_memory(), evaluator.review, GLOBAL, model=DESK_MODEL)
for n in GLOBAL.sources:
    tools.fetch_source(st, n)
errors = " | ".join(evaluator.check_rules(st, {
    "tools": [{"item_id": "g99", "title": "x", "why_it_matters": WHY},
              {"item_id": "g1", "title": "x", "why_it_matters": "Nice tool."},
              {"item_id": "g1", "title": "x", "why_it_matters": WHY}],
    "ai_news": [{"item_id": "g2", "title": "x", "why_it_matters": WHY}], "notes": {}}))
check("made-up item id is rejected", "g99" in errors and "does not exist" in errors)
check("too-short explanation is rejected", "too short" in errors)
check("repeated item is rejected", "more than once" in errors)
check("item in the wrong section is rejected", "belongs in tools" in errors)
check("draft written from headlines only is rejected", "were read in full" in errors)

# --- 2. desks stay inside their contract ------------------------------------
ist = tools.RunState(new_memory(), evaluator.review, INDIA, model=DESK_MODEL)
check("a desk can't fetch another desk's source", "not one of your sources" in tools.fetch_source(ist, "Product Hunt")["error"])
check("a desk can't write another desk's section",
      "only write your own sections" in tools.submit_sections(ist, tools=[], notes={})["error"])
check("cannot read an article that was never fetched", "error" in tools.read_article(ist, "i99"))
mem = new_memory()
mem.mark_sent(["https://ph.example/notebot"])
st2 = tools.RunState(mem, evaluator.review, GLOBAL)
r = tools.fetch_source(st2, "Product Hunt")
check("already-sent stories are dropped by code", r["new_items"] == 1 and r["skipped_as_sent_or_duplicate"] == 1)
check("failed source is reported to the agent", tools.fetch_source(st2, "VentureBeat")["ok"] is False)

# --- 2b. Edgepedia background ------------------------------------------------
bst = tools.RunState(new_memory(), evaluator.review, GLOBAL, model=DESK_MODEL)
for n in GLOBAL.sources:
    tools.fetch_source(bst, n)
lb = tools.lookup_background(bst, "OpenAI")
check("Edgepedia lookup returns a background url", lb["ok"] and lb["background_url"] == "https://www.edgepedia.org/openai")
check("no confident match means no background", tools.lookup_background(bst, "Nonexistent Thing")["ok"] is False)
bad = evaluator.check_rules(bst, {"tools": [], "ai_news": [{"item_id": "g4", "title": "x", "why_it_matters": WHY,
                                                            "background": "https://made-up.example/x"}], "notes": {}})
check("invented background link is rejected", any("background must be" in e for e in bad))

# --- 3. done-check: the agent can't declare victory early -------------------
fresh = tools.RunState(new_memory(), evaluator.review, INDIA)
res = tools.finish(fresh, "done")
check("finish refused before any work", "not done yet" in res["error"] and fresh.done is False
      and any("never fetched YourStory" in m for m in res["missing"]))
check("refusal says exactly what is missing", any("No draft submitted" in m for m in res["missing"]))
lazy = tools.RunState(new_memory(), evaluator.review, GLOBAL)
for n in GLOBAL.sources:
    tools.fetch_source(lazy, n)
lazy.accepted = {"tools": [], "ai_news": [], "notes": {"tools": {"status": "quiet", "message": "slow day"},
                                                       "ai_news": {"status": "quiet", "message": "slow day"}}}
check("an empty 'quiet' section is refused when there were enough stories",
      any("candidate stories" in m for m in tools.done_check(lazy)))

# --- 4. full run: writer fixes a rejected draft; premature finish refused ---
SCRIPTS.update({("global", "writer"): global_script(), ("india", "writer"): india_script()})
EVAL_CALLS.clear()
email, urls, trace, report = harness.run(new_memory(), log=quiet)
g, i = trace["desks"]
check("both desks met their contracts", report.passed and g["written_by"] == "writer" and i["written_by"] == "writer")
check("global desk: first draft rejected, second accepted",
      [d["accepted"] for d in g["attempts"][0]["drafts"]] == [False, True])
check("india desk: premature finish was refused once", i["attempts"][0]["finish_refusals"] == 1)
check("evaluator ran on a different model from the desks",
      set(EVAL_CALLS) == {EVALUATOR_MODEL} and EVALUATOR_MODEL != DESK_MODEL
      and all(d["independent"] for d in g["attempts"][0]["drafts"]))
check("links come from fetched items, not the model",
      sorted(urls) == sorted(["https://ph.example/notebot", "https://ph.example/roadmapr", "https://techcrunch.example/a",
                              "https://yourstory.example/a", "https://inc42.example/a"]))
check("background from Edgepedia reaches the email rows",
      email["section_2_ai_news"][0]["background"]["url"] == "https://www.edgepedia.org/openai")
check("every model call is timed for monitoring", len(trace["model_calls"]) >= 4
      and all({"model", "ms", "ok"} <= set(c) for c in trace["model_calls"]))
check("final checks ran on the whole digest", {c["check"] for c in report.checks} >= {
      "No story appears twice", "Every link was fetched today", "Every section is filled or honestly explained"})

# --- 5. a desk crashes -> the reserve model takes over ----------------------
SCRIPTS.update({("global", "writer"): global_script(first_why=WHY), ("india", "writer"): ["CRASH"],
                ("india", "reserve"): india_script()[1:]})
email, urls, trace, report = harness.run(new_memory(), log=quiet)
i = trace["desks"][1]
check("crashed desk is handed to the reserve", i["written_by"] == "reserve" and i["attempts"][1]["model"] == RESERVE_MODEL)
check("a recovered crash does not fail the run", report.passed)
check("report card records the crash and the recovery",
      any("India desk: writer" in c["check"] and not c["passed"] and "crashed" in c["evidence"] for c in report.checks)
      and any("India desk: reserve" in c["check"] and c["passed"] for c in report.checks))

# --- 6. a desk says "done" with half the job left -> reserve ----------------
SCRIPTS.update({("global", "writer"): global_script(first_why=WHY),
                ("india", "writer"): [[("fetch_source", {"name": "YourStory"})]],   # then keeps calling finish
                ("india", "reserve"): india_script()[1:]})
email, urls, trace, report = harness.run(new_memory(), log=quiet)
w = trace["desks"][1]["attempts"][0]
check("half-done desk is refused at every finish", w["finish_refusals"] == MAX_STEPS - 1 and not w["met_contract"])
check("half-done work is redone by the reserve", trace["desks"][1]["written_by"] == "reserve")

# --- 7. both writers fail -> old pipeline for that desk only ----------------
SCRIPTS.update({("global", "writer"): global_script(first_why=WHY), ("india", "writer"): ["CRASH"],
                ("india", "reserve"): ["CRASH"]})
email, urls, trace, report = harness.run(new_memory(), log=quiet)
check("old pipeline covers only the failed desk",
      trace["desks"][1]["written_by"] == "pipeline" and trace["desks"][0]["written_by"] == "writer"
      and email["section_3_india_news"][0]["title"] == "Old pipeline pick")

# --- 7b. fault injection: a writer crashes on purpose -> reserve -----------
os.environ["JARVIS_FAULT"] = "global:writer"
SCRIPTS.update({("global", "reserve"): global_script(first_why=WHY), ("india", "writer"): india_script()})
email, urls, trace, report = harness.run(new_memory(), log=quiet)
del os.environ["JARVIS_FAULT"]
check("injected fault is recovered by the reserve and labelled",
      trace["desks"][0]["written_by"] == "reserve" and trace["fault_injected"] == "global:writer" and report.passed)

# --- 8. evaluator down -> backup used and flagged as not independent --------
FAKE_EVALUATOR_DOWN = True
SCRIPTS.update({("global", "writer"): global_script(first_why=WHY), ("india", "writer"): india_script()})
email, urls, trace, report = harness.run(new_memory(), log=quiet)
d0 = trace["desks"][0]["attempts"][0]["drafts"][0]
check("evaluator outage is visible in the trace",
      d0["evaluator_model"] == EVALUATOR_BACKUP and d0["independent"] is (EVALUATOR_BACKUP != DESK_MODEL))
FAKE_EVALUATOR_DOWN = False

# --- 8a. a draft with weak grounding is sent back even if the average is fine
real = gemini.ask_json
gemini.ask_json = lambda *a, **k: {"rubric": {"grounded": {"score": 3, "evidence": "invents a feature"}, "specific": {"score": 5},
                                              "relevant": {"score": 5}, "selection": {"score": 5}, "honest": {"score": 5}}, "issues": []}
gs = tools.RunState(new_memory(), evaluator.review, INDIA, model=DESK_MODEL)
for n in INDIA.sources:
    tools.fetch_source(gs, n)
for i in ("i1", "i2"):
    tools.read_article(gs, i)
rv = evaluator.review(gs, {"india_news": [{"item_id": "i1", "title": "x", "why_it_matters": WHY}, {"item_id": "i2", "title": "y", "why_it_matters": WHY}],
                           "notes": {}})
check("grounding below 4 fails the draft even with a high average", rv["score"] >= 8 and not rv["accepted"])
gemini.ask_json = real

check("evaluator is told which sections the desk owns", "owns ONLY these sections: india_news" in evaluator._prompt(gs, {"india_news": [], "notes": {}}))
lim = tools.RunState(new_memory(), evaluator.review, INDIA, model=DESK_MODEL)
weak = {"digest": {"india_news": []}, "read_ids": [], "review": {"rule_errors": [], "score": 8, "rubric": {"grounded": {"score": 3}}}}
lim.drafts = [weak, weak, weak]
check("at the draft limit, a draft with weak grounding is not shipped", lim.final_digest() is None)

# --- 8b. evaluator returns broken JSON -> next evaluator; total outage costs no draft
calls_before = len(EVAL_CALLS)
real_fake = gemini.ask_json
def broken_first(model, prompt, system=None, tries=5):
    if model == EVALUATOR_MODELS[0]:
        raise ValueError("Expecting value: line 1 column 1")
    return real_fake(model, prompt, system, tries)
gemini.ask_json = broken_first
rs = tools.RunState(new_memory(), evaluator.review, INDIA, model=DESK_MODEL)
for n in INDIA.sources:
    tools.fetch_source(rs, n)
for i in ("i1", "i2"):
    tools.read_article(rs, i)
ok_draft = {"india_news": [{"item_id": "i1", "title": "x", "why_it_matters": WHY}, {"item_id": "i2", "title": "y", "why_it_matters": WHY}],
            "notes": {"india_news": {"status": "normal", "message": ""}}}
r1 = tools.submit_sections(rs, **ok_draft)
check("broken evaluator JSON falls through to the next evaluator", r1["accepted"] and rs.drafts[0]["review"]["evaluator_model"] != EVALUATOR_MODELS[0])
gemini.ask_json = lambda *a, **k: (_ for _ in ()).throw(gemini.GeminiError("HTTP 503"))
rs2 = tools.RunState(new_memory(), evaluator.review, INDIA, model=DESK_MODEL)
for n in INDIA.sources:
    tools.fetch_source(rs2, n)
for i in ("i1", "i2"):
    tools.read_article(rs2, i)
r2 = tools.submit_sections(rs2, **ok_draft)
check("total evaluator outage does not use up a draft", r2.get("evaluator_unavailable") and rs2.drafts == [])
gemini.ask_json = real_fake

# --- 9. email + website data -------------------------------------------------
html = email_sender.render_email_html(email, trace)
check("web text is escaped in the email", "<script>x" not in html)
check("email footer shows each desk and the harness checks", "Global desk" in html and "India desk" in html
      and "Harness checks" in html)
import run as runner  # noqa: E402
runner.SITE_DATA_DIR = tempfile.mkdtemp()
links = runner.publish_site_data("2026-01-01_1000", email, trace, "dry run")
idx = json.load(open(os.path.join(runner.SITE_DATA_DIR, "index.json"), encoding="utf-8"))
check("website data is written and read back", sorted(links) == sorted(urls) and idx[0]["id"] == "2026-01-01_1000")

# --- 10. memory --------------------------------------------------------------
m = new_memory()
for n in range(20):
    m.add_lesson(f"lesson {n}", "global" if n % 2 else "india")
m.mark_sent(["https://a"])
m.save()
m2 = Memory(m.path)
check("memory survives a restart and keeps lessons per desk", m2.was_sent("https://a") and len(m2.lessons()) == 15
      and all(l["desk"] == "india" for l in m2.lessons("india")))

print(f"All {len(PASSED)} checks passed.")
