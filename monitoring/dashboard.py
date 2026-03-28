"""
监控看板 - 实时打印组合状态
"""
from datetime import datetime
from typing import Dict


class Dashboard:

    def display(self, state: Dict) -> None:
        portfolio = state.get("portfolio", {})
        print("\n" + "="*60)
        print(f"  MoreMoney 交易系统  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        print(f"  总资产:   ¥{portfolio.get('total_assets', 0):>12,.2f}")
        print(f"  现金:     ¥{portfolio.get('cash', 0):>12,.2f}")
        print(f"  当日盈亏: ¥{portfolio.get('daily_pnl', 0):>12,.2f}")
        print(f"  总盈亏:   ¥{portfolio.get('total_pnl', 0):>12,.2f}")
        print(f"  最大回撤:  {portfolio.get('max_drawdown', 0):>10.2%}")
        print(f"  胜率:      {portfolio.get('win_rate', 0):>10.2%}")
        print(f"  风险等级:  {state.get('risk_level', 'N/A'):>10}")
        print(f"  市场情绪:  {state.get('market_sentiment', 'N/A'):>10}")
        print(f"  迭代次数:  {state.get('iteration_count', 0):>10}")
        # 持仓列表
        positions = portfolio.get("positions", {})
        if positions:
            print("\n  【持仓列表】")
            print(f"  {'代码':<10} {'成本':<10} {'现价':<10} {'盈亏%':<10} {'市值':<12}")
            print("  " + "-"*52)
            for sym, pos in positions.items():
                print(
                    f"  {sym:<10} "
                    f"{pos.get('cost', 0):<10.2f} "
                    f"{pos.get('current_price', 0):<10.2f} "
                    f"{pos.get('pnl_pct', 0):<10.2%} "
                    f"¥{pos.get('market_value', 0):<12,.2f}"
                )
        # 风险预警
        flags = state.get("risk_flags", [])
        if flags:
            print("\n  【风险预警】")
            for f in flags:
                print(f"  ⚠ {f}")
        print("="*60 + "\n")
