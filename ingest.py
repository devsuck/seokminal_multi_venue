"""Unified KIS data ingestion CLI.

Usage examples
--------------
# 국내 개별종목 (KOSPI)
python ingest.py domestic --codes 005930 000660 035720

# 국내 개별종목 파일에서 읽기
python ingest.py domestic --file codes/kospi200.txt

# KOSDAQ 종목
python ingest.py domestic --codes 035420 --market K

# 국내 ETF (KOSPI 상장 ETF = market J, KOSDAQ 상장 ETF = market K)
python ingest.py domestic --codes 069500 360750 --market J

# 해외 주식
python ingest.py overseas --codes AAPL TSLA NVDA MSFT --exchange NAS
python ingest.py overseas --codes BRK.B JPM GS --exchange NYS

# 지수 (KOSPI=0001, KOSDAQ=1001, KRX=0002)
python ingest.py index --codes 0001 1001

# 여러 타입 한번에 (배치 파일)
python ingest.py batch --file ingest_list.csv

기간 옵션:
  --start YYYYMMDD   (기본: 1년 전)
  --end   YYYYMMDD   (기본: 오늘)
  --years N          (기본: 1, start 대신 사용 가능)

기타:
  --catalog-path ./catalog
  --dry-run          (API 호출만, catalog에 저장 안함)
  --mock             (KIS 모의투자 서버 사용)
"""

import argparse
import csv
import datetime as dt
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from nautilus_trader.persistence.catalog import ParquetDataCatalog

import asyncio

from adapters.data_provider import (
    bar_type_for,
    build_kospi_index,
    build_kosdaq_equity,
    build_us_equity,
    build_xkrx_equity,
    map_kis_daily_bar,
    map_kis_index_daily_bar,
    map_ib_daily_bar,
)
from backends.kis.client import KISClient
from backends.ib.client import IBClient

load_dotenv()

# ── helpers ───────────────────────────────────────────────────────────────────

_client_cache: dict[bool, KISClient] = {}


def _make_client(mock: bool = False) -> KISClient:
    """Return cached KISClient — token reused across all commands in one run."""
    if mock not in _client_cache:
        if mock:
            _client_cache[mock] = KISClient(
                app_key=os.environ["KIS_MOCK_APP_KEY"],
                app_secret=os.environ["KIS_MOCK_APP_SECRET"],
                base_url="https://openapivts.koreainvestment.com:29443",
            )
        else:
            _client_cache[mock] = KISClient(
                app_key=os.environ["KIS_APP_KEY"],
                app_secret=os.environ["KIS_APP_SECRET"],
            )
    return _client_cache[mock]


def _date_range(args: argparse.Namespace) -> tuple[str, str]:
    end = args.end or dt.date.today().strftime("%Y%m%d")
    if args.start:
        start = args.start
    else:
        years = getattr(args, "years", 1)
        start = (dt.date.today() - dt.timedelta(days=365 * years)).strftime("%Y%m%d")
    return start, end


def _open_catalog(path: str, dry_run: bool) -> ParquetDataCatalog | None:
    if dry_run:
        return None
    return ParquetDataCatalog(path)


def _clear_bar_data(catalog_path: str, bar_type_str: str) -> None:
    """Delete existing parquet files for a bar type (enables overwrite)."""
    bar_dir = Path(catalog_path) / "data" / "bar" / bar_type_str
    if bar_dir.exists():
        for f in bar_dir.glob("*.parquet"):
            f.unlink()


def _write(
    catalog: ParquetDataCatalog | None,
    instrument,
    bars: list,
    overwrite: bool = False,
    catalog_path: str = "./catalog",
) -> None:
    if catalog is None:
        return
    if overwrite and bars:
        from adapters.data_provider import bar_type_for
        bt = bar_type_for(instrument.id)
        _clear_bar_data(catalog_path, str(bt))
    catalog.write_data([instrument])
    if bars:
        catalog.write_data(bars)


def _log(msg: str) -> None:
    print(msg, flush=True)


# ── subcommand: domestic ──────────────────────────────────────────────────────

def cmd_domestic(args: argparse.Namespace) -> None:
    codes = _resolve_codes(args)
    start, end = _date_range(args)
    client = _make_client(getattr(args, "mock", False))
    catalog = _open_catalog(args.catalog_path, args.dry_run)
    market = getattr(args, "market", "J")  # J=KOSPI/ETF, K=KOSDAQ

    for code in codes:
        try:
            rows = client.get_daily_price(code, start, end)
            if market == "K":
                instrument = build_kosdaq_equity(code)
            else:
                instrument = build_xkrx_equity(code)
            bar_type = bar_type_for(instrument.id)
            bars = [map_kis_daily_bar(r, bar_type, instrument.price_precision) for r in rows]
            _write(catalog, instrument, bars, getattr(args, "overwrite", False), args.catalog_path)
            _log(f"[domestic] {code} ({instrument.id}) → {len(bars)} bars  {start}~{end}" +
                 (" [dry-run]" if args.dry_run else ""))
        except Exception as exc:
            _log(f"[domestic] {code} ERROR: {exc}")
        time.sleep(0.1)


# ── subcommand: ib (해외주식 via Interactive Brokers) ─────────────────────────

async def _fetch_ib_bars(symbol: str, venue: str, duration: str, end_date: str) -> list:
    client = IBClient()
    rows = await client.get_daily_bars(symbol, end_date, duration)
    instrument = build_us_equity(symbol, venue)
    bar_type = bar_type_for(instrument.id)
    bars = [map_ib_daily_bar(r, bar_type, instrument.price_precision) for r in rows]
    return instrument, bars


def cmd_ib(args: argparse.Namespace) -> None:
    symbols = _resolve_codes(args)
    _, end = _date_range(args)
    venue = getattr(args, "venue", "NASDAQ").upper()
    end_dt = f"{end[:4]}-{end[4:6]}-{end[6:]} 23:59:59"
    years = getattr(args, "years", 1)
    duration = f"{years} Y"
    catalog = _open_catalog(args.catalog_path, args.dry_run)

    for symbol in symbols:
        try:
            instrument, bars = asyncio.run(_fetch_ib_bars(symbol, venue, duration, end_dt))
            _write(catalog, instrument, bars, getattr(args, "overwrite", False), args.catalog_path)
            _log(f"[ib]       {symbol}.{venue} → {len(bars)} bars  ({duration})" +
                 (" [dry-run]" if args.dry_run else ""))
        except Exception as exc:
            _log(f"[ib]       {symbol} ERROR: {exc}")


# ── subcommand: index ─────────────────────────────────────────────────────────

INDEX_META: dict[str, tuple] = {
    "0001": ("KOSPI",  "XKRX"),
    "1001": ("KOSDAQ", "XKOS"),
    "0002": ("KRX",    "XKRX"),
}

def cmd_index(args: argparse.Namespace) -> None:
    codes = _resolve_codes(args)
    start, end = _date_range(args)
    client = _make_client(getattr(args, "mock", False))
    catalog = _open_catalog(args.catalog_path, args.dry_run)

    for code in codes:
        try:
            rows = client.get_daily_index_price(code, start, end)
            instrument = build_kospi_index()  # reuse KOSPI builder; id = KOSPI.XKRX
            bar_type = bar_type_for(instrument.id)
            bars = [map_kis_index_daily_bar(r, bar_type, instrument.price_precision) for r in rows]
            _write(catalog, instrument, bars, getattr(args, "overwrite", False), args.catalog_path)
            _log(f"[index]    {code} → {len(bars)} bars  {start}~{end}" +
                 (" [dry-run]" if args.dry_run else ""))
        except Exception as exc:
            _log(f"[index]    {code} ERROR: {exc}")
        time.sleep(0.1)


# ── subcommand: batch ─────────────────────────────────────────────────────────

def cmd_batch(args: argparse.Namespace) -> None:
    """CSV format: type,code_or_symbol,exchange(optional)
    Example:
        domestic,005930
        domestic,035420,K
        overseas,AAPL,NAS
        overseas,TSLA,NAS
        index,0001
    """
    path = Path(args.file)
    if not path.exists():
        _log(f"Batch file not found: {path}")
        sys.exit(1)

    with open(path) as f:
        reader = csv.reader(f)
        for lineno, row in enumerate(reader, 1):
            row = [c.strip() for c in row if c.strip()]
            if not row or row[0].startswith("#"):
                continue
            if len(row) < 2:
                _log(f"Line {lineno}: skip (need at least type,code)")
                continue

            typ, code = row[0].lower(), row[1]
            extra = row[2] if len(row) > 2 else ""

            # Build a fake namespace to reuse subcommand funcs
            sub = argparse.Namespace(
                codes=[code],
                file=None,
                start=args.start,
                end=args.end,
                years=getattr(args, "years", 1),
                catalog_path=args.catalog_path,
                dry_run=args.dry_run,
                mock=getattr(args, "mock", False),
                market=extra or "J",
                exchange=extra or "NAS",
            )

            if typ in ("domestic", "etf", "kosdaq"):
                if typ == "kosdaq":
                    sub.market = "K"
                cmd_domestic(sub)
            elif typ in ("overseas", "ib"):
                sub.venue = extra or "NASDAQ"
                cmd_ib(sub)
            elif typ == "index":
                cmd_index(sub)
            else:
                _log(f"Line {lineno}: unknown type {typ!r}")


# ── resolve codes from --codes or --file ──────────────────────────────────────

def _resolve_codes(args: argparse.Namespace) -> list[str]:
    if getattr(args, "codes", None):
        return args.codes
    if getattr(args, "file", None):
        path = Path(args.file)
        if not path.exists():
            _log(f"Code file not found: {path}")
            sys.exit(1)
        lines = path.read_text().splitlines()
        return [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    _log("Provide --codes or --file")
    sys.exit(1)


# ── subcommand: crno-search ───────────────────────────────────────────────────

def cmd_crno_search(args: argparse.Namespace) -> None:
    """매출액으로 FSC DB에서 법인등록번호(crno) 검색."""
    from corp_finance.client import CorpFinanceClient
    import requests

    key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not key:
        _log("DATA_GO_KR_API_KEY not set in .env")
        sys.exit(1)

    target = args.sale_trillion * 1_000_000_000_000
    biz_year = str(args.year)
    fncl_dcd = args.fncl_dcd
    tolerance = args.tolerance / 100.0

    _log(f"Searching FSC DB: year={biz_year} 매출≈{args.sale_trillion}조 (±{args.tolerance}%) fnclDcd={fncl_dcd}")
    _log("This may take a while (up to 1344 pages)…")

    found: list[tuple[str, float]] = []
    session = requests.Session()
    for page in range(1, 1500):
        r = session.get(
            "https://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2/getSummFinaStat_V2",
            params={"serviceKey": key, "pageNo": page, "numOfRows": 100,
                    "resultType": "json", "bizYear": biz_year, "fnclDcd": fncl_dcd},
            timeout=15,
        )
        r.raise_for_status()
        items = r.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if not items:
            _log(f"Page {page}: no more data.")
            break
        for item in items:
            if item.get("curCd") != "KRW":
                continue
            sale = int(item.get("enpSaleAmt", 0) or 0)
            if abs(sale - target) / max(target, 1) <= tolerance:
                found.append((item["crno"], sale / 1e12))

        if found:
            _log(f"Found on page {page}!")
            break
        if page % 50 == 0:
            _log(f"Page {page}…")

    if found:
        _log("\nResults:")
        for crno, sale in found:
            _log(f"  crno={crno}  매출={sale:.1f}조")
    else:
        _log("No match found.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="KIS 데이터 수집 → NautilusTrader ParquetDataCatalog 저장",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--start",  default=None,     help="YYYYMMDD (기본: --years 전)")
    common.add_argument("--end",    default=None,     help="YYYYMMDD (기본: 오늘)")
    common.add_argument("--years",  type=int, default=1, help="기간(년), --start 없을 때 사용")
    common.add_argument("--catalog-path", default="./catalog")
    common.add_argument("--dry-run",   action="store_true", help="저장 없이 API 호출만")
    common.add_argument("--overwrite", action="store_true", help="기존 데이터 삭제 후 재작성")
    common.add_argument("--mock",      action="store_true", help="KIS 모의투자 서버")

    code_grp = argparse.ArgumentParser(add_help=False)
    code_grp.add_argument("--codes", nargs="+", metavar="CODE")
    code_grp.add_argument("--file",  metavar="PATH", help="코드 목록 파일 (한 줄에 하나)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # domestic
    p = sub.add_parser("domestic", parents=[common, code_grp],
                        help="국내 주식/ETF 일봉 수집")
    p.add_argument("--market", default="J",
                   help="J=KOSPI/ETF(기본), K=KOSDAQ")
    p.set_defaults(func=cmd_domestic)

    # ib (해외주식 via Interactive Brokers)
    p = sub.add_parser("ib", parents=[common, code_grp],
                        help="해외 주식 일봉 수집 (Interactive Brokers TWS/Gateway 필요)")
    p.add_argument("--venue", default="NASDAQ",
                   help="NASDAQ(기본)/NYSE/AMEX/TSE/HKEX 등")
    p.set_defaults(func=cmd_ib)

    # index
    p = sub.add_parser("index", parents=[common, code_grp],
                        help="국내 지수 일봉 수집 (0001=KOSPI, 1001=KOSDAQ)")
    p.set_defaults(func=cmd_index)

    # batch
    p = sub.add_parser("batch", parents=[common],
                        help="CSV 배치 파일로 여러 타입 일괄 수집")
    p.add_argument("--file", required=True, metavar="PATH",
                   help="CSV: type,code,exchange(optional)")
    p.set_defaults(func=cmd_batch)

    # crno-search
    p = sub.add_parser("crno-search",
                        help="매출액으로 FSC DB에서 법인등록번호(crno) 검색")
    p.add_argument("--sale-trillion", type=float, required=True,
                   help="매출액 (조원 단위, 예: 66.2)")
    p.add_argument("--year", type=int, default=2022,
                   help="사업연도 (기본: 2022)")
    p.add_argument("--fncl-dcd", default="110",
                   help="110=연결(기본), 120=별도")
    p.add_argument("--tolerance", type=float, default=4.0,
                   help="허용 오차 %% (기본: 4.0)")
    p.set_defaults(func=cmd_crno_search)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
