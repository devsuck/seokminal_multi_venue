"""테스트가 실제 `jarvis/_state/` 원장에 쓰는 걸 막는 헬퍼.

왜 필요한가(2026-08-27): 테스트를 돌렸더니 `jarvis/_state/audit.jsonl`과
`forward_deployments.jsonl`이 더러워졌다. 픽스처가 `jarvis.audit.log`,
`jarvis.registry.lifecycle` 등을 하나씩 monkeypatch하는 방식이었는데,
`from jarvis.config import state_path`로 **자기 바인딩을 따로 든 모듈이 71개**라
하나만 빠뜨려도 그 경로로 프로덕션 원장에 append된다. 실제로 `jarvis.paper.deploy`가
빠져 있었고, append-only 원장에 오늘 날짜의 가짜 배포 기록이 12건 들어갔다.

키 이름 미스매치 사고들과 같은 형태다 — 열거해서 막으면 반드시 하나를 놓친다.
그래서 여기서는 열거하지 않고 `sys.modules`를 훑어 `state_path` 속성을 가진
jarvis 모듈을 **전부** 찾아 patch한다. 새 모듈이 생겨도 자동으로 커버된다.

사용:

    from tests.jarvis_state_isolation import isolate_jarvis_state

    @pytest.fixture(autouse=True)
    def _isolate(tmp_path, monkeypatch):
        return isolate_jarvis_state(monkeypatch, tmp_path)
"""
from __future__ import annotations

import os
import sys


def isolate_jarvis_state(monkeypatch, tmp_path) -> str:
    """이미 import된 모든 jarvis 모듈의 `state_path`를 tmp_path로 돌린다.

    반환: 원장이 쓰일 임시 디렉터리 경로.
    """
    root = str(tmp_path)

    def _tmp_state_path(name: str) -> str:
        return os.path.join(root, name)

    import jarvis.config as config
    monkeypatch.setattr(config, "state_path", _tmp_state_path)

    # import 시점에 `from jarvis.config import state_path`로 값을 복사해간 모듈들.
    # 열거 대신 스캔 — 열거하면 반드시 하나를 놓친다(이 파일이 존재하는 이유).
    for name, module in list(sys.modules.items()):
        if not name.startswith("jarvis"):
            continue
        if getattr(module, "state_path", None) is None:
            continue
        monkeypatch.setattr(module, "state_path", _tmp_state_path, raising=False)

    return root
