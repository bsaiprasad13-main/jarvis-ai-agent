"""The original one-call pipeline, kept as the last-resort fallback.

One Gemini call over the fetched headlines writes all sections at once. No
reading, no review. The harness uses it only when every agent writer on a desk
has failed. It reads the same agent spec (jarvis.config.json) as the desks.
"""
import json

import requests

from .desks import READER, SECTION_BRIEFS, SECTION_TITLES, TEST_QUESTION

MODEL = "gemini-3.5-flash-lite"


def construct_prompt(items, failed_sources):
    items_text = ""
    for item in items:
        signal_text = f" (Signal: {item.get('signal')})" if item.get('signal') else ""
        items_text += f"- [{item['section']}] [{item['source']}] {item['title']}: {item['url']}{signal_text}\n"
    failed_text = ""
    if failed_sources:
        failed_text = (f"\nThese sources failed today: {', '.join(failed_sources)}. If a section is thin because a "
                       "source failed, say so instead of calling it a quiet day.")
    keys = ["tools", "ai_news", "india_news"]
    sections = "\n".join(f"SECTION {n} ({SECTION_TITLES[k]}, items labeled section_{n}): {SECTION_BRIEFS[k]}"
                         for n, k in enumerate(keys, start=1))
    return f"""You are writing a daily email brief for {READER}.
Every pick and every explanation must answer: "{TEST_QUESTION}"
Write in simple, friendly, everyday English with short sentences.

Use ONLY the items below, gathered in the last 24-72 hours. Do not use outside knowledge or make anything up.
Use popularity signals (upvotes, points) where given to judge importance. Order each section by usefulness.

{sections}

Pick 3 to 8 items per section. If fewer genuine items exist, include only what's real and say the day was quiet.
For every item give: title, source, link, and a 1-2 sentence "why_it_matters" that is specific to the item.
{failed_text}

Return strictly this JSON:
{{"section_1_tools": [{{"title": "", "source": "", "link": "", "why_it_matters": ""}}],
  "section_2_ai_news": [...], "section_3_india_news": [...],
  "section_notes": {{"section_1_status": "normal | quiet | source_issue", "section_1_message": "",
                     "section_2_status": "...", "section_2_message": "",
                     "section_3_status": "...", "section_3_message": ""}}}}

ITEMS:
{items_text}
"""


def generate_email_content(items, failed_sources):
    import os
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set.")
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    payload = {"contents": [{"parts": [{"text": construct_prompt(items, failed_sources)}]}],
               "generationConfig": {"responseMimeType": "application/json"}}
    try:
        response = requests.post(url, headers={"x-goog-api-key": api_key}, json=payload, timeout=60)
        if response.status_code != 200:
            print(f"Gemini API Error ({response.status_code}): {response.text[:300]}")
            return None
        text = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        return json.loads(text)
    except Exception as e:
        print(f"Error calling Gemini REST API: {type(e).__name__}")
        return None
