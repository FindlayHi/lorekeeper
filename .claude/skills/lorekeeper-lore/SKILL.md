---
name: lorekeeper-lore
description: Build, refresh or audit a Lorekeeper lore pack for a game, meaning the curated wiki knowledge (chunks with their source) that the app checks before it searches the live wiki, attached to the game's cart in assets/cartridges.json. Use when the user says "make lore for <game>", "build a knowledge pack for <game>", "Lorekeeper is slow or wrong on <game> questions", or wants to add their own guides as a pack.
---

# Build a Lorekeeper lore pack

A pack is data only: the game's wiki pages cut into sections, each kept with its URL, fetch date and revision. `rag.py` searches it before `lookup.wiki`, and falls back to the live wiki when nothing in the pack answers the question. The cart points at the pack (`"lore": {file, sha256, version, builtForBuild}`); the pack itself is `docs/lore/<slug>.zip`.

**A pack is done when `audit.py` prints PASS**, which needs questions a person wrote, not ones taken from the pack. Never report a pack as good from the build output alone.

Run everything from the repo root with the repo's Python. Tools are in `tools/lore/`; the game's working folder is `lore/<slug>/`.

## 0. Can this game have a pack?

- It needs a **cart** already (`assets/cartridges.json`, see the lorekeeper-cart skill), since the pointer lives there.
- The wiki host must be one the app reads (`lookup.APIS`: `*.wiki.gg`, `*.fandom.com`, and a few named wikis).
- **Read the site's terms and robots.txt yourself**, and write down what they say.
  - The fetch tool reads article pages and category listings only, because wiki.gg disallows `api.php` for crawlers. It stops if robots.txt disallows a page.
  - wiki.gg's robots.txt carries a Content-Signal line (`search=yes, ai-train=no, use=reference`) and says nothing about `ai-input`. That is neither permission nor a ban for retrieval, so **raise it with the repo owner** and consider asking the wiki before shipping an official pack from it.
  - Check the licence in the page footer. Many wikis are CC BY-NC-SA, which is non-commercial: fine only while Lorekeeper stays non-commercial, and the pack must credit the wiki.
  - Never fetch faster than the tool does (one page a second).

## 1. Sources

```
python tools/lore/sources.py init "<Game Name>" --host <wiki host>
python tools/cart/wiki_probe.py <wiki host>        # categories and sizes, to pick seeds
```
Edit `lore/<slug>/sources.json`:
- `license` exactly as the site states it, and `terms`: when you read the terms and what they allow.
- `seeds`: `{"category": "Perks", "kind": "mechanic", "limit": 300}` or `{"pages": [...], "kind": "item"}`. `kind` is one of item, boss, quest, mechanic, build, lore.
- Take what players ask about (perks, items, bosses, mechanics, quests). Leave out lists of cosmetics, patch-note archives and the like.
- `steamAppId` for the staleness check later.
- `skipSections` to drop parts like Gallery, History and Navigation (History on DBD perk pages holds old versions with old numbers).
- `dropLines`: regexes for boilerplate lines every page of a kind repeats.
- **Entries.** Give each seed a specific `kind` (`perk`, `boss`, `item`, `status`, `power`; others: `mechanic`, `quest`, `build`, `lore`) and list the kinds that are *things players name* under `entityKinds`. Each such page becomes an entry in `entities.jsonl`, found by exact name, so "what does Sprint Burst do" is a lookup rather than a search. `entitySkipSections` cuts cosmetics and lore from entries, and `aliases` maps a page title to shorthand players say (`"Decisive Strike": ["ds"]`). Killers' "or \"The Nurse\"" names are picked up automatically. Broad pages (Generators, Hooks) stay search-only.

`python tools/lore/sources.py check "<Game>"` must print `ok`.

## 2. Fetch, clean

```
python tools/lore/fetch.py "<Game>" --max 30     # try 30 pages first and read the result
python tools/lore/fetch.py "<Game>"              # then all (about a second a page)
python tools/lore/clean.py "<Game>"
```
Read some `lore/<slug>/chunks.jsonl` lines. The real content must be in them (stats, descriptions), without menus, footers or duplicate tooltips. If a wiki builds its pages in an odd way, fix `tools/lore/htmltext.py` (it reads the rendered HTML) and check on at least two kinds of page.

**Quarantine.** `clean.py` holds back any chunk that talks to a model, links to another host, hides characters or carries encoded blobs, and lists them in `quarantine.json`. Read every one. Put the hash of a chunk that is fine under `approved`, and a bad one under `rejected`, in `lore/<slug>/reviewed.json`, then run `clean.py` again. Do not approve in bulk without reading.

## 3. Questions (needs the user)

Ask the user (or take from their play) 30+ questions the way a player says them aloud, and write `lore/<slug>/questions.json`:
```json
[{"q": "what does Lithe do", "page": "Lithe", "must": ["rushed vault", "haste status effect for 3 seconds"]},
 {"q": "who is the best streamer", "none": true}]
```
- `page`: the page (or a list of pages) the answer lives on. Its entry, or one of its chunks, must come back. Prefer this: a page name cannot be matched by accident.
- `must`: phrases (any case) the text handed to the model must contain. Use ones that belong to *this* answer: a value with its unit and subject (`"+50 % haste"`), a name, an exact number. Words like "haste", "aura" or "regression" appear on dozens of pages, and `10 %` is inside `110 %`, so alone they prove nothing.
- `none`: nothing in the pack answers it, so the app must use the live wiki. At least 5 of these.

Keep some questions aside and do not tune chunking against them. Strategy questions ("how do I counter the Nurse") are not answered by wiki facts; leave them out until there is a strategy source.

## 4. Build and prove

```
python tools/lore/build.py "<Game>" --build <steam build id or news id> --apply
python tools/lore/eval_lore.py "<Game>"
python tools/lore/audit.py "<Game>"
```
`--apply` writes the pointer into both `assets/cartridges.json` and `docs/cartridges.json`. `eval_lore.py` prints each failing question; fix the seeds, sections or chunking, not the questions. **Target: recall ≥ 0.9 and no false hits on the `none` questions**; the report also shows how many answerable questions the pack would actually answer (the rest go to the live wiki). Run `python -m pytest -q tests` after any change to a tool or to `rag.py`.

## 5. Hand over

- Do not deploy the site and do not push to `main` unless this is the repo owner's own session and they say so. Otherwise:
  1. Commit "Lore: <game>" on a branch `lore/<slug>`: `lore/<slug>/` (sources.json, questions.json, reviewed.json, AUDIT.md; the raw pages are git-ignored), `docs/lore/<slug>.zip`, and both `cartridges.json` files.
  2. Open a pull request to FindlayHi/lorekeeper with `AUDIT.md` in the body, including the licence and terms lines.
- A pack needs no app release: installed apps read the site's `cartridges.json` at startup and download the pack the first time that game is asked about.

## Bring your own

A player can make a pack from their own guides (md or txt files) with a `sources.json` containing `{"kind": "user", "folder": "<path>", "license": "own: <who wrote them>"}`; build with `--trust local` (it writes `lore/<slug>/<slug>.local.zip`, never into the site folder, and ignores `--apply`) and copy that file to `%APPDATA%\Lorekeeper\lore\<slug>.local.zip`. The app uses it for that game ahead of the official pack. A dropped-in file can never claim to be official.
