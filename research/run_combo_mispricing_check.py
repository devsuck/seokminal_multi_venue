"""
Polymarket Combos 가격 vs 구성 레그 확률곱(naive parlay price) 갭 실측.

공개 무인증 엔드포인트만 사용:
  GET https://gamma-api.polymarket.com/sports/{league}/premade-combos?placement=league_top

주의: 이 엔드포인트는 premade "multi_game"(서로 다른 경기) 콤보만 반환한다.
same-game(상관관계 있는 레그) 콤보 가격은 로그인 세션이 필요한
프론트엔드 내부 엔드포인트(polymarket.com/_a/batch)로만 계산되어
공개 데이터로는 실측 불가 — 이 스크립트는 multi_game(독립 가정) 케이스만 다룬다.
independent legs이므로 이론상 product(leg price) ≈ 1/indicativeMultiplier 여야 하고,
갭이 있다면 그게 Polymarket 콤보 엔진의 수수료(vig)/마진이다. 상관관계 미스프라이싱은
same-game 케이스에서만 의미 있는데 그건 이 엔드포인트로 못 잰다.
"""
import argparse
import json
import math
from urllib.request import Request, urlopen

BASE = "https://gamma-api.polymarket.com/sports/{league}/premade-combos?placement=league_top"


def fetch(league: str) -> list[dict]:
    url = BASE.format(league=league)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as r:
        data = json.load(r)
    combos = []
    for shelf in data.get("shelves", []):
        combos.extend(shelf.get("combos", []))
    return combos


def analyze(combo: dict) -> dict:
    legs = combo["legs"]
    prices = [leg["prices"]["selected"] for leg in legs]
    product = math.prod(prices)
    combo_implied_prob = 1.0 / combo["stats"]["indicativeMultiplier"]
    gap = combo_implied_prob - product          # +면 콤보가 naive product보다 비쌈(테이커에게 불리)
    gap_pct = gap / product * 100 if product else float("nan")
    ratio = combo_implied_prob / product if product else float("nan")
    per_leg_vig_pct = (ratio ** (1 / len(legs)) - 1) * 100  # 레그 수로 정규화한 1레그당 평균 마진
    return {
        "id": combo["id"],
        "title": combo["title"],
        "type": combo["comboType"],
        "n_legs": len(legs),
        "leg_prices": prices,
        "product_of_legs": round(product, 6),
        "combo_implied_prob": round(combo_implied_prob, 6),
        "gap": round(gap, 6),
        "gap_pct": round(gap_pct, 3),
        "per_leg_vig_pct": round(per_leg_vig_pct, 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="mlb")
    args = ap.parse_args()

    combos = fetch(args.league)
    rows = [analyze(c) for c in combos]

    print(f"{'title':<24} {'legs':>4} {'product':>10} {'combo_p':>10} {'gap_pct':>9} {'per_leg_vig':>12}")
    for r in rows:
        print(f"{r['title'][:24]:<24} {r['n_legs']:>4} {r['product_of_legs']:>10.4f} "
              f"{r['combo_implied_prob']:>10.4f} {r['gap_pct']:>8.2f}% {r['per_leg_vig_pct']:>11.2f}%")

    vigs = [r["per_leg_vig_pct"] for r in rows]
    print(f"\nn={len(rows)}  mean_per_leg_vig={sum(vigs)/len(vigs):.2f}%  "
          f"min={min(vigs):.2f}%  max={max(vigs):.2f}%")
    print("\n주의: 전부 multi_game(독립 레그). same-game 콤보는 이 엔드포인트로 미측정.")


if __name__ == "__main__":
    main()
