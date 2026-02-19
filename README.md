# LLM Orchestrator

**멀티턴 슬롯필링, 시나리오 기반 AI 오케스트레이션 프레임워크**

LLM 에이전트들을 조합해 대화형 AI 서비스를 만드는 백엔드 엔진.
FastAPI + SSE 스트리밍 백엔드, Streamlit 프론트엔드.

---

## 특징

| | |
|---|---|
| **서비스 독립성** | 프로젝트별로 Agent + Flow만 정의하면 동작 |
| **SSE 스트리밍** | LLM 토큰을 실시간으로 프론트에 전달 |
| **멀티턴 메모리** | raw_history + LLM 자동 요약(summary_text) |
| **상태 머신** | INIT -> FILLING -> READY -> CONFIRMED -> EXECUTED |
| **배치 처리** | 다건 요청 한 번에 처리 |
| **Hooks** | 이벤트를 프론트, 서버 양쪽에 전달 |
| **멀티 서비스** | SuperOrchestrator로 여러 서비스를 하나의 API로 통합 |
| **LLM 프로바이더** | OpenAI / Anthropic 교체 가능 (card.json provider 필드) |

---

## 빠른 시작

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env에 OPENAI_API_KEY 등 설정

# 3. 서버 실행
uvicorn app.main:app --reload

# 4. 프론트엔드 (선택)
streamlit run frontend/app.py
```

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/v1/agent/chat` | 비스트리밍 |
| POST/GET | `/v1/agent/chat/stream` | SSE 스트리밍 |
| GET | `/v1/agent/completed` | 완료 이력 조회 |
| GET | `/v1/agent/debug/{session_id}` | 디버그 (DEV_MODE) |

## 테스트

```bash
pytest app/projects/transfer/tests/ -v
```

---

## 상세 가이드

**[GUIDE.md](GUIDE.md)** — 프레임워크 아키텍처, 새 서비스 만들기, 코드 패턴, API 스펙, 디버깅까지 모든 것을 다루는 종합 문서.

> "GUIDE.md 읽고 XXX 서비스 만들어줘" 한 마디로 바이브 코딩 가능.
