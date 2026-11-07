# Model capability comparison — 2026-11-03

The user asked to test stronger models instead of continuing to extend system instructions. The active default and local model setting were changed from `gpt-5-mini` to `gpt-6.1-sol` after the comparisons below. The existing API key was retained. Application prompts and JSON schemas were frozen throughout comparison.

## Method

Two cases were reconstructed from an actual rejected company-material run:

1. Generate the R2→R3 correction with the same source snapshot, company text, previous material, exact revision request, system instructions and schema.
2. Audit the same known-bad R3, which copied private representative scripts into public brochure fields and retained unwanted scope/source-attribution problems.

Both used medium reasoning, a 6,500-token output limit, no tools, `store:false`, and no automatic retries. The original Mini response supplied the first baseline; one additional request per case/model supplied a repeat. Sol was called twice per case. This comparison therefore made six new API requests, in addition to the captured baseline. The exact revision request matched its persisted request signature. Inputs and hashes are in `output/model-eval/frozen-inputs.json`; fixture SHA256 is `7a9be51769e2c3857b1897173daa0affb323fb0330adb9ba9f2747fbbb33d0a4`.

## Results

Counts refer to two samples per model and include agent comparison of meaning, not only keyword checks.

| Check | gpt-5-mini | gpt-6.1-sol |
| --- | ---: | ---: |
| Valid structured generation | 2/2 | 2/2 |
| Public/private audience separation | 1/2 | 2/2 |
| Requested narrow content scope | 0/2 | 2/2 |
| Visitor's own words and correct opening roles | 2/2 | 2/2 |
| Reject the known-bad audit input | 0/2 | 2/2 |

Mini's repeat removed the copied opening scripts but retained excluded observation-tool/survey content in the private claim map. Sol kept sourced facts to the teach-back definition, labeled the company's appointment example as editorial, and kept delivery scripts in private notes. Both Sol audits rejected the bad input with `factual_support=false` and `consistent=false`; both Mini audits approved every flag.

The first Sol generation took 27.1 seconds and the repeat 25.6 seconds; its audits took 15.4 and 13.6 seconds. The fresh Mini repeat took 36.1 seconds for generation and 32.6 seconds for audit. Captured baseline timing is unavailable, and cache state differs between repetitions, so these are observations rather than a general latency/cost benchmark.

## Fresh source-grounding check

A separate, single full discovery on Sol used the unchanged application pipeline and fixed `communication` category: three requests, no retries, 69.2 seconds, 37,264 input and 3,206 output tokens. It returned one candidate from the [CDC plain-language checklist](https://www.cdc.gov/health-literacy/php/develop-materials/plain-language.html).

Agent comparison to the primary page found all three factual claims supported: lead with the important message; organize familiar words into logical chunks/headings; keep one idea per sentence and remove excess words. Appointment adaptations were labeled editorial. The displayed page date was retained as context without inventing a publication/update distinction. The narrative overstated access to other sources, but the existing body-access/citation gate correctly excluded those sources. Results and the source comparison are in `output/model-eval/live-research-sol/`.

## Interpretation and limitations

These cases support model capability as a contributor to the repeated content and audit failures. The recent failures were valid JSON with wrong meaning or judgment; replacing the JSON framework alone would not address them. A separate upstream problem was evidence contamination: Mini's research narrative invented payment examples, which later no-tools stages received as if they were source context. Stronger generation does not make such input independently verified.

This is a small diagnostic set, not a production reliability estimate or human representative acceptance. Sol used one brochure section rather than the prior three; the final frozen request did not restate a three-section requirement and the application schema permits one to five. Exact layout preservation was not demonstrated. Sol's bad-input audit explained attribution/scope defects without explicitly naming the private-script leak; rejection does not prove recognition of every defect. The comparison audit did not evaluate the newly generated Sol brochure. The comparison alone does not verify application generation/review/export; separate completed verification follows below.

The selected model supports the existing Responses API, web search and Structured Outputs. Official standard pricing is $2 per million input tokens and $10 per million output tokens, with separate cache/tool rules. Account model-list access was checked before the trial. [Model capabilities and pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol)

After selection, the real browser workflow was run from fresh Sol research through company composition and both exports. It needed three research requests and two composition/audit requests, with no correction jobs or out-of-band edits. Both audience materials, the source notice, editable DOCX, two-page Korean PDF and exact reopening passed the bounded review. Details: `output/live-smoke/company-sol/verification.json` and `docs/verification/phase2.md`. Application regression tests also passed (92 tests).

## Jev and open-source alternatives

[Jev](https://docs.typesafe.ai/introduction) returns typed decisions and probabilities; it is a possible future atomic claim-audit comparison, not a prose-writing replacement. [vLLM/XGrammar](https://docs.vllm.ai/en/latest/features/structured_outputs/) and [Outlines](https://dottxt-ai.github.io/outlines/latest/features/models/transformers/) constrain output structure rather than factual support. They were not installed for this semantic failure.

The inspected alternatives do not yet justify replacing the current Korean workflow: [OpenJev](https://github.com/GPT-AGI/OpenJev) reproduces an interface and leaves calibration as future work; [VEJI-V2](https://huggingface.co/racore/VEJI-V2) reports failed production-readiness gates; [Von](https://github.com/wfzyx/von) is archived and documents English-only support. No new provider account/key or model weights were created/downloaded.
