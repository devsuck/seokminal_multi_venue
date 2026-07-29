"""`python -m jarvis.performance <cmd>` — 성능 벤치마크·동등성 CLI. **결과 불변.**

  benchmark [--n N]        대량 레코드 처리 스케일 벤치마크(결정적)
  operations               벤치마크 대상 연산 목록
"""
from __future__ import annotations

import argparse
import json


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_benchmark(a) -> int:
    from jarvis.performance.benchmark import large_record_processing
    _p(large_record_processing(a.n))
    return 0


def _cmd_operations(a) -> int:
    from jarvis.performance.models import BENCHMARK_OPERATIONS
    _p({"operations": list(BENCHMARK_OPERATIONS)})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.performance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    bm = sub.add_parser("benchmark")
    bm.add_argument("--n", type=int, default=1000)
    sub.add_parser("operations")
    args = ap.parse_args(argv)
    return {"benchmark": _cmd_benchmark, "operations": _cmd_operations}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
