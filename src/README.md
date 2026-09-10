# Compiled project layout

All phases merged into one tree:

```
config.py, db.py, models.py, schemas.py, .env.example     # Phase 0
collectors/base.py, synthetic.py, local_import.py         # Phase 1
services/normalization.py, extraction.py                  # Phase 1
services/entity_resolution.py, scoring.py                 # Phase 2
services/stylometry.py, behavior.py                        # Phase 3
services/graph.py                                          # Phase 4
services/search.py                                          # Phase 5
seed_demo.py, data/                                         # Phase 6
app.py                                                       # Phase 7 (single-file dashboard)
services/reporting.py, services/export.py                  # Phase 8
tests/test_pipeline.py, tests/test_reporting_export.py     # Phase 9
scripts/evaluate.py                                          # Phase 9 (precision/recall/F1)
requirements.txt, conftest.py, README.md                    # Phase 10 (minimal)
```

Run: `pip install -r requirements.txt`, then `python seed_demo.py` to write
`data/*.json`, then `streamlit run app.py`. Tests: `pytest`.

## Two things I fixed while merging

1. **Missing scoring weight.** `services/entity_resolution.py` and
   `services/reporting.py` both reference `exact_jabber_xmpp_match`, but
   the Phase 0 `config.py` you uploaded didn't define it (a duplicate
   `config.py` bundled inside the Phase 2 zip had it, the root one
   didn't). Added it to the single canonical `config.py` so both modules
   resolve. Deleted the duplicate.

2. **Two `app.py` candidates.** The plain `phase_7.py` upload and the
   `app.py` bundled inside the Phase 8 zip are near-identical dashboards,
   but the Phase 8 zip's version is the one actually wired up to the real
   `services/export.py` / `services/reporting.py` (PDF/CSV/JSON/STIX
   export) — the standalone `phase_7.py` version only has a placeholder
   "Reports & export" page. I used the Phase 8 zip's version as the
   canonical `app.py` and discarded the standalone one.

## One thing I did *not* fix — needs your call

`tests/test_pipeline.py` (from `phase_9.py`) was written against an
**earlier, simpler sketch of the API**, not the modules that actually got
built in Phases 2–8. It imports things like `search_all`, `build_graph`,
`StylometryEngine`, `behavior_similarity`, `actor_report`, `export_csv`,
`export_json` — none of which exist in the real `services/*.py`. The real
modules instead expose `SearchService`/`load_search_index_from_records`,
`GraphService`/`load_graph_from_records`, `compute_style_features`/
`build_style_profile`, `compute_behavior_features`, `build_pdf_report`,
`to_csv`/`to_json`/`to_stix_bundle` — and most of them take a SQLAlchemy
`Session` and ORM objects (`Persona`, `Observation`, `EntityLink`) rather
than plain dicts.

So `tests/test_pipeline.py` will fail to even import against this real
codebase — it's currently dead weight, not a working integration suite.
`tests/test_reporting_export.py` (from the Phase 8 zip) *is* written
against the real `reporting.py`/`export.py` and should be fine.

I didn't rewrite `test_pipeline.py`'s 20 cases against the real service
signatures without checking with you first, since that's a real chunk of
new test-writing, not just file-moving. Say the word and I'll redo it
against the actual `services/` API instead.

There's also a minor naming collision worth knowing about:
`ConfidenceLevel` is defined independently in both `config.py` (imported
by `models.py`) and `services/graph.py`. They currently have the same
member names/values, so nothing breaks, but they're two separate Python
enum classes — `config.ConfidenceLevel.HIGH is not
services.graph.ConfidenceLevel.HIGH`. Worth consolidating to one
definition if you want strict `is`/enum-identity checks anywhere.
