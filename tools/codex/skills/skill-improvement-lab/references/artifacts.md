# Lightweight comparison artifacts

Use this shape when a reproducible comparison is useful; there is no fixed number of cases or rounds.

```text
iteration-1/
  rubric.md
  evidence.md
  mapping.json              # private from judges: A/B to original versions
  eval-1/
    eval_metadata.json
    A/outputs/article.md
    B/outputs/article.md
  judgments/
    forward.json
    reversed.json
```

`eval_metadata.json`: `{"eval_id": 1, "prompt": "The task and target audience; no version hints"}`.

A judge record contains:
- `winner`: `A`, `B`, `TIE`, `NEITHER`, or `INSUFFICIENT_EVIDENCE`.
- `facts.A` and `facts.B`: `status` (`pass`, `needs_revision`, `insufficient_evidence`) and `findings` (output quote, source ID/excerpt, concise reason).
- `scores.A` and `scores.B`: criterion names and scores from the frozen rubric; use null where unassessable.
- `reasons`: brief output-grounded reasons for the verdict.
- `rubric_version` and `evidence_version`: identifiers supplied by the runner.

Save judgments outside output directories to avoid showing them to a blind reviewer. Keep identity mapping outside the review package. A swapped-order judge sees fresh labels with no first-pass judgment; compare mapped identities afterwards. Human feedback is saved separately and only after an actual review.

## Portable review helper

From the installed skill directory, with Python 3.10+:

```bash
python3 eval-viewer/generate_review.py /absolute/path/to/iteration-1 --skill-name comparison --static /absolute/path/to/review.html
```

The helper uses only Python's standard library and packages text/image outputs into HTML. Static mode does not start a server or call a model. For a blinded human review, use neutral A/B paths and metadata, omit benchmarks and prior feedback, and keep the mapping/judgments outside the viewer inputs. Review HTML may contain all displayed source material; retain it with the local evaluation artifacts.

Optional server mode binds to localhost and falls back to a free port; it never terminates a process already using the requested port. Store actual human feedback without filling empty fields on their behalf. This viewer is qualitative; it does not claim to calculate preference significance or prove improvements.
