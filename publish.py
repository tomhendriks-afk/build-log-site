#!/usr/bin/env python3
"""
publish.py, publish a new Build Log post on build.ambient-advantage.ai.

Usage:
  python3 publish.py drafts/my-new-post.md            # full publish
  python3 publish.py --md-only drafts/my-new-post.md  # only emit .md twin + index.md

What it does (full publish):
  1. Parses the markdown draft (YAML-ish frontmatter + body).
  2. Converts the body to HTML (paragraphs, H2/H3, lists, code blocks,
     blockquotes, inline code, **bold**, *italic*, [links](url)).
  3. Renders the post page from _template.html.
  4. Updates posts.json (inserts or updates by slug, sorts by date desc).
  5. Regenerates index.html with the catalogue layout (pinned hero,
     component grid, recent posts).
  6. Regenerates per-tag listing pages (tag-<slug>.html).
  7. Writes the markdown twin <slug>.md for LLM/agent consumption.
  8. Regenerates index.md, the markdown twin of the homepage.

--md-only mode rebuilds only steps 7 and 8 and reads posts.json without
modifying it. Used for backfilling .md twins on posts whose rendered HTML
contains hand-edited content (inline diagrams etc.) that the minimal markdown
converter would wipe on a full re-publish.

What it does NOT do:
  - Touch git. Review with `git diff`, then commit and push yourself.

Consistent with the rest of the Ambient Advantage stack:
  - Python (matches the cloud-run-podcast pipeline and chiels-take-site).
  - Stdlib-only, no external dependencies.
  - Idempotent, running twice on the same draft is safe.

Frontmatter fields:
  title       (required), headline displayed on the post + index
  slug        (optional), derived from title if omitted
  date        (optional), YYYY-MM-DD; defaults to today
  tag         (optional), primary tag shown as the badge on cards (default: "Notes")
  tags        (optional), comma-separated list of all tags this post carries
  pinned      (optional), "true" pins this post as the hero on the catalogue
  excerpt     (optional), derived from first paragraph if omitted
  read_time   (optional), estimated from word count if omitted
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
ARTICLE_TEMPLATE = REPO_ROOT / "_template.html"
INDEX_TEMPLATE = REPO_ROOT / "_index_template.html"
TAG_TEMPLATE = REPO_ROOT / "_tag_template.html"
POSTS_JSON = REPO_ROOT / "posts.json"
INDEX_PATH = REPO_ROOT / "index.html"
INDEX_MD_PATH = REPO_ROOT / "index.md"

SITE_BASE_URL = "https://build.ambient-advantage.ai"


# =====================================================================
#  Component catalogue, the spine of the index page.
#  Each entry maps a tag slug to its catalogue card metadata.
#  Order here is the order shown on the index grid.
# =====================================================================

COMPONENTS = [
    {
        "slug": "cloud-run",
        "name": "Cloud Run",
        "blurb": "The serverless compute that runs the daily pipeline. Scales to zero, costs nothing when idle.",
        "group": "Compute",
    },
    {
        "slug": "cloud-scheduler",
        "name": "Cloud Scheduler",
        "blurb": "Managed cron. Fires the morning trigger that wakes the pipeline.",
        "group": "Compute",
    },
    {
        "slug": "cloud-build",
        "name": "Cloud Build",
        "blurb": "CI/CD. Watches the service repo, builds the container, deploys to Cloud Run on push.",
        "group": "Compute",
    },
    {
        "slug": "firestore",
        "name": "Firestore",
        "blurb": "Two collections, no migrations. Tracks pipeline state and episode metadata.",
        "group": "State",
    },
    {
        "slug": "gcs",
        "name": "Cloud Storage",
        "blurb": "Where the daily MP3 lives. Public-read URL feeds the podcast RSS enclosure.",
        "group": "State",
    },
    {
        "slug": "secret-manager",
        "name": "Secret Manager",
        "blurb": "Where the API keys live. Mounted into the service at startup.",
        "group": "State",
    },
    {
        "slug": "anthropic",
        "name": "Anthropic API",
        "blurb": "Claude Sonnet for research with web_search; Claude Opus for writing, self-review, and the transcript.",
        "group": "AI",
    },
    {
        "slug": "elevenlabs",
        "name": "ElevenLabs",
        "blurb": "Two-voice text-to-speech that turns the transcript into a real-sounding podcast.",
        "group": "AI",
    },
    {
        "slug": "gemini",
        "name": "Gemini",
        "blurb": "Visual generation: diagrams and banner images. Right tool for the pixel job, for now.",
        "group": "AI",
    },
    {
        "slug": "gmail-api",
        "name": "Gmail API",
        "blurb": "Drafts, sends, and labels live inside my own Gmail account. OAuth, no SMTP server.",
        "group": "Distribution",
    },
    {
        "slug": "github",
        "name": "GitHub",
        "blurb": "Source of truth for the service code and all four content sites. Contents API for daily commits.",
        "group": "Distribution",
    },
    {
        "slug": "cloudflare-pages",
        "name": "Cloudflare Pages",
        "blurb": "Hosts the static sites. Watches GitHub, rebuilds within a minute of every commit.",
        "group": "Distribution",
    },
    {
        "slug": "beehiiv",
        "name": "Beehiiv",
        "blurb": "Subscriber email delivery. Two publications: one for the daily briefing, one for Chiel's Take.",
        "group": "Distribution",
    },
]

COMPONENT_GROUP_ORDER = ["Compute", "State", "AI", "Distribution"]


# ---------- frontmatter + markdown parsing ----------

def parse_draft(text: str) -> tuple[dict, str]:
    """Split a draft into (frontmatter_dict, body_markdown)."""
    if not text.lstrip().startswith("---"):
        raise ValueError(
            "Draft must start with a '---' frontmatter block. "
            "See drafts/EXAMPLE.md for the expected format."
        )
    lines = text.lstrip().splitlines()
    close_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        raise ValueError("Frontmatter block is not closed with a trailing '---'.")

    fm_lines = lines[1:close_idx]
    body = "\n".join(lines[close_idx + 1:]).strip()

    meta: dict = {}
    for raw in fm_lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if ":" not in raw:
            raise ValueError(f"Bad frontmatter line (missing ':'): {raw!r}")
        key, _, value = raw.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"\s+", "-", value.strip())
    value = re.sub(r"-+", "-", value)
    return value


def inline_format(s: str) -> str:
    """Handle `code`, **bold**, *italic*, [link](url) in a single line of text."""
    # Inline code FIRST so we don't format inside it
    placeholders: list[str] = []
    def stash(match: re.Match) -> str:
        placeholders.append(f"<code>{match.group(1)}</code>")
        return f"\x00{len(placeholders) - 1}\x00"
    s = re.sub(r"`([^`]+?)`", stash, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    # Restore inline-code placeholders
    s = re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], s)
    return s


def markdown_to_html(md: str) -> str:
    """Markdown → HTML. Supports paragraphs, ## H2, ### H3, *italic*,
    **bold**, `inline code`, [links](url), unordered lists (- item),
    ordered lists (1. item), code blocks (```), and blockquotes (> ...).
    """
    md = md.replace("\r\n", "\n").strip()
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Code block
        if line.startswith("```"):
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            escaped = "\n".join(buf).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            out.append(f'    <pre><code>{escaped}</code></pre>')
            continue

        # Blank line
        if not line.strip():
            i += 1
            continue

        # Heading
        if line.startswith("## "):
            heading = inline_format(line[3:].strip())
            out.append(f"    <h2>{heading}</h2>")
            i += 1
            continue
        if line.startswith("### "):
            heading = inline_format(line[4:].strip())
            out.append(f"    <h3>{heading}</h3>")
            i += 1
            continue
        if line.startswith("# "):
            i += 1
            continue  # H1 is rendered from frontmatter title

        # Blockquote (one or more consecutive `> ` lines)
        if line.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith("> "):
                buf.append(lines[i][2:])
                i += 1
            quote = inline_format(" ".join(s.strip() for s in buf))
            out.append(f"    <blockquote>{quote}</blockquote>")
            continue

        # Unordered list
        if re.match(r"^\s*[-*] ", line):
            items: list[str] = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                items.append(inline_format(re.sub(r"^\s*[-*] ", "", lines[i]).strip()))
                i += 1
            li = "\n".join(f"      <li>{x}</li>" for x in items)
            out.append(f"    <ul>\n{li}\n    </ul>")
            continue

        # Ordered list
        if re.match(r"^\s*\d+\.\s", line):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s", lines[i]):
                items.append(inline_format(re.sub(r"^\s*\d+\.\s", "", lines[i]).strip()))
                i += 1
            li = "\n".join(f"      <li>{x}</li>" for x in items)
            out.append(f"    <ol>\n{li}\n    </ol>")
            continue

        # Paragraph, accumulate until blank line or block element
        buf = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                break
            if nxt.startswith(("## ", "### ", "# ", "```", "> ")) or re.match(r"^\s*[-*] ", nxt) or re.match(r"^\s*\d+\.\s", nxt):
                break
            buf.append(nxt)
            i += 1
        paragraph = inline_format(" ".join(s.strip() for s in buf))
        out.append(f"    <p>{paragraph}</p>")

    return "\n\n".join(out)


# ---------- metadata derivation ----------

def format_display_date(iso_date: str) -> str:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    try:
        return dt.strftime("%B %-d, %Y")
    except ValueError:
        return dt.strftime("%B %d, %Y").replace(" 0", " ")


def estimate_read_time(body_md: str) -> str:
    words = len(re.findall(r"\w+", body_md))
    minutes = max(1, round(words / 200))
    return str(minutes)


def first_paragraph_excerpt(body_md: str, max_words: int = 42) -> str:
    first = re.split(r"\n\s*\n", body_md.strip())[0]
    first = re.sub(r"\*\*(.+?)\*\*", r"\1", first)
    first = re.sub(r"\*(.+?)\*", r"\1", first)
    first = re.sub(r"`([^`]+?)`", r"\1", first)
    first = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first)
    first = re.sub(r"^#+\s*", "", first, flags=re.MULTILINE)
    first = re.sub(r"\s+", " ", first).strip()
    words = first.split()
    if len(words) <= max_words:
        return first
    return " ".join(words[:max_words]).rstrip(",.;:") + "..."


def parse_tags(raw: str) -> list[str]:
    if not raw:
        return []
    return [slugify(t) for t in re.split(r",\s*", raw.strip()) if t.strip()]


def enrich_meta(meta: dict, body_md: str) -> dict:
    if "title" not in meta or not meta["title"]:
        raise ValueError("Frontmatter must include 'title'.")

    meta.setdefault("tag", "Notes")
    meta.setdefault("slug", slugify(meta["title"]))
    meta.setdefault("date", datetime.today().strftime("%Y-%m-%d"))
    meta.setdefault("read_time", estimate_read_time(body_md))
    meta.setdefault("excerpt", first_paragraph_excerpt(body_md))
    meta["pinned"] = str(meta.get("pinned", "false")).strip().lower() == "true"
    meta["tags"] = parse_tags(meta.get("tags", ""))

    try:
        datetime.strptime(meta["date"], "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Frontmatter 'date' must be YYYY-MM-DD, got {meta['date']!r}")

    meta["date_display"] = format_display_date(meta["date"])
    meta["read_time_display"] = f"{meta['read_time']} min read"
    return meta


# ---------- rendering ----------

def render_tag_chips(tags: list[str]) -> str:
    if not tags:
        return ""
    chips = "\n".join(
        f'      <a class="tag-chip" href="tag-{t}.html">#{t}</a>'
        for t in tags
    )
    return f'    <div class="tag-chips">\n{chips}\n    </div>'


def render_article(meta: dict, body_html: str) -> str:
    import _jsonld

    template = ARTICLE_TEMPLATE.read_text()
    chips_html = render_tag_chips(meta["tags"])
    replacements = {
        "{{TITLE}}": meta["title"],
        "{{META_DESCRIPTION}}": meta["excerpt"],
        "{{OG_DESCRIPTION}}": meta["excerpt"],
        "{{TAG}}": meta["tag"],
        "{{READ_TIME}}": meta["read_time"],
        "{{DATE_DISPLAY}}": meta["date_display"],
        "{{ARTICLE_BODY}}": body_html,
        "{{TAG_CHIPS}}": chips_html,
        "{{JSONLD}}": _jsonld.article(meta),
    }
    for k, v in replacements.items():
        template = template.replace(k, v)
    return template


def render_post_md(meta: dict, body_md: str) -> str:
    """Markdown twin of a post, served at /<slug>.md.

    Mirrors chiels-take-site's pattern, body verbatim under a small header so
    LLMs and agents can fetch clean markdown without parsing HTML. The body is
    the unmodified draft markdown, so any raw HTML embedded in the .html page
    (e.g. inline diagrams) is intentionally absent here.
    """
    tags = ", ".join(meta.get("tags", []))
    tag_line = f"\n*Tags: {tags}*\n" if tags else ""
    return (
        f"# {meta['title']}\n"
        f"\n"
        f"*By Chiel Hendriks · Published {meta['date_display']} · "
        f"{meta['read_time_display']} · {meta['tag']}*\n"
        f"{tag_line}"
        f"\n"
        f"{body_md.rstrip()}\n"
    )


def render_index_md(posts: list[dict]) -> str:
    """Markdown index, short header + bulleted list of every published post."""
    lines = [
        "# Build Log — Ambient Advantage",
        "",
        "> Behind-the-scenes catalogue of how Ambient Advantage is built — "
        "architecture deep-dives, component notes, and operational gotchas. "
        "All published posts, newest-first.",
        "",
        "## Posts",
        "",
    ]
    for p in posts:
        url = f"{SITE_BASE_URL}/{p['slug']}.html"
        tags = " · ".join(f"#{t}" for t in p.get("tags", []))
        suffix = f" · {tags}" if tags else ""
        lines.append(
            f"- [{p['title']}]({url}) — {p['date_display']} · "
            f"{p['read_time_display']} · {p['excerpt']}{suffix}"
        )
    return "\n".join(lines) + "\n"


def _post_card(p: dict) -> str:
    chips = " ".join(f'<a class="post-chip" href="tag-{t}.html">#{t}</a>' for t in p.get("tags", []))
    return f'''    <article class="post-card">
      <div class="post-date">{p["date_display"]}</div>
      <h3 class="post-title"><a href="{p["slug"]}.html">{p["title"]}</a></h3>
      <p class="post-excerpt">{p["excerpt"]}</p>
      <div class="post-meta">
        <div class="post-chips">{chips}</div>
        <a class="post-read" href="{p["slug"]}.html">Read &rarr;</a>
      </div>
    </article>'''


def _component_card(component: dict, post_count: int) -> str:
    count_label = "1 post" if post_count == 1 else f"{post_count} posts"
    state = "is-empty" if post_count == 0 else "has-posts"
    cta = f'<a class="component-cta" href="tag-{component["slug"]}.html">Read posts &rarr;</a>' if post_count else '<span class="component-cta-empty">Coming soon</span>'
    return f'''      <article class="component-card {state}">
        <div class="component-group">{component["group"]}</div>
        <h3 class="component-name">{component["name"]}</h3>
        <p class="component-blurb">{component["blurb"]}</p>
        <div class="component-meta">
          <span class="component-count">{count_label}</span>
          {cta}
        </div>
      </article>'''


def render_index(posts: list[dict]) -> str:
    template = INDEX_TEMPLATE.read_text()

    # Pinned hero, first pinned post if present, else the most recent post
    pinned_posts = [p for p in posts if p.get("pinned")]
    hero = pinned_posts[0] if pinned_posts else (posts[0] if posts else None)

    if hero:
        hero_chips = " ".join(f'<span class="hero-chip">#{t}</span>' for t in hero.get("tags", [])[:5])
        hero_html = f'''<article class="hero-card">
  <div class="hero-label"><span class="hero-label-dot"></span>Start here &middot; The architecture</div>
  <h1 class="hero-title"><a href="{hero["slug"]}.html">{hero["title"]}</a></h1>
  <p class="hero-excerpt">{hero["excerpt"]}</p>
  <div class="hero-meta">
    <span class="author">Chiel Hendriks</span>
    <span>&middot;</span>
    <span>{hero["read_time_display"]}</span>
    <span>&middot;</span>
    <span>{hero["date_display"]}</span>
  </div>
  <div class="hero-chips">{hero_chips}</div>
  <a href="{hero["slug"]}.html" class="hero-read-btn">Read the deep dive &rarr;</a>
</article>'''
    else:
        hero_html = '<div class="hero-empty">No posts yet.</div>'

    # Recent posts list, exclude the hero so it isn't shown twice
    other_posts = [p for p in posts if p is not hero]
    if other_posts:
        cards = "\n".join(_post_card(p) for p in other_posts[:12])
        recent_html = f'''<section class="recent-section">
  <div class="recent-header">
    <h2>Recent posts</h2>
    <a class="recent-all" href="all.html">All posts &rarr;</a>
  </div>
  <div class="post-list">
{cards}
  </div>
</section>'''
    else:
        recent_html = ""

    import _jsonld

    return (
        template
        .replace("{{HERO}}", hero_html)
        .replace("{{RECENT}}", recent_html)
        .replace("{{JSONLD}}", _jsonld.index())
    )


def render_tag_page(tag: str, posts_for_tag: list[dict]) -> str:
    template = TAG_TEMPLATE.read_text()
    if posts_for_tag:
        cards = "\n".join(_post_card(p) for p in posts_for_tag)
        body = f'<div class="post-list">\n{cards}\n</div>'
    else:
        body = '<p class="tag-empty">No posts under this tag yet. Coming soon.</p>'

    # Friendly display name: component name wins; otherwise prettify the slug
    display = tag.replace("-", " ").title()
    for c in COMPONENTS:
        if c["slug"] == tag:
            display = c["name"]
            break
    count = len(posts_for_tag)
    count_label = f"{count} post" if count == 1 else f"{count} posts"
    return (template
            .replace("{{TAG}}", tag)
            .replace("{{TAG_DISPLAY}}", display)
            .replace("{{TAG_BODY}}", body)
            .replace("{{POST_COUNT_LABEL}}", count_label)
            .replace("{{POST_COUNT}}", str(count)))


# ---------- posts.json bookkeeping ----------

def update_posts_json(meta: dict) -> list[dict]:
    posts: list[dict] = []
    if POSTS_JSON.exists():
        posts = json.loads(POSTS_JSON.read_text())

    posts = [p for p in posts if p.get("slug") != meta["slug"]]
    posts.append({
        "slug": meta["slug"],
        "title": meta["title"],
        "tag": meta["tag"],
        "tags": meta["tags"],
        "date": meta["date"],
        "date_display": meta["date_display"],
        "read_time": meta["read_time"],
        "read_time_display": meta["read_time_display"],
        "excerpt": meta["excerpt"],
        "pinned": meta["pinned"],
    })
    posts.sort(key=lambda p: p["date"], reverse=True)

    POSTS_JSON.write_text(json.dumps(posts, indent=2) + "\n")
    return posts


# ---------- main ----------

def publish(draft_path: Path, md_only: bool = False) -> None:
    """Render a draft.

    Default mode rebuilds every artefact (.html page, posts.json, index.html,
    per-tag pages, plus the .md twins). --md-only mode rebuilds *only* the
    markdown surfaces (<slug>.md, index.md) and leaves the HTML files and
    posts.json untouched. The md-only path exists so that past posts whose
    rendered HTML carries hand-edited inline diagrams (raw HTML the minimal
    markdown converter would wipe) can have their markdown twin emitted
    without losing the diagram.
    """
    if not draft_path.exists():
        raise SystemExit(f"Draft not found: {draft_path}")

    raw = draft_path.read_text()
    meta, body_md = parse_draft(raw)
    meta = enrich_meta(meta, body_md)

    print(f"Publishing{' (md-only)' if md_only else ''}: {meta['title']}")
    print(f"  slug:      {meta['slug']}")
    print(f"  date:      {meta['date_display']}")
    print(f"  tags:      {', '.join(meta['tags']) or '(none)'}")
    print(f"  pinned:    {meta['pinned']}")
    print(f"  read time: {meta['read_time']} min")

    if md_only:
        # Read existing posts.json without modifying it; we need its sorted
        # listing to render index.md correctly. If it's missing, bail — md-only
        # is a backfill mode that assumes a published catalogue already exists.
        if not POSTS_JSON.exists():
            raise SystemExit("posts.json not found; --md-only requires a published catalogue.")
        posts = json.loads(POSTS_JSON.read_text())
        print(f"  reading:   posts.json ({len(posts)} total, unchanged)")
    else:
        # 1. Render the post page
        body_html = markdown_to_html(body_md)
        article_html = render_article(meta, body_html)
        article_out = REPO_ROOT / f"{meta['slug']}.html"
        article_out.write_text(article_html)
        print(f"  wrote:     {article_out.relative_to(REPO_ROOT)}")

        # 2. Update posts.json
        posts = update_posts_json(meta)
        print(f"  updated:   posts.json ({len(posts)} total)")

    # 3. Write the post markdown twin
    article_md = render_post_md(meta, body_md)
    article_md_out = REPO_ROOT / f"{meta['slug']}.md"
    article_md_out.write_text(article_md)
    print(f"  wrote:     {article_md_out.relative_to(REPO_ROOT)}")

    if not md_only:
        # 4. Regenerate index.html
        index_html = render_index(posts)
        INDEX_PATH.write_text(index_html)
        print(f"  rebuilt:   index.html")

    # 5. Regenerate index.md (markdown twin of homepage)
    INDEX_MD_PATH.write_text(render_index_md(posts))
    print(f"  rebuilt:   index.md")

    if not md_only:
        # 6. Regenerate per-tag pages
        all_tags: set[str] = set()
        for p in posts:
            for t in p.get("tags", []):
                all_tags.add(t)
        # Always render tag pages for known components, even if empty
        for c in COMPONENTS:
            all_tags.add(c["slug"])

        for tag in sorted(all_tags):
            posts_for_tag = [p for p in posts if tag in p.get("tags", [])]
            tag_html = render_tag_page(tag, posts_for_tag)
            (REPO_ROOT / f"tag-{tag}.html").write_text(tag_html)
        print(f"  rebuilt:   {len(all_tags)} tag pages")

    print()
    print("Done. Next steps:")
    print("  git diff               # review what changed")
    print("  git add .              # stage")
    print("  git commit -m '…'      # commit")
    print("  git push origin main   # push; Cloudflare auto-deploys")


def main() -> None:
    args = sys.argv[1:]
    md_only = False
    if "--md-only" in args:
        md_only = True
        args.remove("--md-only")
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    publish(Path(args[0]).expanduser().resolve(), md_only=md_only)


if __name__ == "__main__":
    main()
