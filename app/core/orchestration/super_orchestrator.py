# app/core/orchestration/super_orchestrator.py
"""
SuperOrchestrator: 여러 서비스(CoreOrchestrator 또는 A2A 원격 서비스)를 하나로 묶는 상위 계층.

설계 원칙:
  - CoreOrchestrator와 A2AServiceProxy가 동일한 handle_stream() 인터페이스를 구현
  → SuperOrchestrator는 둘을 구분 없이 사용 가능 (교체 가능)

  Embedded 모드:
      services["transfer"] = CoreOrchestrator(transfer_manifest)

  A2A 모드 (별도 프로세스):
      services["transfer"] = A2AServiceProxy("http://transfer-svc/v1/agent")

  확장:
      새 서비스 추가 = services dict에 한 줄 + ServiceRouter 규칙 등록
"""

from typing import Any, Dict, Generator


class BaseServiceRouter:
    """어느 서비스로 라우팅할지 결정. 규칙 기반 or LLM 기반으로 구현."""

    def route(self, user_message: str, session_context: dict) -> str:
        raise NotImplementedError


class KeywordServiceRouter(BaseServiceRouter):
    """
    키워드 기반 서비스 라우터. 빠르고 예측 가능.
    LLM 기반 라우팅이 필요하면 이 클래스를 교체하면 됨.

    예시:
        router = KeywordServiceRouter(
            rules={
                "transfer": ["이체", "송금", "보내"],
                "balance":  ["잔액", "얼마", "조회"],
                "card":     ["카드", "신청", "발급"],
            },
            default="transfer",
        )
    """

    def __init__(self, rules: Dict[str, list], default: str):
        self.rules = rules
        self.default = default

    def route(self, user_message: str, session_context: dict) -> str:
        for service, keywords in self.rules.items():
            if any(kw in user_message for kw in keywords):
                return service
        return self.default


class SuperOrchestrator:
    """
    여러 서비스를 묶는 상위 오케스트레이터.

    CoreOrchestrator와 동일한 handle_stream() / handle() 인터페이스를 구현하므로
    기존 FastAPI 라우터(create_agent_router)에 그대로 꽂을 수 있음.

    사용 예시 (app/main.py):
        from app.core.orchestration import SuperOrchestrator, KeywordServiceRouter

        orchestrator = SuperOrchestrator(
            services={
                "transfer": CoreOrchestrator(transfer_manifest),
                "balance":  CoreOrchestrator(balance_manifest),   # 추가 시 한 줄
                "card":     A2AServiceProxy("http://card-svc"),   # A2A 서비스
            },
            router=KeywordServiceRouter(
                rules={
                    "transfer": ["이체", "송금", "보내"],
                    "balance":  ["잔액", "얼마", "조회"],
                },
                default="transfer",
            ),
        )
        agent_router = create_agent_router(orchestrator)  # 기존 코드 그대로
    """

    def __init__(
        self,
        services: Dict[str, Any],   # name → CoreOrchestrator | A2AServiceProxy
        router: BaseServiceRouter,
    ):
        self.services = services
        self._router = router
        self._session_service_map: Dict[str, str] = {}  # session_id → 현재 서비스

    def handle_stream(self, session_id: str, user_message: str) -> Generator:
        """CoreOrchestrator와 동일한 인터페이스. create_agent_router에 그대로 사용 가능."""
        session_context = {"current_service": self._session_service_map.get(session_id)}
        service_name = self._router.route(user_message, session_context)
        self._session_service_map[session_id] = service_name
        service = self.services[service_name]
        yield from service.handle_stream(session_id, user_message)

    def handle(self, session_id: str, user_message: str) -> dict:
        """비스트리밍 버전."""
        session_context = {"current_service": self._session_service_map.get(session_id)}
        service_name = self._router.route(user_message, session_context)
        self._session_service_map[session_id] = service_name
        return self.services[service_name].handle(session_id, user_message)


class A2AServiceProxy:
    """
    별도 프로세스(또는 별도 서버)로 실행 중인 서비스를 HTTP로 호출.
    Google A2A 패턴: 기존 /v1/agent/chat/stream SSE 엔드포인트를 그대로 활용.

    CoreOrchestrator와 동일한 handle_stream() 인터페이스 → SuperOrchestrator에서 교체 투명.

    사용 예시:
        proxy = A2AServiceProxy(endpoint="http://card-service/v1/agent")
        # SuperOrchestrator.services["card"] = proxy
    """

    def __init__(self, endpoint: str):
        self.endpoint = endpoint.rstrip("/")

    def handle_stream(self, session_id: str, user_message: str) -> Generator:
        import json
        import requests
        import sseclient

        url = f"{self.endpoint}/chat/stream"
        resp = requests.post(
            url,
            json={"session_id": session_id, "message": user_message},
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=60,
        )
        for event in sseclient.SSEClient(resp).events():
            yield json.loads(event.data)

    def handle(self, session_id: str, user_message: str) -> dict:
        import requests

        url = f"{self.endpoint}/chat"
        resp = requests.post(
            url,
            json={"session_id": session_id, "message": user_message},
            timeout=30,
        )
        return resp.json()
