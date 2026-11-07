"""Reader-facing editorial guidance shared by discovery and composition."""
from pathlib import Path

PROMPT_DIR = Path(__file__).with_name('prompts')
EDITORIAL_VERSION = '2026-11-08.2'


def editorial_guidance(*, examples=False):
    guidance = (PROMPT_DIR / 'editorial.md').read_text(encoding='utf-8')
    if examples:
        guidance += '\n' + (PROMPT_DIR / 'editorial-examples.md').read_text(encoding='utf-8')
    return '\n' + guidance + '\n'


EDITORIAL_REVIEW = '''Judge reader-facing quality separately from factual support. A factually
correct text may still fail its purpose if its title obscures the story, the opening never says
what happened, or repetitive caveats and editorial instructions dominate the useful content.
Also read the sentences as Korean prose: can the reader picture who did what and what happened,
or must they unpack abstract study-variable labels strung together? Accurate statistical wording
alone is not evidence of natural writing. Judge whether awkward phrasing materially interrupts
understanding; do not demand conversational slang or replace useful technical terms indiscriminately.
Judge the whole reading experience, not forbidden words or a fixed length. Preserve a qualification
when removing it would change the meaning; its presence is not a style defect. A focused news brief
can be complete without an action item, example or limitation list. Do not penalize omission of
unrelated facts from the source, or require every possible misreading to be explained.
Use a short concrete reason for a material editorial failure, rather than praising caution volume.
'''
