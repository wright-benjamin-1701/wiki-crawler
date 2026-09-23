# Prompt: Generate Filter Logic

Use this prompt to generate just the `matches()` method for a new extraction job,
given a description of what pages you want.

---

## System / Role Context

You are an expert in Wikipedia's category structure and Python regex patterns.

---

## Codebase Context

```python
from wiki_dumps.parse.types import WikiPage
from wiki_dumps.extract.filters import (
    has_category,
    has_category_matching,
    title_matches,
    is_article,
    is_not_redirect,
)
```

A `WikiPage` has:
- `title: str` — the page title
- `namespace: int` — 0 = article, 1 = talk, 4 = project, etc.
- `categories: tuple[str, ...]` — extracted from `[[Category:X]]` links
- `redirect_to: str | None` — non-None if it's a redirect page

---

## Task Description

**[FILL IN: Describe the type of Wikipedia pages you want to match. Examples:]**

- "All pages about jazz musicians and jazz albums. Include redirects."
- "All articles about mountains in the Alps, but exclude list pages."
- "All articles about Python programming language, its libraries, and tools."

---

## Output Requirements

Generate:

1. A `matches(self, page: WikiPage) -> bool` method implementation
2. A comment listing the top 10–20 Wikipedia categories that are most relevant
3. Any title pattern regex to catch articles not covered by categories alone
4. An explanation of why each filter condition was chosen

---

## Tips for the LLM

- Wikipedia categories are hierarchical — check both specific and parent categories
- "List of X" pages often have category `Lists of X` — decide whether to include
- Disambiguation pages have category `All disambiguation pages`
- Stub articles have categories like `Jazz music stubs` — consider whether to include
- The `has_category_matching` helper accepts regex — use it for category families
  like `r"Jazz"` to match any category containing "Jazz"
