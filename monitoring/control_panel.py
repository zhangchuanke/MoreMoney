"""
应急管控 Web 面板 (Flask)

提供轻量化管控台，支持：
  - 实时查看系统状态、持仓、风险预警
  - 一键暂停/恢复交易
  - 一键紧急止损（清仓）
  - 一键完全停止（Halt）
  - 查看 Kill Switch 操作历史

启动::

    python -m monitoring.control_panel
    # 或
    from monitoring.control_panel import create_app, run_panel
    run_panel(shared_state, port=8765)

安全提示：生产环境请加 BasicAuth 或限制监听 IP。
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Dict, Optional

try:
    from flask import Flask, jsonify, render_template_string, request
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False

from monitoring.kill_switch import KillSwitch

logger = logging.getLogger("monitoring.control_panel")

# ---------------------------------------------------------------------------
# HTML 管控台（内联模板）
# ---------------------------------------------------------------------------
_HTML_HEAD = """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="10">
<title>MoreMoney 应急管控台</title>
<style>
:root{
  --bg:#0d1117;--surface:#161b22;--border:#30363d;
  --accent:#f0883e;--green:#3fb950;--red:#f85149;
  --yellow:#d29922;--text:#e6edf3;--muted:#8b949e;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Noto Sans SC',sans-serif;min-height:100vh}
header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 32px;
  display:flex;align-items:center;justify-content:space-between}
header h1{font-size:1.2rem;letter-spacing:.05em;color:var(--accent)}
.badge{padding:4px 12px;border-radius:20px;font-size:.8rem;font-weight:700}
.badge-normal{background:#1a3a2a;color:var(--green)}
.badge-paused{background:#3a3010;color:var(--yellow)}
.badge-emergency{background:#3a1010;color:var(--red);animation:blink 1s infinite}
.badge-halted{background:#2a0000;color:var(--red)}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
main{max-width:1100px;margin:32px auto;padding:0 24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:28px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px}
.card-label{font-size:.75rem;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em}
.card-value{font-size:1.6rem;font-weight:700}
.green{color:var(--green)}.red{color:var(--red)}.yellow{color:var(--yellow)}
.controls{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:28px}
btn,.btn{border:none;border-radius:6px;padding:12px 24px;font-size:.95rem;font-weight:700;
  cursor:pointer;transition:.15s}
.btn-pause{background:#3a3010;color:var(--yellow);border:1px solid var(--yellow)}
.btn-resume{background:#1a3a2a;color:var(--green);border:1px solid var(--green)}
.btn-emergency{background:#3a1010;color:var(--red);border:1px solid var(--red)}
.btn-halt{background:#2a0000;color:#ff6060;border:1px solid #ff6060}
section h2{font-size:1rem;margin-bottom:12px;color:var(--muted);border-bottom:1px solid var(--border);padding-bottom:8px}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th{text-align:left;padding:8px 12px;color:var(--muted);border-bottom:1px solid var(--border);font-weight:400}
td{padding:8px 12px;border-bottom:1px solid #21262d}
.flags{margin-top:20px}
.flag-item{background:#2a1a00;border-left:3px solid var(--yellow);padding:8px 14px;
  border-radius:0 4px 4px 0;margin-bottom:6px;font-size:.88rem}
.history-list{max-height:240px;overflow-y:auto}
.history-item{padding:6px 0;border-bottom:1px solid #21262d;font-size:.83rem;color:var(--muted)}
.history-item span{color:var(--text);margin-right:8px}
footer{text-align:center;padding:24px;color:var(--muted);font-size:.8rem}
</style>
</head>
"""

_HTML_BODY = """
<body>
<header>
  <h1>&#9889; MoreMoney 应急管控台</h1>
  <span class="badge badge-{{ state_cls }}">{{ state }}</span>
</header>
<main>
  <div class="grid">
    <div class="card">
      <div class="card-label">账户净值</div>
      <div class="card-value">&#165;{{ total_assets }}</div>
    </div>
    <div class="card">
      <div class="card-label">当日盈亏</div>
      <div class="card-value {{ pnl_cls }}">{{ daily_pnl }}</div>
    </div>
    <div class="card">
      <div class="card-label">最大回撤</div>
      <div class="card-value {{ dd_cls }}">{{ max_drawdown }}</div>
    </div>
    <div class="card">
      <div class="card-label">风险等级</div>
      <div class="card-value {{ risk_cls }}">{{ risk_level }}</div>
    </div>
    <div class="card">
      <div class="card-label">持仓数量</div>
      <div class="card-value">{{ position_count }}</div>
    </div>
    <div class="card">
      <div class="card-label">防御模式</div>
      <div class="card-value {{ defense_cls }}">{{ defense_mode }}</div>
    </div>
  </div>

  <div class="controls">
    <form method="post" action="/api/pause" onsubmit="return confirm('确认暂停交易？')">
      <button class="btn btn-pause">&#9646;&#9646; 暂停交易</button>
    </form>
    <form method="post" action="/api/resume">
      <button class="btn btn-resume">&#9654; 恢复交易</button>
    </form>
    <form method="post" action="/api/emergency" onsubmit="return confirm('确认触发紧急止损（不清仓）？')">
      <button class="btn btn-emergency">&#9888; 紧急止损</button>
    </form>
    <form method="post" action="/api/liquidate" onsubmit="return confirm('确认一键清仓？此操作将市价卖出所有持仓！')">
      <button class="btn btn-emergency">&#128293; 一键清仓</button>
    </form>
    <form method="post" action="/api/halt" onsubmit="return confirm('确认完全停止所有交易？')">
      <button class="btn btn-halt">&#128721; 完全停止</button>
    </form>
  </div>

  {% if positions %}
  <section>
    <h2>持仓列表</h2>
    <table>
      <tr><th>代码</th><th>成本</th><th>现价</th><th>盈亏%</th><th>市值</th><th>止损价</th></tr>
      {% for sym, pos in positions.items() %}
      <tr>
        <td>{{ sym }}</td>
        <td>{{ "%.2f"|format(pos.get('cost',0)) }}</td>
        <td>{{ "%.2f"|format(pos.get('current_price',0)) }}</td>
        <td class="{{ 'green' if pos.get('pnl_pct',0)>0 else 'red' }}">
          {{ "%.2f%%"|format(pos.get('pnl_pct',0)*100) }}</td>
        <td>&#165;{{ "{:,.0f}"|format(pos.get('market_value',0)) }}</td>
        <td>{{ "%.2f"|format(pos.get('stop_loss',0)) }}</td>
      </tr>
      {% endfor %}
    </table>
  </section>
  {% endif %}

  {% if risk_flags %}
  <div class="flags" style="margin-top:24px">
    <section><h2>风险预警</h2></section>
    {% for f in risk_flags %}
    <div class="flag-item">&#9888; {{ f }}</div>
    {% endfor %}
  </div>
  {% endif %}

  <section style="margin-top:24px">
    <h2>操作历史</h2>
    <div class="history-list">
      {% for h in history %}
      <div class="history-item">
        <span>{{ h.timestamp[:19] }}</span>
        <span style="color:var(--accent)">{{ h.state }}</span>
        [{{ h.operator }}] {{ h.reason }}
      </div>
      {% endfor %}
    </div>
  </section>
</main>
<footer>MoreMoney Risk Control Panel &mdash; 每10秒自动刷新</footer>
</body>
</html>
"""

_TEMPLATE = _HTML_HEAD + _HTML_BODY


# ---------------------------------------------------------------------------
# Flask 应用工厂
# ---------------------------------------------------------------------------

def create_app(shared_state: Optional[Dict] = None) -> "Flask":
    """
    创建 Flask 管控台应用。

    Parameters
    ----------
    shared_state : 可变 dict，由主交易图持续写入最新状态。
                   None 时使用内部空状态（仅展示 Kill Switch 信息）。
    """
    if not _FLASK_AVAILABLE:
        raise ImportError("Flask 未安装，请执行: pip install flask")

    app = Flask(__name__)
    ks = KillSwitch.instance()
    _state: Dict = shared_state if shared_state is not None else {}

    def _render():
        portfolio  = _state.get("portfolio", {})
        positions  = portfolio.get("positions", {})
        risk_flags = _state.get("risk_flags", [])
        risk_level = _state.get("risk_level", "N/A")
        daily_pnl  = portfolio.get("daily_pnl", 0)
        total      = portfolio.get("total_assets", 0)
        drawdown   = portfolio.get("max_drawdown", 0)
        defense    = _state.get("defense_mode", False)

        ks_status = ks.status()
        state_str = ks_status["state"]
        state_cls = state_str.lower()

        pnl_cls  = "green" if daily_pnl >= 0 else "red"
        dd_cls   = "green" if drawdown < 0.05 else ("yellow" if drawdown < 0.10 else "red")
        risk_map = {"low": "green", "medium": "yellow", "high": "red", "extreme": "red"}
        risk_cls = risk_map.get(risk_level, "")

        return render_template_string(
            _TEMPLATE,
            state=state_str,
            state_cls=state_cls,
            total_assets=f"{total:,.0f}",
            daily_pnl=f"{daily_pnl:+,.0f}",
            pnl_cls=pnl_cls,
            max_drawdown=f"{drawdown:.2%}",
            dd_cls=dd_cls,
            risk_level=risk_level.upper(),
            risk_cls=risk_cls,
            position_count=len(positions),
            defense_mode="ON" if defense else "OFF",
            defense_cls="red" if defense else "green",
            positions=positions,
            risk_flags=risk_flags,
            history=list(reversed(ks.history()))[:20],
        )

    @app.route("/")
    def index():
        return _render()

    @app.route("/api/status")
    def api_status():
        portfolio = _state.get("portfolio", {})
        return jsonify({
            "kill_switch":  ks.status(),
            "risk_level":   _state.get("risk_level", "N/A"),
            "risk_flags":   _state.get("risk_flags", []),
            "portfolio":    {
                "total_assets": portfolio.get("total_assets", 0),
                "daily_pnl":    portfolio.get("daily_pnl", 0),
                "max_drawdown": portfolio.get("max_drawdown", 0),
                "position_count": len(portfolio.get("positions", {})),
            },
            "timestamp": datetime.now().isoformat(),
        })

    @app.route("/api/pause", methods=["POST"])
    def api_pause():
        reason = request.form.get("reason", "管控台手动暂停")
        ks.pause(operator="web_panel", reason=reason)
        logger.warning("[ControlPanel] 交易已暂停: %s", reason)
        return _render()

    @app.route("/api/resume", methods=["POST"])
    def api_resume():
        reason = request.form.get("reason", "管控台手动恢复")
        ks.resume(operator="web_panel", reason=reason)
        logger.info("[ControlPanel] 交易已恢复: %s", reason)
        return _render()

    @app.route("/api/emergency", methods=["POST"])
    def api_emergency():
        reason = request.form.get("reason", "管控台触发紧急止损")
        ks.emergency_stop(operator="web_panel", reason=reason, liquidate=False)
        logger.critical("[ControlPanel] 紧急止损触发: %s", reason)
        return _render()

    @app.route("/api/liquidate", methods=["POST"])
    def api_liquidate():
        reason = request.form.get("reason", "管控台触发一键清仓")
        ks.emergency_stop(operator="web_panel", reason=reason, liquidate=True)
        logger.critical("[ControlPanel] 一键清仓触发: %s", reason)
        return _render()

    @app.route("/api/halt", methods=["POST"])
    def api_halt():
        reason = request.form.get("reason", "管控台触发完全停止")
        ks.halt(operator="web_panel", reason=reason)
        logger.critical("[ControlPanel] 系统完全停止: %s", reason)
        return _render()

    return app


# ---------------------------------------------------------------------------
# 便捷启动函数
# ---------------------------------------------------------------------------

def run_panel(
    shared_state: Optional[Dict] = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    debug: bool = False,
) -> None:
    """
    在独立线程中启动管控台。

    Parameters
    ----------
    shared_state : 与主交易图共享的可变 dict
    host         : 监听地址（默认仅本机）
    port         : 监听端口
    debug        : Flask 调试模式
    """
    if not _FLASK_AVAILABLE:
        logger.error("Flask 未安装，管控台无法启动。pip install flask")
        return

    app = create_app(shared_state)

    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=debug, use_reloader=False),
        daemon=True,
        name="ControlPanel",
    )
    t.start()
    logger.info(
        "[ControlPanel] 管控台已启动: http://%s:%d", host, port
    )
    print(f"\n[MoreMoney] 应急管控台: http://{host}:{port}\n")


if __name__ == "__main__":
    run_panel(debug=True)
