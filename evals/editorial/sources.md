# 편집 평가 입력의 출처

2026-11-08에 12개 사례를 고정했다. 생성 결과와 새 서비스 프롬프트를 보기 전에 출처를 선택하고 본문을 읽었다. 소식 6개와 실용 자료 6개이며, 뉴스뿐 아니라 연구·기능·생활 정보와 참고 자료를 포함한다. 이전 시점의 자료를 최신 뉴스로 가장하지 않는다.

모든 사례는 열람한 1차 자료를 한국어로 요약했다. 원문 전체나 정답 문안은 담지 않았다. `task`는 독자와 산출물의 용도를 지정하며, 품질 평가 기준이나 목표 문체를 지시하지 않는다. 기능·시간 정보는 확인일의 기록이며, 이후 변경을 자동 반영하지 않는다.

이 데이터셋은 문장 생성과 편집 품질을 비교한다. 실제 검색·주제 선별 품질, 사용자 만족, 클릭률, 배포 적합성을 검증한 데이터는 아니다. 12개는 작은 탐색용 표본이며 평가자 점수를 일반적인 품질 보증으로 해석하지 않는다.

고정 파일 SHA-256: `5bbbc300c9931494f2e965a28b114b9f28e972d4c5615d483305bef37f1dcd07`

| 사례 | 분류 | 원문 | 날짜 근거 |
| --- | --- | --- | --- |
| `news-influenza-week44` | news | [질병관리청: 인플루엔자 발생 다시 증가! 어린이·어르신 예방접종 서두르고, 의심증상 시 신속한 진료 당부](https://kdca.go.kr/bbs/kdca/42/310702/download.do) | PDF 첫 쪽에 보도시점·배포일 명시. |
| `news-chatgpt-account-switching` | news | [OpenAI: Using multiple ChatGPT accounts on web and mobile](https://help.openai.com/en/articles/20001068-using-multiple-chatgpt-accounts-on-web-and-mobile) | 본문의 Updated: 3 days ago는 상대 표기이므로 정확한 수정일로 환산하지 않음. |
| `news-amie-feasibility` | news | [Brodeur 외 연구진 · arXiv: A prospective clinical feasibility study of a conversational diagnostic AI in an ambulatory primary care clinic](https://arxiv.org/abs/2603.08448v3) | arXiv 제출 이력 확인. v3 고정 링크 사용. |
| `news-otc-hearing-aids` | news | [미국 FDA: OTC Hearing Aids: What You Should Know](https://www.fda.gov/medical-devices/hearing-aids/otc-hearing-aids-what-you-should-know) | 시행일은 본문에 명시되지만 페이지 발행·수정일은 확인하지 못해 비워 둠. |
| `news-form13f` | news | [미국 SEC: Frequently Asked Questions About Form 13F](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f) | 페이지 머리 날짜는2023-05-24이며 본문2026~2028 기한표를2026-11-08에 확인. 별도 수정일은 미표시. |
| `news-museum-evening` | news | [국립중앙박물관: 관람 안내](https://www.museum.go.kr/MUSEUM/contents/M0101000000.do?menuId=tour-guidance) | 페이지에 발행·수정일이 없어 비워 둠. 관람시간은 확인일 기준. |
| `practical-print-queue` | practical | [Microsoft: Fix print spooler service not running errors in Windows](https://support.microsoft.com/en-us/windows/hardware/printer/fix-print-spooler-service-not-running-errors-in-windows) | 페이지에 발행·수정일이 표시되지 않아 비워 둠. |
| `practical-custom-instructions` | practical | [OpenAI: ChatGPT Custom Instructions](https://help.openai.com/en/articles/8096356-chatgpt-custom-instructions) | Updated: 10 days ago라는 상대 표기이므로 정확한 수정일은 비워 둠. |
| `practical-temporary-chat` | practical | [OpenAI: Temporary chat in ChatGPT](https://help.openai.com/en/articles/8914046-temporary-chat-in-chatgpt) | Updated: 7 days ago라는 상대 표기이므로 정확한 수정일은 비워 둠. |
| `practical-google-hours` | practical | [Google: How to set Special hours](https://support.google.com/business/answer/6303076?hl=en) | 페이지에 발행·수정일이 표시되지 않아 비워 둠. |
| `practical-contact-lenses` | practical | [미국 CDC: Healthy Habits: Keeping Water Away from Contact Lenses](https://www.cdc.gov/contact-lenses/about/healthy-habits-keeping-water-away-from-contact-lenses.html) | 페이지의 날짜2025-05-27 확인. 일반 예방 정보이며 개별 진단·처방 사례 없음. |
| `practical-phishing-message` | practical | [미국 FTC: How To Recognize and Avoid Phishing Scams](https://consumer.ftc.gov/articles/how-recognize-avoid-phishing-scams) | 페이지에September2022만 표기돼 일자를 만들지 않고 published_at을 비워 둠. |

검증 메모:

- 독감 숫자는 사용자 예시를 재사용하기에 앞서 질병관리청 PDF 1~3쪽과 대조했다.
- AMIE는 arXiv v3의 성인100명 사례다. 의료진 감독과 단일군 연구 맥락을 포함했다.
- 임시 채팅은 확인일 문서의 개인화 선택과 일반 채팅 저장 동작을 반영했다. 과거 도움말의 동작을 섞지 않았다.
- CISA는403 응답이어서 사용하지 않았으며, 피싱 사례는 직접 열람한 FTC 본문을 근거로 한다.
- 날짜를 일 단위로 확인할 수 없거나 상대 날짜만 표시한 출처는 발행·수정일을 추정하지 않았다.
- 사실 입력을 고친다면 버전을 바꾸고 비교를 다시 실행한다. 결과를 본 뒤 유리한 사례로 교체하지 않는다.
