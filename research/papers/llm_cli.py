"""Claude Code CLI 헤드리스 서브프로세스 호출 — 신규 API 키 불필요.

extract_spec.py/codegen_signal.py 전용 LLM 호출 경로. 툴 접근 없이 순수
텍스트생성만 하도록 --allowedTools ""로 제한(파일쓰기는 호출측이 직접 함)."""
from __future__ import annotations

import json
import subprocess


class LLMCallError(Exception):
    pass


def call_claude(prompt: str, timeout: int = 300) -> str:
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json", "--allowedTools", ""],
            capture_output=True, text=True, timeout=timeout, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        raise LLMCallError(f"claude CLI 호출 실패: {e}") from e

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LLMCallError(f"claude CLI 출력 JSON 파싱 실패: {e}\n원본: {proc.stdout[:500]}") from e

    if payload.get("is_error"):
        raise LLMCallError(f"claude CLI가 에러 반환: {payload}")

    result = payload.get("result")
    if not isinstance(result, str):
        raise LLMCallError(f"claude CLI 출력에 result 필드 없음: {payload}")
    return result
