import logging
import os
import subprocess
import time
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)

SUBREDDIT_QUERIES = [
    ("r/Kalshi", "Kalshi temperature weather market strategies edges mispricing 2026"),
    ("r/PredictionMarkets", "weather prediction market edge strategy mispricing temperature"),
    ("r/algotrading", "prediction market algorithmic strategy edge temperature weather"),
    ("r/weather", "temperature forecast accuracy model comparison NWS reliability"),
]

SESSION_NAME = "gemini_reddit_research"


def _run(cmd: str, timeout: int = 10) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout + result.stderr


def _tmux_send(session: str, text: str):
    subprocess.run(
        ["tmux", "send-keys", "-t", session, text, "Enter"],
        capture_output=True,
    )


def _tmux_capture(session: str) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session, "-p", "-S", "-500"],
        capture_output=True, text=True,
    )
    return result.stdout


def _kill_session(session: str):
    subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)


def run_daily_research() -> str:
    """Run Reddit research via Gemini CLI. Returns markdown report string."""
    findings = {}

    # Start tmux session with Gemini CLI
    _run(f"tmux kill-session -t {SESSION_NAME} 2>/dev/null; true")
    _run(f"tmux new-session -d -s {SESSION_NAME} -x 200 -y 50")
    time.sleep(1)
    _tmux_send(SESSION_NAME, "gemini -m gemini-2.5-pro-preview-05-06")
    time.sleep(5)  # wait for Gemini to load

    for subreddit, query in SUBREDDIT_QUERIES:
        full_query = (
            f"Search Reddit {subreddit} for recent posts about: {query}. "
            f"Summarize the top strategies, edges, or insights mentioned. "
            f"Be concise — 3-5 bullet points max."
        )
        logger.info(f"reddit_research: querying {subreddit}")
        _tmux_send(SESSION_NAME, full_query)
        time.sleep(45)  # wait for response

        output = _tmux_capture(SESSION_NAME)
        # Extract the response: everything after the query text up to the next prompt box
        lines = output.split("\n")
        capturing = False
        response_lines = []
        for line in lines:
            if query[:30] in line and not line.strip().startswith("│"):
                capturing = True
                continue
            if capturing:
                if "╭" in line or "Type your message" in line:
                    break
                response_lines.append(line)

        findings[subreddit] = "\n".join(response_lines).strip() or "(no response captured)"

    _kill_session(SESSION_NAME)

    # Build markdown report
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# Strategy Research — {today}", ""]
    for subreddit, content in findings.items():
        lines.append(f"## {subreddit}")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)


def research_today_if_needed():
    """Run research once per day. Skips if today's report already exists."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(config.LOG_DIR, f"research_{today}.md")

    if os.path.exists(path):
        logger.info("reddit_research: today's research already done, skipping")
        return

    logger.info("reddit_research: starting daily research session")
    os.makedirs(config.LOG_DIR, exist_ok=True)

    try:
        # Check tmux and gemini are available
        if subprocess.run(["which", "tmux"], capture_output=True).returncode != 0:
            logger.warning("reddit_research: tmux not found, skipping research")
            return
        if subprocess.run(["which", "gemini"], capture_output=True).returncode != 0:
            logger.warning("reddit_research: gemini CLI not found, skipping research")
            return

        report = run_daily_research()
        with open(path, "w") as f:
            f.write(report)
        logger.info(f"reddit_research: saved to {path}")
        print(f"  Research report saved: {path}")

    except Exception as e:
        logger.error(f"reddit_research: failed: {e}")
        print(f"  WARNING: Reddit research failed: {e} (trading continues normally)")
