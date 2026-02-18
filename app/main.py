# app/main.py
from fastapi import FastAPI

from app.core.config import settings
from app.core.orchestration import CoreOrchestrator
from app.core.api import create_agent_router
from app.projects.transfer.manifest import load_manifest

# ── 현재: 단일 서비스 ──────────────────────────────────────────────────────────
manifest = load_manifest()
orchestrator = CoreOrchestrator(manifest)

# ── 멀티 서비스로 확장 시 아래 패턴으로 교체 (main 코드 외 변경 없음) ──────────
#
# from app.core.orchestration import SuperOrchestrator, KeywordServiceRouter, A2AServiceProxy
# from app.projects.balance.manifest import load_manifest as load_balance_manifest
#
# orchestrator = SuperOrchestrator(
#     services={
#         "transfer": CoreOrchestrator(load_manifest()),
#         "balance":  CoreOrchestrator(load_balance_manifest()),   # 새 서비스: 한 줄
#         "card":     A2AServiceProxy("http://card-service/v1/agent"),  # A2A: 한 줄
#     },
#     router=KeywordServiceRouter(
#         rules={
#             "transfer": ["이체", "송금", "보내"],
#             "balance":  ["잔액", "얼마", "조회"],
#             "card":     ["카드", "신청", "발급"],
#         },
#         default="transfer",
#     ),
# )
# ─────────────────────────────────────────────────────────────────────────────

agent_router = create_agent_router(orchestrator)

app = FastAPI(title=settings.APP_NAME)
app.include_router(agent_router)
