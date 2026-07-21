# 오라클 클라우드 상시구동 이전 — 파일럿 런북

> 맥(발열·이동) / 윈도우 데스크탑(1개월 임시)에서 벗어나, 오라클 Cloud Always
> Free ARM VM을 상시 본진으로 만드는 **단계적 파일럿**. 통째로 믿고 넘기지 않고,
> 리스크 큰 것부터 실측해 go/no-go를 가른다. 검증 끝날 때까지 **맥은 fallback으로
> 유지**(며칠), 검증되면 맥 종료.

## 스코프

- **포함**: 폴리마켓/크립토 수집기·페이퍼봇, uvicorn API, 백테스트, KIS 의존 봇(dart_bot).
- **제외**: 라이브 IB(Interactive Brokers). exploratory라 이전 안 함. `backends/ib`,
  오더플로우 IB 어댑터, IB 주문 실행 프로세스는 VM에서 **안 띄운다**(코드는 그대로 둠).
- 대시보드(별도 레포 `seokminal_dashboard`)는 백엔드 검증 후 6단계에서.

## 검증된 것 / 미검증 리스크 (이전 전 눈뜨고 갈 것)

- ✅ 검증됨: 모든 컴파일 의존성(numpy/scipy/pandas/pyarrow/pydantic/**nautilus_trader** 등)
  aarch64 wheel 존재 → ARM VM에서 설치·import 됨.
- ⚠️ 미검증: (1) **KIS가 해외 IP에서 응답하는지**(최대 관문 — 3단계에서 먼저 검증),
  (2) 실제로 며칠 무정지로 도는지(4단계), (3) 로컬 데이터/봇 상태 마이그레이션(5단계),
  (4) 오라클 무료티어 best-effort(회수/장애 가능 — 단일 장애점).

---

## 1단계 — 오라클 VM 프로비저닝 (님이 인터랙티브로)

1. Oracle Cloud 가입(카드 인증). Always Free 대상.
2. **Compute > Instances > Create**:
   - Image: **Ubuntu 24.04** (python3.12 기본 — 22.04는 python3.10이라 부적합)
   - Shape: **VM.Standard.A1.Flex** (Ampere ARM), 예: 2 OCPU / 12GB (무료 한도 4 OCPU/24GB 내)
   - "out of capacity" 뜨면 다른 가용도메인/리전으로 재시도(무료 ARM 물량 숙명)
   - SSH 공개키 등록
3. **네트워킹**: VCN 기본 생성. 보안리스트에서 필요한 인바운드만 오픈:
   - 22(SSH) — 기본 열림
   - (선택) 8000(API), 3000/대시보드 — **되도록 열지 말고 SSH 터널 사용** 권장
   - ⚠️ 우분투 이미지 자체 iptables가 잠겨있을 수 있음 → `sudo iptables -L` 확인,
     필요 시 netfilter-persistent 규칙 추가
4. 접속: `ssh ubuntu@<VM-공인IP>`

## 2단계 — 코드 + 셋업 (VM에서)

```bash
# 두 레포 clone (백엔드 + 대시보드)
git clone <multi_venue-repo-url> ~/seokminal_multi_venue
git clone <dashboard-repo-url>   ~/seokminal_dashboard   # 대시보드는 6단계에서

cd ~/seokminal_multi_venue

# (권장) 맥에서 검증된 버전 핀 가져오기 — nautilus 버전 드리프트 예방:
#   맥에서:  pip freeze > requirements.lock   -> scp로 VM 레포 루트에 복사
# 그런 다음:
bash scripts/deploy/setup_server.sh
```

`.env` 재구성(맥에서 복사 또는 재작성) — 최소 파일럿엔 KIS 키만 있으면 됨.
전체 이전 시 FRED/ECOS/KRX/DART/data.go.kr/OpenAI/CORS_ORIGINS 등 전부 필요.
`.env`는 gitignore라 GitHub에 없음 — **직접 옮겨야 함**(scp 또는 재입력).

## 3단계 — KIS 해외IP 관문 (★ go/no-go 게이트, 제일 먼저)

```bash
cd ~/seokminal_multi_venue
python scripts/deploy/test_kis_connectivity.py
```

- **PASS** → KIS가 해외 IP에서 정상. 계속 진행.
- **FAIL** → 로컬 맥에서 *같은 키로* 같은 스크립트 실행:
  - 맥은 PASS인데 VM만 FAIL → **KIS가 해외 IP 차단 확정**. 선택지:
    (a) dart_bot만 맥/한국VPS에 남기고 나머지는 클라우드, (b) 서울/춘천 리전 VM
    (무료 ARM 물량 확보 어려움), (c) dart_bot 클라우드 이전 보류.
  - 맥도 FAIL → 자격증명/키 문제(IP 무관). .env 점검.

KIS가 dart_bot의 유일한 브로커 의존이므로, 이 게이트가 "전부 클라우드"의 마지노선이다.

## 4단계 — 파일럿 상시서비스 1개 (며칠 관찰)

가장 안전한 서비스(순수 HTTP 수집기)부터 systemd로:

```bash
sudo cp scripts/deploy/systemd/sharp-wallet-collect.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sharp-wallet-collect
systemctl status sharp-wallet-collect
tail -f logs/sharp-wallet-collect.log
```

- 하루이틀 무정지로 도는지 + `research/data/polymarket_sharp_wallet/*.jsonl`이
  실제로 쌓이는지 확인. (이 VM은 이 컨테이너와 달리 Polymarket 아웃바운드 열림)
- systemd `Restart=always`라 크래시/재부팅에도 자동 부활 — tmux 수동 babysitting 끝.
  progress 로그의 "고아 프로세스(PPID=1)" 이슈도 systemd 관리로 해소됨.
- 나머지 수집기/봇도 같은 패턴으로 유닛 복제(ExecStart의 `-m` 모듈명만 교체).

## 5단계 — 데이터/상태 마이그레이션 (맥 → VM)

새 VM은 백지다. gitignore라 GitHub에 없는 로컬 산출물을 직접 옮겨야 한다.
**맥에서** rsync(같은 게 없으면 scp):

```bash
# 맥에서 실행 (VM으로 push). 경로는 실제 맥 레포 위치에 맞게.
cd <맥의 seokminal_multi_venue>
VM=ubuntu@<VM-공인IP>

# 봇 상태·감사로그·그래프 (연속성 필수 — 없으면 페이퍼봇 포지션/PnL 끊김)
rsync -avz data/                         $VM:~/seokminal_multi_venue/data/
# nautilus 백테스트 카탈로그 (백테스트용)
rsync -avz catalog/                      $VM:~/seokminal_multi_venue/catalog/    2>/dev/null || true
# 에이전트 상태 (lv5 등 cycle 히스토리)
rsync -avz jarvis/_state/                $VM:~/seokminal_multi_venue/jarvis/_state/
# 수집 원자재 중 재생성 불가한 것들(용량 큼 — 필요한 것만 선별):
#   research/data/polymarket_sharp_wallet, polymarket_arb, polymarket_event_divergence,
#   polymarket_tick, cross_venue_skew, hl_orderflow_* 등
rsync -avz research/data/polymarket_sharp_wallet/  $VM:~/seokminal_multi_venue/research/data/polymarket_sharp_wallet/
# (그 외 큰 틱 디렉토리는 용량 보고 선별 — 200GB 무료 디스크 관리)
```

체크리스트:
- [ ] `data/` (dart_autobot.json, order_audit.json, knowledge_graph.json, KRX parquet 등)
- [ ] `catalog/` (nautilus 백테스트 카탈로그)
- [ ] `jarvis/_state/` (에이전트 cycle/성과)
- [ ] `research/data/` 하위 필요한 수집 원자재(재생성 불가한 것 우선)
- [ ] `.env` (2단계에서 이미 했으면 skip)
- [ ] `~/.cache/kis_tokens/`는 **안 옮겨도 됨**(자동 재발급)

⚠️ 봇을 VM에서 켜기 전에 상태파일을 먼저 옮길 것 — 안 그러면 백지 상태로
새로 시작해 포지션/PnL 연속성이 끊긴다(맥에선 계속 돌던 것과 별개 히스토리가 됨).
**이전 중엔 맥과 VM에서 같은 봇을 동시에 돌리지 말 것**(이중 주문/상태 충돌).

## 6단계 — go/no-go 판정 & 전체 전환

- 수집기 며칠 안정 + KIS PASS + 상태 마이그레이션 OK → 나머지 서비스 systemd 등록:
  - uvicorn API (nautilus import 확인 필수 — setup 스모크에서 봤을 것)
  - 폴리마켓 다각화 봇, dart_bot, 오더플로우(단, IB 어댑터 제외), lv5 에이전트 등
  - 대시보드: `seokminal_dashboard`에서 `npm ci && npm run build && npm run start`,
    SSH 터널로 접속(공개 포트 노출 지양)
- 안정 확인되면 **맥 종료** — 여기서부터 "내 컴퓨터 안 켜도 상시구동" 달성.
- 문제 나면 맥이 아직 살아있으니 롤백 안전.

## 되돌리기 / 정리

- VM만 정리하면 됨(인스턴스 종료). 로컬 맥은 이전 내내 그대로였으니 원상복귀 리스크 0.
- 이 파일럿 킷 파일들(`scripts/deploy/*`, `docs/deploy/*`)은 레포에 남겨 재사용.
