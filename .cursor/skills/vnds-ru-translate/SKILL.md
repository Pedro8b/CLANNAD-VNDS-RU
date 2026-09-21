---
name: vnds-ru-translate
description: >-
  Translates and QA-reviews CLANNAD VNDS scripts from English to Russian.
  Use when translating .scr files, checking translated-ru/script, updating
  listing.json, fixing gender/context, or running tools/vnds_pipeline.py.
---

# VNDS RU translation loop

Work on **one `.scr` file at a time**. Never rewrite engine commands.

Paths:

- original: `script/<file>`
- Russian: `translated-ru/script/<file>`
- listing: `translated-ru/listing.json`
- names: `translated-ru/speakers.json`

## Commands (run these)

```bash
python tools/vnds_pipeline.py scan
python tools/vnds_pipeline.py next --limit 1
python tools/vnds_pipeline.py check SEENXXXX_X_X.scr
python tools/vnds_pipeline.py init-file SEENXXXX_X_X.scr
python tools/vnds_pipeline.py translate-speakers SEENXXXX_X_X.scr
python tools/vnds_pipeline.py set-status SEENXXXX_X_X.scr approved
python tools/vnds_pipeline.py set-status SEENXXXX_X_X.scr qa_failed --notes "..."
```

`listing.json` is the source of truth. `approved` only after language QA **and** `structure_ok`.

## File loop

1. `scan` if listing is stale, then `next`.
2. Branch on `status`:
   - `missing` / `empty` / `untranslated` → `init-file` (if missing/empty), then translate every `text`/`choice` line; then speakers.
   - `partial` / `needs_qa` / `qa_failed` → do **not** retranslate from scratch; fix issues.
3. Translate or edit `translated-ru/script/<file>` only.
4. `translate-speakers` then `check`.
5. If structure fails → fix code lines (must match original exactly) and re-check.
6. Language QA (below). If fail → edit, re-check, repeat.
7. If pass → `set-status <file> approved`. If still bad after edits → `qa_failed` with notes.

Do not mark empty files `approved`.

## What may change

Allowed:

- payload of `text ...` (dialogue/narration)
- payload of `choice A|B|...` (same number of `|` branches)
- speaker tags `text @[English]` → `text @[Русское]` per `speakers.json`

Forbidden:

- any other line (`setvar`, `if`, `goto`, `label`, `jump`, `bgload`, `setimg`, `sound`, `music`, `delay`, `gsetvar`, `cleartext`, `fi`, …)
- indent/tabs
- line count
- `{$...}` tokens (including `{$lnmA}` speakers)
- filenames, image/audio names, labels

Broken original tags like `{$strS[1017` stay broken.

## Language QA (must all pass)

Read original and Russian in parallel. Fail the file if any item fails:

- Gender: Томоя/Сунохара/Акио/Ёсино/Каппэй — masculine; Нагиса/Кё/Рё/Томоё/Фуко/Котоми/Санаэ/Мэй/Мисаэ/Коко/Усио — feminine. Кё is female (rough speech, not male). `Furukawa` tag is usually Sanae (female).
- Context: same events, jokes, hesitation, inner vs spoken (`(...)` stays inner).
- Names: `speakers.json` only; do not invent variants (not «Кёу», not «Томойя»).
- Natural Russian, not calque; keep tone (Fuko childlike, Nagisa shy, Kyou blunt, Sunohara loud).
- No leftover English in dialogue except intentional names/onoma if original keeps them.
- `choice` options remain short UI strings, same count and meaning.

See [qa-checklist.md](qa-checklist.md) for the per-file tick list.

## Translation method

Copy the original file structure. Replace only translatable payloads. Prefer existing Russian in the file when it is already good; rewrite inaccurate lines.

After translating a chunk, keep speaker tags consistent in that file.
