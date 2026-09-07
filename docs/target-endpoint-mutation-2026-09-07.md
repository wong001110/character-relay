# Target endpoint policy mutation evidence — 2026-09-07

Scope: `echo_masque.target_endpoint_policy.*`, using the configured focused tests in
`tests/test_target_endpoint_policy_review.py`.

Command:

```bash
python -m mutmut run 'echo_masque.target_endpoint_policy.*' --max-children 2
python -m mutmut export-cicd-stats
```

The targeted scope generated 87 mutants: 65 killed and 22 survived. There were zero no-test,
timeout, suspicious, skipped, or interrupted results. The generated aggregate stats file reports
193 total records because it retains 106 prior, unselected policy-mutant records as not checked;
the 87 checked records are the target endpoint-policy scope above.

The review added behavioral tests for missing hostname, non-HTTP(S) schemes, username-only and
password credentials, default ports, trailing-dot normalization, IPv6 formatting, operator
query/fragment/credential rejection, the root-slash operator origin, and the three loopback
development HTTP origins. Those tests killed all surviving mutations that could widen endpoint
admission or change canonical origin identity.

All 22 remaining survivors are equivalent for the endpoint-admission contract:

- `canonical_endpoint_origin` mutants 1, 2, 3, 8, 20, and 26 alter only a default label or an
  exception message. Mutants 24 and 40 preserve the result for every parseable hostname: hostname
  is case-folded before `rstrip("XX.XX")`, leaving only the original dot behavior, and
  `urlsplit(...).hostname` never contains a bracket prefix. These are message-only/equivalent.
- `_is_local_http_origin` mutant 5 changes the fallback used only for a missing hostname. The
  function is called after `canonical_endpoint_origin`, which rejects a missing hostname, so that
  branch is unreachable through policy admission.
- `validated_operator_origin` mutants 4, 5, 6, 7, 22, 26, 28, 29, 30, 31, 32, and 33 change only
  labels or exception messages. Mutant 8 weakens its local username/password condition, but the
  following `canonical_endpoint_origin` independently rejects either credential form before an
  origin can be returned. It is therefore defense-in-depth equivalent, not an admission survivor.

Focused pytest validation completed with 11 passing tests. The mutmut run used the repository's
offline test configuration; no live provider, embedding, or network dependency was used.
