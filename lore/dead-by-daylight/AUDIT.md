# Lore audit: Dead by Daylight

2026-10-13. **PASS**

| check | result | detail |
|---|---|---|
| sources.json complete | ok |  |
| pack exists | ok | docs\lore\dead-by-daylight.zip |
| the app accepts the pack (rag.load) | ok |  |
| size | ok | 3.75 MB (limit 20) |
| nothing waiting in quarantine | ok | 0 chunk(s): read them, then list their hash under approved or rejected in reviewed.json |
| every chunk is from a listed source | ok | 0, e.g. [] |
| no unapproved chunk looks like instructions | ok | 0, e.g. [] |
| every source has a license | ok |  |
| non-commercial licence (info) | ok | deadbydaylight.wiki.gg: the text may be used only while Lorekeeper stays non-commercial, with attribution and the same licence |
| cart points at this pack in both cartridges.json copies | ok | hash differs: run build.py --apply |
| questions.json exists | ok |  |
| at least 30 questions and 5 that the pack should not answer | ok | 33 questions, 7 'none' |
| recall >= 0.9 | ok | 0.97 |
| no false confidence on unanswerable questions | ok | 0 of 7 |
| answered from the pack (info) | ok | 100% of the answerable questions; the rest go to the live wiki |

## Sources

| host | license | chunks | pages |
|---|---|---|---|
| deadbydaylight.wiki.gg | CC BY-NC-SA 3.0 | 2425 | 520 |

Terms read: deadbydaylight.wiki.gg: Read 2026-10-13: page footer says content is CC BY-NC-SA 3.0 (pages from before Nov 2024 adapted from the Fandom wiki); robots.txt allows /wiki/ article and category pages and disallows api.php; its Content-Signal line is search=yes, ai-train=no, use=reference with no ai-input signal.

Pack: version 1, built for game build unknown, trust official, 2425 chunks.

## Questions

- ok: what does Lithe do 
- ok: how long am I exhausted after using Lithe 
- ok: what does Hex Ruin do 
- ok: how do I get rid of Ruin 
- ok: what is Sprint Burst 
- ok: what does Borrowed Time do 
- ok: how does Adrenaline work 
- ok: does Adrenaline work while exhausted 
- ok: what does Unbreakable do 
- ok: how fast is the heal with Self-Care 
- ok: what does Kindred show me 
- ok: what does Dark Sense do 
- ok: what does Resilience do 
- ok: what does Tinkerer do 
- ok: which killer has Tinkerer 
- ok: what does Pop Goes the Weasel do 
- ok: what does Thrill of the Hunt do 
- ok: what does Will to Live do 
- ok: which survivor has Dead Hard 
- ok: which is better, Sprint Burst or Lithe 
- FAIL: how many generators do I have to repair missing: a total of 5 generators
- ok: how many totems are on the map 
- ok: what are the different totem states 
- ok: how fast is the Nurse 
- ok: how fast is the Trapper 
- ok: what is the Nurse's terror radius 
- ok: what is the Trapper's power 
- ok: what does a toolbox do 
- ok: how long does a flashlight last 
- ok: how many charges does a med-kit have 
- ok: how many bloodpoints is a great skill check worth 
- ok: what happens on the second hook stage 
- ok: how does the obsession work 
- ok: when does the next patch come out 
- ok: how many people are playing right now 
- ok: why is my game stuttering on my laptop 
- ok: who won the last tournament 
- ok: what's the weather like today 
- ok: is the new chapter worth buying 
- ok: what does the Frobnicate perk do 
