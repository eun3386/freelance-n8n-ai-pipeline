# AI 콘텐츠 자동 발행 파이프라인 (n8n + LLM)

키워드 뉴스 수집 → AI 요약/글 작성 → 워드프레스 발행 → 슬랙 알림까지 사람 손 없이 도는 자동화.
실패 시 재시도, 한 건 실패 격리, 워크플로우 전체 에러 알림까지 포함한 **운영형** 구성입니다.

## 구성
| 경로 | 설명 |
|---|---|
| `n8n/ai-content-pipeline.workflow.json` | n8n에 Import → 바로 사용 (10개 노드) |
| `pipeline/run.py` | 같은 흐름의 Python 구현. API 키 없이 `--demo`로 로컬 검증 |
| `dashboard/index.html` | 실행 로그 대시보드 (현재 **샘플 데이터**, `runs.jsonl` 연결 가능) |
| `fixtures/sample_feed.xml` | 데모용 RSS |

## n8n 워크플로우 흐름
`매일 09시` → `RSS 수집`(재시도 3회) → `키워드 필터 + 중복 제거`(Static Data로 발행 이력 유지) → `LLM 요약/작성`(재시도 3회, 실패 시 별도 출력) → `글 포맷 정리` → `워드프레스 발행`(재시도 3회) → `슬랙 완료 알림`
- LLM 실패 건은 `LLM 실패 격리` 출력으로 빠져 슬랙에 알리고 **나머지 건은 계속 처리**
- `에러 트리거` → 워크플로우 전체 실패를 슬랙으로 통보

### 설정
1. n8n에서 Import from file → 위 JSON
2. Credentials: WordPress, Slack 연결 (JSON의 `REPLACE_ME` 교체)
3. 환경변수: `ANTHROPIC_API_KEY`, 선택 `RSS_URL`, `KEYWORDS`, `MAX_POSTS`
4. 활성화 전 'Execute workflow'로 1회 테스트

## 로컬 데모
```bash
python3 pipeline/run.py --demo                 # 키 없이 동작
ANTHROPIC_API_KEY=... python3 pipeline/run.py --feed <RSS_URL>
open dashboard/index.html
```
