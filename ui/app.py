"""
MoreMoney Web UI - Flask 后端
提供 REST API + Server-Sent Events 实时推送
"""
import json
import random
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, Response, request

app = Flask(__name__)

# ──────────────────────────────────────────────────────────
# 模拟状态数据（可后续替换为真实 AgentState 注入）
# ──────────────────────────────────────────────────────────
_state = {
    "session_id": "session_20260328_090000",
    "trading_phase": "morning",
    "risk_level": "medium",
    "market_sentiment": "greed",
    "iteration_count": 14,
    "max_iterations": 20,
    "circuit_breaker_triggered": False,
    "daily_loss_limit_reached": False,
    "portfolio": {
        "total_assets": 1_032_580.00,
        "cash": 412_800.00,
        "daily_pnl": 8_420.50,
        "total_pnl": 32_580.00,
        "max_drawdown": 0.042,
        "win_rate": 0.673,
        "sharpe_ratio": 1.87,
        "positions": {
            "600519": {"name": "贵州茅台", "qty": 20, "cost": 1680.0, "current_price": 1724.5, "market_value": 34490, "pnl_pct": 0.0265, "sector": "食品饮料"},
            "000858": {"name": "五 粮 液", "qty": 100, "cost": 148.0, "current_price": 155.3, "market_value": 15530, "pnl_pct": 0.0493, "sector": "食品饮料"},
            "300750": {"name": "宁德时代", "qty": 50, "cost": 220.0, "current_price": 208.4, "market_value": 10420, "pnl_pct": -0.0527, "sector": "新能源"},
            "601318": {"name": "中国平安", "qty": 200, "cost": 44.5, "current_price": 47.8, "market_value": 9560, "pnl_pct": 0.0742, "sector": "金融"},
            "000001": {"name": "平安银行", "qty": 500, "cost": 10.2, "current_price": 9.87, "market_value": 4935, "pnl_pct": -0.0324, "sector": "金融"},
        },
    },
    "market_overview": {
        "sh_index": {"code": "000001", "name": "上证指数", "price": 3287.45, "change_pct": 0.82},
        "sz_index": {"code": "399001", "name": "深证成指", "price": 10523.76, "change_pct": 1.14},
        "cyb_index": {"code": "399006", "name": "创业板指", "price": 2156.33, "change_pct": 1.47},
        "kcb_index": {"code": "000688", "name": "科创50",  "price": 1043.22, "change_pct": 0.63},
    },
    "sector_rotation": {
        "食品饮料": 2.34, "新能源": -0.87, "金融": 1.12, "医药": 0.45,
        "科技": 1.89, "消费": 0.73, "地产": -1.23, "军工": 3.12,
        "有色金属": 2.56, "煤炭": -0.44,
    },
    "signals": [
        {"symbol": "600519", "dimension": "technical",    "direction": "bullish", "strength": 0.82, "confidence": 0.79, "reasoning": "MACD金叉，KDJ超卖反弹，布林带下轨支撑有效"},
        {"symbol": "600519", "dimension": "capital_flow",  "direction": "bullish", "strength": 0.75, "confidence": 0.81, "reasoning": "北向资金净流入1.2亿，主力超大单净流入"},
        {"symbol": "000858", "dimension": "fundamental",  "direction": "bullish", "strength": 0.68, "confidence": 0.72, "reasoning": "PE 25x低于历史均值，ROE持续提升"},
        {"symbol": "300750", "dimension": "sentiment",    "direction": "bearish", "strength": 0.61, "confidence": 0.65, "reasoning": "市场情绪偏空，产能过剩担忧情绪升温"},
        {"symbol": "601318", "dimension": "technical",    "direction": "bullish", "strength": 0.71, "confidence": 0.74, "reasoning": "均线多头排列，RSI回调至合理区间"},
        {"symbol": "000001", "dimension": "capital_flow",  "direction": "bearish", "strength": 0.55, "confidence": 0.60, "reasoning": "主力资金持续流出，融资余额下降"},
    ],
    "decisions": [
        {"action": "buy",    "symbol": "600519", "target_position": 0.08, "current_position": 0.05, "stop_loss": 1612.0, "take_profit": 2068.0, "urgency": "normal",    "reasoning": "四维综合评分0.79，技术面+资金面双重确认", "risk_score": 0.28},
        {"action": "hold",   "symbol": "000858", "target_position": 0.05, "current_position": 0.05, "stop_loss": 137.6,  "take_profit": 177.6,  "urgency": "passive",   "reasoning": "基本面强劲，等待技术面确认信号", "risk_score": 0.22},
        {"action": "reduce", "symbol": "300750", "target_position": 0.02, "current_position": 0.04, "stop_loss": 193.8,  "take_profit": 249.6,  "urgency": "normal",    "reasoning": "情绪面转空，建议减仓至安全仓位", "risk_score": 0.55},
        {"action": "sell",   "symbol": "000001", "target_position": 0.00, "current_position": 0.02, "stop_loss": 9.20,   "take_profit": 11.22,  "urgency": "immediate", "reasoning": "触及止损线，执行风控清仓指令", "risk_score": 0.72},
    ],
    "executed_orders": [
        {"action": "buy",  "symbol": "600519", "quantity": 10, "filled_price": 1718.0, "amount": 17180, "status": "filled", "time": "09:32:14"},
        {"action": "sell", "symbol": "300750", "quantity": 20, "filled_price": 209.1,  "amount": 4182,  "status": "filled", "time": "10:15:37"},
        {"action": "buy",  "symbol": "601318", "quantity": 100,"filled_price": 47.5,   "amount": 4750,  "status": "filled", "time": "10:48:02"},
        {"action": "sell", "symbol": "000001", "quantity": 200,"filled_price": 9.85,   "amount": 1970,  "status": "filled", "time": "11:03:29"},
        {"action": "buy",  "symbol": "000858", "quantity": 50, "filled_price": 154.8,  "amount": 7740,  "status": "partial","time": "11:22:45"},
    ],
    "risk_flags": [
        "300750 持仓亏损超过 5%，接近止损线",
        "000001 日内累计亏损触及风控阈值，已清仓",
    ],
    "memory": {
        "market_regime": "trending",
        "learned_rules": [
            "白酒板块在春节前后有明显的季节性行情规律",
            "北向资金连续3日净流入超10亿时，大盘短期上涨概率达75%",
            "RSI > 80 时入场胜率显著下降，应等待回调",
            "MACD柱状线由负转正配合成交量放大，为强信号",
        ],
        "recent_decisions": [],
        "successful_patterns": ["均线多头 + 北向净流入", "MACD金叉 + 成交量放大"],
        "failed_patterns": ["单纯依赖情绪面信号", "逆势抄底高波动小盘股"],
    },
    "logs": [
        {"time": "09:15:00", "level": "INFO",  "msg": "交易系统启动，模拟盘模式"},
        {"time": "09:30:05", "level": "INFO",  "msg": "市场开盘，开始扫描股票池（300只）"},
        {"time": "09:31:22", "level": "INFO",  "msg": "技术面Agent完成分析，发现12个信号"},
        {"time": "09:31:45", "level": "INFO",  "msg": "资金面Agent：北向今日净流入 +32.4亿"},
        {"time": "09:32:01", "level": "WARN",  "msg": "情绪面Agent：新能源板块负面情绪上升"},
        {"time": "09:32:14", "level": "INFO",  "msg": "执行买入 600519 x10 @ 1718.0"},
        {"time": "10:15:37", "level": "INFO",  "msg": "执行卖出 300750 x20 @ 209.1（减仓）"},
        {"time": "11:03:29", "level": "WARN",  "msg": "风控触发：000001 止损清仓"},
        {"time": "11:22:45", "level": "INFO",  "msg": "反思Agent：本轮操作复盘完成，提取2条规则"},
    ],
    "dimension_weights": {
        "technical": 0.30,
        "sentiment": 0.25,
        "capital_flow": 0.25,
        "fundamental": 0.20,
    },
    "equity_curve": [],
}

# 生成权益曲线历史数据
def _gen_equity_curve():
    base = 1_000_000
    curve = []
    val = base
    for i in range(30):
        d = (datetime.now() - timedelta(days=29 - i)).strftime("%m-%d")
        val = val * (1 + random.gauss(0.003, 0.008))
        curve.append({"date": d, "value": round(val, 2)})
    return curve

_state["equity_curve"] = _gen_equity_curve()

# 后台线程模拟数据更新
_lock = threading.Lock()
def _simulate_tick():
    while True:
        time.sleep(3)
        with _lock:
            p = _state["portfolio"]
            p["daily_pnl"] += random.gauss(0, 200)
            p["total_assets"] = round(p["total_assets"] + random.gauss(0, 150), 2)
            for sym, pos in p["positions"].items():
                delta = random.gauss(0, 0.003)
                pos["current_price"] = round(pos["current_price"] * (1 + delta), 2)
                pos["pnl_pct"] = round((pos["current_price"] - pos["cost"]) / pos["cost"], 4)
                pos["market_value"] = round(pos["current_price"] * pos["qty"], 2)
            for idx_key, idx in _state["market_overview"].items():
                idx["change_pct"] = round(idx["change_pct"] + random.gauss(0, 0.05), 2)
                idx["price"] = round(idx["price"] * (1 + random.gauss(0, 0.0005)), 2)
            _state["iteration_count"] = min(_state["iteration_count"] + (1 if random.random() > 0.8 else 0), 20)

threading.Thread(target=_simulate_tick, daemon=True).start()

# ──────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

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
        return jsonify({
            "overview": _state["market_overview"],
            "sector_rotation": _state["sector_rotation"],
        })

@app.route("/api/risk")
def api_risk():
    with _lock:
        return jsonify({
            "risk_level": _state["risk_level"],
            "risk_flags": _state["risk_flags"],
            "circuit_breaker_triggered": _state["circuit_breaker_triggered"],
            "daily_loss_limit_reached": _state["daily_loss_limit_reached"],
        })

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

@app.route("/stream")
def stream():
    """Server-Sent Events — 每3秒推送一次完整状态摘要"""
    def generate():
        while True:
            time.sleep(3)
            with _lock:
                payload = {
                    "ts": datetime.now().strftime("%H:%M:%S"),
                    "total_assets": _state["portfolio"]["total_assets"],
                    "daily_pnl": round(_state["portfolio"]["daily_pnl"], 2),
                    "risk_level": _state["risk_level"],
                    "market_sentiment": _state["market_sentiment"],
                    "iteration_count": _state["iteration_count"],
                    "indices": {k: {"price": v["price"], "change_pct": v["change_pct"]}
                                for k, v in _state["market_overview"].items()},
                    "positions": {
                        sym: {"current_price": pos["current_price"], "pnl_pct": pos["pnl_pct"], "market_value": pos["market_value"]}
                        for sym, pos in _state["portfolio"]["positions"].items()
                    },
                }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    print("MoreMoney UI 启动: http://127.0.0.1:5688")
    app.run(host="0.0.0.0", port=5688, debug=False, threaded=True)
 