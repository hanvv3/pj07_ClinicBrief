# Topic selection comparison protocol

Frozen before reading either completed response on 2026-11-03 (Asia/Seoul).

## Question

Does Clinic Brief's revised discovery process produce source-grounded, concrete
clinic tasks and finished materials that a director or staff member could use?
Compare the first completed run with the actual ChatGPT website using `brief.txt`.
Do not replace a weak result with a more favorable retry.

## Conditions

- ChatGPT: actual web UI, temporary chat, Unpersonalized; exposed model label Pro.
  The underlying model, tool budget and internal instructions are not exposed.
- Clinic Brief: configured OpenAI model, six requests at most, three research
  stages of eight web actions each at most. No manually seeded topics or URLs.
  Existing owner-public research and shared public history are available to avoid
  repetition (one old AHRQ research topic and one shared WHO topic in this run).
- Both receive the same dated public task brief. Clinic Brief also applies its
  stage-specific instructions, schema, history and validation gates.
- This is a comparison of two service workflows, not a controlled model or cost
  benchmark. One run per workflow is insufficient to establish general superiority.
- The new run uses the app's ordinary private “전체 분야에서 찾기” path. The old
  scheduled09:00 shared collection had already consumed the second shared slot
  and failed. No public quota or collection ledger was changed for this test.
- An initial incomplete ChatGPT UI submission was stopped before a final answer;
  native typing had submitted only the first line. It is excluded as an input error.
  The full multiline brief was subsequently pasted and its submission verified.

## Assessment fixed in advance

Rate each topic 0–3 in these dimensions, providing a concrete reason:

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Task specificity | No task | Broad advice | Clear audience and situation | Concrete observed friction plus a fitting task |
| Immediate utility | No asset | Blank template or instructions to create | Usable with narrowly identified local checks | Complete and ready to copy under stated conditions |
| Source support | Missing or fabricated | Indirect or unclear | Direct relevant body evidence | Complementary sources supporting problem and answer |
| Freshness/novelty honesty | Misleading | Generic or ambiguous dates | Useful reference or dated change clearly labeled | Distinct useful finding with precise time and scope |
| Readability | Hard to understand | Jargon-heavy or bloated | Clear Korean with minor editing | Concise, natural, action-oriented Korean |

Unsupported local rules, medical effects, software capabilities or blanket
benefits block a “ready to use” verdict even when the numeric score is high.
A source example establishes that case, not industry-wide demand or prevalence.
Recent publication is not required for a useful reference; old/unknown dates must
remain explicit. A reviewer can prefer ChatGPT or find neither result ready.

## Verification

1. Save both original outputs and observable run metadata without credentials or
   unrelated account history. Retain zero-result reports and rejected candidates.
2. Give an independent reviewer neutral A/B labels without product identity;
   preserve substantive wording and links. Formatting can still reveal origins.
3. Independently inspect the critical source claims, dates and scope. Record what
   was verified and any inaccessible source; do not infer body access from snippets.
4. In the local app, open an actual selected result, copy its asset, save feedback,
   reload to check persistence, and verify the existing composition/export path.
5. Report output quality separately from software tests. This is an editorial and
   usability inspection, not a trial with practicing clinicians or measured savings.
