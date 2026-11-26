"""The two desks and their contracts.

Each desk is its own agent with a written contract: which sources it owns,
which sections it writes, and what "done" means for it. A desk can't touch
another desk's sources or sections. The harness checks the contract in code.
"""
from dataclasses import dataclass

SECTION_BRIEFS = {
    "tools": "AI tools useful for PM work (roadmapping, user research, analytics, prototyping, writing, "
             "productivity) or for student/professional life.",
    "ai_news": "Model releases, big company moves, funding, shutdowns: what is shaping the AI industry.",
    "india_news": "Funding, layoffs, leadership changes, launches and big moves by Indian startups and companies.",
}
SECTION_TITLES = {"tools": "AI tools for PMs", "ai_news": "AI industry news", "india_news": "India startup & company news"}


@dataclass(frozen=True)
class Desk:
    key: str            # "global" / "india"
    title: str
    prefix: str         # item ids look like g12 / i7
    sources: tuple
    sections: tuple
    min_read: int       # picks that must be read in full before a draft can pass
    max_items: int = 8
    min_items: int = 3  # aim; fewer is allowed only with an honest "quiet" note


GLOBAL = Desk("global", "Global desk", "g",
              ("Product Hunt", "Hacker News", "TechCrunch", "VentureBeat"), ("tools", "ai_news"), min_read=3)
INDIA = Desk("india", "India desk", "i",
             ("YourStory", "Inc42", "Business Standard Technology"), ("india_news",), min_read=2)
DESKS = (GLOBAL, INDIA)
