# Visual design: "a personal annotated notebook"

**The direction is inferred, not verified.** It comes from a separate session's description of saved Pinterest pins (handmade, warm, playful; tomato red, leaf green, blush, cream, stars). It is not a confirmed preference spec and may not match what the owner wants. The pass is visual only and easy to revert (`git revert` the design commits; no behaviour, data or backend was touched).

## Where to change things
- **Colours, fonts, radii:** the single marked token block at the top of `app/static/style.css` (light `:root`, dark inside `@media (prefers-color-scheme: dark)`).
- **Star:** one file, `app/static/star.svg`, drawn by the `.star` class via CSS mask, so it takes the `--star` colour. Used in the brand, and in empty states. Replace the file or remove `<span class="star">` elements to change/drop it.
- **Headings:** serif stack (`--font-head`: Iowan Old Style / Palatino / Georgia, system fonts only). Body: system sans (`--font-body`). No remote fonts or assets; no handwriting fonts for text or controls.
- Wavy blush underline on top-level headings is the only "pencil" detail; no animation (reduced-motion honoured), no texture behind text.
- Passages, answers and hits are capped at `--measure: 68ch`.

## Tokens (light / dark)
| Token | Light | Dark |
|---|---|---|
| bg (paper) | #FAF6ED | #1C1A16 |
| panel (reading surface) | #FFFCF6 | #26231D |
| ink / muted | #292821 / #5C574A | #F1EADB / #BDB5A2 |
| accent (tomato, text-safe) | #B83A2E | #F0897D |
| star (decorative tomato) | #C53E32 | #F0897D |
| leaf | #456349 | #9CC4A0 |
| blush / blush-ink | #F0DCD8 / #5E1F19 | #4A2D2A / #F6DDD9 |

The suggested tomato #C53E32 is kept for the star only; the text/button tomato was darkened to #B83A2E so primary-button text and links pass comfortably. Dark mode was kept and re-derived in the same warm family.

## Measured contrast (WCAG 2.x, computed by `scripts/check_contrast.py`; re-run it after any palette change)
| Pairing | Target | Light | Dark |
|---|---|---|---|
| Body text on page (`ink` on `bg`) | 4.5:1 | 13.71 | 14.50 |
| Body text on reading surface (`ink` on `panel`) | 4.5:1 | 14.44 | 13.08 |
| Muted text on page (`muted` on `bg`) | 4.5:1 | 6.67 | 8.52 |
| Muted text on reading surface (`muted` on `panel`) | 4.5:1 | 7.03 | 7.68 |
| Primary button text on tomato (`accent-ink` on `accent`) | 4.5:1 | 5.70 | 7.32 |
| Approve button text on leaf (`leaf-ink` on `leaf`) | 4.5:1 | 6.70 | 8.42 |
| Link / cite chip tomato on surface (`accent` on `panel`) | 4.5:1 | 5.57 | 6.40 |
| Link tomato on page (`accent` on `bg`) | 4.5:1 | 5.29 | 7.10 |
| Text on blush (user message, selected, passage) (`blush-ink` on `blush`) | 4.5:1 | 9.45 | 9.57 |
| Body text on blush (nav hover) (`ink` on `blush`) | 4.5:1 | 11.22 | 10.31 |
| Warning notice (`warn-ink` on `warn-bg`) | 4.5:1 | 8.13 | 9.17 |
| Error / withheld notice (`bad-ink` on `bad-bg`) | 4.5:1 | 7.43 | 8.13 |
| OK notice / live chip (`ok-ink` on `ok-bg`) | 4.5:1 | 7.98 | 8.98 |
| Label: quotation (`quote` on `panel`) | 4.5:1 | 6.71 | 6.40 |
| Label: interpretation (`interp` on `panel`) | 4.5:1 | 6.90 | 7.73 |
| Label: synthesis (`synth` on `panel`) | 4.5:1 | 6.51 | 8.44 |
| Label: fiction (`fiction` on `panel`) | 4.5:1 | 6.08 | 8.50 |
| Label: app coaching (`coach` on `panel`) | 4.5:1 | 7.84 | 8.74 |
| Label: limits (`limits` on `panel`) | 4.5:1 | 7.40 | 7.59 |
| Input / button boundary vs surface (UI 3:1) (`line-strong` on `panel`) | 3.0:1 | 4.09 | 4.21 |
| Input boundary vs page (UI 3:1) (`line-strong` on `bg`) | 3.0:1 | 3.89 | 4.67 |
| Focus ring vs page (UI 3:1) (`focus` on `bg`) | 3.0:1 | 13.71 | 14.50 |
| Focus ring vs surface (UI 3:1) (`focus` on `panel`) | 3.0:1 | 14.44 | 13.08 |
| Tomato control boundary vs surface (UI 3:1) (`accent` on `panel`) | 3.0:1 | 5.57 | 6.40 |
| Leaf accent on ok badge (UI 3:1) (`leaf` on `ok-bg`) | 3.0:1 | 5.41 | 6.95 |

All pairs meet their target. Focus ring: 3px solid `--focus` with a 2px offset, so it is drawn against the page/surface (rows above), not against a button fill.

## What this pass is (and is not)
A **visual reskin** plus small fixes. Delivered: tokens, star, typography, restyled existing screens, wrapping of long titles/tokens, a modal accessibility fix (below) and a scope-preview bug fix (a stray "null" line: native \`replaceChildren()\` stringifies nullish children; all calls now go through a \`put()\` helper that drops them).
**Not delivered** (earlier workspace-redesign ideas; no structural change was made): a persistent source side panel, a simplified session-start flow, a searchable/filterable library, any new workflow. These remain open.

Modal (passage/document view): focus moves into the dialog on open, Tab/Shift+Tab stay inside it, Escape closes, focus returns to the control that opened it, and it has \`role="dialog" aria-modal="true"\` with its heading as the accessible name. Covered by \`tests/e2e/test_dialog_and_scope.py\`.

## Verification
- `python scripts/make_screenshots.py` drives the real app (demo provider, synthetic fixtures approved, temp data dir) at 1280px and 390px, deviceScaleFactor 2, and asserts no horizontal scroll. Output: `docs/design/screenshots/` (1-conversation, 1b-passage-panel, 2-library, 3-new-session, 4-session-history, focus-*).
- Dark-mode shots (`*-dark-*`) and a long-title / long-unbroken-token stress case (`5-long-title-passage-view-dark-narrow.png`) were also captured and inspected; no horizontal scroll at either width in light or dark.
- Contrast figures cover only the listed pairs; they do not establish full accessibility. No screen-reader testing was done.
- Not verified: other browsers/OS (the heading font falls back by platform); real-document content; the owner's taste.
