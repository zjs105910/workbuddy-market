---
name: pubmed-verifier
author: DoctorQ Lab
license: MIT-0
version: 4.2.0
description: >-
  Reference checker for AI-fabricated citations: batch-verify PMIDs against
  PubMed and catch the hallucination existence checks miss — a REAL PMID
  pointing to a DIFFERENT paper. Five-state citation verification (correct /
  mismatch / partial / invalid / unknown), citation-context parsing, Crossref
  DOI cross-check, retraction detection (capped at partial), correct-PMID
  suggestion, arXiv ID verification, plain-text reference list parsing,
  formatted reference lists (GB/T 7714 / Vancouver / APA / AMA), OpenAlex DOI
  fallback for non-Crossref registries, Chinese-reference title search,
  CSV/JSON claims, HTML/JSON/text reports. Four data sources: NCBI, Europe PMC
  fallback, Crossref, OpenAlex. Network failures are honestly reported as
  unverified, never as "not found". Zero dependencies, runs fully local.
  Triggers: verify PMIDs, check citations, citation audit, reference check,
  PMID check, batch verify references, AI hallucination detection, verify DOI,
  DOI check, citation formatting, reference formatter, GB/T 7714.
---

# PubMed Citation Verifier v4.2.0

Batch verification of PMID citations via the PubMed E-utilities API. Not just
"does this PMID exist" — **does this PMID point to the paper you claim?**
Zero dependencies, pure standard library, fully local.

## When to use this skill

Invoke it whenever citation truth matters:

- "Verify / check these PMIDs / this reference list" (before submission or release)
- Auditing citations in AI-generated text (fabricated or mismatched references)
- Spot-checking a systematic review's bibliography
- "Does PMID 12345678 really say X?" — point-of-doubt verification
- Batch QA of a knowledge base's PMID/DOI citations
- Automatic invocation: trigger this skill whenever the user asks to
  "verify/check/audit" citations, PMIDs, DOIs, arXiv preprints or
  references — no flags needed for a first pass; add `--claims-file`
  when they supply the expected titles.

**Trigger priority & tool choice** — explicit "verify / check / audit
citations, references, PMIDs, DOIs" requests invoke this skill first.
cite-holmes is for deep research with machine-verified citations; when a
request mixes research and verification, run the research first, then
this tool for the final reference audit.

## Trigger words

Use this skill when the user's request matches any of: **verify PMIDs**,
**check citations**, **validate references**, **citation audit**,
**reference check**, **batch verify references**, **AI hallucination
detection**, **verify DOI**, **DOI check**, **citation formatting**,
**reference formatter**, **GB/T 7714**, 中文文献验证 / 参考文献核查 /
文献排版. A pasted reference list, a `.bib`/`.ris` file, or a claims CSV
are all direct inputs.

## Use from Python

The whole tool is one stdlib module — import it without installing
anything (full reference: `references/python_api.md`):

```python
import sys
sys.path.insert(0, "/path/to/pubmed-verifier/scripts")
import verify_pmids as vp

info = vp.fetch_summaries(["31018962"], batch_size=1)["31018962"]
cross = vp.cross_check_citation(
    {"claimed_title": "Classification criteria for autoinflammatory recurrent fevers",
     "claimed_year": "2019"},
    {"title": info["title"], "authors": info["authors"],
     "journal": info["journal"], "pubdate": info["pubdate"]})
print(cross["verdict"], round(cross["confidence"], 2))
```

## The five-state verdict

| Verdict | Meaning |
|---------|---------|
| ✅ Correct | PMID exists AND matches the claimed paper |
| ⚠️ Mismatch | PMID exists but points to a **different** paper (the most common AI hallucination!) |
| 🔶 Partial | Some metadata matches (e.g. author+journal but title differs) |
| ❌ Invalid | PMID does not exist in PubMed |
| ❓ Unknown | Not enough claimed metadata to cross-check — or both data sources unreachable (never misreported as invalid) |

**Why existence checks are not enough:** a large share of fabricated
citations use REAL PMIDs that point to a different paper from the same
year/journal/field — in one of our own audits, 4 of 5 "valid" PMIDs were
wrong this way. A binary exists/not-exists check misses them all.

## Quick start

```bash
# Scan a project directory for PMIDs (parses citation context automatically)
python3 scripts/verify_pmids.py --source /path/to/project --output report.html

# Verify specific PMIDs
python3 scripts/verify_pmids.py --pmids 31018962,22213727

# Mismatch demo: PMID 34078778 is actually a dental-materials paper, so the
# JIA claims below will NOT match it — expect ⚠️ mismatch verdicts
python3 scripts/verify_pmids.py --claims '[{"pmid":"34078778","title":"JIA pathogenesis","authors":["Zaripova"],"journal":"Pediatr Rheumatol Online J","year":"2021"}]' --output report.html

# Claims from a CSV file + suggest correct PMIDs for mismatches
python3 scripts/verify_pmids.py --claims-file claims.csv --suggest --output report.html

# Crossref DOI cross-verification + audit working-paper + BibTeX + full pipeline
python3 scripts/verify_pmids.py --source /path/to/files --verify-doi --suggest --output report.html --export-audit audit.json --export-bibtex refs.bib

# Verify DOIs directly (no PMIDs) + delta audit vs a previous run
python3 scripts/verify_pmids.py --dois "10.1038/nature12968,10.4012/dmj.2020-408" --workers 4 --export-audit audit.json --export-csv table.csv
python3 scripts/verify_pmids.py --source /path/to/project --diff audit.json --output report.html

# Verify arXiv IDs (preprints) — mixed audits supported
python3 scripts/verify_pmids.py --arxivs "2401.12345,cs/0211004" --no-cache

# Pre-flight: are the five data sources reachable right now?
python3 scripts/verify_pmids.py --check-net

# Audit a BibTeX or RIS bibliography file directly (PMID > DOI > arXiv routing)
python3 scripts/verify_pmids.py --bibliography refs.bib --no-cache
python3 scripts/verify_pmids.py --bibliography refs.ris --no-cache --export-ris verified.ris

# Verify a reference list copied from a paper draft (inline IDs route
# exactly; title-only entries resolve via PubMed title search)
python3 scripts/verify_pmids.py --parse-text references.txt --no-cache

# Format the verified entries as a ready-to-paste reference list
# (--citation-style: gbt | vancouver | apa | ama; default gbt)
python3 scripts/verify_pmids.py --parse-text references.txt --format-references refs_gbt.txt --citation-style gbt

# Institutional niceties (recommended): NCBI API key + contact email
python3 scripts/verify_pmids.py --source . --verify-doi --ncbi-api-key $NCBI_API_KEY --mailto you@lab.org
```

## What the output looks like

Terminal text report (verdict line, then per-citation evidence):

```
Readiness: NOT SUBMISSION-READY — 1 invalid, 1 mismatched
Results: 1/3 correct, 1 mismatch, 1 invalid, 0 partial, 0 unknown
============================================================

✅ PMID 31018962 (claims) [correct]
   Actual: Classification criteria for autoinflammatory recurrent fevers
   Claimed: Classification criteria for autoinflammatory recurrent fevers
   Evidence: title ✓ · author ✓ · journal ✓ · year ✓

⚠️ PMID 34078778 (claims) [mismatch]
   Actual: Effect of CAD/CAM materials on the marginal fit of crowds
   Claimed: JIA pathogenesis and treatment
   → Suggest: PMID 34425842 - Juvenile idiopathic arthritis: from aetio...
   Evidence: title ✗ · author ✗ · journal ✗ · year —

❌ PMID 99999999 (cli) [invalid]
   Error: PMID not found in API response
```

`--output report.json` carries the same verdicts plus the full evidence
chain per citation (`evidence.title_match / author_match / journal_match /
year_match`, `fields` tri-state, `meta_source` naming which registry
answered, `resolved_by` when the title-search/OpenAlex legs matched) and a
`stats` block with the submission-readiness verdict. `--format-references`
writes the ready-to-paste citation list shown in the v4.0.0 section.

## FAQ & common mistakes

**Top 10 things NOT to do** (each is detailed below or in Anti-patterns):

| # | Don't | Do instead |
|---|-------|------------|
| 1 | Treat `--pmids` existence output as "verified" | Feed `--claims-file` with titles for real verification |
| 2 | Submit claims without `title` | Always include titles — the verdict caps at partial without one |
| 3 | Trust cached verdicts on publication day | Final check with `--no-cache` |
| 4 | Read "not found" as "fabricated" for auto-extracted DOIs | Check doi.org / arxiv.org by hand first |
| 5 | Treat the leading `'` in CSV cells as corruption | It is the formula-injection guard — strip after import |
| 6 | Read the READY line as a quality score | It means "no problems among the checks that ran" |
| 7 | Pass `--source` together with `--pmids` | `--source` is ignored entirely when `--pmids` is given |
| 8 | Deep-verify (`--verify-doi` / `--suggest`) a thousand-entry sweep | Sweep first, deep-verify the flagged subset |
| 9 | Expect author matching across CJK↔Latin names | They are skipped honestly (`author_check: skipped`) |
| 10 | Ship a reference list without the audit trail | `--export-audit` writes a replayable working paper |

**Large batch (hundreds of PMIDs) is slow — how to speed it up?**
Metadata-only verification queries in batches of 50 with 0.4 s spacing
(0.12 s with `--ncbi-api-key`); cached re-runs are ~5 s. `--verify-doi` adds
one Crossref call *per citation* and `--suggest` adds one search *per
mismatch* — skip them for bulk sweeps, run them on the flagged subset.

**When must I use `--claims-file` instead of scanning?**
Context parsing is heuristic (v3.3.0 guards common abbreviations, exotic formatting can still mis-split).
For precise verification — or DOIs in claims (splice detection needs `doi`)
— feed structured JSON/CSV claims.

**My citation text is in Chinese — the scan parses little?**
GB/T 7714-style references (……标题[J]. 刊名, 年… PMID: xxx) parse since
v3.9.0 — title/journal comparisons against Latin registries are skipped
cross-language, so verdicts rest on year/DOI evidence. Free Chinese prose
without a PMID marker still yields little — feed `--claims-file` for full
verdicts regardless of language.

**Slow or unstable network (China)?**
Standard `HTTPS_PROXY`/`HTTP_PROXY` env vars are honored natively; raise
`--timeout`; `--meta-source europepmc` routes via Europe PMC when NCBI is
unreachable (per-entry `meta_source` shows which was used); cached results
are reused for 30 days.

**❓ unknown vs ❌ invalid?**
`unknown` (exit 2) = "could not verify, sources unreachable" — retry later;
`invalid` (exit 1) = "verified not-found". Network failures are never
reported as not-found and never cached.

**What does RETRACTED mean in a report?**
The registry itself lists the paper's publication type as "Retracted
Publication" (checked for every citation since v2.7.0 — no DOI or flags
needed), and/or Crossref records a retraction. The verdict is capped at
partial and a human review note is attached — citing it would propagate
withdrawn science. A retraction *notice* is never flagged; papers under
*Expression of Concern* (an editorial note, not a retraction) are not
flagged either. Retraction status reflects the registry at cache time — for
a final pre-submission check, run with `--no-cache`.

**Mismatch reported but the title looks similar?**
Check `details` for which field diverged; thresholds are strict on purpose.
Feed the full citation via `--claims-file` for a precise verdict.

**Can I audit my .bib or .ris file directly?**
Yes — `--bibliography refs.bib` (BibTeX) and `--bibliography refs.ris`
(RIS/Zotero/EndNote/Mendeley) route each entry by PMID > DOI > arXiv
and cross-check the claimed metadata. `--lint-claims` validates either
format offline first. The round trip works both ways: `--export-bibtex`
and `--export-ris` output can be fed back after edits.

**My claims file seems to lose rows / verdicts look weaker than expected?**
Lint it offline first: `python3 scripts/verify_pmids.py --lint-claims
claims.csv` reports unusable rows, ID shape errors, unknown columns
(typo'd headers like "titel"), missing titles and DOI prefix problems —
no network, exit 1 on errors.

**Can I verify a DOI with claimed metadata (full verdict)?**
Yes — since v3.4.0 a claims row keyed by `doi` (with `title`, optionally
`authors`/`journal`/`year`) gets the same cross-check as PMID claims:
correct / mismatch / partial against the registered metadata. A DOI row
without claims stays `unknown` (existence only).

**Why did my arXiv citation drop from correct to partial?**
Your claims row paired an `arxiv_id` with a `doi`, and the DOI does not
match the version-of-record DOI registered on that arXiv entry — a typo,
or a DOI from a different paper. The registered DOI is in `details`;
fix the claim or drop the `doi` cell.

### Worked scenarios

- **"The reviewer asked how I checked my references."** — run the audit
  with `--export-audit audit.json --verify-doi`: the JSON working-paper
  contains tool identity, version, the exact (API-key-redacted) invocation,
  and the per-citation evidence chain a reviewer or editor can replay.
  Submit it alongside the manuscript.
- **"Checking the reference list of my thesis."** — copy the list into a
  plain-text file (one reference per line, or keep the `[1]` numbering) and
  run `--parse-text refs.txt`: inline PMIDs/DOIs route exactly; English
  entries resolve via PubMed title search; Chinese entries resolve via the
  OpenAlex CJK leg. Finish with
  `--format-references refs_clean.txt --citation-style gbt` for a corrected,
  uniformly formatted list.
- **"Screening a systematic review's bibliography (PRISMA)."** — verify the
  full list once, export the audit as the baseline, then re-run
  `--diff audit.json` before each resubmission: newly retracted, degraded
  and new citations are reported as deltas, so you only re-read what
  changed.

## Anti-patterns — things done WRONG

Each entry: the mistake → why it fails → the right way.

1. **Treating `--pmids` output as "fully verified"** — existence-only.
   → Wrong: "all 5 PMIDs exist, so the citations are correct."
   → Right: existence-checked only; feed `--claims-file` with titles for
   real verification (the READY line says so explicitly).
2. **Claims without `title`** — author/journal/year alone can never reach
   `correct`; the report caps at `partial`. → Always include titles.
3. **Trusting a cached verdict right after publication day** — a brand-new
   PMID may have been cached as not-found by an earlier run, and retraction
   status is as of cache time. → Final pre-submission check: `--no-cache`.
4. **Assuming "not found" always means fabricated** — a Crossref 404 is
   re-checked at OpenAlex (DataCite/Zenodo/Chinese-registry DOIs live
   there), so "unknown in both registries" is now the bar; auto-extracted
   DOIs that 404 in both stay *suspects*. arXiv IDs removed by moderators
   also return empty. → Check doi.org / arxiv.org by hand before accusing.
5. **Copying the leading `'` from CSV cells** — that apostrophe is the
   formula-injection guard, not data corruption. → Strip it after import.
6. **Reading the READY line as a quality score** — it only means "no
   problems found among the checks that ran", not "this paper is good".

## Boundaries — declared limits

What this tool can NOT do, consolidated in one place:

- **Splice/mismatch signals report disagreement, never pick a side** —
  when claim and registry disagree, a human reads the evidence line.
- **Cross-language authors are skipped, not failed** — CJK↔Latin author
  names are never compared (`author_check: skipped`); the verdict rests
  on title/journal/year alone.
- **Context parsing is heuristic** — v3.3.0 keeps common abbreviations
  (U.S., e.g., vs., St., Vol., No.) from splitting a title, but exotic
  formatting can still mis-split; for exact metadata use `--claims-file`.
- **DataCite/repository DOIs are not in Crossref — OpenAlex covers them**
  (v4.1.0): a Crossref 404 now gets a second look at OpenAlex; only when
  BOTH registries report the DOI unknown do the 404 semantics apply
  (`--dois`/claims = invalid, auto-extracted = suspect). Resolved-via-
  OpenAlex entries carry `meta_source: openalex`.
- **arXiv moderator removals also return "not found"** — the invalid
  verdict carries that caveat in its details.
- **Retraction status is as-of-cache-time** — final pre-submission
  checks should run with `--no-cache`.
- **Single-letter initials never match** — "Smith J" vs "Smith John" is
  not counted as a miss.
- **unknown ≠ invalid** — unreachable sources yield exit 2 and
  `unknown`; network failures are never reported as "not found" and
  never cached.
- **arXiv pacing is deliberate** — the official API asks for ≥3 s
  between calls; large arXiv batches are slow by design (progress + ETA
  on stderr). Entries that register a version-of-record DOI add one
  Europe PMC lookup each for the PMID link.
- **DOI claims compare against the registry that actually answered** —
  the linked PubMed record when the DOI resolves to one, Crossref
  otherwise (Crossref author fields are sparser, so the author mark is
  more often "—"); a DOI row without a claimed title stays `unknown`,
  not partial; an explicitly user-provided DOI (`--dois` or claims) that
  is missing from Crossref counts as invalid.

## Claims reference format

`--claims-file` accepts JSON (an array of objects) or CSV. Recognized
columns: `pmid`, `title`, `authors` (semicolon/pipe-separated),
`journal`, `year`, `doi`, `arxiv_id`. A row needs one of `pmid`,
`arxiv_id` or `doi`; a missing `title` caps the verdict at partial.

```csv
pmid,title,authors,journal,year,doi,arxiv_id
31018962,Candidate criteria for diagnosis of familial...,Gattorno,Ann Rheum Dis,2019,10.1136/annrheumdis-2019-215048,
,Attention Is All You Need,Vaswani,NeurIPS,2017,,1706.03762
,City size and the spreading of COVID-19 in Brazil,Silva Junior;Other,PLOS ONE,2020,10.1371/journal.pone.0239699,
```

Validate any file offline first: `--lint-claims file.csv` reports
unusable rows, ID shape errors, unknown columns, duplicates and missing
titles (no network). Lint wins when combined with verification flags —
only the lint runs.

## Best practices & tuning

- **Speed up large batches** — request an NCBI API key (see
  https://ncbiinsights.ncbi.nlm.nih.gov/api-keys/): batches of 50 IDs run
  at 0.12 s spacing instead of 0.4 s; cached re-runs take seconds.
- **Parallel DOI verification** — `--workers` (default 4, cap 8) applies to
  Crossref resolution and Europe PMC linking; arXiv stays serial by
  official etiquette (≥3 s between calls).
- **Two-phase workflow** — sweep with metadata-only verification first
  (no `--verify-doi`, no `--suggest`), then deep-verify only the flagged
  subset; each deep flag adds one API call per citation.
- **Round-trip bibliographies** — `--export-bibtex` / `--export-ris`
  write verified entries; after edits, `--bibliography refs.bib` /
  `refs.ris` re-audits the file (the PMID re-links the full record).
- **Claims over context parsing** — whenever you know the expected titles,
  feed `--claims-file`: it enables the full verdict ladder and the DOI /
  arXiv pairing checks. Validate the file offline first:
  `python3 scripts/verify_pmids.py --lint-claims claims.csv` reports ID
  shape errors, missing titles, unknown columns and duplicates without any
  network access.
- **Flaky networks** — raise `--timeout`; HTTPS_PROXY/HTTP_PROXY are
  honored natively; unreachable NCBI falls back to Europe PMC
  automatically (`meta_source` shows which answered).
- **Cache policy** — results cache 30 days, negative entries 3 days;
  `--cache-days` to tune; `--no-cache` for the final pre-submission pass.
- **Scale expectations** — metadata-only throughput is API-bound
  (~1–2 min per 1000 PMIDs with an API key); DOI resolution adds one
  Crossref call per DOI. One deliberate trade-off: the verifier is a
  single stdlib-only file — copy `scripts/verify_pmids.py` anywhere with
  Python 3.9+ and it runs, no pip, no venv (that portability is why the
  code is not split into modules).

## v2.2.0 — network hardening

| Feature | Flag | Effect |
|---------|------|--------|
| NCBI API key | `--ncbi-api-key` / env `NCBI_API_KEY` | Rate ceiling 3→10 req/s, batch interval 0.4s→0.12s (~3x faster) |
| Europe PMC fallback | `--meta-source auto\|ncbi\|europepmc` | NCBI batch failure automatically retries via Europe PMC (free, no key); per-entry origin in JSON (`meta_source`) |
| Crossref polite pool | `--mailto` / env `PUBMED_VERIFIER_MAILTO` | `?mailto=` on Crossref + tool/email params on NCBI — more generous limits |
| Retry-After backoff | automatic | 429 responses honored (clamped 1–5 s) instead of failing |
| UA rotation | automatic | 403/406 retried with a browser User-Agent |
| Host circuit breaker | automatic | After 2 call-level transport failures a host is skipped with an actionable message; success resets; HTTP errors never trip it |
| Honest unknown | automatic | Network failures report as ❓ unknown + exit code 2, never as "PMID not found", and are never cached |

**Exit codes:** `0` clean · `1` problems found (invalid / mismatch / retracted /
DOI-splice, incl. arXiv claimed-DOI pairing mismatches) · `2` could not verify
(data sources unreachable) — automation can tell "all good" from "no answer".

## v2.3.0 — retraction detection

With `--verify-doi`, each cited DOI is also checked against Crossref's
withdrawal records (`updated-by`). A paper Crossref lists as RETRACTED is:

- flagged in JSON (`retracted: true` + `retraction_note`) and in reports,
- **capped at 🔶 partial** even when every metadata field matches — citing a
  retracted paper is never "correct"; the report says *human review required*.

Corrections and other update types do not trigger the cap. Crossref outages
never flag anything (a missing check is not a retraction).

## v2.4.0 — DOI↔PMID cross-check & journal abbreviations

- **DOI splice detection**: add a `doi` field to your claims (JSON or CSV).
  The claimed DOI is compared with the DOI registered for that PMID — a
  mismatch is a splice/fabrication signal (a real DOI attached to the wrong
  paper): flagged in JSON (`doi_splice_suspect`), verdict capped at 🔶
  partial, counted in exit 1. Uses the PubMed record only — no extra API call.
- **Journal abbreviation equivalence**: journal matching now understands
  NLM-style abbreviations in both directions — "N Engl J Med" matches "New
  England Journal of Medicine", "Pediatr Rheumatol" matches "Pediatric
  Rheumatology" (in-order word prefixes, function words skipped). No more
  false "journal differs" for abbreviated citations.

Known limits: highly ambiguous abbreviations can over-match at the
journal-only level ("J Immunol" ~ "Journal of Immunology Research") — the
title remains the decisive field. A DOI-splice flag can also appear on an
otherwise-unverifiable citation (the DOI mismatch is an independent fact).

## v2.5.0 — author-name verification

- **Initials never match**: single-letter tokens ("A.", "L.") on either side
  are excluded from surname matching — an initial is not evidence, and
  substring-matching one produced false author hits.
- **Cross-language honesty**: CJK author names claimed against Latin
  registry records (or the reverse) are skipped, not counted as a mismatch —
  the report marks them `author_check: skipped` and the verdict falls back
  to what was actually comparable (title/journal/year), or to ❓ unknown
  when nothing else is checkable.

## Security & behavior declaration

- Single-run CLI: scan, verify, write the report, exit. No daemons, no
  background jobs, nothing downloaded or installed at runtime (pure standard
  library, zero dependencies).
- Network access is limited to these official academic registries, always
  over HTTPS: `eutils.ncbi.nlm.nih.gov`, `www.ebi.ac.uk` (Europe PMC),
  `api.crossref.org`, `api.openalex.org`, `export.arxiv.org` — no other
  hosts are contacted; no telemetry, no
  analytics, no data collection — the only outbound payloads are the PMIDs,
  DOIs and titles you asked to verify.
- Your files and reports stay on your machine. Writes are limited to the
  report paths you pass and the SQLite cache under
  `~/.cache/pubmed-verifier/` (`--no-cache` to disable).
- Optional environment variables `NCBI_API_KEY` / `PUBMED_VERIFIER_MAILTO`
  authenticate or attribute your own API requests and are never sent
  anywhere else.
- No OS integration: no subprocesses, no system services, no privilege
  changes, no scheduled tasks.

## v2.6.0 — audit working-paper & report v2

- **`--export-audit audit.json`** — a self-contained JSON working-paper for
  transparent review: tool identity and version, the exact (API-key-redacted)
  invocation, per-citation evidence chains (claimed vs registered fields,
  title match scores from both algorithms, author match with cross-language
  skip records, DOI cross-check, retraction signals) and the
  verdict-ladder trace for every citation. A reviewer can replay the entire
  verification from this file alone.
- **HTML report v2** — verdict filter tabs, severity-sorted rows (retracted
  and DOI-splice first, highlighted), a field-level evidence column
  (title/author/journal/year ✓✗—) and a reproducibility footer (redacted
  command line + version + data sources).
- **Reliability** — negative cache entries now expire after 3 days (a
  legitimately new, ahead-of-print PMID is no longer reported "not found"
  for a month), and the circuit breaker self-heals: after a 30 s cooldown it
  admits one probe call and resets on success.

## v2.7.0 — retraction for every PMID, BibTeX export, readiness verdict

- **Retraction detection, source-independent** — the registry's own
  publication type ("Retracted Publication"; present in both NCBI esummary
  and Europe PMC) now flags retracted papers for EVERY citation: no DOI
  required, no `--verify-doi` required, and the flag survives the cache
  (schema v3). Crossref `updated-by` remains the detail source (the
  retraction-notice DOI) when `--verify-doi` is on. A retraction *notice*
  itself is never flagged.
- **`--export-bibtex refs.bib`** — export the verified bibliography: correct
  entries as `@article`, partial entries commented out with their divergence
  note, mismatched/invalid/unknown/retracted entries excluded and counted.
- **Submission-readiness verdict** — every report now leads with one line:
  `SUBMISSION READY` or `NOT SUBMISSION-READY — <per-problem counts>`.
- Cache schema v3 (adds a `retracted` column, auto-migrated).

## v2.8.0 — DOI-native verification & delta audits

- **`--dois "10.x/a, 10.y/b"`** — verify DOIs natively, no PMID required.
  `--source` scans now also extract DOIs from your files automatically.
  Each DOI is resolved via the Crossref works API: not-found on an explicitly
  provided DOI = fabrication signal (invalid, exit 1); on one auto-extracted
  from scanned text it stays a suspect (unknown) — scanned strings are never
  user-endorsed, and DataCite/repository DOIs do not live in Crossref, so
  always double-check at doi.org. Resolved = existence confirmed with the
  registered metadata attached for manual comparison — *existence is never
  dressed up as a match*.
- **`--diff previous-audit.json`** — delta audit against a previous working
  paper: **newly retracted** (the safety signal — a paper retracted after
  your last audit; act on it: swap or drop the citation, cite the retraction
  notice instead, and re-check any conclusion that relied on it), degraded,
  improved, new and dropped citations, with counts in every report format.
  Built for periodic knowledge-base audits: "what changed since last time?"

## v2.9.0 — DOI entries become first-class

- **DOI→PMID linking** — a resolved DOI is linked back to its PMID via the
  Europe PMC DOI field query, pulling the full PubMed record: complete
  metadata, retraction pubtype signal, and cache coverage. A DOI citation
  now gets the same five-state record as a PMID citation (existence
  confirmation only — the verdict remains unknown until claims are
  provided).
- **Parallel DOI resolution** — `--workers N` (default 4, max 8) resolves
  DOI batches on a thread pool (roughly 3x faster on large lists), with
  live progress output. For large `--dois` batches, set `--mailto` to stay
  in Crossref's polite pool.
- **`--export-csv table.csv`** — spreadsheet-friendly audit table
  (key/verdict/flags/fields/details; formula-injection hardened).

## v3.0.0 — arXiv ID verification (three citation types, one audit)

Reference lists carry preprints. v3.0.0 verifies **arXiv IDs** alongside
PMIDs and DOIs: `arXiv:2401.12345` and `arxiv.org/abs/...` patterns are
extracted from scans (or passed via `--arxivs`), checked against the
official arXiv API, and judged — nonexistent ID = fabrication signal
(invalid, exit 1); resolving ID = registered title/year attached, verdict
stays unknown. Malformed IDs (bad YYMM month) are flagged by shape.
Timely: arXiv penalizes submissions containing hallucinated or unverified
references (2026-05 policy) — audit before you submit.

## v3.3.0 — preprint ↔ published-version cross-check

arXiv entries carry the version-of-record DOI their authors registered at
publication (`arxiv:doi`). v3.3.0 puts it to work:

- **Claimed DOI vs registered DOI** — a claims row with both `arxiv_id`
  and `doi` is cross-checked: agreement is reported as evidence
  (`fields.doi ✓`); disagreement caps the verdict at `partial` — the DOI
  belongs to a different paper (same failure class as PMID DOI-splice).
- **Version of record surfaced** — verifying a bare preprint ID now shows
  the registered DOI and, when the published version is PubMed-indexed,
  its linked PMID — cite and verify the final version, not just the
  preprint.
- **Honest accounting** — the readiness line counts arXiv DOI-pairing
  mismatches as problems; DOI/arXiv phase progress (stderr) now includes
  elapsed time and an ETA for large batches.
- Context parsing no longer truncates titles at sentence-internal
  abbreviations ("U.S. population", "e.g.", "vs.", "Vol.").

Pairing example (match → correct with DOI evidence; wrong DOI → partial):

```bash
python3 scripts/verify_pmids.py --claims '[{"arxiv_id":"2005.13892",
  "title":"City size and the spreading of COVID-19 in Brazil",
  "doi":"10.1371/journal.pone.0239699"}]'
```

## v3.4.0 — DOI claims become first-class

Claims rows could carry a PMID or an arXiv ID — a row keyed by DOI alone
was silently ignored, and DOI entries always stayed `unknown` ("no claimed
metadata to cross-verify"). v3.4.0 closes the matrix: all three citation
types now accept claimed metadata.

- A claims row with a `doi` (no PMID, no arXiv ID) is cross-checked against
  the registered metadata — the linked PubMed record when the DOI resolves
  to one, Crossref otherwise — and gets the full verdict ladder:
  correct / mismatch / partial.
- Retraction capping applies as everywhere: a claimed-correct match on a
  retracted paper is capped at partial with the retraction note.
- Without claims, DOI entries stay unknown — existence is never dressed up
  as a match.

```bash
python3 scripts/verify_pmids.py --claims '[{"doi":"10.1371/journal.pone.0239699",
  "title":"City size and the spreading of COVID-19 in Brazil",
  "journal":"PLoS ONE","year":"2020"}]'
```

## v3.5.0 — claims lint & usage-first restructuring

- **`--lint-claims FILE`** — offline pre-flight for claims files
  (JSON/CSV, zero network): ID shape errors, missing titles (the verdict
  would cap at partial), unknown/typo'd columns, DOI prefix checks,
  unusable rows — exit 1 on errors. Fix the format before the run
  instead of guessing from weak verdicts.
- **Documentation restructured around usage**: FAQ, anti-patterns and
  declared boundaries now sit right after Quick start, led by a Top-10
  "don't do this" table; new **Best practices & tuning** section (API-key
  batching, worker tuning, two-phase deep-verification, cache policy,
  scale expectations — and why the verifier is deliberately one file).

## v3.6.0 — BibTeX bibliography audit

**`--bibliography refs.bib`** audits a .bib file directly: entries route by
PMID (the `pmid` field, or a "PMID: NNNN" in the note — including the
notes `--export-bibtex` itself writes) > DOI > arXiv (`eprint`, or an
"arXiv:XXXX.XXXXX" in the journal/note), each carrying its claimed
title/authors/journal/year for the full cross-check. Entries without any
routable ID are counted and skipped. This closes the loop with
`--export-bibtex`: a verified bibliography can be re-audited after edits.
`--lint-claims refs.bib` validates the file offline (unroutable entries,
missing titles, unclosed blocks).

## v3.7.0 — RIS bibliography support

`--bibliography` now accepts **RIS files** (`refs.ris` — Zotero/EndNote/
Mendeley exports) alongside BibTeX: records route by PMID (AN tag, or a
"PMID: NNNN" note) > DOI (DO) > arXiv (UR/eprint), each with claimed
metadata for the full cross-check. **`--export-ris`** completes the loop —
verified entries as `TY JOUR`, partials as `TY DATA` with a PARTIAL note.
`--lint-claims refs.ris` validates offline (unroutable records, missing
titles, duplicates, unterminated records).

## v3.8.0 — verdict-ladder corrections (independent external test audit)

An independent real-data audit (24 scenarios, registry-ground-truthed) found
three judgment-ladder defects; all three are fixed and locked:

- **B1 scan false positives** — when a citation is not the first sentence of
  its block, the author line was taken as the claimed title (correct
  references reported as mismatch). The parser now shifts past an
  author-shaped segment.
- **B2 author mis-attribution** — a claimed author set entirely different
  from the registry (zero surname overlap) was still reported as correct
  when title and journal matched; it now caps at partial. Partial surname
  overlap (abbreviated or reordered names) keeps correct.
- **B3 title-less claims** — author+journal+year matches without a claimed
  title now cap at partial, exactly as the FAQ/anti-patterns/boundaries
  always promised (the same author/journal/year can cover several papers).
  Cross-language author skips follow the same cap.
- Also: duplicate arXiv IDs announce their merge on stderr (run
  `--lint-claims` to catch duplicate claim rows offline); the
  cross-language skip no longer coexists with contradictory details text;
  empty `--claims` gets a one-line hint; docs state that Chinese-language
  citation contexts parse weakly — use `--claims-file`.

## v3.9.0 — Chinese references (GB/T 7714), network pre-flight, Python API

- **GB/T 7714 Chinese references parse** — `……标题[J]. 刊名, 年… PMID: xxx`
  contexts now yield the title (via the `[J]/[M]/[R]` type marker),
  authors, journal, year and any DOI that follows the PMID. The title
  comparison against a Latin registry title is skipped cross-language
  (never a mismatch source); a DOI in the reference is cross-checked
  against the registry like any claims DOI. Requires a PMID marker per
  reference.
- **`--check-net`** — probes the data sources (5 s each), shows your
  proxy state and prints practical next steps when something is
  unreachable. Run it when results come back unknown on a constrained
  network.
- **Python API reference** — `references/python_api.md` documents the
  stable importable surfaces (`fetch_summaries`, `cross_check_citation`,
  `verify_doi_entry`, `parse_citation_context`, `suggest_correct_pmid`)
  with copy-paste examples.

## v4.0.0 — plain-text reference lists & formatted reference list export

- **`--parse-text refs.txt`** — verify a reference list copied straight out
  of a manuscript draft. Numbered entries (`[1]`, `1.`) split cleanly;
  inline PMID / DOI / arXiv IDs route exactly (full five-state
  cross-check); a markerless entry with a parseable title resolves via
  PubMed title search and is marked `resolved_by: title_search` — weaker
  evidence than a supplied ID, honestly labeled, and never a mismatch
  source. A network failure stays unknown with a retry hint, never
  "not found". Entries with no routable ID and no usable title are
  skipped with a note instead of being guessed.
- **`--format-references out.txt --citation-style gbt|vancouver|apa|ama`**
  — the formatting leg of verify-then-format: verified entries rendered as
  a ready-to-paste numbered reference list (GB/T 7714-2015 numeric for
  Chinese submissions, Vancouver, APA 7th, AMA 11th). Formatting stands on
  registry-verified records only: correct entries form the list, partial
  entries go to a manual-review section (never silently dropped), and
  retracted entries are excluded with a warning. Author lists are
  formatted per style without inventing names — a registry-truncated list
  closes with the style's et-al form, and APA discloses the truncation.
- Markerless Latin references now parse through the full sentence
  segmentation (titles feed the title-search leg); CJK entries without a
  PMID/DOI marker keep the documented weak-parsing boundary — supply a
  PMID or DOI for exact routing.
- `examples/refs_list.sample.txt` ships a ready-made parse-text fixture.

## v4.1.0 — OpenAlex fallback & Chinese-reference title search

- **OpenAlex is now the fourth data source** — a DOI that Crossref reports
  404 gets a second look at OpenAlex before any verdict: DataCite, Zenodo,
  SSRN and Chinese-registry DOIs (which do not live in Crossref) become
  fully decidable — resolved, metadata attached, claims cross-checked,
  retractions flagged (`is_retracted`). Only when OpenAlex also comes up
  empty do the original 404 semantics stand (explicit DOI = invalid,
  scanned DOI = suspect). `--check-net` probes five sources now.
- **Chinese references without any ID can now be verified** — a markerless
  CJK entry in `--parse-text` searches OpenAlex by its title (the query is
  the title-shaped segment of the entry, not the whole line); a candidate
  counts only when its registered title appears **verbatim** in your entry
  text with an agreeing year, and the verdict carries
  `resolved_by: openalex_cjk_search`. No hit = honestly unknown; this leg
  never manufactures a mismatch, and a network failure stays unknown.
- Docs: the reports' actual shape is now shown in "What the output looks
  like"; three worked scenarios added to the FAQ (reviewer evidence,
  thesis citation check, PRISMA screening).

## v4.2.0 — retraction replacement suggestions & delta detail panel

- **Retraction replacement suggestions** (`--suggest`) — a retracted entry
  now comes with up to three same-topic live candidates (retracted papers
  and the entry's own PMID excluded), marked `replacement_for_retracted`
  and carrying an honest note: they are search suggestions, NOT verdicts —
  verify each before citing. Answers the reviewer question "this paper is
  retracted, what should I cite instead?" at audit time.
- **Delta audits now show their full detail** — alongside the counts
  line, the HTML report renders a per-category panel (newly retracted /
  degraded / improved / new / dropped, up to 50 rows each); the markdown
  report lists degraded/improved/new/dropped rows too. Built for PRISMA
  re-runs: you only re-read what changed.
- `--check-net` masks proxy credentials (`http://user:****@host:port`) so
  the pre-flight output is paste-safe.
- Docs: "Trigger words" and "Use from Python" sections moved up front.

## How it works

1. **Extract + parse context** — finds `PMID: 12345678` / PubMed URLs in
   `.html .md .txt .htm .json`, and parses the surrounding reference into
   claimed authors / title / journal / year.
2. **Fetch metadata (cached)** — PubMed esummary in batches of 50, SQLite
   cache (30 days, `--cache-days`), 3 retries with backoff.
   Europe PMC steps in per failed batch when NCBI is unreachable.
3. **Cross-check claimed vs actual** — dual fuzzy matching: word-level
   Jaccard overlap ≥ 50% OR SequenceMatcher ≥ 90% on titles; author surname
   hits; journal containment or NLM abbreviation equivalence; exact year.
4. **DOI↔PMID cross-check** (automatic when claims include `doi`) — a claimed
   DOI differing from the PMID's registered DOI is a splice/fabrication
   signal (capped at partial).
5. **Crossref DOI verification** (optional `--verify-doi`) — resolves each
   cited DOI via Crossref, compares the registered title with the PubMed
   record (`doi_title_match` in JSON), and detects RETRACTED papers (verdict
   capped at partial). A `doi_verified: false` with note
   "crossref unreachable" is a network fact, not a verdict.
6. **Suggest the right PMID** (optional `--suggest`) — for mismatches,
   searches PubMed with the claimed metadata and proposes top-3 candidates.
   (Suggestion search always uses NCBI, even with `--meta-source europepmc`.)

Context parsing is heuristic — since v3.3.0, common abbreviations
("U.S.", "e.g.", "vs.") no longer split a title, but exotic formatting
still can. For precise verification, feed structured claims via
`--claims-file`.

| Report | Flag | Use |
|--------|------|-----|
| HTML | `--output report.html` | Human review: claimed vs actual side by side |
| JSON | `--output report.json` | Programmatic processing (includes `meta_source` per entry) |
| Text | default | Quick terminal look |

## Performance

Measured on a 225-PMID audit (5 esummary batches): metadata-only verification
runs in seconds; cached re-runs take ~5 s. Each batch waits 0.4 s between
calls (0.12 s with `--ncbi-api-key`). Optional extras are per-citation:
`--verify-doi` adds one Crossref call (~0.5–1 s) per cited DOI, and
`--suggest` adds one PubMed search per mismatch.

## When to use which tool

- **pubmed-verifier (this skill)** — fast, batch, targeted: I have a list of
  PMIDs/DOIs and need to know if they are real and correctly cited.
- **cite-holmes** — deep research: interrogate every citation of a whole
  document across multiple databases, with graded confidence reports.

They share the same five-state philosophy and are safe to use together.

## Use cases

- Systematic review / meta-analysis reference audits
- Verifying citations in AI-generated content
- Pre-submission self-check of a manuscript's reference list
- Medical knowledge base / teaching material QA
- Pharmacovigilance literature verification

## Related tools

Each tool solves one step of reference work; use whichever fits the task.

- **cn-med-oa** — free Chinese medical literature full-text download & metadata
- **cite-holmes** — deep research with machine-verified citations
- **paper-polisher-pro** — academic polishing, terminology & journal precheck
- **academic-figures** — publication-ready scientific figures in one command
- **doc-holmes** — layout-preserving PDF translation (in testing)

Typical order: get papers (cn-med-oa), verify citations (this tool or
cite-holmes), polish (paper-polisher-pro), make figures (academic-figures),
translate PDFs (doc-holmes) — pick whichever step you need.

## Files

| File | Purpose |
|------|---------|
| `scripts/verify_pmids.py` | Main verifier (v4.2.0, stdlib-only) |
| `references/api_examples.md` | PubMed / Europe PMC / Crossref / arXiv API notes |
| `references/python_api.md` | Calling the verifier from Python (stable surfaces + examples) |
| `examples/claims.sample.csv` | Reference format for `--claims-file` (incl. a DOI-only row) |
| `examples/refs.sample.bib` | Sample bibliography for `--bibliography` (DOI/PMID/arXiv routing) |
| `examples/refs.sample.ris` | Sample RIS bibliography (Zotero/EndNote/Mendeley) |
| `tests/` | Offline matrix + real-network acceptance (repo only, not in the package) |

## License

MIT-0 — free to use, modify and redistribute, no attribution required.
