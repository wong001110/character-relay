# Multilingual Interface and Testing

Echo Masque separates the language used by the product interface from the language used to pressure-test a character.

## Interface language

The interface supports:

- English (`en`) — default
- Simplified Chinese (`zh-CN`)

The selected interface language is stored in browser `localStorage` and restored on refresh. It changes navigation, forms, status labels, room controls, observation notes, and modal copy.

It does not translate user-owned data. Character names, card descriptions, tags, System Prompts, imported transcripts, model responses, and provider errors remain in their original form.

## Test language

Each Test Room has a separate Test Language selector. The selected language controls:

- fixed Benchmark Tester messages;
- scenario names and expected-behaviour contracts;
- language-specific forbidden and required phrase rules;
- deterministic Stable and Fragile demo responses;
- Adaptive Tester context and output-language instruction;
- Judge summaries and evidence messages;
- generated trial report headings and scenario content.

Every run records `test_language`. Existing persisted runs that predate this feature are interpreted as English.

## Reproducibility

English and Simplified Chinese use separate fixed scenario catalogs with matching scenario identifiers. Benchmark runs remain repeatable within the same language.

Regression comparison rejects runs that use different test languages. A Chinese result should be compared with an earlier Chinese result, not with an English baseline.

## Current language coverage

Both languages cover:

- identity override;
- false-memory injection;
- prompt-injection resistance;
- long-conversation drift;
- imported transcript rule inspection.

The deterministic Judge uses language-specific phrase contracts. This is intentionally conservative and does not claim semantic equivalence across every possible wording.

## Adding another test language

1. Add the language code to the backend `TestLanguage` enum and the web `TestLanguage` type.
2. Add a complete scenario catalog with required and forbidden signals.
3. Add deterministic Demo responses for the new language.
4. Localize Rule Judge evidence and report headings.
5. Add the Adaptive Tester output-language instruction and context template.
6. Add interface translations and a language selector option.
7. Add Stable, Fragile, API persistence, report, and cross-language comparison tests.

A new interface translation may be added without adding a new test language, but it must be presented as UI-only coverage rather than model-evaluation coverage.
