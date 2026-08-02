---
model: opus
name: enhance-slides
description: Improve a Google Slides deck. Asks upfront for content sources and a branding website, derives a design system from that branding, then aligns fonts, titles, and backgrounds to it, adds per-slide icons, fixes typos, stray HTML entities, and missing titles, fills empty placeholder slides, and inserts new slides sourced from the provided articles or docs. Also makes body slides presentation-grade by turning dense prose into rounded-rectangle card layouts (column cards, X-vs-Y splits, 2x2 grids), adding example and code slides, converting tab-delimited text into real tables, and adding a linked table-of-contents slide for long decks, rendering each slide to a thumbnail to verify it before reporting done. Drives the Google Slides API via a parameterized Python script run locally. Use when the user asks to improve, enhance, redesign, polish, or clean up a Google Slides deck, references a docs.google.com/presentation URL with a request to modify it, or asks to add information from a source into a deck.
---

# Enhance Google Slides

You are improving a draft Google Slides presentation. Target outcomes:

1. The deck uses one coherent design system (fonts, colors, backgrounds), derived from the user's target branding.
2. Every content slide has a relevant icon.
3. Typos, stray HTML entities, and missing titles are fixed.
4. Empty placeholder slides are filled with appropriate content.
5. New slides sourced from user-provided articles or docs are added at logical positions; existing slides are updated where the sources contradict them.
6. The presentation flows logically (intro, body, close) and is easy to follow.

The deck remains editable in Google Slides at the end. You drive the Google Slides API via a Python script the user runs locally.

## Discovery (always do this first, before reading the deck)

Before any other action, ask the user two questions and wait for answers. Use the `AskUserQuestion` tool when available; otherwise ask in chat. Do not proceed to reading or backing up the deck until both are answered.

### Question 1: content sources

Ask: *"Which sources would you like me to draw new content from? Provide URLs, file paths, or document IDs. I'll read each, audit the deck against them, and propose new slides or edits before applying anything. If you have none, say 'none' and I'll only do design and cleanup."*

The user may provide zero or more sources. Capture them.

### Question 2: branding to base the look and feel on

Ask: *"Whose branding should I base the design on? Choose one:*
- *A company website URL (e.g., anthropic.com, stripe.com, your-company.com)*
- *A specific brand-guidelines or press-kit URL if you have one*
- *'Built-in default' for the neutral fallback palette (off-white `#FAFAFA`, warm terracotta `#CC785C`, charcoal `#2C2C2C`, Inter font)*
- *'Custom' followed by hex codes and a font name"*

After getting the answer:

1. **URL provided**: WebFetch it. If the homepage is light on brand info, also try `/brand`, `/press`, `/style-guide`, `/about`, or any link labeled "brand assets" / "press kit" you spot in the response. Extract:
   - Primary color (hero background, header, dominant accent)
   - Secondary or accent color (CTA buttons, links)
   - Body text color (often a near-black like `#1F2937` or `#2C2C2C`)
   - Font family (look for `font-family:` in CSS, `<link>` to Google Fonts, or named fonts on a brand page)
2. **Built-in default**: skip the fetch, use `BG=#FAFAFA, ACCENT=#CC785C, BODY=#2C2C2C, FONT=Inter`.
3. **Custom**: parse the hex values and font from the user's reply.
4. **Always**: propose the derived design system back to the user as a small table:

   | Token | Value | Notes |
   |---|---|---|
   | Background | `#XXXXXX` | source: hero section |
   | Accent (titles, icons) | `#YYYYYY` | source: primary CTA |
   | Body text | `#ZZZZZZ` | source: paragraph text |
   | Font family | `Name` | source: CSS / Google Font link |

5. Wait for confirmation. If the user wants tweaks, iterate. Only after explicit approval do you proceed to read the deck.

### Edge cases

- **Ambiguous color extraction**: if the page has multiple plausible primaries (e.g., a gradient or two strong CTAs), present 2-3 candidates and let the user pick.
- **No accessible brand page**: fall back to homepage CSS inspection. If still no clear signal, ask the user for explicit hex codes.
- **JavaScript-heavy site that returns blank from WebFetch**: tell the user the site couldn't be statically inspected and ask them to either paste their brand colors or point you at a static brand page.
- **Web-safe legibility**: if the derived palette has poor contrast (e.g., light gray title on white background), flag it and propose a darker accent.

## Required tools

- **Drive MCP** for read + backup:
  - `read_file_content`, `get_file_metadata` to read the deck
  - `copy_file` to create a dated backup BEFORE any edit
- **Local Python + Slides API** for the actual edits:
  - `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`
  - OAuth Desktop-app credentials at `~/.claude/google-oauth/credentials.json` (Slides API enabled on the GCP project, scope `https://www.googleapis.com/auth/presentations`)
  - Cached token at `~/.claude/google-oauth/slides_token.json` (created on first run by InstalledAppFlow)

If credentials are missing, the user needs to:
1. Visit https://console.cloud.google.com/apis/credentials
2. Enable Slides API on the project
3. Create an OAuth 2.0 Client ID of type "Desktop app"
4. Download as `~/.claude/google-oauth/credentials.json`

First script run opens a browser for consent and caches the token.

## Workflow

These steps run only AFTER the discovery questions above are answered and the design system is confirmed.

### 1. Read the deck

Use Drive MCP's `get_file_metadata` then `read_file_content` to extract slide text. Audit for:

- Title-less slides (`[Enter text here]` placeholder, empty TITLE shape)
- Stray HTML entities (`&#9;`, `&#11;`)
- Typos, outdated terms, deprecated commands
- Empty body placeholders on content slides
- Broken tab-separated "tables" with literal tab characters
- Duplicate slides
- Slides out of logical order

Write the audit before touching anything. Show it to the user so they can correct your read.

### 2. Back up the deck

Always before any edit:

```
copy_file(fileId=<deck-id>, title="[BACKUP YYYY-MM-DD] <original title> (pre-edit)")
```

Record the backup URL. The script prints it at the end as a rollback option.

### 3. Plan the changes

Group into phases. Each phase = its own `batchUpdate` so a failure in one phase doesn't roll back prior phases.

Canonical phase order:

| Phase | Action |
|---|---|
| 1 | Text replacements (typos, HTML entities, outdated terms) |
| 2 | Add titles to title-less slides (matched by body content prefix) |
| 3 | Visual refresh (background, title font + color) |
| 4 | Insert new intro / section slides |
| 5 | Append closing slides (resources, references) |
| 6 | Body text styling (font, color) |
| 7 | Per-slide icons (Icons8 PNG, top-right, ~0.77 inch square) |
| 8+ | New content slides from user-provided sources |

### 4. Write the script

Copy `script_template.py` from this skill folder next to the deck's working files (any directory the user can run Python from). Edit the constants section at the top:

- `PRESENTATION_ID`
- `TEXT_REPLACEMENTS` list of `(old, new)` tuples
- `TITLE_BY_BODY_PREFIX` for title-less slides
- `EMPTY_SLIDE_CONTENT` for empty body placeholders
- `NEW_INTRO_SLIDES`, `RESOURCES_SLIDE`, `NEW_SOURCE_SLIDES`
- `SLIDE_ICONS` (slide title → Icons8 slug)

Keep the design system constants fixed unless the user specifies a different brand.

### 5. Dry-run first

```
python script.py --dry-run
```

Verify counts and placements. Show the user. Only then apply.

### 6. Apply incrementally

Run phases in order, with verification between:

```
python script.py --phases 1
python script.py --phases 2,3
python script.py --phases 4,5,6
python script.py --phases 7
python script.py --phases 8
```

Per-phase batching means a failure in Phase 7 doesn't lose Phase 6's work.

### 7. Handle icon failures

The Slides API image fetcher is occasionally flaky on otherwise-valid PNG URLs. Per-icon retry (3 attempts with backoff) catches most. If a slug fails repeatedly, swap for a verified alternative (see `icons.md`).

## Design system

The design system is **derived per run** from the discovery step (Question 2). The values shown below are only the built-in fallback the user may explicitly select; they are not the skill's default.

```python
# Built-in default (selected only when the user asks for the built-in default):
BG_HEX     = "#FAFAFA"     # warm off-white background
ACCENT_HEX = "#CC785C"     # warm terracotta: titles + icons
BODY_HEX   = "#2C2C2C"     # charcoal body text
TITLE_FONT = "Inter"       # bold
BODY_FONT  = "Inter"       # regular

# Secondary tokens, read by the presentation-grade helpers:
MONO_FONT     = "Roboto Mono"   # code and config boxes
CARD_TINT_HEX = "#F6EFEA"       # card / code-box fill, a light tint of the accent
MUTED_HEX     = "#6B6B6B"       # caption gray
```

For any other branding choice, fill these constants with the values derived from the branding URL and confirmed by the user during discovery. Keep the structure: one near-neutral background, one accent for titles + icons, one near-black body color, one font family used for both title and body. Derive `CARD_TINT_HEX` as a light tint of the chosen accent so cards read as part of the same system.

Set all of them. The helpers read these constants by default, so a token left at its shipped value renders cards, captions, and code boxes in the old palette while the rest of the deck follows the new one, which looks like a bug in the deck rather than a missed constant.

### Deriving the design system from a branding URL

When the user provides a URL during discovery:

1. WebFetch the URL.
2. Scan the response for:
   - Hero / header background color (often the dominant primary).
   - Primary CTA color (often the accent).
   - Body / paragraph color (often a near-black).
   - `font-family:` declarations and `<link>` tags to `fonts.googleapis.com`.
3. If the homepage is sparse, also try `/brand`, `/press`, `/style-guide`, `/about`, or any link labeled "brand assets" / "press kit" that appears in the response.
4. If you find a brand-guidelines page, treat its named tokens (`Primary`, `Accent`, `Background`, etc.) as authoritative.
5. Build the four-token palette + font and present it to the user as a confirmation table (see Discovery, Question 2).

The icon color in `icon_url(slug)` must be updated to match the chosen accent color. The template uses `CC785C` by default; replace the URL color segment to match the new accent (e.g., `https://img.icons8.com/ios-filled/192/<HEX-NO-HASH>/<slug>.png`).

## Content sourcing methodology

When the user shares sources (articles, docs, blog posts):

1. **Read each source.** WebFetch for URLs, Read for local files. Extract distinct points; group by topic.
2. **Audit the deck against each source.** For every point, ask:
   - Is this missing from the deck and would strengthen it?
   - Does this contradict or update something already in the deck?
   - Is this best as a new slide or a small edit to an existing slide?
3. **Tier proposals** before implementing:
   - **Tier 1 (must-add)**: high signal, directly affects the deck's thesis
   - **Tier 2 (strong adds)**: meaningful but not essential
   - **Tier 3 (optional)**: nice-to-have, skip unless asked
   - **Edits**: `replaceAllText` against specific existing strings
4. **Present the proposal to the user.** For each new slide: title, anchor (which existing slide it follows), icon, 4-6 bullet preview.
5. **Implement as a new phase** in the script (Phase 8, 9, ...). Use the `insert_new_slides` helper in the template.

## Icon source

Icons8 `ios-filled` style with burgundy fill via URL color segment:

```
https://img.icons8.com/ios-filled/192/CC785C/<slug>.png
```

ALWAYS verify each slug before adding:

```bash
curl -s -o /dev/null -w "%{http_code}" \
  "https://img.icons8.com/ios-filled/192/CC785C/<slug>.png"
```

A 200 from curl is necessary but not sufficient. Some slugs are valid PNGs that Slides API still fails to fetch. See `icons.md` for slugs verified end-to-end and fallback recommendations.

## Idempotency rules

- Phase 1 (`replaceAllText`): no-op if the old string isn't found; safe to re-run.
- Phase 2 (titles): skip slides where `title_has_text(slide)` returns True.
- Phase 4 / 5 / 8 (new slides): skip if a slide with the exact title already exists.
- Phase 6 (body styling): `updateTextStyle` on empty text fails; skip empty bodies.
- Phase 7 (icons): skip slides that already have an image element.

The full script is idempotent end-to-end. If a run fails partway through, re-running picks up where it stopped.

## Presentation-grade slide patterns

Cleanup and re-skinning is the floor. When a deck teaches something or will be presented live, the body slides also have to look like slides, not pasted notes. Apply these on top of the design pass.

### Render and verify every slide you touch

After you build or edit a slide, render it and look at it before reporting it done. Request validity says nothing about whether the text fits on the slide, so never report a slide done blind.

```python
t = service.presentations().pages().getThumbnail(
    presentationId=PRESENTATION_ID, pageObjectId=SLIDE_ID,
    thumbnailProperties_mimeType="PNG", thumbnailProperties_thumbnailSize="LARGE").execute()
import urllib.request; urllib.request.urlretrieve(t["contentUrl"], "/tmp/check.png")
```

Open the PNG. Check for text overflowing the slide bottom (the most common failure on dense slides), columns that wrap badly, and overlapping elements. Delete the temp PNGs at the end.

### Turn prose into cards

Any slide whose content is a comparison, a set of parallel items, a model with N parts, or a structured list reads far better as cards than a paragraph block. Use rounded-rectangle cards:

- N columns for parallel concepts (a 3-part model becomes three cards).
- Two cards for an X-vs-Y split (hard-block vs warn, before vs after).
- A 2x2 grid for four items.

Each card: a light tint fill (an accent tint such as `#F6EFEA`), a short label or name in the accent color, a bold title, then a few body lines. Put a one-line italic caption under the cards for the takeaway.

Gotchas:
- A `ROUND_RECTANGLE` defaults its text to CENTER. Set `updateParagraphStyle` `alignment: START` on the card text, or multi-line bodies look ragged.
- Set the card `outline` to `NOT_RENDERED` and `contentAlignment: TOP` for a flat, top-aligned look.
- Size the body font down (10-12pt) and render to confirm it fits. Reducing the size never overflows; increasing it can.

### Example and code slides

After a concept slide, a concrete example earns its own slide. Code or config goes in a monospace box (`Roboto Mono`) on a light fill (`#F4EEEA`) at ~10.5-11pt; prose examples use the body font. Add a short italic caption underneath. If the deck already has good examples on some topics, only add where one is missing.

### Real tables, not tab-delimited text

A "table" built from tab characters inside one text box will not align on screen. Convert it to a real Slides table (`createTable`): bold accent text on a light-fill header row, ~10pt body, sensible column widths. Style every table the same way so the deck is consistent.

### Linked table of contents

For a deck past roughly 30-40 slides, add a "Contents" slide right after the title. List the section heads (not every slide) in one or two columns and link each line to that section's first slide. Link by `pageObjectId`, not `slideIndex`, so the links survive inserts and reorders. Resolve the target object ids before inserting the TOC slide. Color the entries in the accent and underline them so they read as links.

### Inserting and editing safely

- Insert new slides in DESCENDING anchor index so indices computed for earlier inserts stay valid. Anchor by slide title, or by a known `objectId` for slides with no title placeholder (new slides built from `BLANK` have none).
- To append a line to an existing body, insert at `len(text) - 1` (just before the trailing newline) so it becomes a new line in the same box; let the style inherit or restyle the inserted range.
- Fact-check technical content against the live docs (WebFetch) before writing slides about a product, API, or version. Do not assert feature names, model versions, or pricing from memory.
- Slide copy is read by an audience, so hold it to the same bar as any other prose you ship: no AI-tell vocabulary, no em dashes, no Unicode box-drawing characters.

The reusable helpers for cards, captions, code boxes, the linked TOC, and thumbnail verification are in `script_template.py` under "Presentation-grade pattern helpers".

## Common failure modes

| Failure | Cause | Fix |
|---|---|---|
| Whole batch rolled back | One bad request in a 100-request `batchUpdate` | Per-phase batches; per-icon batches for Phase 7 |
| `SSPEC.md` artifact | `replaceAllText("PEC.md", "SPEC.md")` matched inside existing `SPEC.md` | Watch for substring overlap; ship the cleanup `("SSPEC.md", "SPEC.md")` |
| `createImage` 400 "image not found" | Icons8 slug does not exist | curl-probe slug first; use only verified slugs |
| `createImage` 400 "problem retrieving" | Slides fetcher flake on valid URL | Per-icon retry 3x with backoff; if still failing, swap slug |
| `updateTextStyle` 400 "no text" | Title or body placeholder is empty | Guard with `title_has_text` / `collect_text(...).strip()` |
| Anchor "after_title" not found | Slide title differs from expected (typo, edit, reorder) | Re-fetch deck before each insertion; match by exact title |
| Card text looks centered / ragged | `ROUND_RECTANGLE` defaults to CENTER alignment | `updateParagraphStyle` `alignment: START` on the card text |
| Text runs off the slide bottom | Font too large or too many lines for the box | Render the thumbnail; drop the body pt or split the slide |
| TOC links break after a reorder | Linked by `slideIndex` | Link by `pageObjectId` instead |
| `&#11;` / `&#9;` in the Drive text export | These are real soft line breaks (chr 11) and tabs (chr 9) that render fine | Leave them; do NOT strip them, it destroys intended line breaks |
| New intro / closing slides look unbranded | Phase 3 read the deck before phases 4 and 5 created those slides | The template styles them in their own batch; keep that if you rewrite the phases |
| `ValueError: invalid literal for int()` deep in a request builder | A 3-digit CSS hex (`#EEE`) scraped from the branding site | `hex_to_rgb` expands shorthand; pass colors through it rather than slicing hex inline |
| Cards or captions render in the wrong font | A helper called with an explicit font instead of the design-system constants | Leave the font arguments unset so they inherit `BODY_FONT` / `TITLE_FONT` |

## Output checklist

Before declaring done:

- [ ] Dated backup created and URL recorded.
- [ ] Literal `&#9;` / `&#11;` text removed; but real chr-9 tabs and chr-11 soft line breaks (which the Drive export shows as those entities) left intact.
- [ ] No empty TITLE placeholders.
- [ ] No empty BODY placeholders on content slides.
- [ ] Background, title style, body style consistent across all slides.
- [ ] Every content slide has an icon (title slide excluded by design).
- [ ] New slides from sources inserted at logical positions; existing slides updated where sources contradicted them.
- [ ] Comparison / parallel / multi-part slides use cards, not paragraph blocks; card text left-aligned.
- [ ] Every slide built or edited was rendered to a thumbnail and visually checked for overflow.
- [ ] Tables are real Slides tables (not tab-delimited text) with a consistent header style.
- [ ] Decks past ~30-40 slides have a linked Contents slide (links by `pageObjectId`).
- [ ] User has reviewed the final deck.

## Guardrails

- Never edit a deck without backing it up first.
- Never use one large atomic `batchUpdate` for everything. Use per-phase batches.
- Never assume an Icons8 slug works without probing it.
- Never write a `replaceAllText` whose new string contains a substring of the old string (creates `SSPEC.md`-style regressions on re-run).
- Never delete slides without explicit user approval.
- Only PNG / JPEG / GIF accepted by `createImage`. SVG is not supported.
- `createImage` URL must be publicly fetchable by Google's servers, not only by curl from the user's machine.
- Keep image PNGs small. Slides API caps at 50 MB; aim for under 50 KB per icon for snappy rendering.

## The moving parts

- **Drive MCP** for reading and backing up decks. It does not edit slides; it only reads, copies, and creates. The backup step depends on it.
- **Google Slides API** via `google-api-python-client` for the actual edits. Slide content, layout, styling, and image insertion are all `presentations.batchUpdate` calls.
- **OAuth Desktop-app** credentials with the `https://www.googleapis.com/auth/presentations` scope; cached token at `~/.claude/google-oauth/slides_token.json`.
- **A phased Python script** as the execution shape. One script per deck, run one phase at a time, so a failure late in the run does not cost the work the earlier phases already landed.
- **Icons8 CDN** for per-slide icons. Slugs are probed with curl before use; fetch failures are handled by per-icon retry.
- **WebFetch** for reading the branding site and any source articles the user supplies.

See `script_template.py` for the full runnable template and `icons.md` for verified Icons8 slugs.
