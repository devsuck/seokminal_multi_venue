"""`python -m jarvis` — 부트(시드) + 상태 배너."""
from __future__ import annotations

from jarvis import banner, boot

if __name__ == "__main__":
    boot()
    print(banner())
