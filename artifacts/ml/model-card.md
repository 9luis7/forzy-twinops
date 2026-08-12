# Model card - robust-baseline 1.0.0

## Intended use

Relative anomaly and deterioration scoring against a historical steady-regime
baseline. Scores are not failure probabilities and do not diagnose components.

## Training evidence

- Dataset kind: `deterministic_reference_fixture_not_real_forzy_csv`
- Trained until: `2026-08-12T13:00:03+00:00`
- Report status: `fixture_validation_only_real_eda_pending`
- Config hash: `sha256:5ff7b883606cf692a0eb1ba7e0a7f5d6b5468c3899cd508194d2e6fca3360415`

## Limitations

- Acceleration is excluded while its statistic remains unknown.
- S1-S2 physical differences are excluded until mounting and axis are confirmed.
- Operating phases are estimated from vibration velocity RMS.
- No deep learning, RUL, automatic online learning, or failure classification.
- Human validation remains required before operational action.
