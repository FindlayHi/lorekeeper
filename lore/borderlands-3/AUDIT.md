# Lore audit: Borderlands 3

2026-10-20. **PASS**

| check | result | detail |
|---|---|---|
| sources.json complete | ok |  |
| pack exists | ok | docs\lore\borderlands-3.zip |
| the app accepts the pack (rag.load) | ok |  |
| size | ok | 4.63 MB (limit 20) |
| nothing waiting in quarantine | ok | 0 chunk(s): read them, then list their hash under approved or rejected in reviewed.json |
| every chunk is from a listed source | ok | 0, e.g. [] |
| no unapproved chunk looks like instructions | ok | 0, e.g. [] |
| every source has a license | ok |  |
| cart points at this pack in both cartridges.json copies | ok | hash differs: run build.py --apply |
| questions.json exists | ok |  |
| at least 30 questions and 5 that the pack should not answer | ok | 41 questions, 6 'none' |
| recall >= 0.9 | ok | 1.00 |
| no false confidence on unanswerable questions | ok | 0 of 6 |
| answered from the pack (info) | ok | 100% of the answerable questions; the rest go to the live wiki |

## Sources

| host | license | chunks | pages |
|---|---|---|---|
| borderlands.fandom.com | CC BY-SA 3.0 | 4892 | 1696 |
| github.com | own: Lorekeeper contributors | 7 | 1 |

Terms read: borderlands.fandom.com: Read 2026-10-19: the wiki's siteinfo gives its rights as CC-BY-SA (https://www.fandom.com/licensing) and Fandom's Help:Licensing names the Creative Commons Attribution-Share Alike License 3.0, attribution required; Fandom's robots.txt allows api.php?action= for all agents but disallows AI crawlers it names (GPTBot, ClaudeBot, CCBot and others), and the wiki's article pages and robots.txt are behind a Cloudflare check that scripts can't pass, so pages are read through api.php (action=parse) at one a second.; github.com: Written 2026-10-19 in our own words from four published guides (MentalMars, Saul Tink's Steam guide, Game Rant, Newsweek), each farm spot backed by at least one of them and every place checked against the wiki's entries; the guides are listed in the file's Sources section, which is left out of the pack.

Pack: version 2, built for game build unknown, trust official, 4899 chunks.

## Questions

- ok: where does the Monarch drop 
- ok: who drops the 9-Volt 
- ok: where can I farm the Agonizer 1500 
- ok: where do I get the Lyuda 
- ok: who drops the Hellwalker 
- ok: where does the Kaoson drop 
- ok: how do I get the Sand Hawk 
- ok: best place to farm the Flakker 
- ok: who drops the Ion Cannon 
- ok: where do I farm the Plaguebearer 
- ok: where does the Recursion drop 
- ok: who drops the Re-Router shield 
- ok: where can I get a Frozen Heart shield 
- ok: where do I farm the Victory Rush artifact 
- ok: who drops the Deathless 
- ok: where does the Night Hawkin drop 
- ok: who drops the Killing Word 
- ok: where do I find Killavolt 
- ok: where is Mouthpiece 
- ok: where does Graveward spawn 
- ok: where is Tink of Cunning 
- ok: where do I find Chupacabratch 
- ok: where is Wotan the Invincible 
- ok: where do I fight Captain Traunt 
- ok: what does Warty drop 
- ok: where is Billy the Anointed 
- ok: where can I find Road Dog 
- ok: where is Joey Ultraviolet 
- ok: where do I find Heckle and Hyde 
- ok: where is Gigamind 
- ok: where does Anathema the Relentless spawn 
- ok: where is Hemovorous 
- ok: how do vault card challenges work 
- ok: where should I farm psychos for my vault card challenge 
- ok: best place to farm saurians for the vault card 
- ok: where do I farm vehicle kills for the vault card weekly 
- ok: where do I farm the Elemental Projector 
- ok: where is Tremendous Rex 
- ok: where is Apollo 
- ok: where do I kill enemies on Eden-6 for my vault card 
- ok: where can I open red chests for the vault card 
- ok: what's the weather tomorrow 
- ok: who won the super bowl 
- ok: how much does a PS5 cost 
- ok: tell me a joke 
- ok: when is the next Borderlands 3 patch 
- ok: how do I make pancakes 
