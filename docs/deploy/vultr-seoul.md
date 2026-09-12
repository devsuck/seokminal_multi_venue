# Vultr Seoul 상시구동 이전 — 런북

> `docs/deploy/oracle-pilot.md` 각색판. 오라클 대신 **Vultr Seoul(ICN) 리전**을 쓰는 이유:
> 1) 국내 IP라 KIS 해외IP 차단 게이트(오라클 파일럿의 최대 리스크였음) 자체가 거의 없음,
> 2) 오라클 Always Free는 계정 예고없이 정지/자원회수 사례가 많아 무인 5주+엔 안 맞음,
> 3) 유료($6~12/월)라 대신 안정성·지원 확실.
>
> 배경: 군 입대(2026-10-19 예정)로 맥을 상시 켜둘 수 없어 진짜 클라우드 이전 필요.
> `docs/deploy/oracle-pilot.md` 3단계(KIS go/no-go 게이트), 5단계(데이터 마이그레이션)
> 런북은 프로바이더 무관하게 그대로 재사용.

## 스코프 (이 문서)

VM 생성 → 코드 배포 → nginx+HTTPS → systemd로 API/대시보드 상시구동까지.
**포함 안 됨** (별도 서브프로젝트): launchd 잡 9개 → cron/systemd timer 이전,
세션인증 SameSite/CORS 조정, `data/`·`jarvis/_state/` 등 상태 마이그레이션,
백업/스냅샷 전략. 각각 `docs/progress.md` 참고.

## 1단계 — VM 생성 (사람이 인터랙티브로, 결제/SSH키라 대행 불가)

1. Vultr 가입, 결제수단 등록.
2. **Deploy New Server**:
   - Location: **Seoul (ICN)**
   - Type: Cloud Compute — Regular Performance, $6/mo(1 vCPU/1GB) 또는 $12/mo(2GB) — 페이퍼 단계 저트래픽엔 1GB로 충분, nautilus_trader 빌드 메모리 빡빡하면 2GB로
   - Image: **Ubuntu 24.04 LTS** (python3.12 기본 — 22.04는 3.10이라 부적합, 오라클 문서와 동일 이유)
   - SSH 공개키 등록(비밀번호 로그인 끄기)
3. 방화벽(Vultr Cloud Firewall 또는 서버 내 ufw): 22(SSH), 80/443(nginx)만 오픈. 8000/3000은
   **외부 노출 안 함** — nginx가 로컬에서만 리버스프록시.
4. 접속: `ssh root@<VM-공인IP>` (또는 생성한 non-root 유저)

## 2단계 — 도메인 + DNS

도메인 하나 구매(가비아/Namecheap 등, 연 1만원대). A 레코드 2개를 VM 공인IP로:
- `api.<도메인>` → API(8000)
- `app.<도메인>` → 대시보드(3000)

서브도메인 분리 이유: `api_server/auth.py`의 세션쿠키가 `SameSite=Lax`(같은 사이트 전제)로
돼있어 — 서브도메인 분리하면 `SameSite=None; Secure`로 바꿔야 함. **(서브프로젝트3 완료:
`COOKIE_SAMESITE`/`COOKIE_SECURE` env로 오버라이드 가능해짐.)** VM `.env`에 추가:
```
COOKIE_SAMESITE=none
COOKIE_SECURE=true
CORS_ORIGINS=https://app.<도메인>
```
(`CORS_ORIGINS`는 이미 env화돼있던 기존 기능 — 서브3에서 새로 안 만듦, 여기서만 값 채움.)

## 3단계 — 코드 + 셋업 (VM에서)

```bash
git clone <this-repo-url> ~/seokminal-multi-venue
cd ~/seokminal-multi-venue
bash scripts/deploy/setup_server.sh   # ARM 전용처럼 써있지만 실제론 python>=3.11만 체크 — x86도 그대로 동작
```

`.env` 재구성(서브프로젝트4 — 시크릿 관리) — gitignore라 GitHub엔 없음, 최신 키
목록은 `.env.example` 참고. 별도 시크릿 매니저는 이 규모(1인 운영, 단일 VM)엔
과함(YAGNI) — SSH(이미 암호화 채널) 경유 scp면 충분:

```bash
# 맥에서
scp .env root@<VM-공인IP>:~/seokminal-multi-venue/.env
ssh root@<VM-공인IP> "chmod 600 ~/seokminal-multi-venue/.env"
```

VM에서 새로 채울 값(맥 값 그대로 재사용해도 되지만 별도 머신이니 새로 발급 권장):
- `SESSION_SECRET`: `python -c "import secrets; print(secrets.token_hex(32))"`로 VM 전용 새 값
- `COOKIE_SAMESITE=none`, `COOKIE_SECURE=true`, `CORS_ORIGINS=https://app.<도메인>` (2단계 참고)
- `SEOKMINAL_RSS_LIMIT_MB=400` (1GB VM 기준, `docs/deploy/vultr-seoul-jobs.md` 참고)

대시보드도 같은 VM에 clone+build:
```bash
git clone <dashboard-repo-url> ~/seokminal-dashboard
cd ~/seokminal-dashboard
npm ci
echo "NEXT_PUBLIC_API_URL=https://api.<도메인>" > .env.production
npm run build
```

## 4단계 — KIS 게이트 확인 (지금 3전략 다 unarmed라 안 급함, 그래도 미리)

```bash
cd ~/seokminal-multi-venue
python scripts/deploy/test_kis_connectivity.py
```
Seoul 리전이라 오라클 파일럿 때보다 PASS 가능성 높음. FAIL이어도 지금 arm된 전략이
없어 즉시 영향 없음 — `docs/deploy/oracle-pilot.md` 3단계의 대응 옵션 그대로 적용 가능.

## 5단계 — nginx + HTTPS

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp scripts/deploy/nginx/seokminal.conf /etc/nginx/sites-available/seokminal
# 파일 안 <API_DOMAIN>/<APP_DOMAIN>을 실제 도메인으로 치환
sudo ln -s /etc/nginx/sites-available/seokminal /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d api.<도메인> -d app.<도메인>   # Let's Encrypt, 자동갱신 cron 같이 설치됨
```

## 6단계 — systemd로 API/대시보드 상시구동

```bash
sudo cp scripts/deploy/systemd/seokminal-api.service /etc/systemd/system/
sudo cp scripts/deploy/systemd/seokminal-dashboard.service /etc/systemd/system/
# 두 파일 안 <REPO_USER>/<REPO_PATH> 치환(주석 참고)
sudo systemctl daemon-reload
sudo systemctl enable --now seokminal-api seokminal-dashboard
systemctl status seokminal-api seokminal-dashboard
journalctl -u seokminal-api -f
```

`Restart=always`라 크래시/재부팅에도 자동 부활 — launchd KeepAlive와 동급.

## 검증

- `curl https://api.<도메인>/health` — API 응답
- 브라우저로 `https://app.<도메인>` — 대시보드 로드, API 호출 정상(CORS_ORIGINS에
  `https://app.<도메인>` 추가 안 하면 여기서 막힘 — `.env`의 `CORS_ORIGINS` 확인)
- 재부팅 후(`sudo reboot`) 두 서비스 자동 기동하는지

## 다음 (별도 서브프로젝트)

- ~~launchd 9개 → systemd timer/cron 이전~~ 서브2 완료(`docs/deploy/vultr-seoul-jobs.md`)
- ~~세션인증 SameSite=None+Secure 전환~~ 서브3 완료(위 2단계 `.env` 참고)
- ~~시크릿 관리~~ 서브4 완료(위 3단계, `.env.example` 최신화)
- `data/`·`jarvis/_state/`·`research/data/` 마이그레이션(`docs/deploy/oracle-pilot.md` 5단계
  런북 그대로, VM 주소만 교체) + 백업 전략(서브5)
- 컷오버 + 며칠 드라이런, 맥 종료(서브6) — VM 실제 생성 후에만 진행 가능
