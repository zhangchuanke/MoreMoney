import json, random, time, threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, Response, request, send_file

app = Flask(__name__)
_lock = threading.Lock()

_state = {
    "session_id": "session_20260329_090000",
    "trading_phase": "morning",
    "risk_level": "medium",
    "market_sentiment": "greed",
    "iteration_count": 14,
    "max_iterations": 20,
    "circuit_breaker_triggered": False,
    "daily_loss_limit_reached": False,
    "defense_mode": False,
    "kill_switch_state": "NORMAL",
    "portfolio": {
        "total_assets": 1032580.00,
        "cash": 412800.00,
        "daily_pnl": 8420.50,
        "total_pnl": 32580.00,
        "max_drawdown": 0.042,
        "win_rate": 0.673,
        "sharpe_ratio": 1.87,
        "calmar_ratio": 2.14,
        "sortino_ratio": 2.53,
        "profit_factor": 1.92,
        "total_trades": 47,
        "win_trades": 31,
        "loss_trades": 16,
        "avg_win": 3240.0,
        "avg_loss": -1890.0,
        "positions": {
            "600519": {"name": "\u8d35\u5dde\u8305\u53f0", "qty": 20,  "cost": 1680.0, "current_price": 1724.5, "market_value": 34490, "pnl_pct": 0.0265,  "sector": "\u98df\u54c1\u996e\u6599", "stop_loss": 1612.0, "take_profit": 2068.0},
            "000858": {"name": "\u4e94\u7c2e\u6db2",   "qty": 100, "cost": 148.0,  "current_price": 155.3,  "market_value": 15530, "pnl_pct": 0.0493,  "sector": "\u98df\u54c1\u996e\u6599", "stop_loss": 137.6,  "take_profit": 177.6},
            "300750": {"name": "\u5b81\u5fb7\u65f6\u4ee3", "qty": 50,  "cost": 220.0,  "current_price": 208.4,  "market_value": 10420, "pnl_pct": -0.0527, "sector": "\u65b0\u80fd\u6e90", "stop_loss": 193.8,  "take_profit": 249.6},
            "601318": {"name": "\u4e2d\u56fd\u5e73\u5b89", "qty": 200, "cost": 44.5,   "current_price": 47.8,   "market_value": 9560,  "pnl_pct": 0.0742,  "sector": "\u91d1\u878d",     "stop_loss": 40.1,   "take_profit": 53.4},
            "000001": {"name": "\u5e73\u5b89\u94f6\u884c", "qty": 500, "cost": 10.2,   "current_price": 9.87,   "market_value": 4935,  "pnl_pct": -0.0324, "sector": "\u91d1\u878d",     "stop_loss": 9.20,   "take_profit": 11.22},
        },
    },
    "market_overview": {
        "sh_index":  {"code": "000001", "name": "\u4e0a\u8bc1\u6307\u6570", "price": 3287.45,  "change_pct": 0.82, "open": 3261.2,  "high": 3295.1,  "low": 3255.8,  "volume": 3421.5},
        "sz_index":  {"code": "399001", "name": "\u6df1\u8bc1\u6210\u6307", "price": 10523.76, "change_pct": 1.14, "open": 10401.3, "high": 10558.2, "low": 10389.4, "volume": 4832.1},
        "cyb_index": {"code": "399006", "name": "\u521b\u4e1a\u677f\u6307", "price": 2156.33,  "change_pct": 1.47, "open": 2123.5,  "high": 2168.7,  "low": 2118.2,  "volume": 1923.4},
        "kcb_index": {"code": "000688", "name": "\u79d1\u521b50",         "price": 1043.22,  "change_pct": 0.63, "open": 1036.8,  "high": 1048.3,  "low": 1031.9,  "volume": 892.3},
    },
    "sector_rotation": {
        "\u98df\u54c1\u996e\u6599": 2.34, "\u65b0\u80fd\u6e90": -0.87,
        "\u91d1\u878d": 1.12, "\u533b\u836f": 0.45, "\u79d1\u6280": 1.89,
        "\u6d88\u8d39": 0.73, "\u5730\u4ea7": -1.23, "\u519b\u5de5": 3.12,
        "\u6709\u8272\u91d1\u5c5e": 2.56, "\u7164\u70ad": -0.44,
    },
    "capital_flow": {
        "northbound": {"today_net": 32.4, "5day_net": 128.7, "consecutive_days": 3, "sh_stock_connect": 18.2, "sz_stock_connect": 14.2},
        "main_force": {"net_inflow": 45.6, "large_order_net": 28.3, "super_large_net": 12.1, "medium_order_net": -8.4, "small_order_net": -31.2},
        "sector_flow": {"\u98df\u54c1\u996e\u6599": 12.3, "\u79d1\u6280": 8.7, "\u519b\u5de5": 15.2, "\u91d1\u878d": 4.1, "\u65b0\u80fd\u6e90": -6.3, "\u533b\u836f": 2.8},
    },
    "signals": [
        {"symbol": "600519", "dimension": "technical",    "direction": "bullish", "strength": 0.82, "confidence": 0.79, "reasoning": "MACD\u91d1\u53c9\uff0cKDJ\u8d85\u5356\u53cd\u5f39"},
        {"symbol": "600519", "dimension": "capital_flow", "direction": "bullish", "strength": 0.75, "confidence": 0.81, "reasoning": "\u5317\u5411\u8d44\u91d1\u51c0\u6d41\u51651.2\u4ebf"},
        {"symbol": "000858", "dimension": "fundamental",  "direction": "bullish", "strength": 0.68, "confidence": 0.72, "reasoning": "PE 25x\u4f4e\u4e8e\u5386\u53f2\u5747\u503c"},
        {"symbol": "300750", "dimension": "sentiment",    "direction": "bearish", "strength": 0.61, "confidence": 0.65, "reasoning": "\u5e02\u573a\u60c5\u7eea\u504f\u7a7a"},
        {"symbol": "601318", "dimension": "technical",    "direction": "bullish", "strength": 0.71, "confidence": 0.74, "reasoning": "\u5747\u7ebf\u591a\u5934\u6392\u5217"},
        {"symbol": "000001", "dimension": "capital_flow", "direction": "bearish", "strength": 0.55, "confidence": 0.60, "reasoning": "\u4e3b\u529b\u8d44\u91d1\u6301\u7eed\u6d41\u51fa"},
    ],
    "decisions": [
        {"action": "buy",    "symbol": "600519", "target_position": 0.08, "current_position": 0.05, "stop_loss": 1612.0, "take_profit": 2068.0, "urgency": "normal",    "reasoning": "\u56db\u7ef4\u7efc\u5408\u8bc4\u52060.79", "risk_score": 0.28},
        {"action": "hold",   "symbol": "000858", "target_position": 0.05, "current_position": 0.05, "stop_loss": 137.6,  "take_profit": 177.6,  "urgency": "passive",   "reasoning": "\u57fa\u672c\u9762\u5f3a\u52b2", "risk_score": 0.22},
        {"action": "reduce", "symbol": "300750", "target_position": 0.02, "current_position": 0.04, "stop_loss": 193.8,  "take_profit": 249.6,  "urgency": "normal",    "reasoning": "\u60c5\u7eea\u9762\u8f6c\u7a7a", "risk_score": 0.55},
        {"action": "sell",   "symbol": "000001", "target_position": 0.00, "current_position": 0.02, "stop_loss": 9.20,   "take_profit": 11.22,  "urgency": "immediate", "reasoning": "\u89e6\u53ca\u6b62\u635f\u7ebf", "risk_score": 0.72},
    ],
    "executed_orders": [
        {"action": "buy",  "symbol": "600519", "name": "\u8d35\u5dde\u8305\u53f0", "quantity": 10,  "filled_price": 1718.0, "amount": 17180, "status": "filled",  "time": "09:32:14", "slippage": 0.0012},
        {"action": "sell", "symbol": "300750", "name": "\u5b81\u5fb7\u65f6\u4ee3", "quantity": 20,  "filled_price": 209.1,  "amount": 4182,  "status": "filled",  "time": "10:15:37", "slippage": 0.0008},
        {"action": "buy",  "symbol": "601318", "name": "\u4e2d\u56fd\u5e73\u5b89", "quantity": 100, "filled_price": 47.5,   "amount": 4750,  "status": "filled",  "time": "10:48:02", "slippage": 0.0005},
        {"action": "sell", "symbol": "000001", "name": "\u5e73\u5b89\u94f6\u884c", "quantity": 200, "filled_price": 9.85,   "amount": 1970,  "status": "filled",  "time": "11:03:29", "slippage": 0.0015},
        {"action": "buy",  "symbol": "000858", "name": "\u4e94\u7c2e\u6db2",       "quantity": 50,  "filled_price": 154.8,  "amount": 7740,  "status": "partial", "time": "11:22:45", "slippage": 0.0006},
    ],
    "risk_flags": [
        "300750 \u6301\u4ed3\u4e8f\u635f\u8d85\u8fc75%\uff0c\u63a5\u8fd1\u6b62\u635f\u7ebf",
        "000001 \u65e5\u5185\u7d2f\u8ba1\u4e8f\u635f\u89e6\u53ca\u98ce\u63a7\u9608\u5024\uff0c\u5df2\u6e05\u4ed3",
    ],
    "dynamic_position": {
        "max_single_position_pct": 0.15, "max_sector_pct": 0.32, "max_total_position_pct": 0.60,
        "stop_loss_pct": 0.065, "take_profit_pct": 0.18, "trailing_stop_pct": 0.045,
        "vol_multiplier": 0.82, "drawdown_multiplier": 0.95, "effective_risk_level": "medium",
        "current_total_position": 0.60, "vix_estimate": 22.4, "sh_amplitude": 0.024,
    },
    "risk_params": {
        "MAX_SINGLE_POSITION_PCT": 0.20, "MAX_SECTOR_CONCENTRATION_PCT": 0.40,
        "MAX_TOTAL_POSITION_PCT": 0.80, "DEFAULT_STOP_LOSS_PCT": 0.07,
        "DEFAULT_TAKE_PROFIT_PCT": 0.20, "MAX_DAILY_LOSS_PCT": 0.02,
        "MAX_DAILY_TRADES": 20, "MAX_DRAWDOWN_LIMIT": 0.15,
        "MARKET_CIRCUIT_BREAKER_PCT": 5.0, "LIQUIDITY_MIN_DAILY_AMOUNT": 50000000,
        "CIRCUIT_BREAKER_AMPLITUDE": 0.15, "COST_BUY_COMMISSION_PCT": 0.0003,
        "COST_SELL_COMMISSION_PCT": 0.0013, "COST_DEFAULT_SLIPPAGE_PCT": 0.002,
        "DYNAMIC_POSITION_ENABLED": True, "COUNTERPARTY_NB_MARKET_THRESHOLD": -30.0,
        "COUNTERPARTY_CONSECUTIVE_DAYS": 3,
    },
    "market_regime": {
        "regime": "bull", "confidence": 0.76, "veto_active": False,
        "description": "\u725b\u5e02\u8d8b\u52bf\uff0c\u6280\u672f/\u60c5\u7eea\u9762\u4f18\u5148",
        "base_weights": {"technical": 0.35, "sentiment": 0.30, "capital_flow": 0.25, "fundamental": 0.10},
        "signals": {"sh_change_pct": 0.82, "vix": 18.3,             "northbound_flow_bn": 32.4, "limit_up_count": 63,
            "limit_down_count": 12, "turnover_ratio_vs_avg": 1.18, "csi300_pe": 14.2},
    },
    "agent_status": {
        "orchestrator": {"name": "\u7f16\u6392Agent",   "status": "idle",    "last_run": "11:22:45", "run_count": 14, "avg_duration_ms": 320,  "error_count": 0},
        "technical":    {"name": "\u6280\u672f\u9762Agent", "status": "idle",    "last_run": "11:22:12", "run_count": 14, "avg_duration_ms": 180,  "error_count": 0},
        "fundamental":  {"name": "\u57fa\u672c\u9762Agent", "status": "idle",    "last_run": "11:20:33", "run_count": 7,  "avg_duration_ms": 540,  "error_count": 0},
        "sentiment":    {"name": "\u60c5\u7eea\u9762Agent", "status": "idle",    "last_run": "11:22:18", "run_count": 14, "avg_duration_ms": 210,  "error_count": 1},
        "capital_flow": {"name": "\u8d44\u91d1\u9762Agent", "status": "idle",    "last_run": "11:22:25", "run_count": 14, "avg_duration_ms": 260,  "error_count": 0},
        "risk":         {"name": "\u98ce\u63a7Agent",   "status": "idle",    "last_run": "11:22:38", "run_count": 14, "avg_duration_ms": 95,   "error_count": 0},
        "execution":    {"name": "\u6267\u884cAgent",   "status": "idle",    "last_run": "11:22:45", "run_count": 5,  "avg_duration_ms": 1240, "error_count": 0},
        "reflection":   {"name": "\u53cd\u601dAgent",   "status": "idle",    "last_run": "11:22:45", "run_count": 3,  "avg_duration_ms": 820,  "error_count": 0},
    },
    "kill_switch_history": [
        {"state": "NORMAL", "operator": "system", "reason": "\u7cfb\u7edf\u542f\u52a8", "timestamp": "2026-03-29T09:00:00"},
    ],
    "memory": {
        "market_regime": "bull",
        "learned_rules": [
            "\u767d\u9152\u677f\u5757\u5728\u6625\u8282\u524d\u540e\u6709\u660e\u663e\u7684\u5b63\u8282\u6027\u884c\u60c5\u89c4\u5f8b",
            "\u5317\u5411\u8d44\u91d1\u8fde\u7eed3\u65e5\u51c0\u6d41\u516510\u4ebf\u65f6\uff0c\u5927\u76d8\u77ed\u671f\u4e0a\u6da8\u6982\u738775%",
            "RSI > 80 \u65f6\u5165\u573a\u80dc\u7387\u663e\u8457\u4e0b\u964d\uff0c\u5e94\u7b49\u5f85\u56de\u8c03",
            "MACD\u67f1\u72b6\u7ebf\u7531\u8d1f\u8f6c\u6b63\u914d\u5408\u6210\u4ea4\u91cf\u653e\u5927\uff0c\u4e3a\u5f3a\u4fe1\u53f7",
        ],
        "successful_patterns": ["\u5747\u7ebf\u591a\u5934 + \u5317\u5411\u51c0\u6d41\u5165", "MACD\u91d1\u53c9 + \u6210\u4ea4\u91cf\u653e\u5927"],
        "failed_patterns": ["\u5355\u7eaf\u4f9d\u8d56\u60c5\u7eea\u9762\u4fe1\u53f7", "\u9006\u52bf\u6284\u5e95\u9ad8\u6ce2\u52a8\u5c0f\u76d8\u80a1"],
    },
    "dimension_weights": {"technical": 0.30, "sentiment": 0.25, "capital_flow": 0.25, "fundamental": 0.20},
    "daily_watchlist": [
        {"code": "600519", "name": "\u8d35\u5dde\u8305\u53f0", "sector": "\u98df\u54c1\u996e\u6599", "price": 1724.5, "change_pct": 1.23, "pe": 28.5, "pb": 9.2, "volume_ratio": 1.45, "score": 0.89, "reason": "MACD\u91d1\u53c9+\u5317\u5411\u51c0\u6d41\u5165", "added_at": "09:31:00", "added_by": "AI"},
        {"code": "300750", "name": "\u5b81\u5fb7\u65f6\u4ee3", "sector": "\u65b0\u80fd\u6e90",   "price": 208.4,  "change_pct": -0.87, "pe": 35.2, "pb": 4.8, "volume_ratio": 0.92, "score": 0.74, "reason": "\u57fa\u672c\u9762\u4f30\u503c\u4fee\u590d", "added_at": "10:05:00", "added_by": "AI"},
        {"code": "000858", "name": "\u4e94\u7c2e\u6db2",       "sector": "\u98df\u54c1\u996e\u6599", "price": 155.3,  "change_pct": 0.65,  "pe": 25.1, "pb": 6.3, "volume_ratio": 1.12, "score": 0.81, "reason": "PE\u4f4e\u4e8e\u5386\u53f2\u5747\u503c", "added_at": "10:22:00", "added_by": "\u624b\u52a8"},
    ],
    "logs": [
        {"time": "09:15:00", "level": "INFO",  "msg": "\u4ea4\u6613\u7cfb\u7edf\u542f\u52a8\uff0c\u6a21\u62df\u76d8\u6a21\u5f0f"},
        {"time": "09:30:05", "level": "INFO",  "msg": "\u5e02\u573a\u5f00\u76d8\uff0c\u5f00\u59cb\u626b\u63cf\u80a1\u7968\u6c60"},
        {"time": "09:31:22", "level": "INFO",  "msg": "\u6280\u672f\u9762Agent\u5b8c\u6210\u5206\u6790\uff0c\u53d1\u73b012\u4e2a\u4fe1\u53f7"},
        {"time": "09:31:45", "level": "INFO",  "msg": "\u8d44\u91d1\u9762Agent\uff1a\u5317\u5411\u4eca\u65e5\u51c0\u6d41\u5165 +32.4\u4ebf"},
        {"time": "09:32:01", "level": "WARN",  "msg": "\u60c5\u7eea\u9762Agent\uff1a\u65b0\u80fd\u6e90\u677f\u5757\u8d1f\u9762\u60c5\u7eea\u4e0a\u5347"},
        {"time": "09:32:14", "level": "INFO",  "msg": "\u6267\u884c\u4e70\u5165 600519 x10 @ 1718.0"},
        {"time": "10:15:37", "level": "INFO",  "msg": "\u6267\u884c\u5356\u51fa 300750 x20 @ 209.1"},
        {"time": "11:03:29", "level": "WARN",  "msg": "\u98ce\u63a7\u89e6\u53d1\uff1a000001 \u6b62\u635f\u6e05\u4ed3"},
        {"time": "11:22:45", "level": "INFO",  "msg": "\u53cd\u601dAgent\uff1a\u672c\u8f6e\u64cd\u4f5c\u590d\u76d8\u5b8c\u6210"},
    ],
    "equity_curve": [],
}

def _gen_equity_curve():
    base = 1_000_000
    curve = []
    val = base
    for i in range(60):
        d = (datetime.now() - timedelta(days=59 - i)).strftime("%m-%d")
        val = val * (1 + random.gauss(0.002, 0.007))
        curve.append({"date": d, "value": round(val, 2)})
    return curve

_state["equity_curve"] = _gen_equity_curve()

def _simulate_tick():
    while True:
        time.sleep(3)
        with _lock:
            p = _state["portfolio"]
            p["daily_pnl"] += random.gauss(0, 180)
            p["total_assets"] = round(p["total_assets"] + random.gauss(0, 120), 2)
            p["total_pnl"] = round(p["total_assets"] - 1_000_000, 2)
            for pos in p["positions"].values():
                delta = random.gauss(0, 0.0025)
                pos["current_price"] = round(pos["current_price"] * (1 + delta), 2)
                pos["pnl_pct"] = round((pos["current_price"] - pos["cost"]) / pos["cost"], 4)
                pos["market_value"] = round(pos["current_price"] * pos["qty"], 2)
            for idx in _state["market_overview"].values():
                idx["change_pct"] = round(idx["change_pct"] + random.gauss(0, 0.04), 2)
                idx["price"] = round(idx["price"] * (1 + random.gauss(0, 0.0004)), 2)
            cf = _state["capital_flow"]
            cf["northbound"]["today_net"] = round(cf["northbound"]["today_net"] + random.gauss(0, 0.5), 1)
            cf["main_force"]["net_inflow"] = round(cf["main_force"]["net_inflow"] + random.gauss(0, 0.8), 1)
            _state["iteration_count"] = min(_state["iteration_count"] + (1 if random.random() > 0.85 else 0), 20)
            agents = list(_state["agent_status"].keys())
            active = random.choice(agents)
            for k, v in _state["agent_status"].items():
                v["status"] = "running" if k == active else "idle"

threading.Thread(target=_simulate_tick, daemon=True).start()

@app.route("/")
def index():
    import os
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")
    return send_file(html_path, mimetype="text/html")

@app.route("/api/state")
def api_state():
    with _lock:
        return jsonify(_state)

@app.route("/api/portfolio")
def api_portfolio():
    with _lock:
        return jsonify(_state["portfolio"])

@app.route("/api/signals")
def api_signals():
    with _lock:
        return jsonify(_state["signals"])

@app.route("/api/decisions")
def api_decisions():
    with _lock:
        return jsonify(_state["decisions"])

@app.route("/api/orders")
def api_orders():
    with _lock:
        return jsonify(_state["executed_orders"])

@app.route("/api/market")
def api_market():
    with _lock:
        return jsonify({"overview": _state["market_overview"], "sector_rotation": _state["sector_rotation"]})

@app.route("/api/capital_flow")
def api_capital_flow():
    with _lock:
        return jsonify(_state["capital_flow"])

@app.route("/api/risk")
def api_risk():
    with _lock:
        return jsonify({
            "risk_level": _state["risk_level"],
            "risk_flags": _state["risk_flags"],
            "circuit_breaker_triggered": _state["circuit_breaker_triggered"],
            "daily_loss_limit_reached": _state["daily_loss_limit_reached"],
            "dynamic_position": _state["dynamic_position"],
            "risk_params": _state["risk_params"],
            "kill_switch_state": _state["kill_switch_state"],
        })

@app.route("/api/agents")
def api_agents():
    with _lock:
        return jsonify(_state["agent_status"])

@app.route("/api/regime")
def api_regime():
    with _lock:
        return jsonify(_state["market_regime"])

@app.route("/api/logs")
def api_logs():
    with _lock:
        return jsonify(_state["logs"])

@app.route("/api/memory")
def api_memory():
    with _lock:
        return jsonify(_state["memory"])

@app.route("/api/equity_curve")
def api_equity_curve():
    with _lock:
        return jsonify(_state["equity_curve"])

@app.route("/api/weights")
def api_weights():
    with _lock:
        return jsonify(_state["dimension_weights"])

@app.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    with _lock:
        return jsonify(_state["daily_watchlist"])

@app.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "code cannot be empty"}), 400
    with _lock:
        if any(s["code"] == code for s in _state["daily_watchlist"]):
            return jsonify({"error": f"{code} already exists"}), 409
        entry = {
            "code": code,
            "name": (data.get("name") or "").strip() or code,
            "sector": (data.get("sector") or "").strip() or "--",
            "price": float(data.get("price") or 0),
            "change_pct": float(data.get("change_pct") or 0),
            "pe": float(data.get("pe") or 0),
            "pb": float(data.get("pb") or 0),
            "volume_ratio": float(data.get("volume_ratio") or 0),
            "score": min(1.0, max(0.0, float(data.get("score") or 0))),
            "reason": (data.get("reason") or "").strip() or "\u624b\u52a8\u6dfb\u52a0",
            "added_at": datetime.now().strftime("%H:%M:%S"),
            "added_by": "\u624b\u52a8",
        }
        _state["daily_watchlist"].append(entry)
        return jsonify(entry), 201

@app.route("/api/watchlist/<code>", methods=["DELETE"])
def api_watchlist_delete(code):
    with _lock:
        before = len(_state["daily_watchlist"])
        _state["daily_watchlist"] = [s for s in _state["daily_watchlist"] if s["code"] != code]
        if len(_state["daily_watchlist"]) == before:
            return jsonify({"error": f"{code} not found"}), 404
        return jsonify({"ok": True})

@app.route("/api/kill_switch/<action>", methods=["POST"])
def api_kill_switch(action):
    reason = (request.get_json(force=True, silent=True) or {}).get("reason", "web panel")
    with _lock:
        if action == "pause":
            _state["kill_switch_state"] = "PAUSED"
        elif action == "resume":
            _state["kill_switch_state"] = "NORMAL"
        elif action == "emergency":
            _state["kill_switch_state"] = "EMERGENCY"
        elif action == "halt":
            _state["kill_switch_state"] = "HALTED"
        elif action == "liquidate":
            _state["kill_switch_state"] = "EMERGENCY"
        _state["kill_switch_history"].append({
            "state": _state["kill_switch_state"],
            "operator": "web_panel",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })
        return jsonify({"ok": True, "state": _state["kill_switch_state"]})

def _get_skill_registry():
    try:
        import sys, os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        from skills.registry import SkillRegistry
        return SkillRegistry.instance()
    except Exception:
        return None

@app.route("/api/skills", methods=["GET"])
def api_skills_list():
    reg = _get_skill_registry()
    if reg is None:
        return jsonify({"error": "Skills module not loaded"}), 503
    return jsonify(reg.to_list())

@app.route("/api/skills/<skill_id>/enable", methods=["POST"])
def api_skills_enable(skill_id):
    reg = _get_skill_registry()
    if reg is None:
        return jsonify({"error": "Skills module not loaded"}), 503
    ok = reg.enable(skill_id)
    return jsonify({"ok": ok, "skill_id": skill_id, "enabled": True}) if ok \
        else (jsonify({"error": f"{skill_id} not found"}), 404)

@app.route("/api/skills/<skill_id>/disable", methods=["POST"])
def api_skills_disable(skill_id):
    reg = _get_skill_registry()
    if reg is None:
        return jsonify({"error": "Skills module not loaded"}), 503
    ok = reg.disable(skill_id)
    return jsonify({"ok": ok, "skill_id": skill_id, "enabled": False}) if ok \
        else (jsonify({"error": f"{skill_id} not found"}), 404)

@app.route("/api/skills/<skill_id>/run", methods=["POST"])
def api_skills_run(skill_id):
    reg = _get_skill_registry()
    if reg is None:
        return jsonify({"error": "Skills module not loaded"}), 503
    try:
        from skills.engine import SkillEngine
        engine = SkillEngine.instance()
        with _lock:
            snap = dict(_state)
        result = engine.run_one(skill_id, snap)
        if result is None:
            return jsonify({"error": f"{skill_id} not found or failed"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/skills/run_all", methods=["POST"])
def api_skills_run_all():
    reg = _get_skill_registry()
    if reg is None:
        return jsonify({"error": "Skills module not loaded"}), 503
    try:
        from skills.engine import SkillEngine
        engine = SkillEngine.instance()
        with _lock:
            snap = dict(_state)
        merged = engine.run_all(snap)
        with _lock:
            for line in merged.get("advice_lines", []):
                _state["logs"].append({"time": datetime.now().strftime("%H:%M:%S"), "level": "INFO", "msg": line})
        return jsonify(merged)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stream")
def stream():
    def generate():
        while True:
            time.sleep(3)
            with _lock:
                payload = {
                    "ts": datetime.now().strftime("%H:%M:%S"),
                    "total_assets": _state["portfolio"]["total_assets"],
                    "daily_pnl": round(_state["portfolio"]["daily_pnl"], 2),
                    "total_pnl": round(_state["portfolio"]["total_pnl"], 2),
                    "risk_level": _state["risk_level"],
                    "kill_switch_state": _state["kill_switch_state"],
                    "market_sentiment": _state["market_sentiment"],
                    "iteration_count": _state["iteration_count"],
                    "agent_status": {k: v["status"] for k, v in _state["agent_status"].items()},
                    "indices": {k: {"price": v["price"], "change_pct": v["change_pct"]}
                                for k, v in _state["market_overview"].items()},
                    "positions": {
                        sym: {"current_price": pos["current_price"], "pnl_pct": pos["pnl_pct"], "market_value": pos["market_value"]}
                        for sym, pos in _state["portfolio"]["positions"].items()
                    },
                    "northbound_today": _state["capital_flow"]["northbound"]["today_net"],
                    "main_force_net": _state["capital_flow"]["main_force"]["net_inflow"],
                }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

if __name__ == "__main__":
    print("MoreMoney UI v2: http://127.0.0.1:5688")
    app.run(host="0.0.0.0", port=5688, debug=False, threaded=True)
