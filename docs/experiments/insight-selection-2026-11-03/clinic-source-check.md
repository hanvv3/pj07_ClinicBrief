# ClinicBrief primary-source check

Checked 2026-11-03 against `clinic-original.json` and `clinic-readable.md`. This is a factual and usability audit of these two candidates, not a comparative ranking. All three cited URLs were opened and their relevant body text read; search snippets were not treated as verification. No paid API calls were made.

## Finding

The principal features, dates, and AMIE numbers are supported. Both assets contain substantive, source-specific content rather than just questions for the reader to research. Neither demonstrates that the proposed problem was discovered among Korean clinic staff or directors. The output explicitly admits that distinction.

The assets are usable as conditional educational drafts. Before circulating them, narrow the administrator-setting sentence to Enterprise and restore the AMIE study's urgent-care appointment scope. The AMIE country description also needs a directly supported location citation or omission. None of these changes requires inventing a local clinic rule.

## 1. Account switching and subscriptions

Primary sources: [S1: OpenAI Help Center article](https://help.openai.com/en/articles/20001068-using-multiple-chatgpt-accounts-on-web-and-mobile), [S2: ChatGPT release notes](https://help.openai.com/en/articles/6825453-chatgpt-release-notes).

| Draft detail | Body verification |
|---|---|
| Maximum two signed-in accounts; one active | Supported, S1 overview. This is a simultaneous-login limit, not a lifetime account limit. |
| Chats, files, memory, settings and subscriptions stay separate | Supported, S1 overview and switching/subscription sections. |
| Web account menu; mobile Settings → Switch account | Supported, S1 switching instructions. |
| Check subscription-owning account when paid access is missing | Explicitly supported, S1 subscription section. |
| Opening another account's mobile notification switches accounts | Supported, S1 notification section. |
| Missing mobile menu can reflect incomplete rollout | Supported, S1 opening notice. |
| Administrator can restrict switching | Supported specifically for Enterprise workspaces, not every organizational account. |
| Account switching differs from workspace switching | Supported, S1 FAQ. |
| Mobile rollout announced 2026-10-30 | Supported by that dated S2 entry. |
| S1 absolute publication/update dates unknown | Appropriate. The visible update label remained “Updated: 7 hours ago”; it is not an absolute timestamp. |

This is strong first-party evidence for product behavior, with rollout-dependent availability. The manuscript properly distinguishes a release-entry date from the entire document's date. [S1](https://help.openai.com/en/articles/20001068-using-multiple-chatgpt-accounts-on-web-and-mobile), [S2](https://help.openai.com/en/articles/6825453-chatgpt-release-notes).

**Required precision edit:** In ready asset step 6, replace the broad organizational-account wording with: `Enterprise 계정은 워크스페이스 소유자가 계정 전환을 허용했는지도 확인합니다.` Apply the same narrowing to the adaptation note.

**Practical usefulness:** This can become an actual staff notice after checking the local account and menu. Steps identify specific UI actions and a concrete billing-access trap; it is not merely a generic caution checklist. However, its usefulness depends on the clinic already using multiple ChatGPT accounts. The headline describes a possible troubleshooting case, not an observed clinic incident. It does not constitute a full paid-access troubleshooting guide or identify who locally resolves unresolved cases. The public-material-only boundary is the author's chosen scope, not a newly discovered vendor rule.

## 2. AMIE feasibility study

Primary source: [S3: PubMed record, author abstract, bibliographic details and conflict declaration](https://pubmed.ncbi.nlm.nih.gov/42849491/).

| Draft detail | Body verification |
|---|---|
| Prospective, single-centre, single-arm feasibility design | Supported. |
| English-speaking adults, one principal complaint | Supported; specifically urgent primary-care appointments, up to five days after AI interaction. |
| Physician supervision and predefined intervention criteria | Supported. |
| Transcript and summary supplied before appointment | Supported. |
| 114 enrolled; 98 completed both components | Supported. |
| Zero safety stops; one hallucination; information added in five interactions | Supported. |
| Post-surveys 60/98; prior transcript review 44 cases; helpful preparation 33/44 | Supported. Cases/responses must not become counts of distinct physicians. |
| Alphabet funding | Supported; the conflict declaration additionally identifies company employment, equity and patent interests. |
| Online 2026-10-08; journal issue 2026-10-24 | Supported by bibliographic fields. |
| US study site | Not explicit in the abstract. US affiliations support an inference, not direct site verification. |

The draft's contrast between no required safety stops and observed errors/interventions follows the reported findings. It correctly avoids turning subjective preparation usefulness into measured time savings or comparative effectiveness. [S3](https://pubmed.ncbi.nlm.nih.gov/42849491/).

**Required precision edits:** Restore `urgent primary care` in the population description, with wording such as `단일 주증상으로 긴급 일차진료(urgent primary care)를 예약한 영어 사용 성인`. Do not silently expand this population to all routine clinic visits. Omit `미국` unless a directly verified site source is added. These are scope corrections; the critical numerical claims do not need correction.

**Access and interpretation limits:** The publisher link returned HTTP 403. The linked [trial registry](https://clinicaltrials.gov/study/NCT06911398) yielded a page shell; its API endpoint was also inaccessible through this browsing tool. I did not verify the full paper, exact stop criteria, all outcomes, or a registry site listing. The manuscript accurately declares abstract-level coverage; this audit does not upgrade it to full-text verification. The issue date falls within 14 days of November 3, but the first online date does not. The draft correctly discloses this weaker recency basis.

**Practical usefulness:** The director memo is already a coherent, reusable explanation of one research claim. Its separate product-review questions are explicitly editorial recommendations and do not pretend to be study-derived deployment requirements. Its best use is when someone actually encounters this AMIE study or a similar safety claim in a proposal. No actual vendor proposal, Korean-language validation, procurement decision, or clinic demand was discovered here. The funding disclosure is useful; mentioning the disclosed company relationships would make the conflict assessment more complete, but omission does not make the reported funding false.

## Source quality, clinic voices and readiness

- **Source quality:** Direct official documentation for the product feature; a primary author abstract indexed in PubMed for the study. These sources support accurate descriptions. Source authority does not establish local relevance, and a feasibility study does not supply strong comparative clinical evidence.
- **Clinic voices:** The supplied result has no Korean clinic interviews, community complaints, staff quotations, director requests, measured pain frequency, or local workflow observations. The AMIE clinician survey supplies research-setting feedback, not independently discovered local demand. This conclusion concerns the supplied output; it cannot establish what uncited searches occurred.
- **Copy readiness:** Both assets contain the substantive material promised. Readers need local applicability checks, not another literature search to assemble the notice or explanatory memo. They should not be labeled unconditionally deployable, nor reduced to generic checklists. The precision edits above are small and concrete.
- **Remaining editorial weakness:** The notice and memo repeatedly explain what they do not prove. This is honest but increases reading burden for three-minute items. A shorter, single scope note could preserve the important boundaries. The internal maximum evidence/specificity/usability scores are self-ratings, not evidence of clinic demand or external validation.
- **Audit boundary:** The result reports four sources read, but only three unique sources are attached to the selected candidates; the rejected candidate has no accessible source trace here. This audit verifies the three cited bodies, not the completeness of that process statistic or all discovery activity.

Overall: no material numerical fabrication found; precise source support is materially stronger than the evidence for audience need. The record supports educational usefulness under stated conditions, not a finding that these were problems actually surfaced by clinics.
