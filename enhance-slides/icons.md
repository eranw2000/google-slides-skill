# Icons8 slugs reference

URL shape: `https://img.icons8.com/ios-filled/192/<HEX-NO-HASH>/<slug>.png`

The hex color is derived per run from `ACCENT_HEX` in `script_template.py` (see Discovery in SKILL.md). The slugs below were verified against `CC785C`, the built-in default accent. Slug existence is independent of color, so the same lists apply for any accent color, but Slides API's image fetcher is flaky so even "200 OK from curl" does not guarantee success on every fetch.

## Slugs that succeeded end-to-end (curl 200 AND Slides API fetched)

Use these freely.

- book
- brain
- bug
- chat
- checkmark
- command-line
- document
- download
- idea
- lightning-bolt
- rocket
- settings
- shield
- star
- workflow

## Slugs that returned 200 from curl but failed in Slides API at least once

These often work on retry, but plan for failure. Provide a fallback from the verified list.

| Risky slug | Suggested fallback |
|---|---|
| bot | settings (no perfect alternative for "robot" in the verified set) |
| compass | map (untested) or workflow |
| console | command-line (semantically identical, fully verified) |
| folder | folder-invoices (untested at time of writing); fallback book |
| folder-invoices | book |
| gear | settings |
| globe | workflow (no perfect "web" alternative verified) |
| jigsaw | star or shield |
| play | lightning-bolt |
| puzzle | star or shield |
| search | document or command-line |
| speech-bubble-with-dots | chat |
| speedometer | settings (no perfect "gauge" verified) |

## Recommended mappings by content type

| Slide intent | Slug |
|---|---|
| What is X / introduction | command-line |
| Install / setup | download |
| Interactive session / chat | chat |
| Prompting / messaging | chat |
| Context / dashboard | settings |
| Markdown / config files | document |
| Memory / persistence | brain |
| Skills / capabilities | star |
| Commands | command-line |
| Hooks / triggers | lightning-bolt |
| Subagents / orchestration | settings |
| Security / safety | shield |
| Pro tips / insights | idea |
| What's new / highlights | star |
| Workflow / process | workflow |
| Verification / quality | checkmark |
| Scale / production | rocket |
| Failure modes / debugging | bug |
| Resources / references | book |

## URL format

```
https://img.icons8.com/ios-filled/192/<HEX-NO-HASH>/<slug>.png
```

- Style `ios-filled` is monochrome and accepts a color override in the URL.
- Size 192 renders well at the 0.77 inch placement used by the template.
- Color must be a 6-character hex without `#` (e.g., `CC785C`, `1A73E8`).
- Some Icons8 styles (e.g., `fluency-systems-filled`) appear to refuse arbitrary color overrides and return 404. Stick to `ios-filled`.

## Verification command

Before adding a new slug to a script, probe it against the chosen accent color:

```bash
# Replace ACCENT with the user-confirmed accent hex (no #).
ACCENT=CC785C
curl -s -o /dev/null -w "%{http_code}" \
  "https://img.icons8.com/ios-filled/192/${ACCENT}/<slug>.png"
```

A 200 is necessary but not sufficient. If Slides API fails to fetch a 200-OK URL, retry up to three times with a backoff (the template does this) and swap to a verified slug if it still fails.
