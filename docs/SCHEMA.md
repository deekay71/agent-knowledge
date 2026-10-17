# Schema v1

Pages use a `---json` line, a JSON object, then `---` and Markdown body. JSON keeps the
Python standard-library implementation dependency-free; it is not general YAML front matter.
`templates/page.md` is the starting shape. Paths are repository-relative in metadata,
page-relative in Markdown. Use simple inline Markdown links; external URLs and heading
anchors are not fetched/validated by lint. No symlinks in any path component or escaping/absolute paths. Source metadata paths must be
canonical and inside raw/. Only regular Markdown files are supported in raw/ and wiki/;
only the exact wiki/index.md and wiki/log.md paths are exempt from page metadata.

Required strings: id (unique), title, summary, scope (`shared`), status, updated_at (ISO date).
Required nonempty string arrays: tags, sources (`raw/` paths), applies_to (exact version labels).
Required nonempty claims array: text, kind (`evidence`, `inference`, `unknown`), sources array,
applies_to array (subset of page versions). Evidence needs at least one page source; each exact claim version must match a cited raw version.
Unknown may have no source. Each claim preserves its own scope and source association.
Statuses: draft, reviewed, verified, deprecated, superseded. Reviewed/verified need a
repository-relative review_record file. Verified also needs verified_at and verification_evidence.
verified_at cannot predate updated_at. Synthetic sources require fixture: true and cannot
become verified. Duplicate JSON keys, nonstandard JSON constants and duplicate list members
are rejected. Deprecated/superseded need superseded_by to another knowledge page, without cycles. Optional supersedes is an array of other knowledge-page paths documenting reverse lineage.
Optional contradictions: objects with status open/resolved, at least two distinct page sources,
and resolution explaining uncertainty or evidence-based resolution. Open entries warn.
`fixture: true` identifies synthetic content; fixtures are never production verification.

Raw Markdown uses the same header with origin, collected_at, scope, version, permission.
Permission is synthetic-fixture or approved; approval rationale belongs in the raw body/review.
Archive only sources whose reproduction is permitted; do not copy entire copyrighted sources.
Review/evidence files must be nonempty, but their presence cannot prove the review happened.
Schema checks are necessary but do not certify factual truth, rights or secrecy.

Log format: exact # Wiki log header, followed by one JSON object per Markdown bullet,
with at (timezone-bearing ISO timestamp), operation and detail. Allowed operations are
ingest, review, maintain, query, index and lint. Every line ends in a newline.
History checks compare raw bytes and first-parent log bytes; merge-parent checks preserve
each incoming event line, including duplicates and ordering. A trusted baseline is required.
