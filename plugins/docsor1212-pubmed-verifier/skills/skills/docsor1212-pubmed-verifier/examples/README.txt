claims.sample.csv — reference format for --claims-file

- pmid column: PubMed pipeline (full five-state verification)
- rows with only arxiv_id (+title): arXiv pipeline (official API check)
- doi column: DOI-splice cross-check against the PubMed-registered DOI
  (PMID rows) / version-of-record pairing check (arXiv rows, v3.3.0) /
  full five-state verdicts (doi-only rows, v3.4.0)
- title: required for verdicts beyond existence-check
- expected verdicts (as of v3.4.0): the 31018962 row carries a
  deliberately inexact title → partial (title mismatch, everything else
  matches — demonstrates the partial rung, not a data error); the
  1706.03762 row → correct; the doi-only 10.1371 row → correct (its
  second author "Other" is a synthetic placeholder; v3.8.0's
  mis-attribution cap means a wrong author set would drop it to partial); the 24476887 row
  (STAP cells) is RETRACTED on purpose → RETRACTED flag with a partial
  cap — it demonstrates retraction detection, not a data error

Run:  python3 scripts/verify_pmids.py --claims-file examples/claims.sample.csv

Lint first (offline, v3.5.0): python3 scripts/verify_pmids.py --lint-claims examples/claims.sample.csv

Bibliography (v3.6.0): refs.sample.bib audits a .bib file directly —
python3 scripts/verify_pmids.py --bibliography examples/refs.sample.bib

RIS (v3.7.0): refs.sample.ris audits Zotero/EndNote/Mendeley exports —
python3 scripts/verify_pmids.py --bibliography examples/refs.sample.ris
