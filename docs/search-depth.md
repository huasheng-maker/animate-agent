# Query evidence depth

Query ingestion now searches for the user's mechanism (inputs, intermediate
operations, outputs, examples/equations), keeps up to three distinct sources,
and reads the first two public pages concurrently through the existing reader.
URL/file/text ingestion still uses its dedicated adapter.

Search excerpts and readable bodies have a 9,000-character evidence budget per
document after ranking. Complete paragraphs and structured equation/table blocks
are preferred. This replaces the query path's unconditional 3,000-character
cutoff; it does not send raw HTML to the model.

A deterministic bilingual lexical check looks for inputs, operations, outputs,
and examples. Missing categories trigger at most one targeted supplemental
search and one additional page read. The final evidence remains at most three
sources. The heuristic is not semantic verification: keyword presence does not
prove a correct or sufficient explanation. Remaining gaps are passed to the
planner, which must not invent mechanism facts.

Page reads have a 20-second timeout; supplemental search has a 30-second timeout.
Failure retains existing search evidence and records only the error type, never
response bodies or credentials. URL/DNS/redirect/content protections remain in
the existing adapters. The configured search and reader providers are reused;
this change does not switch models. Depending on that configuration, future user
generation can incur one additional search and up to three reader requests.

`01-source-document.json` records `read_status`, `search_source_id`,
`coverage_method`, `evidence_gaps`, and `supplement_status`. A successfully read
body keeps its own source identity and final URL. The planner may construct
explicitly labeled teaching numbers, but may not attribute those numbers to the
source as measured values or trained parameters.

Composition operands written as numeric literals (including numeric strings)
are lifted into bounded constant nodes before validation. The canonical spec
and browser still accept node references only. Expressions, unknown references,
nonfinite values, invalid dimensions and excessive graph size remain errors.

Validation uses local adapter fixtures, schema/numerical tests and fake model
responses. Live provider behavior and live page availability require separate
verification; no paid requests were made for these changes.
