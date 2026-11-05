# Visual design: Ethereal direction (design-revision branch)

**Provenance.** Source: the "Ethereal" Design System artifact (README + tokens + cover preview; read as source, not seen rendered). It replaces the earlier Sugar Doodle pass. The direction is a stated preference relayed through another session, not something I could verify with the owner; the app is still demo mode.

## Taken from Ethereal
cotton-haze page (#F5E9F0) and pearl surfaces, ink #2C2438, Jost 300 display + Jost 400 body + DM Mono for meta/nav/labels (bundled locally in `app/static/fonts`, SIL OFL licences included, no remote requests), square corners (2px inputs), 1px hairline/outline controls, one heavy twilight header band, soft horizontal pastel smears behind the page, chromatic ghost on large headings, candy-wine links, baby-pink selection, mint for approve/ok, butter-glow passage highlight.

## Adapted for a reading tool (deviations)
- **Lowercase is interface-only** (nav, buttons, headings, badges). Passages, quotes, answers, document titles, citations, chips with titles, and the required disclosure wording ("Demo: scripted responses, not live tutoring.", "citation checks passed", scope notices) keep their original case.
- **No grain, no drifting/blur-breathing motion, no blurred images**: nothing textured or moving behind long text; smears sit behind opaque panels only. Reduced-motion is respected (nothing animates).
- No sparkles/icons (the previous star motif was removed, per the Ethereal "avoid" list).
- Dark mode is **not part of Ethereal**; it is my derivation (deep violet ground, pearl ink) and is contrast-checked below.
- The passage highlight is ink on butter-glow over a pearl panel (the README warns against butter-glow text on haze; this pairing is measured).

## Where to change things
Tokens: marked block at the top of `app/static/style.css` (overrides for this direction are at the end of the file). Contrast: `python scripts/check_contrast.py [--markdown]`. Screenshots: `python scripts/make_screenshots.py` (real app, synthetic fixtures, demo provider, light+dark, 1280 and 390px, asserts no horizontal scroll) → `docs/design/screenshots/`.

## Functionality retained
Same markup and ids; passage view remains a modal drawer on ≥1100px (page behind is inert, focus trap, Escape, focus restored; covered by `tests/e2e/test_dialog_and_scope.py`). Not delivered: persistent source panel, library search, new workflows.

## Measured contrast (WCAG 2.x; light / dark)
| Pairing | Target | Light | Dark |
|---|---|---|---|
| Body text on page (`ink` on `bg`) | 4.5:1 | 12.56 | 14.49 |
| Body text on reading surface (`ink` on `panel`) | 4.5:1 | 14.17 | 12.76 |
| Muted text on page (`muted` on `bg`) | 4.5:1 | 6.35 | 10.08 |
| Muted text on reading surface (`muted` on `panel`) | 4.5:1 | 7.16 | 8.88 |
| Primary button text on twilight / baby-pink (`btn-ink` on `btn`) | 4.5:1 | 11.63 | 8.65 |
| Approve button text on mint (`leaf-ink` on `leaf`) | 4.5:1 | 10.95 | 9.10 |
| Olive text on page (`leaf-text` on `bg`) | 4.5:1 | 5.27 | 9.99 |
| Passage highlight / step number text (`hl-ink` on `hl`) | 4.5:1 | 11.35 | 11.35 |
| Ink on butter (warning, question, passage target) (`ink` on `butter`) | 4.5:1 | 11.35 | 7.25 |
| Ink on sky (cite chip) (`ink` on `sky`) | 4.5:1 | 11.34 | 10.99 |
| Ink on lilac (tag chip, cite hover) (`ink` on `lilac`) | 4.5:1 | 7.44 | 7.79 |
| Pearl text on twilight (header band) (`pearl` on `twilight`) | 4.5:1 | 11.63 | 17.65 |
| Baby-pink on twilight (active nav) (`star` on `twilight`) | 4.5:1 | 7.10 | 10.77 |
| Link candy-wine on surface (`accent` on `panel`) | 4.5:1 | 6.03 | 8.78 |
| Link candy-wine on page (`accent` on `bg`) | 4.5:1 | 5.35 | 9.97 |
| Text on blush (user message, selected, passage) (`blush-ink` on `blush`) | 4.5:1 | 8.65 | 8.96 |
| Body text on blush (nav hover) (`ink` on `blush`) | 4.5:1 | 8.65 | 7.95 |
| Warning notice (`warn-ink` on `warn-bg`) | 4.5:1 | 11.35 | 8.02 |
| Error / withheld notice (`bad-ink` on `bad-bg`) | 4.5:1 | 7.03 | 7.91 |
| OK notice / live chip (`ok-ink` on `ok-bg`) | 4.5:1 | 7.90 | 8.66 |
| Label: quotation (`quote` on `panel`) | 4.5:1 | 6.03 | 8.78 |
| Label: interpretation (`interp` on `panel`) | 4.5:1 | 5.94 | 8.80 |
| Label: synthesis (`synth` on `panel`) | 4.5:1 | 5.99 | 9.34 |
| Label: fiction (`fiction` on `panel`) | 4.5:1 | 5.95 | 8.17 |
| Label: app coaching (`coach` on `panel`) | 4.5:1 | 7.16 | 8.88 |
| Label: limits (`limits` on `panel`) | 4.5:1 | 6.75 | 7.99 |
| Input / button boundary vs surface (UI 3:1) (`line-strong` on `panel`) | 3.0:1 | 5.39 | 5.86 |
| Input boundary vs page (UI 3:1) (`line-strong` on `bg`) | 3.0:1 | 4.78 | 6.65 |
| Focus ring vs page (UI 3:1) (`focus` on `bg`) | 3.0:1 | 12.56 | 14.49 |
| Focus ring vs surface (UI 3:1) (`focus` on `panel`) | 3.0:1 | 14.17 | 12.76 |
| Outline vs page (UI 3:1) (`line-strong` on `bg`) | 3.0:1 | 4.78 | 6.65 |

Only listed pairs are measured; this does not establish full accessibility, and there was no screen-reader testing.
