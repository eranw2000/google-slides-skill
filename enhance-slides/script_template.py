#!/usr/bin/env python3
"""
Template: enhance a Google Slides deck via the Slides API.

Copy this file next to the deck's working files (e.g. fix_<deck>.py),
fill in the constants block below, then run incrementally by phase.

Setup (one-time):
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

OAuth:
    ~/.claude/google-oauth/credentials.json   (Desktop-app OAuth client, Slides API enabled)
    ~/.claude/google-oauth/slides_token.json  (auto-created on first run)

Phases:
    1  text replacements                  (typos, HTML entities, outdated terms)
    2  add titles to title-less slides    (matched by body content prefix)
    3  visual refresh                     (background color, title font + color)
    4  insert intro slides at the top     (after the title slide)
    5  append closing slide               (resources / references)
    6  body text styling                  (Inter, charcoal)
    7  per-slide icons                    (Icons8 PNG, burgundy, top-right)
    8  insert source-based slides         (content from user-provided articles)

Run:
    python script.py --phases 1 --dry-run
    python script.py --phases 1
    python script.py --phases 2,3
    python script.py --phases 4,5,6,7
    python script.py --phases 8
"""

import argparse
import sys
# Read and write UTF-8 on every OS: the Windows default code page misreads it.
if __name__ == "__main__":
    for _stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
import json
import sys
from pathlib import Path

# ===========================================================================
# CONFIGURE THIS BLOCK FOR EACH DECK
# ===========================================================================

PRESENTATION_ID = "REPLACE_WITH_DECK_ID"
BACKUP_URL = "https://docs.google.com/presentation/d/REPLACE_WITH_BACKUP_ID/edit"

# Design system, derived during the discovery step in SKILL.md from the user's
# chosen branding URL (or the built-in default, or a custom palette). The values
# shown here are the built-in fallback; OVERRIDE them for any other branding choice.
BG_HEX     = "#FAFAFA"     # near-neutral background
ACCENT_HEX = "#CC785C"     # primary accent: titles + icons
BODY_HEX   = "#2C2C2C"     # near-black body text
TITLE_FONT = "Inter"       # bold
BODY_FONT  = "Inter"       # regular

# Secondary tokens used by the presentation-grade helpers. These are part of the
# same design system: the helpers read them by default so a card, caption, or code
# box never silently renders in a font or tint the run did not choose.
MONO_FONT     = "Roboto Mono"   # code and config boxes
CARD_TINT_HEX = "#F6EFEA"       # card / code-box fill, a light tint of the accent
MUTED_HEX     = "#6B6B6B"       # caption gray

# Phase 1: text replacements. Order matters; later entries see results of earlier.
# Beware substring collisions (e.g. "PEC.md" -> "SPEC.md" mutates existing "SPEC.md").
TEXT_REPLACEMENTS = [
    # ("&#11;", " "),
    # ("&#9;",  " "),
    # ("PlaceholderToFix", "Corrected version"),
]

# Phase 2: title additions. Match by lowercased, whitespace-collapsed body prefix.
TITLE_BY_BODY_PREFIX = [
    # ("in claude code, double-tapping esc", "Pro tip: Rewind with Esc Esc"),
]

# Phase 2.5: body content for empty placeholder slides (matched by exact title).
EMPTY_SLIDE_CONTENT = {
    # "CLAUDE.md": ["bullet 1", "bullet 2", ...],
}

# Phase 4: new intro slides. Each is inserted at insertion_index (0-based).
# Process from highest insertion_index down so earlier insertions don't shift later ones.
NEW_INTRO_SLIDES = [
    # {
    #     "id_base":         "intro_what",
    #     "insertion_index": 1,
    #     "title":           "What is X?",
    #     "icon":            "console",
    #     "bullets": [
    #         "First bullet.",
    #         "Second bullet.",
    #     ],
    # },
]

# Phase 5: closing slide appended at end.
RESOURCES_SLIDE = {
    "id_base":  "outro_resources",
    "title":    "Resources and further reading",
    "icon":     "book",
    "bullets": [
        # "Docs: ...",
    ],
}

# Phase 7: title -> Icons8 slug. See icons.md for verified slugs.
SLIDE_ICONS = {
    # "What is X?": "console",
}

# Phase 8: source-based slides. Each anchors AFTER an existing slide by exact title.
NEW_SOURCE_SLIDES = [
    # {
    #     "id_base":     "source_topic_a",
    #     "after_title": "Some existing slide title",
    #     "title":       "New slide from source",
    #     "icon":        "star",
    #     "bullets": [
    #         "Point 1 from the source.",
    #         "Point 2.",
    #     ],
    # },
]

# ===========================================================================
# CONSTANTS (rarely edited)
# ===========================================================================

SCOPES = ["https://www.googleapis.com/auth/presentations"]
OAUTH_DIR = Path.home() / ".claude" / "google-oauth"
CLIENT_SECRETS_FILE = OAUTH_DIR / "credentials.json"
TOKEN_FILE = OAUTH_DIR / "slides_token.json"


def icon_url(slug):
    """Icons8 PNG, ios-filled style, accent-colored fill via URL color segment.

    The color in the URL is derived from ACCENT_HEX so icons stay consistent
    with the title color whenever the design system is changed.
    """
    color = ACCENT_HEX.lstrip("#").upper()
    return f"https://img.icons8.com/ios-filled/192/{color}/{slug}.png"


# ===========================================================================
# HELPERS
# ===========================================================================

def hex_to_rgb(hex_str):
    # Accept CSS shorthand. The discovery step reads colors out of a site's CSS, where
    # #EEE is as common as #EEEEEE, and the raw slice below turns that into a bare
    # int('') ValueError several frames away from the color that caused it.
    h = str(hex_str).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"Not a hex color: {hex_str!r} (expected #RGB or #RRGGBB)")
    return {
        "red":   int(h[0:2], 16) / 255.0,
        "green": int(h[2:4], 16) / 255.0,
        "blue":  int(h[4:6], 16) / 255.0,
    }


def slide_background_request(slide_id, hex_color):
    return {
        "updatePageProperties": {
            "objectId": slide_id,
            "pageProperties": {
                "pageBackgroundFill": {
                    "solidFill": {
                        "color": {"rgbColor": hex_to_rgb(hex_color)},
                        "alpha": 1.0,
                    }
                }
            },
            "fields": "pageBackgroundFill.solidFill.color,pageBackgroundFill.solidFill.alpha",
        }
    }


def title_text_style_request(title_object_id, hex_color):
    return {
        "updateTextStyle": {
            "objectId": title_object_id,
            "style": {
                "foregroundColor": {"opaqueColor": {"rgbColor": hex_to_rgb(hex_color)}},
                "bold": True,
                "fontFamily": TITLE_FONT,
            },
            "fields": "foregroundColor,bold,fontFamily",
            "textRange": {"type": "ALL"},
        }
    }


def body_text_style_request(body_object_id, hex_color):
    return {
        "updateTextStyle": {
            "objectId": body_object_id,
            "style": {
                "foregroundColor": {"opaqueColor": {"rgbColor": hex_to_rgb(hex_color)}},
                "fontFamily": BODY_FONT,
            },
            "fields": "foregroundColor,fontFamily",
            "textRange": {"type": "ALL"},
        }
    }


def collect_text(text_field):
    buf = []
    for t in text_field.get("textElements", []):
        tr = t.get("textRun")
        if tr and tr.get("content"):
            buf.append(tr["content"])
    return "".join(buf)


def extract_title(slide):
    for elem in slide.get("pageElements", []):
        shape = elem.get("shape", {})
        if shape.get("placeholder", {}).get("type") == "TITLE":
            return collect_text(shape.get("text", {})).strip()
    return None


def extract_body(slide):
    for elem in slide.get("pageElements", []):
        shape = elem.get("shape", {})
        if shape.get("placeholder", {}).get("type") in ("BODY", "SUBTITLE"):
            return collect_text(shape.get("text", {})).strip()
    return None


def find_title_object_id(slide):
    for elem in slide.get("pageElements", []):
        shape = elem.get("shape", {})
        if shape.get("placeholder", {}).get("type") == "TITLE":
            return elem.get("objectId")
    return None


def find_body_object_id(slide):
    for elem in slide.get("pageElements", []):
        shape = elem.get("shape", {})
        if shape.get("placeholder", {}).get("type") in ("BODY", "SUBTITLE"):
            return elem.get("objectId")
    return None


def title_has_text(slide):
    return bool(extract_title(slide))


def body_is_empty(slide):
    body = extract_body(slide)
    return not body or body == extract_title(slide)


def normalize_for_match(s):
    return " ".join(s.lower().split()) if s else ""


def get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    OAUTH_DIR.mkdir(parents=True, exist_ok=True)

    def run_consent():
        if not CLIENT_SECRETS_FILE.exists():
            sys.exit(
                f"Missing OAuth client at {CLIENT_SECRETS_FILE}. Setup:\n"
                "  1. https://console.cloud.google.com/apis/credentials\n"
                "  2. Enable Slides API on the project\n"
                "  3. Create OAuth 2.0 Client ID, type 'Desktop app'\n"
                f"  4. Download as {CLIENT_SECRETS_FILE}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
        return flow.run_local_server(port=0)

    creds = None
    if TOKEN_FILE.exists():
        # No scopes= argument on purpose. A stored token refreshes with the scopes it
        # was actually granted; handing it a widened SCOPES list makes Google reject
        # the whole refresh with invalid_scope, which reads like a broken credential.
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            # Revoked or otherwise dead refresh token. Re-consent instead of dying,
            # so the fix is not "go delete a cache file you were never told about".
            print(f"Stored token could not be refreshed ({e}). Re-running consent.")
            creds = run_consent()
    else:
        creds = run_consent()
    TOKEN_FILE.write_bytes((creds.to_json()).encode("utf-8"))
    return creds


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phases", default="1,2,3,4,5,6,7,8")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    phases = {int(p.strip()) for p in args.phases.split(",")}

    creds = get_credentials()
    from googleapiclient.discovery import build
    service = build("slides", "v1", credentials=creds)

    pres = service.presentations().get(presentationId=PRESENTATION_ID).execute()
    slides = pres.get("slides", [])
    print(f"Presentation has {len(slides)} slides. Title: {pres.get('title')}")

    def send(label, reqs):
        if not reqs:
            print(f"  {label}: 0 requests, skipping")
            return
        if args.dry_run:
            print(f"  {label}: would send {len(reqs)} requests (dry-run)")
            return
        CHUNK = 100
        for i in range(0, len(reqs), CHUNK):
            chunk = reqs[i:i + CHUNK]
            service.presentations().batchUpdate(
                presentationId=PRESENTATION_ID,
                body={"requests": chunk},
            ).execute()
        print(f"  {label}: sent {len(reqs)} requests")

    # ---- Phase 1: text replacements ----
    if 1 in phases:
        phase1 = [
            {"replaceAllText": {"containsText": {"text": old, "matchCase": True}, "replaceText": new}}
            for old, new in TEXT_REPLACEMENTS
        ]
        print(f"Phase 1: {len(phase1)} text replacements")
        send("Phase 1", phase1)

    # ---- Phase 2: add titles to title-less slides ----
    if 2 in phases:
        phase2 = []
        for slide in slides:
            if title_has_text(slide):
                continue
            body = extract_body(slide)
            if not body:
                continue
            body_norm = normalize_for_match(body)
            new_title = next(
                (cand for prefix, cand in TITLE_BY_BODY_PREFIX if body_norm.startswith(prefix)),
                None,
            )
            if not new_title:
                continue
            title_id = find_title_object_id(slide)
            if not title_id:
                continue
            phase2.append({"insertText": {"objectId": title_id, "insertionIndex": 0, "text": new_title}})

        # Also fill empty bodies (Phase 2.5).
        for slide in slides:
            title = extract_title(slide)
            if not title or title not in EMPTY_SLIDE_CONTENT:
                continue
            if not body_is_empty(slide):
                continue
            body_id = find_body_object_id(slide)
            if not body_id:
                continue
            body_text = "\n".join(EMPTY_SLIDE_CONTENT[title])
            phase2.append({"insertText": {"objectId": body_id, "insertionIndex": 0, "text": body_text}})
            phase2.append({"createParagraphBullets": {
                "objectId": body_id, "textRange": {"type": "ALL"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }})
        print(f"Phase 2: {len(phase2)} requests")
        send("Phase 2", phase2)

    # ---- Phase 3: visual refresh ----
    if 3 in phases:
        phase3 = []
        for slide in slides:
            slide_id = slide.get("objectId")
            if slide_id:
                phase3.append(slide_background_request(slide_id, BG_HEX))
            title_id = find_title_object_id(slide)
            if title_id and title_has_text(slide):
                phase3.append(title_text_style_request(title_id, ACCENT_HEX))
        print(f"Phase 3: visual refresh on {len(slides)} slides")
        send("Phase 3", phase3)

    # ---- Phase 4: insert new intro slides ----
    # Process from highest insertion_index down so earlier insertions don't shift later ones.
    if 4 in phases and NEW_INTRO_SLIDES:
        existing = {extract_title(s) for s in slides if extract_title(s)}
        phase4 = []
        added = 0
        for slide_def in sorted(NEW_INTRO_SLIDES, key=lambda s: s["insertion_index"], reverse=True):
            if slide_def["title"] in existing:
                print(f"  Skipping {slide_def['title']!r}: already present")
                continue
            id_base = slide_def["id_base"]
            title_id = f"{id_base}_title"
            body_id = f"{id_base}_body"
            phase4.append({"createSlide": {
                "objectId": id_base,
                "insertionIndex": slide_def["insertion_index"],
                "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
                "placeholderIdMappings": [
                    {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": title_id},
                    {"layoutPlaceholder": {"type": "BODY",  "index": 0}, "objectId": body_id},
                ],
            }})
            phase4.append({"insertText": {"objectId": title_id, "insertionIndex": 0, "text": slide_def["title"]}})
            phase4.append({"insertText": {"objectId": body_id, "insertionIndex": 0,
                                          "text": "\n".join(slide_def["bullets"])}})
            phase4.append({"createParagraphBullets": {
                "objectId": body_id, "textRange": {"type": "ALL"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }})
            # Style the slide in this same batch. Phase 3 read the deck before these
            # slides existed, and the recommended run order puts phase 3 in an earlier
            # invocation, so a new slide left unstyled here keeps the layout default
            # background and title color and visibly does not match the rest of the deck.
            phase4.append(slide_background_request(id_base, BG_HEX))
            phase4.append(title_text_style_request(title_id, ACCENT_HEX))
            phase4.append(body_text_style_request(body_id, BODY_HEX))
            added += 1
        print(f"Phase 4: adding {added} new intro slides")
        send("Phase 4", phase4)

    # ---- Phase 5: append a closing slide ----
    if 5 in phases and RESOURCES_SLIDE.get("bullets"):
        existing = {extract_title(s) for s in slides if extract_title(s)}
        phase5 = []
        if RESOURCES_SLIDE["title"] in existing:
            print(f"Phase 5: {RESOURCES_SLIDE['title']!r} already present, skipping")
        else:
            id_base = RESOURCES_SLIDE["id_base"]
            title_id = f"{id_base}_title"
            body_id = f"{id_base}_body"
            phase5.append({"createSlide": {
                "objectId": id_base,
                "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
                "placeholderIdMappings": [
                    {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": title_id},
                    {"layoutPlaceholder": {"type": "BODY",  "index": 0}, "objectId": body_id},
                ],
            }})
            phase5.append({"insertText": {"objectId": title_id, "insertionIndex": 0, "text": RESOURCES_SLIDE["title"]}})
            phase5.append({"insertText": {"objectId": body_id, "insertionIndex": 0,
                                          "text": "\n".join(RESOURCES_SLIDE["bullets"])}})
            phase5.append({"createParagraphBullets": {
                "objectId": body_id, "textRange": {"type": "ALL"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }})
            # Same reason as phase 4: style it here or it ships unbranded.
            phase5.append(slide_background_request(id_base, BG_HEX))
            phase5.append(title_text_style_request(title_id, ACCENT_HEX))
            phase5.append(body_text_style_request(body_id, BODY_HEX))
            print("Phase 5: appending closing slide")
        send("Phase 5", phase5)

    # ---- Phase 6: body text styling ----
    if 6 in phases:
        pres_b = service.presentations().get(presentationId=PRESENTATION_ID).execute()
        phase6 = []
        for slide in pres_b.get("slides", []):
            for elem in slide.get("pageElements", []):
                shape = elem.get("shape", {})
                ptype = shape.get("placeholder", {}).get("type")
                if ptype not in ("BODY", "SUBTITLE"):
                    continue
                body_id = elem.get("objectId")
                if not body_id:
                    continue
                if not collect_text(shape.get("text", {})).strip():
                    continue
                phase6.append(body_text_style_request(body_id, BODY_HEX))
        print(f"Phase 6: body styling on {len(phase6)} bodies")
        send("Phase 6", phase6)

    # ---- Phase 7: per-slide icons (per-icon batches with retry) ----
    if 7 in phases:
        import time
        pres_i = service.presentations().get(presentationId=PRESENTATION_ID).execute()
        page_width = pres_i.get("pageSize", {}).get("width", {}).get("magnitude", 9144000)
        icon_size_emu = 700000
        margin = 350000
        attempted = succeeded = skipped = 0
        for idx, slide in enumerate(pres_i.get("slides", [])):
            if idx == 0:
                continue   # never icon the title slide
            title = extract_title(slide)
            if not title or title not in SLIDE_ICONS:
                continue
            if any(elem.get("image") for elem in slide.get("pageElements", [])):
                skipped += 1
                continue
            slide_id = slide.get("objectId")
            slug = SLIDE_ICONS[title]
            req = {
                "createImage": {
                    "url": icon_url(slug),
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "width":  {"magnitude": icon_size_emu, "unit": "EMU"},
                            "height": {"magnitude": icon_size_emu, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": page_width - icon_size_emu - margin,
                            "translateY": margin,
                            "unit": "EMU",
                        },
                    },
                }
            }
            attempted += 1
            if args.dry_run:
                continue
            ok = False
            last_err = None
            for attempt in range(3):
                try:
                    service.presentations().batchUpdate(
                        presentationId=PRESENTATION_ID,
                        body={"requests": [req]},
                    ).execute()
                    ok = True
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.0 * (attempt + 1))
            if ok:
                succeeded += 1
            else:
                # Print the error. "image not found" means a bad slug (swap it),
                # "problem retrieving" means the fetcher flaked (retry later). The two
                # need opposite fixes and are indistinguishable without the message.
                print(f"  Failed after 3 tries: {title!r} (slug={slug}): {last_err}")
            time.sleep(0.3)
        if args.dry_run:
            print(f"Phase 7: would attempt {attempted} icons (skipped {skipped} already-imaged)")
        else:
            print(f"Phase 7: {succeeded}/{attempted} icons added (skipped {skipped})")

    # ---- Phase 8: source-based slides ----
    if 8 in phases and NEW_SOURCE_SLIDES:
        insert_new_slides(service, args, NEW_SOURCE_SLIDES, "Phase 8")

    print("\nDone.")
    print(f"View:   https://docs.google.com/presentation/d/{PRESENTATION_ID}/edit")
    if BACKUP_URL and "REPLACE_WITH" not in BACKUP_URL:
        print(f"Backup: {BACKUP_URL}")


def insert_new_slides(service, args, slide_defs, phase_label):
    """Insert slides that anchor by 'after_title'. Each slide is created,
    styled, and icon'd in its own batchUpdate, so partial failures isolate."""
    import time
    print(f"{phase_label}: inserting {len(slide_defs)} candidate slides")

    def title_index_map():
        p = service.presentations().get(presentationId=PRESENTATION_ID).execute()
        return p, {extract_title(s): i for i, s in enumerate(p.get("slides", [])) if extract_title(s)}

    pres_n, titles_to_index = title_index_map()
    page_width = pres_n.get("pageSize", {}).get("width", {}).get("magnitude", 9144000)
    icon_size_emu = 700000
    margin = 350000
    added = 0

    for slide_def in slide_defs:
        if slide_def["title"] in titles_to_index:
            print(f"  Skipping {slide_def['title']!r}: already present")
            continue
        anchor = slide_def["after_title"]
        if anchor not in titles_to_index:
            _, titles_to_index = title_index_map()
        if anchor not in titles_to_index:
            print(f"  Could not find anchor {anchor!r} for {slide_def['title']!r}, skipping")
            continue

        insertion_index = titles_to_index[anchor] + 1
        id_base = slide_def["id_base"]
        title_id = f"{id_base}_title"
        body_id = f"{id_base}_body"

        if args.dry_run:
            print(f"  Would insert {slide_def['title']!r} at index {insertion_index} (after {anchor!r})")
            titles_to_index[slide_def["title"]] = insertion_index
            continue

        try:
            service.presentations().batchUpdate(
                presentationId=PRESENTATION_ID,
                body={"requests": [
                    {"createSlide": {
                        "objectId": id_base,
                        "insertionIndex": insertion_index,
                        "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
                        "placeholderIdMappings": [
                            {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": title_id},
                            {"layoutPlaceholder": {"type": "BODY",  "index": 0}, "objectId": body_id},
                        ],
                    }},
                    {"insertText": {"objectId": title_id, "insertionIndex": 0, "text": slide_def["title"]}},
                    {"insertText": {"objectId": body_id, "insertionIndex": 0,
                                    "text": "\n".join(slide_def["bullets"])}},
                    {"createParagraphBullets": {"objectId": body_id, "textRange": {"type": "ALL"},
                                                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}},
                ]},
            ).execute()
        except Exception as e:
            print(f"  Failed to create {slide_def['title']!r}: {e}")
            continue

        try:
            service.presentations().batchUpdate(
                presentationId=PRESENTATION_ID,
                body={"requests": [
                    slide_background_request(id_base, BG_HEX),
                    title_text_style_request(title_id, ACCENT_HEX),
                    body_text_style_request(body_id, BODY_HEX),
                ]},
            ).execute()
        except Exception as e:
            print(f"  Styling failed for {slide_def['title']!r}: {e}")

        icon = slide_def.get("icon")
        if icon:
            icon_req = {
                "createImage": {
                    "url": icon_url(icon),
                    "elementProperties": {
                        "pageObjectId": id_base,
                        "size": {
                            "width":  {"magnitude": icon_size_emu, "unit": "EMU"},
                            "height": {"magnitude": icon_size_emu, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": page_width - icon_size_emu - margin,
                            "translateY": margin,
                            "unit": "EMU",
                        },
                    },
                }
            }
            ok = False
            last_err = None
            for attempt in range(3):
                try:
                    service.presentations().batchUpdate(
                        presentationId=PRESENTATION_ID,
                        body={"requests": [icon_req]},
                    ).execute()
                    ok = True
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.0 * (attempt + 1))
            if not ok:
                print(f"  Icon failed for {slide_def['title']!r} (slug={icon}): {last_err}")

        added += 1
        _, titles_to_index = title_index_map()
        time.sleep(0.3)

    print(f"{phase_label}: added {added} new slides")


# ---------------------------------------------------------------------------
# Presentation-grade pattern helpers
#
# Reusable request-builders for the slide-quality patterns documented in
# SKILL.md ("Presentation-grade slide patterns"): rounded-rectangle cards,
# title/caption blocks, code boxes, a linked table-of-contents, and thumbnail
# verification. Each builder returns a list of batchUpdate request dicts (except
# render_thumbnail, which calls the API). Pass colors in so they track the
# design system derived for the run. Send the collected requests in per-slide
# batches, then call render_thumbnail and look at the PNG before reporting done.
# ---------------------------------------------------------------------------

def _box(object_id, slide_id, x, y, w, h, shape="TEXT_BOX"):
    return {"createShape": {"objectId": object_id, "shapeType": shape,
        "elementProperties": {"pageObjectId": slide_id,
            "size": {"width": {"magnitude": w, "unit": "EMU"}, "height": {"magnitude": h, "unit": "EMU"}},
            "transform": {"scaleX": 1, "scaleY": 1, "translateX": x, "translateY": y, "unit": "EMU"}}}}

def _insert(object_id, text):
    return {"insertText": {"objectId": object_id, "insertionIndex": 0, "text": text}}

def _style(object_id, start, end, pt=None, hex_color=None, bold=False, italic=False,
           font=None, underline=False, link_page_id=None):
    # Default to the run's body font, not a literal. A hardcoded default here silently
    # renders every card, caption, and TOC entry in a font the design system did not pick.
    font = font or BODY_FONT
    style, fields = {"bold": bold, "italic": italic, "underline": underline}, ["bold", "italic", "underline"]
    if font:
        style["fontFamily"] = font; fields.append("fontFamily")
    if pt is not None:
        style["fontSize"] = {"magnitude": pt, "unit": "PT"}; fields.append("fontSize")
    if hex_color:
        style["foregroundColor"] = {"opaqueColor": {"rgbColor": hex_to_rgb(hex_color)}}; fields.append("foregroundColor")
    if link_page_id:
        style["link"] = {"pageObjectId": link_page_id}; fields.append("link")
    return {"updateTextStyle": {"objectId": object_id, "style": style, "fields": ",".join(fields),
        "textRange": {"type": "FIXED_RANGE", "startIndex": start, "endIndex": end}}}

def _align(object_id, alignment="START"):
    return {"updateParagraphStyle": {"objectId": object_id, "style": {"alignment": alignment},
        "fields": "alignment", "textRange": {"type": "ALL"}}}

def _fill_flat(object_id, hex_color):
    # Solid fill, no outline, top-aligned content: the card look.
    return {"updateShapeProperties": {"objectId": object_id, "shapeProperties": {
        "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": hex_to_rgb(hex_color)}, "alpha": 1.0}},
        "outline": {"propertyState": "NOT_RENDERED"}, "contentAlignment": "TOP"},
        "fields": "shapeBackgroundFill.solidFill.color,outline.propertyState,contentAlignment"}}

def card(object_id, slide_id, x, y, w, h, tint_hex, lines):
    """A rounded-rectangle card. lines = [(text, pt, hex_color, bold), ...]; "" is a blank spacer line.
    Text is left-aligned (a ROUND_RECTANGLE otherwise centers it)."""
    reqs = [_box(object_id, slide_id, x, y, w, h, "ROUND_RECTANGLE"), _fill_flat(object_id, tint_hex)]
    text = "\n".join(t for t, *_ in lines)
    reqs.append(_insert(object_id, text))
    off = 0
    for t, pt, hex_color, bold in lines:
        if t:
            reqs.append(_style(object_id, off, off + len(t), pt=pt, hex_color=hex_color, bold=bold))
        off += len(t) + 1
    reqs.append(_align(object_id, "START"))
    return reqs

def title_block(slide_id, key, title, subtitle, accent_hex, body_hex, left=311700, width=8520600):
    reqs = [_box(f"{key}_ttl", slide_id, left, 250000, width, 560000), _insert(f"{key}_ttl", title),
            _style(f"{key}_ttl", 0, len(title), pt=26, hex_color=accent_hex, bold=True, font=TITLE_FONT)]
    if subtitle:
        reqs += [_box(f"{key}_sub", slide_id, left, 880000, width, 360000), _insert(f"{key}_sub", subtitle),
                 _style(f"{key}_sub", 0, len(subtitle), pt=13, hex_color=body_hex)]
    return reqs

def caption_block(slide_id, object_id, text, y, gray_hex=None, left=311700, width=8520600):
    gray_hex = gray_hex or MUTED_HEX
    return [_box(object_id, slide_id, left, y, width, 560000), _insert(object_id, text),
            _style(object_id, 0, len(text), pt=11, hex_color=gray_hex, italic=True)]

def code_box(object_id, slide_id, x, y, w, h, code, body_hex=None, fill_hex=None, pt=11):
    """Monospace code/config on a light fill."""
    body_hex = body_hex or BODY_HEX
    fill_hex = fill_hex or CARD_TINT_HEX
    return [_box(object_id, slide_id, x, y, w, h), _fill_flat(object_id, fill_hex),
            _insert(object_id, code), _style(object_id, 0, len(code), pt=pt, hex_color=body_hex, font=MONO_FONT),
            _align(object_id, "START")]

def build_linked_toc(slide_id, entries, accent_hex, bg_hex=None,
                     left=311700, right=4760000, col_w=4072300, top=1080000, col_h=3850000):
    """entries = [(label, target_slide_object_id), ...]. Splits into two columns and links each
    line by pageObjectId (stable across reorders). Create the slide with objectId=slide_id
    (BLANK layout) first, then send these requests."""
    bg_hex = bg_hex or BG_HEX
    half = (len(entries) + 1) // 2
    cols = {"toc_left": (entries[:half], left), "toc_right": (entries[half:], right)}
    reqs = [{"updatePageProperties": {"objectId": slide_id, "pageProperties": {
                "pageBackgroundFill": {"solidFill": {"color": {"rgbColor": hex_to_rgb(bg_hex)}, "alpha": 1.0}}},
                "fields": "pageBackgroundFill.solidFill.color"}},
            _box("toc_ttl", slide_id, left, 300000, 8520600, 560000), _insert("toc_ttl", "Contents"),
            _style("toc_ttl", 0, len("Contents"), pt=28, hex_color=accent_hex, bold=True)]
    for box_id, (items, x) in cols.items():
        if not items:
            continue   # insertText with an empty string is a 400; a 1-entry TOC hits this
        text = "\n".join(lbl for lbl, _ in items)
        reqs += [_box(box_id, slide_id, x, top, col_w, col_h), _insert(box_id, text)]
        off = 0
        for lbl, target in items:
            reqs.append(_style(box_id, off, off + len(lbl), pt=13, hex_color=accent_hex,
                               underline=True, link_page_id=target))
            off += len(lbl) + 1
    return reqs

def render_thumbnail(service, presentation_id, page_object_id, out_path):
    """Render one slide to a PNG and save it. Open the PNG and check for overflow / overlap
    before reporting the slide done. Delete temp PNGs at the end of the run."""
    import urllib.request
    t = service.presentations().pages().getThumbnail(
        presentationId=presentation_id, pageObjectId=page_object_id,
        thumbnailProperties_mimeType="PNG", thumbnailProperties_thumbnailSize="LARGE").execute()
    urllib.request.urlretrieve(t["contentUrl"], out_path)
    return out_path


if __name__ == "__main__":
    main()
