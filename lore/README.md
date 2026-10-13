# Lore packs: handoff

Written 2026-10-13 for anyone picking this up. It covers what we set out to do, what exists now, and what is still to build. The pilot is Dead by Daylight (DBD).

## The idea

Today every question runs `claude -p` with web search on. Before that, `lookup.wiki()` fetches wiki pages live and picks sections by keyword. That is slow and costly, and the sources are whatever the web returns that day.

A **lore pack** is a curated, auditable, per-game knowledge file attached to a game's cartridge. The app checks it first and falls back to the live wiki when nothing in it answers the question. We build official packs to a quality bar, and players can build or drop in their own.

Goals, in the order they were set:
1. Faster and cheaper for most questions.
2. A known dataset: every chunk carries its source URL, fetch date and revision, and a build can only read hosts listed in `sources.json`.
3. Repeatable: a skill plus tools, the same shape as the cart maker.
4. Bring your own: a pack from a player's own guides, dropped in by hand.
5. Stay fresh: a Steam update should trigger a refresh (not built yet).

## What exists now

**In the app**
- `rag.py` reads a pack (zip of json, data only), searches it and renders prompt text.
  - Named things (a perk, a killer) are looked up exactly by name, alias or shorthand. This uses `entities.jsonl`.
  - Everything else is BM25 keyword search over `chunks.jsonl`, with title and section words counted extra.
  - A search hit counts only if it covers enough of the question and its title shares a word with it. Questions about now or next ("latest", "today", "when does") always go to the live wiki.
- `lorekeeper.py`: `App.lore()` runs before `lookup.wiki`. Any failure falls back to the live lookup.
- `icons.py`: a cart can carry `"lore": {file, sha256, version, builtForBuild}`, validated in `valid()`. `icons.text()` now uses a pack's exact entry for each perk read from the screen, instead of fetching the live page (for DBD the live page is almost empty, because pages are built by Lua modules).
- `config.py`: a `lore` setting, on by default.
- Safety: `rag.load` caps sizes, requires the cart's sha256, rejects pickles, paths and non-https URLs. A dropped-in pack (`<slug>.local.zip`) can never claim to be official. A cached official pack is only used while the cart still points at it with a matching hash.

**To build packs** (`tools/lore/`, run from the repo root; `.claude/skills/lorekeeper-lore/SKILL.md` has the full walkthrough)
`sources.py` (set up and check `sources.json`), `fetch.py`, `clean.py`, `build.py`, `eval_lore.py`, `audit.py`.
- `fetch.py` reads public article and category pages only, never `api.php` (wiki.gg's robots.txt disallows it). It checks robots.txt for every URL, pauses a second between pages, and resumes where it stopped.
- `clean.py` turns the rendered HTML into sections (`htmltext.py`), builds chunks and entries, and holds back anything that looks like it is talking to a model, links to another host or hides text. A person lists approved or rejected hashes in `reviewed.json`.
- `audit.py` is the gate. It writes `lore/<slug>/AUDIT.md`.

**The DBD pilot** (`lore/dead-by-daylight/`, `docs/lore/dead-by-daylight.zip`)
- 520 wiki pages, 2,425 chunks and 388 entries, 3.75 MB.
- Eval on 40 questions: recall 0.97 (32 of 33 answerable), 0 false hits on the 7 off-topic questions. Audit passes.
- One known miss: "how many generators do I have to repair". The page is found, but the chunk holding "a total of 5 Generators" is not in the top five.
- `tests/test_rag.py` and `tests/test_lore_tools.py` cover the loader, the name finder, cleaning, the injection flags and a full clean-build-eval run.

## Things we found along the way

1. **Lua-built pages.** DBD perk pages have almost no wikitext. The rendered page is the content, which is why the tools read HTML.
2. **robots.txt on wiki.gg** disallows `api.php` for crawlers and carries `Content-Signal: search=yes, ai-train=no, use=reference`, with nothing about `ai-input` (retrieval). That neither grants nor bans what we do. **Open question for the repo owner:** is this acceptable for an official pack, and should we ask wiki.gg?
3. **Licence.** The DBD wiki is CC BY-NC-SA 3.0. That is fine only while Lorekeeper stays non-commercial, with attribution. The audit lists the licence of each source.
4. **The wiki has its own mistakes.** The Dead Hard page contains a mangled sentence ("After being unhooked by any means, Dead Hard activates:While injured and running..."). A pack repeats what the wiki says.
5. **Tuning risk.** We tuned search and chunking against the same 33 questions we gate on, so 0.97 is probably optimistic. We tried 180-word chunks (worse, 0.91) and kept 300.
6. **No strategy in the wiki.** Killer pages have no counterplay section, so "how do I counter the Nurse" is not answered by wiki facts. The pack returns the Nurse's stats and power, and the model has to supply the advice.

## Still to build

In rough priority order:

1. **Review the DBD questions.** Add some of your own, especially messy ones. This is the biggest quality lever.
2. **Steam build id.** `games.py` parses `appmanifest_*.acf` but ignores `buildid`. Read it, store `builtForBuild` in packs, and pass it to `rag.context(build=...)` so the "may be out of date" note can fire. Right now the field is empty.
3. **Steam update trigger.** A scheduled GitHub Action polls `ISteamNews/GetNewsForApp` per cart appid and opens a PR when there is a new post. Build ids need PICS data, which is not in the public Web API (SteamCMD or similar), so start with the news feed. Verify the endpoints and rate limits first. DBD's appid is 381210.
4. **`update.py`.** Refresh a pack by re-fetching only pages whose revision changed, with a diff for review.
5. **Strategy source.** Needs input from the two of us and other players. Probably a curated guide, built with the bring-your-own path.
6. **Embeddings** (optional). A small local ONNX model (the app already bundles onnxruntime) for hybrid search. The manifest has an empty `embed` field for it. Measure against keyword-only first, since keyword search is already fast and scores well.
7. **Signing.** Official packs signed with a key the app embeds. Today `trust` is just a label, and integrity comes from the cart's sha256.
8. **Tray UI.** A toggle for `lore`, a list of installed packs with their age, and a loader for dropped-in packs.
9. **README and privacy table.** Mention packs: they download from the site and nothing new is sent out.
10. **More games.** Each one needs its cart first (see the lorekeeper-cart skill).

## Decisions we made

- A pack is a separate downloaded file referenced from the cart, not part of `cartridges.json`.
- Data only (json), no code. Keyword search first, with exact-name lookup for things players name. Embeddings later if they earn it.
- Official packs are built in a PR and reviewed through `AUDIT.md`. Nothing deploys itself.
- Strategy waits for a source we trust.

## Running it

```
python tools/lore/sources.py check "Dead by Daylight"
python tools/lore/fetch.py "Dead by Daylight"        # about an hour for DBD; safe to stop and rerun
python tools/lore/clean.py "Dead by Daylight"
python tools/lore/build.py "Dead by Daylight" --apply
python tools/lore/eval_lore.py "Dead by Daylight"
python tools/lore/audit.py "Dead by Daylight"
python -m pytest -q tests
```
`lore/<slug>/raw/` (the downloaded pages, about 120 MB) and the generated `chunks.jsonl` / `entities.jsonl` are git-ignored; the pack zip is what ships.
