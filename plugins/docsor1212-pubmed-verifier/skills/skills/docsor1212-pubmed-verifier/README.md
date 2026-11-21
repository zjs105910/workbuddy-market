# PubMed Citation Verifier 🔬

[![GitHub Stars](https://img.shields.io/github/stars/docsor1212/pubmed-verifier?style=social&label=Star)](https://github.com/docsor1212/pubmed-verifier/stargazers)

Batch-verify PMID citations against PubMed API. Built for researchers, medical writers, and evidence-based medicine teams.

## 简介（中文）

**PubMed 文献引用批量验证工具**——把引用列表交给它，逐条核验 PMID/DOI/arXiv ID 是否真实存在、是否指向你声称的那篇论文（AI 幻觉引用最常见的形态就是「真 PMID 指向别的论文」）。五态判定（正确/不匹配/部分匹配/无效/待确认），撤稿检测全覆盖，网络故障如实标注「未判定」、绝不误报「不存在」。零依赖、纯本地运行。

- **中文文献**：GB/T 7714 格式参考文献可解析（`……标题[J]. 刊名, 年… PMID: xxx`）；`--parse-text` 粘贴即核验整张文献表——行内 PMID/DOI 精确路由，中文条目经 OpenAlex 标题检索判定（无编号 ID 也能核）
- **参考文献格式化**：`--format-references --citation-style gbt`（另支持 Vancouver/APA/AMA），先验证后排版，只排已验真的条目
- **四数据源**：NCBI PubMed、Europe PMC 自动兜底、Crossref、OpenAlex（DataCite/Zenodo 等非 Crossref 注册的 DOI 也可判定）
- **投稿就绪判定 + 审计底稿**：每份报告自带证据链，`--export-audit` 输出可复放的 JSON 工作底稿

## Why?

Academic projects routinely contain hundreds of PMID citations. Manual verification is tedious and error-prone. During our own 225-reference audit, we found 3 invalid PMIDs and 6 cross-domain mismatches — errors that would have undermined the entire project.

## Features

> **核心能力（中文速览）**：五态判定（正确/不匹配/部分匹配/无效/待确认）· 撤稿检测全覆盖+撤稿替代推荐 · DOI/arXiv/PMID 三类一站审计 · OpenAlex 兜底（DataCite/Zenodo DOI 可判定）· 中文文献 OpenAlex 标题检索 · 参考文献格式化导出（GB/T 7714/Vancouver/APA/AMA）· 差分审计（PRISMA 复跑只看变化）· 审计底稿可复放 · 网络故障诚实标注绝不误报不存在


- **Batch verification** — Scan entire project directories, extract all PMIDs, verify against PubMed in one run
- **Mismatch detection** — Five-state verdicts catch a REAL PMID pointing to a DIFFERENT paper (the most common AI hallucination)
- **Metadata validation** — Title, authors, journal and date fuzzy-compared against your claims (DOI cross-checked via Crossref with `--verify-doi`)
- **Dual sources** — NCBI E-utilities primary, Europe PMC automatic fallback when NCBI is unreachable
- **Network hardening** — Optional NCBI API key (3x faster batches), Crossref polite pool, 429 Retry-After backoff, UA rotation, per-host circuit breaker
- **Content matching** — Keyword overlap scoring flags potentially irrelevant citations
- **Three citation types in one audit** — PMIDs, DOIs and arXiv IDs (preprints) verified in a single scan; arXiv IDs checked against the official API (nonexistent = fabrication signal); claims rows keyed by DOI get full verdicts, and preprints surface their published version of record
- **Claims lint** — `--lint-claims file.csv` validates a claims file offline (ID shapes, missing titles, unknown columns, duplicates) before any verification run
- **Bibliography audit** — `--bibliography refs.bib` / `refs.ris` verifies BibTeX and RIS files directly (Zotero/EndNote/Mendeley exports; entries route by PMID > DOI > arXiv with full cross-checks); round-trips with `--export-bibtex` / `--export-ris`
- **Plain-text reference list parsing** — `--parse-text refs.txt` verifies a reference list copied straight out of a manuscript draft: numbered entries (`[1]`, `1.`) split cleanly, inline PMID/DOI/arXiv IDs route exactly, and a title-only entry resolves via PubMed title search (honestly labeled `resolved_by: title_search`, never a mismatch source)
- **Formatted reference list export** — `--format-references out.txt --citation-style gbt|vancouver|apa|ama` renders verified entries as a ready-to-paste numbered list (GB/T 7714-2015, Vancouver, APA 7th, AMA 11th); partial entries go to a manual-review section, retracted ones are excluded with a warning — formatting that stands on registry-verified records
- **Retraction detection for every citation** — the registry publication type ("Retracted Publication") flags retracted papers with no DOI or extra flags needed; Crossref `updated-by` adds the retraction-notice DOI
- **Verified-bibliography export** — `--export-bibtex` writes correct entries as BibTeX, comments partial ones, excludes and counts the rest
- **Submission-readiness verdict** — every report leads with `SUBMISSION READY` / `NOT SUBMISSION-READY` and per-problem counts
- **Audit working-paper** — `--export-audit` writes a self-contained JSON trail (tool identity, redacted invocation, evidence chain, verdict trace) a third party can replay
- **DOI-native verification** — `--dois` verifies DOIs directly (Crossref resolve, 404 = fabrication signal on explicit input); `--source` scans auto-extract DOIs; linked back to PMIDs via Europe PMC
- **Delta audits** — `--diff previous-audit.json` reports newly retracted, degraded, improved, new and dropped citations
- **Exports** — `--export-audit` (self-contained JSON trail), `--export-bibtex` (verified bibliography), `--export-csv` (spreadsheet audit table)
- **Replacement search** — Find correct PMIDs for broken citations via PubMed search
- **Multiple output formats** — HTML report, JSON (with per-entry metadata origin), or terminal summary

## Quick Start

```bash
# Install
openclaw skills install docsor1212/pubmed-verifier

# 中文场景速览
python3 scripts/verify_pmids.py --parse-text references.txt --no-cache          # 核验整张参考文献表
python3 scripts/verify_pmids.py --parse-text references.txt --format-references out.txt --citation-style gbt
python3 scripts/verify_pmids.py --pmids 31018962,22213727                       # 批量验证 PMID
python3 scripts/verify_pmids.py --check-net                                     # 网络预检（五源）

# Verify all PMIDs in a project
python3 scripts/verify_pmids.py --source /path/to/project --output report.html

# Verify specific PMIDs
python3 scripts/verify_pmids.py --pmids 31018962,22213727,999999999

# Verify a reference list copied from a paper draft
python3 scripts/verify_pmids.py --parse-text references.txt --no-cache

# Format verified entries as a citation list (gbt | vancouver | apa | ama)
python3 scripts/verify_pmids.py --parse-text references.txt --format-references refs_gbt.txt --citation-style gbt

# Institutional mode: API key + polite pool
python3 scripts/verify_pmids.py --source ./papers --verify-doi --ncbi-api-key $NCBI_API_KEY --mailto you@lab.org
```

**China mirror (ModelScope 魔搭)**: <https://modelscope.cn/skills/Docsor/pubmed-verifier> — if you find this skill useful, a like there helps others find it.

## Use Cases

| Scenario | Example |
|----------|---------|
| **Systematic review QA** | Verify all 200+ references before submission |
| **Medical website audit** | Check evidence citations across clinical case library |
| **Paper manuscript check** | Validate every PMID in your draft |
| **Teaching material review** | Ensure lecture citations are accurate |
| **Evidence library maintenance** | Periodic batch verification of reference databases |
| **Draft reference list check & formatting** | Paste a manuscript's reference list, verify it, get a GB/T 7714 / APA list back |

## Real-World Results

Audited a 35-file pediatric rheumatology evidence library (225 PMID citations):
- **222** citations: valid and content-matched ✅
- **3** citations: invalid PMIDs found and corrected
- **6** cross-domain citations: correctly flagged, reviewed, confirmed appropriate
- Total time: ~5 minutes for full audit

## Technical Details

- **APIs**: PubMed E-utilities (esummary, esearch); Europe PMC fallback; Crossref DOI check
- **Rate limit**: 3 req/s free (0.4s batch delay), 10 req/s with `--ncbi-api-key` (0.12s)
- **Resilience**: 429 Retry-After backoff, 403/406 UA rotation, per-host circuit breaker
- **Batch size**: 50 PMIDs per request
- **File types**: `.html`, `.md`, `.txt`, `.json`, `.htm`
- **PMID patterns**: `PMID: 12345678`, `PubMed: 12345678`, `pubmed.ncbi.nlm.nih.gov/12345678/`
- **Exit codes**: 0 clean / 1 problems found / 2 network-incomplete

## License

MIT-0
