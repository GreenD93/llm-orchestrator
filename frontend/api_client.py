# frontend/api_client.py
"""백엔드 SSE 스트림 및 REST API 클라이언트."""

import json
from typing import Any, Generator, Tuple

import requests
import sseclient


def stream_chat(
    session_id: str,
    message: str,
    api_base: str = "http://localhost:8010",
) -> Generator[Tuple[str, Any], None, None]:
    """
    백엔드 SSE 스트림을 읽어 (event_type, data) 튜플을 yield.
    event_type: AGENT_START | AGENT_DONE | LLM_TOKEN | LLM_DONE | TASK_PROGRESS | DONE
    """
    url = f"{api_base}/v1/agent/chat/stream"
    headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
    payload = {"session_id": session_id, "message": message}

    try:
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        for event in sseclient.SSEClient(response).events():
            if not event.data or event.data.strip() in ("", "{}"):
                continue
            try:
                data = json.loads(event.data)
            except json.JSONDecodeError:
                data = event.data
            yield event.event, data

    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"백엔드 서버({api_base})에 연결할 수 없습니다.\n"
            "서버가 실행 중인지 확인해주세요: uvicorn app.main:app --reload"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError("응답 시간이 초과되었습니다.")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"서버 오류: {e.response.status_code} {e.response.text}")


def get_completed(session_id: str, api_base: str = "http://localhost:8010") -> list:
    """완료된 거래 목록 조회."""
    try:
        r = requests.get(f"{api_base}/v1/agent/completed", params={"session_id": session_id}, timeout=10)
        r.raise_for_status()
        return r.json().get("completed", [])
    except Exception:
        return []


def get_debug(session_id: str, api_base: str = "http://localhost:8010") -> dict:
    """개발용 세션 내부 상태 조회 (DEV_MODE=true 시 사용 가능)."""
    try:
        r = requests.get(f"{api_base}/v1/agent/debug/{session_id}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}
