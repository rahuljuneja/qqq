from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yfinance as yf

from trading_logic import build_decision


OUTPUT_PATH = Path("data.json")
STATE_PATH = Path("state.json")
DEFAULT_STARTING_CAPITAL = 10000.0


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def determine_change(
    prev_scenario: str | None,
    prev_action: str | None,
    current_scenario: str,
    current_action: str,
) -> str:
    if prev_scenario is None and prev_action is None:
        return "INITIAL"
    if prev_scenario != current_scenario:
        return "SCENARIO_CHANGED"
    if prev_action != current_action:
        return "ACTION_CHANGED"
    return "NO_CHANGE"


def normalize_state(state: dict[str, Any], decision_payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False

    if not isinstance(state.get("starting_capital"), (int, float)):
        state["starting_capital"] = DEFAULT_STARTING_CAPITAL
        changed = True

    if not isinstance(state.get("positions"), list):
        state["positions"] = []
        changed = True

    reference_snapshot = state.get("reference_snapshot")
    if not isinstance(reference_snapshot, dict) or not reference_snapshot:
        state["reference_snapshot"] = {
            "status": "NOT_DEPLOYED",
            "created_at": decision_payload["timestamp"],
            "qqq": decision_payload["qqq"],
            "tqqq": decision_payload["tqqq"],
        }
        changed = True

    return state, changed


def fetch_option_price(symbol: str, expiration: str, option_type: str, strike: float) -> float:
    chain = yf.Ticker(symbol).option_chain(expiration)
    table = chain.calls if option_type.lower() == "call" else chain.puts
    matches = table.loc[(table["strike"] - float(strike)).abs() < 0.001]
    if matches.empty:
        raise ValueError(f"No {option_type} contract found for {symbol} {expiration} {strike}.")

    row = matches.iloc[0]
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    last_price = float(row.get("lastPrice", 0) or 0)

    if bid > 0 and ask > 0:
        price = (bid + ask) / 2
    elif last_price > 0:
        price = last_price
    else:
        price = max(bid, ask)

    if price <= 0:
        raise ValueError(f"No usable market price found for {symbol} {expiration} {strike} {option_type}.")

    return round(price, 2)


def enrich_position(position: dict[str, Any], price_cache: dict[str, float]) -> dict[str, Any]:
    enriched = dict(position)
    position_type = str(position.get("type", "stock")).lower()
    status = str(position.get("status", "NOT_DEPLOYED")).upper()
    side = str(position.get("side", "LONG")).upper()
    symbol = str(position["symbol"]).upper()

    enriched["symbol"] = symbol
    enriched["status"] = status
    enriched["side"] = side
    enriched["current_price"] = None
    enriched["market_value"] = None
    enriched["cost_basis"] = None
    enriched["pnl"] = None
    enriched["pnl_percent"] = None

    if status != "OPEN":
        return enriched

    if position_type == "stock":
        quantity = float(position["quantity"])
        entry_price = float(position["entry_price"])
        current_price = price_cache.setdefault(symbol, decision_price(symbol))
        cost_basis = quantity * entry_price
        market_value = quantity * current_price
        pnl = market_value - cost_basis if side == "LONG" else cost_basis - market_value
    elif position_type == "option":
        contracts = float(position["contracts"])
        multiplier = float(position.get("multiplier", 100))
        entry_price = float(position["entry_price"])
        expiration = str(position["expiration"])
        option_type = str(position["option_type"]).lower()
        strike = float(position["strike"])
        current_price = fetch_option_price(symbol, expiration, option_type, strike)
        units = contracts * multiplier
        cost_basis = units * entry_price
        market_value = units * current_price
        pnl = market_value - cost_basis if side == "LONG" else cost_basis - market_value
    else:
        raise ValueError(f"Unsupported position type: {position_type}")

    pnl_percent = (pnl / cost_basis * 100) if cost_basis else 0.0

    enriched["current_price"] = round(current_price, 2)
    enriched["market_value"] = round(market_value, 2)
    enriched["cost_basis"] = round(cost_basis, 2)
    enriched["pnl"] = round(pnl, 2)
    enriched["pnl_percent"] = round(pnl_percent, 2)
    return enriched


def decision_price(symbol: str) -> float:
    history = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
    if history.empty:
        raise ValueError(f"No price data returned for {symbol}.")
    close = history["Close"].dropna()
    if close.empty:
        raise ValueError(f"No closing prices returned for {symbol}.")
    return round(float(close.iloc[-1]), 2)


def main() -> None:
    previous = load_json(OUTPUT_PATH, None)
    decision = build_decision()
    payload = asdict(decision)

    state, state_changed = normalize_state(load_json(STATE_PATH, {}), payload)
    positions = state["positions"]
    price_cache = {"QQQ": payload["qqq"], "TQQQ": payload["tqqq"]}
    enriched_positions = [enrich_position(position, price_cache) for position in positions]

    prev_scenario = previous.get("scenario") if previous else None
    prev_action = previous.get("action") if previous else None
    total_pnl = round(sum(position["pnl"] or 0.0 for position in enriched_positions), 2)
    starting_capital = float(state["starting_capital"])
    portfolio_value = round(starting_capital + total_pnl, 2)
    pnl_percent = round((total_pnl / starting_capital * 100), 2) if starting_capital else 0.0

    payload["prev_scenario"] = prev_scenario
    payload["prev_action"] = prev_action
    payload["change"] = determine_change(
        prev_scenario=prev_scenario,
        prev_action=prev_action,
        current_scenario=decision.scenario,
        current_action=decision.action,
    )
    payload["portfolio_value"] = portfolio_value
    payload["pnl"] = total_pnl
    payload["pnl_percent"] = pnl_percent
    payload["starting_capital"] = starting_capital
    payload["reference_snapshot"] = state["reference_snapshot"]
    payload["positions"] = enriched_positions
    payload["position_summary"] = {
        "open": sum(1 for position in enriched_positions if position["status"] == "OPEN"),
        "not_deployed": sum(1 for position in enriched_positions if position["status"] == "NOT_DEPLOYED"),
        "closed": sum(1 for position in enriched_positions if position["status"] == "CLOSED"),
    }

    if state_changed:
        save_json(STATE_PATH, state)

    save_json(OUTPUT_PATH, payload)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
