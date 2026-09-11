# Auditor instructions (live v3 go-live inventory)

Parent: Cursor Grok 4.6. You are a **spawned** auditor. You cannot see the user chat.

## Scope

Inventory / structure-audit the **live production app in `/workspace/v3/`** (Flask home site). Do **not** inventory `rebuild/` `/test-next` as if it were production. `/legacy` (`webapp/`) only where v3 still calls it (Live login, OData).

This is rebuild protocol Phase 0 Step 2. Do **not** propose a from-scratch rewrite. Do **not** edit application code.

## REQUIRED READING

Read each of these files IN FULL, top to bottom, before doing anything else. Do not skim, do not stop at headings, do not rely on this prompt's summary -- the files are the source of truth and this prompt is only an orientation:

1. `/workspace/go-live/rebuild-audit/graph-backbone/INDEX.md`
2. Your area digest (path given in the spawn prompt)
3. This file

Open your deliverable with a 3–5 line proof-of-read of each required file (counts of routes/tables/report keys you saw).

## CodeGraph

First action: run `codegraph status` in `/workspace`. If healthy, use `codegraph` CLI only for structural lookups (no Grep/SemanticSearch/Read-tree for symbols). If CLI missing (expected): header line `graph via parent digest`. Drill into files **named in the digest** with Read. Do not grep the whole tree for structure. List any extra `codegraph` queries you would have run.

## Deliverable

Write to the path in the spawn prompt. Header must include:

```
Model: <the slug you were assigned>
Runner: spawn
Area: ...
Role: inventory | structure
```

Your final chat reply must be ≤10 lines: file path written, proof-of-read block, headline counts only. Do not paste the deliverable. Follow ponytail anti-slop (no sycophancy, no stock vocab, no hedging stacks).
