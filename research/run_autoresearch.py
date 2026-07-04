"""Auto-Research 배치 CLI — 후보 생성 → 검증 → 배치 BH-FDR → 리더보드."""
from research.autoresearch.engine import run_batch


def main():
    s = run_batch()
    print("=" * 76)
    print(f"AUTO-RESEARCH 배치 — 검증 {s['n_tested']} · 저파워 {s['n_underpowered']} · "
          f"CANDIDATE {s['n_candidates']} (BH alpha={s['bh_alpha']})")
    print("=" * 76)
    for e in s["leaderboard"]:
        print(f"[{e['verdict']:<15}] {e['cid']:<22} net={e['net']:+.4f} pct={e['percentile']} p={e['p']} "
              f"BH={'Y' if e['bh_survivor'] else 'n'} RT={e['redteam']}"
              + (f" 실패={','.join(e['redteam_failed'])}" if e['redteam_failed'] else ""))
    for u in s["underpowered"]:
        print(f"[UNDERPOWERED   ] {u['cid']:<22} n={u['n']}")
    print(f"\n{s['honest_note']}")


if __name__ == "__main__":
    main()
