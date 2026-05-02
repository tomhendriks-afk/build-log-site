---
title: A short title for this post
slug: a-short-title-for-this-post
date: 2026-05-01
tag: Notes
tags: cloud-run, gotchas, claude-cowork
pinned: false
excerpt: One-sentence hook shown on cards and link previews. Optional, derived from the first paragraph if omitted.
---

The body starts here. Write in plain markdown. Paragraphs are separated by a blank line.

## Sections use H2

You can use **bold**, *italic*, `inline code`, and [links](https://example.com) inside paragraphs.

### Subsections use H3

Lists work too:

- One item
- Another item
- A third item

Numbered lists also work:

1. First step
2. Second step
3. Third step

Code blocks are fenced with three backticks:

```
gcloud run deploy podcast-pipeline \
  --source . \
  --region northamerica-northeast2
```

> Block quotes are also supported, handy for callouts or quoting yourself from a previous post.

That's all. Run `python3 publish.py drafts/your-file.md` to publish.

## Frontmatter reference

- `title`, required. The headline shown on the post and on cards.
- `slug`, optional. URL slug; derived from the title if omitted.
- `date`, optional. YYYY-MM-DD; defaults to today.
- `tag`, optional. Primary tag shown as the orange badge on cards. Default: "Notes".
- `tags`, optional. Comma-separated list of all tags this post carries. These power the tag pages and the component-card post counts.
- `pinned`, optional. Set to `true` to feature this post as the hero on the index page. Only one pinned post is shown at a time (the most recent).
- `excerpt`, optional. One-sentence hook for cards and link previews. Derived from the first paragraph if omitted.
- `read_time`, optional. Estimated minutes to read. Auto-calculated from word count if omitted.
