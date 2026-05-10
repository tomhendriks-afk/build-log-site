"""Schema.org JSON-LD helpers for build.ambient-advantage.ai.

Person and Organization are defined once here as the canonical source.
Every page emits the full @graph (so each page's structured data is
self-contained for validators), while the stable @id values let agents
cross-link entities across the five Ambient Advantage sites.

Schema.org type for individual posts: TechArticle — these are
architecture deep-dives and operational notes, the most-specific fit.

Tag pages (`tag-<slug>.html`) deliberately do not get JSON-LD: they're
listing pages, covered by the homepage's WebSite + CollectionPage.
"""

from __future__ import annotations

import json


PERSON: dict = {
    "@type": "Person",
    "@id": "https://ambient-advantage.ai/#chiel",
    "name": "Chiel Hendriks",
    "jobTitle": "Managing Director, Cloud, Data & AI",
    "worksFor": {"@type": "Organization", "name": "PwC Canada"},
    "url": "https://ambient-advantage.ai",
    "sameAs": ["https://www.linkedin.com/in/chielhendriks/"],
}

ORG: dict = {
    "@type": "Organization",
    "@id": "https://ambient-advantage.ai/#org",
    "name": "Ambient Advantage",
    "url": "https://ambient-advantage.ai",
    "founder": {"@id": "https://ambient-advantage.ai/#chiel"},
    "description": "Daily AI news briefing, podcast, and opinion column from Chiel Hendriks.",
}


def _embed(graph: list[dict]) -> str:
    payload = {"@context": "https://schema.org", "@graph": graph}
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    body = body.replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{body}\n</script>'


def article(meta: dict) -> str:
    """JSON-LD block for a single Build Log post."""
    art = {
        "@type": "TechArticle",
        "headline": meta["title"],
        "datePublished": meta["date"],
        "dateModified": meta["date"],
        "author": {"@id": PERSON["@id"]},
        "publisher": {"@id": ORG["@id"]},
        "mainEntityOfPage": f"https://build.ambient-advantage.ai/{meta['slug']}.html",
        "description": meta["excerpt"],
    }
    return _embed([PERSON, ORG, art])


def index() -> str:
    """JSON-LD block for the homepage — WebSite + CollectionPage."""
    website = {
        "@type": "WebSite",
        "@id": "https://build.ambient-advantage.ai/#website",
        "url": "https://build.ambient-advantage.ai",
        "name": "Build Log — Ambient Advantage",
        "publisher": {"@id": ORG["@id"]},
        "description": "Behind-the-scenes catalogue of how the Ambient Advantage system itself is built — architecture, components, decisions, gotchas.",
    }
    collection = {
        "@type": "CollectionPage",
        "@id": "https://build.ambient-advantage.ai/#catalogue",
        "url": "https://build.ambient-advantage.ai",
        "name": "Build Log component catalogue",
        "author": {"@id": PERSON["@id"]},
        "publisher": {"@id": ORG["@id"]},
        "isPartOf": {"@id": "https://build.ambient-advantage.ai/#website"},
    }
    return _embed([PERSON, ORG, website, collection])
