# Synthetic room-routing corpus

`corpus.jsonl.gz` is reproducible from `scripts/build_room_routing_corpus.py` with no network,
production transcripts or model calls. It contains 30 template families x 8 language/ID variants:
240 synthetic/unreviewed decision points, 192 development and 48 reserved by whole family.
Variants are correlated; this is not a human-reviewed model benchmark or a promotion result.

Decompressed JSONL SHA-256:
`7711a706d68d5e3e0f596802c200adef4b95aba8c106dbc4ebb19412f23fcf48`.
The gzip wrapper may vary across zlib versions; content identity is the decompressed bytes.

Model-visible IDs do not reveal scenario labels. Family/case/expected/review metadata is for
offline evaluation only. Adding real/redacted examples requires authorization, privacy review,
label provenance and grouping that prevents conversation/variant leakage across splits.
See [replay usage](../../../docs/developer/room-routing-replay.md).
