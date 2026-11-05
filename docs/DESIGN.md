# Visual design: Sugar Doodle direction

**Provenance.** The primary reference is the "Sugar Doodle Examples" design artifact (a shop landing page plus its Sugar Doodle token set). I read its source and tokens; I did **not** see it rendered. The earlier handmade/Pinterest direction was itself inferred, not a verified preference. Nothing here claims to match Jasmien's taste: it is a reversible visual pass, and the app is still in demo mode.

## What was taken from the reference, and what was not
Taken: cream paper page (#FBF4E6) with paper-white surfaces, warm ink (#3B2F2A) used for text *and* 2px outlines, pill buttons and nav chips, 24px card radius, solid "sticker" offset shadow on primary buttons, pastel fills (peony, blush, butter, lilac, sky, matcha), the four-point sparkle motif, marker-highlight under headings, Fredoka (headings) / Nunito (body) / Caveat (short empty-state notes only).
Deliberately **not** taken: shop/cart/newsletter/product UI, tilted cards, twinkle animation, scalloped dividers, remote Google Fonts. Sticker shadows are limited to primary/approve buttons, the active session and the exercise panel, never behind long text. Fonts are bundled locally in `app/static/fonts/` (SIL OFL licence included); the app makes no remote font requests.

## Where to change things
- **Tokens (colours, fonts, radii, shadows):** the marked block at the top of `app/static/style.css` (light `:root`; dark in `@media (prefers-color-scheme: dark)`).
- **Sparkle:** `app/static/star.svg` (theme-aware inside the file), used via the `.star` class in the brand and empty states.
- **Contrast:** `python scripts/check_contrast.py [--markdown]` recomputes the table below.

## Layout changes in this pass (CSS plus two tiny markup edits)
- Conversation: bubbles with outlines, user messages blush, answer blocks keep their coloured left bars and labels; passages/answers capped at 68ch.
- Passage inspection: on screens ≥1100px the passage dialog is a right-hand drawer (conversation stays visible); on narrow screens it is a centred dialog. It is a **modal** passage drawer, not a side-by-side interactive workspace: the page behind is `inert`, focus enters the drawer, stays inside, and returns to the opening control (e.g. the citation chip) on close.
- New session: the two form sections are numbered (1 Source scope, 2 Tutor) with the same controls; nothing removed.
- Library/history: same outlined cards, pastel badges and pills.
- **Not delivered:** a persistent in-page source panel, library search/filter, or any new workflow.

## Measured contrast (WCAG 2.x; light / dark)
| Pairing | Target | Light | Dark |
|---|---|---|---|
| Body text on page (`ink` on `bg`) | 4.5:1 | 11.80 | 14.22 |
| Body text on reading surface (`ink` on `panel`) | 4.5:1 | 12.70 | 12.68 |
| Muted text on page (`muted` on `bg`) | 4.5:1 | 5.98 | 8.88 |
| Muted text on reading surface (`muted` on `panel`) | 4.5:1 | 6.44 | 7.91 |
| Primary button text on peony (`btn-ink` on `btn`) | 4.5:1 | 6.60 | 6.60 |
| Approve button text on matcha (`leaf-ink` on `leaf`) | 4.5:1 | 7.15 | 7.75 |
| Olive text on page (`leaf-text` on `bg`) | 4.5:1 | 5.59 | 10.87 |
| Passage highlight / step number text (`hl-ink` on `hl`) | 4.5:1 | 10.11 | 10.11 |
| Ink on butter (warning, question, passage target) (`ink` on `butter`) | 4.5:1 | 10.11 | 7.32 |
| Ink on sky (cite chip) (`ink` on `sky`) | 4.5:1 | 9.40 | 9.38 |
| Ink on lilac (tag chip, cite hover) (`ink` on `lilac`) | 4.5:1 | 7.32 | 7.95 |
| Link peony-deep on surface (`accent` on `panel`) | 4.5:1 | 5.10 | 7.40 |
| Link peony-deep on page (`accent` on `bg`) | 4.5:1 | 4.74 | 8.30 |
| Text on blush (user message, selected, passage) (`blush-ink` on `blush`) | 4.5:1 | 9.76 | 9.48 |
| Body text on blush (nav hover) (`ink` on `blush`) | 4.5:1 | 9.76 | 10.29 |
| Warning notice (`warn-ink` on `warn-bg`) | 4.5:1 | 10.11 | 8.25 |
| Error / withheld notice (`bad-ink` on `bad-bg`) | 4.5:1 | 6.39 | 7.97 |
| OK notice / live chip (`ok-ink` on `ok-bg`) | 4.5:1 | 7.76 | 8.75 |
| Label: quotation (`quote` on `panel`) | 4.5:1 | 5.10 | 7.40 |
| Label: interpretation (`interp` on `panel`) | 4.5:1 | 6.95 | 8.32 |
| Label: synthesis (`synth` on `panel`) | 4.5:1 | 6.56 | 8.33 |
| Label: fiction (`fiction` on `panel`) | 4.5:1 | 6.12 | 8.11 |
| Label: app coaching (`coach` on `panel`) | 4.5:1 | 6.44 | 7.91 |
| Label: limits (`limits` on `panel`) | 4.5:1 | 7.46 | 7.24 |
| Input / button boundary vs surface (UI 3:1) (`line-strong` on `panel`) | 3.0:1 | 12.70 | 9.25 |
| Input boundary vs page (UI 3:1) (`line-strong` on `bg`) | 3.0:1 | 11.80 | 10.38 |
| Focus ring vs page (UI 3:1) (`focus` on `bg`) | 3.0:1 | 11.80 | 14.22 |
| Focus ring vs surface (UI 3:1) (`focus` on `panel`) | 3.0:1 | 12.70 | 12.68 |
| Outline vs page (UI 3:1) (`line-strong` on `bg`) | 3.0:1 | 11.80 | 10.38 |

Only the listed pairs are measured; this does not establish full accessibility, and there was no screen-reader testing. Peony (#E8A8B8) buttons are identified by their 2px ink outline plus text, not by fill contrast. Dark mode is re-derived (dark brown paper, cream ink).

## Verification
`python scripts/make_screenshots.py` drives the real app (demo provider, SYNTHETIC fixtures approved, temp data dir) at 1280px and 390px, deviceScaleFactor 2, light and dark, and asserts no horizontal scroll. Output in `docs/design/screenshots/`. Not verified: other browsers/OSes, real documents, the owner's taste, live tutoring.
