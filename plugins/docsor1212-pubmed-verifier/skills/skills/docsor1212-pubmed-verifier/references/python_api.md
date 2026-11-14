# Python API — calling pubmed-verifier from your code

The whole tool is one stdlib-only module. Import it directly — no pip, no
venv (Python 3.9+):

```python
import sys
sys.path.insert(0, "/path/to/pubmed-verifier/scripts")
import verify_pmids as vp
```

All functions below are stable surfaces used by the CLI itself (behavior
is pinned by the offline test matrix in the source repository).

## 1. Batch metadata for PMIDs

```python
info = vp.fetch_summaries(["31018962", "22213727"])   # NCBI, EPMC fallback
r = info["31018962"]
print(r["valid"], r["title"], r["journal"], r.get("retracted"))
```

## 2. Cross-check claimed vs registered metadata (the five-state ladder)

```python
cross = vp.cross_check_citation(
    {"claimed_title": "Classification criteria for autoinflammatory recurrent fevers",
     "claimed_authors": ["Gattorno"], "claimed_journal": "Ann Rheum Dis",
     "claimed_year": "2019"},
    {"title": r["title"], "authors": r["authors"],
     "journal": r["journal"], "pubdate": r["pubdate"]})
print(cross["verdict"], cross["details"])
# verdict ∈ correct / mismatch / partial / unknown
```

`claimed` / `actual` keys are plain strings/lists — feed them from any
source (database, form, LLM extraction). Cross-language CJK↔Latin author
names (and, since v3.9.0, CJK↔Latin titles) are skipped honestly, never
counted as misses.

## 3. DOI-native verification

```python
res = vp.resolve_doi("10.1038/nature12968")     # Crossref resolve (+retraction)
entry, audit = vp.verify_doi_entry(
    "10.1038/nature12968", "cli", resolution=res,
    claimed={"claimed_title": "...", "claimed_year": "2014"})
print(entry["verdict"], entry.get("retracted"))
```

## 4. Context parsing (extract claims from free text)

```python
claimed = vp.parse_citation_context(
    "Gattorno A, Van Dijk M. Classification criteria for autoinflammatory "
    "recurrent fevers. Ann Rheum Dis. 2019. PMID: 31018962")
print(claimed)
# GB/T 7714 Chinese references are recognized since v3.9.0 (title via the
# [J]/[M] type marker; the title comparison itself is cross-language-skipped)
```

## 5. Suggestions for broken citations

```python
cands = vp.suggest_correct_pmid({"claimed_title": "Juvenile idiopathic arthritis",
                                 "claimed_journal": "Pediatric Rheumatology"})
for c in cands[:3]:
    print(c["pmid"], c["title"][:60])   # abbreviated journal names can return [] — use the full NLM name
```

## 6. Plain-text reference lists & formatted output (v4.0.0)

```python
entries, issues = vp.parse_plaintext_references("refs_list.txt")
for e in entries:
    print(e["key"], e["pmid"] or e["doi"] or e["arxiv_id"] or
          "(title search)", e["claimed_title"][:50])

# One markerless entry, verified by title search (honest route label):
res, audit = vp.verify_title_entry(entries[0], "refs_list.txt")
print(res["verdict"], res.get("resolved_by"))   # correct title_search

# Render verified results as a numbered reference list:
print(vp.generate_reference_list(results, "gbt"))       # also: vancouver / apa / ama
```

`parse_citation_context` accepts markerless Latin references since v4.0.0
(returns `claimed_source_format: "plaintext"`); CJK entries without a
PMID marker stay with the weak-parsing boundary.

## Notes

- Network failures surface as `network_error=True` entries / honest
  `unknown` verdicts — never as "not found", never cached. Run
  `python3 scripts/verify_pmids.py --check-net` to diagnose connectivity.
- Retraction status follows the registry at call time; for final
  pre-submission passes run without the cache (`--no-cache` on the CLI).
