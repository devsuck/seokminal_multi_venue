"""Jarvis 에이전트 — 표준 principal(레벨 고정). AI는 자기 레벨 못 올린다."""
from jarvis.permissions import Level, Principal

RESEARCH_AGENT = Principal("research_agent", Level.RESEARCH_ONLY)
DATAGATE_AGENT = Principal("datagate_agent", Level.BACKTEST_ONLY)
BACKTEST_AGENT = Principal("backtest_agent", Level.BACKTEST_ONLY)
CRITIC_AGENT = Principal("critic_agent", Level.BACKTEST_ONLY)
PAPER_AGENT = Principal("paper_agent", Level.PAPER_ONLY)
LIVE_PROPOSAL_AGENT = Principal("live_proposal_agent", Level.LIVE_PROPOSAL_ONLY)
# 사람만 — live 승인·리스크·레벨 변경
HUMAN_ADMIN = Principal("human_admin", Level.ADMIN_HUMAN_ONLY, is_human=True)
