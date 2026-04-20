from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from os import getenv
from pathlib import Path

import streamlit as st

from trading_logic import notes_for_scenario


DATA_PATH = Path("data.json")


st.set_page_config(page_title="Daily Trading Decision Dashboard", page_icon="📈", layout="centered")


def load_dashboard_data() -> dict:
    if not DATA_PATH.exists():
        subprocess.run([sys.executable, "job.py"], check=True)

    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if "scenario" not in raw or "action" not in raw:
        raise ValueError("data.json is missing required dashboard fields.")
    return raw


def main() -> None:
    try:
        data = load_dashboard_data()
    except Exception as exc:
        st.title("Daily Trading Decision Dashboard")
        st.error(f"Unable to load market data: {exc}")
        st.stop()

    notes = notes_for_scenario(data["scenario"])
    timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    summary = data.get("position_summary", {})

    st.title("Daily Trading Decision Dashboard")
    st.caption(f"Serving on port {getenv('PORT', '8501')}")

    qqq_col, tqqq_col = st.columns(2)
    qqq_col.metric("QQQ", f"${data['qqq']:,.2f}")
    tqqq_col.metric("TQQQ", f"${data['tqqq']:,.2f}")

    value_col, pnl_col, pnl_pct_col = st.columns(3)
    value_col.metric("Portfolio Value", f"${data.get('portfolio_value', 0):,.2f}")
    pnl_col.metric("PnL", f"${data.get('pnl', 0):,.2f}")
    pnl_pct_col.metric("PnL %", f"{data.get('pnl_percent', 0):.2f}%")

    st.subheader(f"Scenario: {data['scenario']}")
    st.markdown(
        f"""
        <div style="padding: 1.5rem 1rem; border-radius: 0.75rem; background: #111827; text-align: center;">
            <div style="font-size: 1rem; color: #9ca3af; letter-spacing: 0.2em;">ACTION</div>
            <div style="font-size: 2.4rem; font-weight: 800; color: #f9fafb; margin-top: 0.5rem;">
                {data['action']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Notes")
    st.write(notes)

    st.markdown("### Tracking State")
    ref = data.get("reference_snapshot") or {}
    st.write(
        f"Starting capital: ${data.get('starting_capital', 0):,.2f} | "
        f"Open: {summary.get('open', 0)} | "
        f"Not deployed: {summary.get('not_deployed', 0)} | "
        f"Closed: {summary.get('closed', 0)}"
    )
    if ref:
        st.caption(
            f"Reference snapshot: {ref.get('created_at', 'n/a')} | "
            f"QQQ {ref.get('qqq', '--')} | TQQQ {ref.get('tqqq', '--')}"
        )

    positions = data.get("positions", [])
    if positions:
        st.markdown("### Positions")
        st.dataframe(positions, use_container_width=True)

    st.caption(f"Last updated: {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')} from data.json")


if __name__ == "__main__":
    main()
