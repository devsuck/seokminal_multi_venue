# Failure Scenarios

- 원장 파일 손상 → verify_chain 이 변조·체인 단절 탐지 → 복구 절차
- 부분 쓰기 → append-only 이므로 마지막 유효 레코드까지 재생 가능
- 상위 원장 부재 → source_count 0 반환(안전), 이상 탐지 기록
- 중복 genesis → duplicate_integrity 탐지
- 디스크 부족 → 쓰기 실패(원자적), 기존 원장 불변 유지
