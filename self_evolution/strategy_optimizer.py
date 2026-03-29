"""
策略优化器 - 基于历史绩效自动调整策略参数

重构要点：
  1. 样本周期拉长：从「近30条」升级为「覆盖至少1个完整市场风格周期」的数据集
  2. 回测前置关卡：LLM建议的新权重必须先通过 BacktestGate 验证才可写入
  3. 权重边界四维限制：单维度 [10%, 50%]，写入前强制裁剪归一化
  4. 合规边界检查：reasoning 含违规意图则清除且跳过权重更新（原有逻辑保留）
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from llm.qwen_client import QwenClient
from llm.prompts.reflection_prompts import STRATEGY_OPTIMIZATION_PROMPT
from core.memory.long_term import LongTermMemory
from self_evolution.knowledge_updater import KnowledgeUpdater
from self_evolution.backtest_gate import BacktestGate
from compliance.rule_boundary import RuleBoundaryChecker

logger = logging.getLogger("self_evolution.strategy_optimizer")

# ---------------------------------------------------------------------------
# 权重边界（与 core/signal_aggregator.py 保持一致）
# ---------------------------------------------------------------------------
WEIGHT_LOWER_BOUND: float = 0.10
WEIGHT_UPPER_BOUND: float = 0.50
DIMENSIONS = ("technical", "sentiment", "capital_flow", "fundamental")

# 样本覆盖要求
MIN_SAMPLE_TRADES: int    = 60    # 最少交易条数
PREFERRED_SAMPLE_TRADES: int = 200  # 理想样本量（覆盖完整风格周期）


class StrategyOptimizer:
    """
    定期（每周 / 达到亏损阈值时）触发，让 LLM 根据历史交易数据提出参数调整建议。

    流程：
      1. 收集覆盖完整市场风格周期的历史数据
      2. 统计绩效（含市场风格分布）
      3. LLM 分析并给出优化建议
      4. 合规边界检查（RuleBoundaryChecker）
      5. 回测前置关卡（BacktestGate）验证新权重
      6. 验证通过 → 边界裁剪归一化 → 写入配置
    """

    def __init__(self):
        self.llm              = QwenClient(model="qwen-max")
        self.long_term        = LongTermMemory()
        self.knowledge_updater = KnowledgeUpdater()
        self.backtest_gate    = BacktestGate()
        self.rule_boundary    = RuleBoundaryChecker()

    async def optimize(self, price_data: Optional[Dict] = None) -> Dict:
        """
        执行一次策略优化。

        Args:
            price_data: 历史价格数据 Dict[symbol, pd.DataFrame]。
                        若为 None 则跳过回测前置关卡（降级，仅在无行情数据时使用）。
        Returns:
            优化结果字典
        """
        # ── 1. 收集覆盖完整市场周期的历史数据 ──────────────────────────
        recent_trades = self._collect_full_cycle_trades()
        if len(recent_trades) < MIN_SAMPLE_TRADES:
            logger.warning(
                "[StrategyOptimizer] 样本量不足（%d < %d），优化已跳过，"
                "请积累更多交易数据后再触发",
                len(recent_trades), MIN_SAMPLE_TRADES,
            )
            return {
                "skipped": True,
                "reason": (
                    f"样本不足（{len(recent_trades)} < {MIN_SAMPLE_TRADES}），"
                    "需覆盖至少1个完整市场风格周期（牛/熊/震荡）"
                ),
            }

        current_weights = self.knowledge_updater.load_current_weights()

        # ── 2. 统计绩效（含市场风格分布） ──────────────────────────────
        stats       = self._calc_stats(recent_trades)
        regime_dist = self._calc_regime_distribution(recent_trades)

        # ── 3. LLM 分析并给出优化建议 ─────────────────────────────────
        prompt = STRATEGY_OPTIMIZATION_PROMPT.format(
            performance_stats=json.dumps(stats,            ensure_ascii=False, indent=2),
            current_params=json.dumps(current_weights,     ensure_ascii=False, indent=2),
            market_regimes=json.dumps(regime_dist,         ensure_ascii=False, indent=2),
            trade_summary=json.dumps(
                [
                    {
                        "symbol":      t["symbol"],
                        "action":      t["action"],
                        "outcome":     t["outcome"],
                        "pnl_pct":     t.get("pnl_pct", 0),
                        "market_date": t.get("market_date", ""),
                    }
                    for t in recent_trades
                ],
                ensure_ascii=False, indent=2,
            ),
        )
        response = await self.llm.chat(prompt, response_format="json")

        try:
            suggestion = json.loads(response)
        except Exception:
            return {"error": "LLM 输出解析失败", "raw": response}

        # ── 4. 合规边界检查：校验 reasoning 字段 ──────────────────────
        reasoning_text   = suggestion.get("reasoning", "")
        boundary_result  = self.rule_boundary.check(reasoning_text)
        if not boundary_result.is_compliant:
            logger.warning(
                "[StrategyOptimizer] LLM 优化建议的 reasoning 触及合规红线，已清除: %s",
                "; ".join(boundary_result.violations),
            )
            suggestion["reasoning"]            = "[已清除：含违规意图]"
            suggestion["compliance_rejected"]   = boundary_result.violations

        # ── 5. 权重边界裁剪 ────────────────────────────────────────────
        new_weights = suggestion.get("dimension_weights")
        if new_weights and boundary_result.is_compliant:
            new_weights = self._clamp_weights(new_weights)
            suggestion["dimension_weights"] = new_weights

            # ── 6. 回测前置关卡 ───────────────────────────────────────
            if price_data:
                gate_result = self.backtest_gate.validate(
                    candidate_weights=new_weights,
                    price_data=price_data,
                    baseline_weights=current_weights,
                )
                suggestion["backtest_gate"] = {
                    "passed":            gate_result.passed,
                    "candidate_metrics": gate_result.candidate_metrics,
                    "baseline_metrics":  gate_result.baseline_metrics,
                    "failure_reasons":   gate_result.failure_reasons,
                    "notes":             gate_result.notes,
                }

                if gate_result.passed:
                    self.knowledge_updater.apply_weight_update(new_weights)
                    logger.info(
                        "[StrategyOptimizer] 新权重通过回测关卡，已写入配置: %s",
                        new_weights,
                    )
                else:
                    logger.warning(
                        "[StrategyOptimizer] 新权重未通过回测关卡，已拒绝写入: %s",
                        "; ".join(gate_result.failure_reasons),
                    )
            else:
                # 无行情数据时降级：仅做边界校验后直接写入（记录告警）
                logger.warning(
                    "[StrategyOptimizer] 未提供 price_data，回测前置关卡已跳过（降级模式），"
                    "直接写入边界裁剪后的权重"
                )
                self.knowledge_updater.apply_weight_update(new_weights)
                suggestion["backtest_gate"] = {"passed": None, "notes": "降级：未执行回测"}

        elif new_weights and not boundary_result.is_compliant:
            logger.warning(
                "[StrategyOptimizer] 因 reasoning 含违规意图，本次权重更新已跳过"
            )

        # ── 7. 持久化策略版本 ─────────────────────────────────────────
        self.long_term.save_strategy_version(
            version=self._next_version(),
            description=suggestion.get("reasoning", ""),
            params=suggestion,
            performance=stats,
        )

        logger.info("[StrategyOptimizer] 优化完成: %s", suggestion.get("reasoning", ""))
        return suggestion

    # ------------------------------------------------------------------
    # 样本收集：覆盖完整市场风格周期
    # ------------------------------------------------------------------
    def _collect_full_cycle_trades(self) -> List[Dict]:
        """
        优先拉取 PREFERRED_SAMPLE_TRADES 条历史交易，
        确保样本中涵盖多种市场风格（牛/熊/震荡）。
        若数据库记录不足则返回全量。
        """
        trades = self.long_term.get_recent_trades(last_n=PREFERRED_SAMPLE_TRADES)
        if len(trades) < MIN_SAMPLE_TRADES:
            return trades

        # 检查风格覆盖：按市场风格字段分组
        regimes_covered = set()
        for t in trades:
            regime = t.get("market_regime", "")  # 交易记录中记录的风格标签
            if regime:
                regimes_covered.add(regime)

        if len(regimes_covered) < 2:
            logger.warning(
                "[StrategyOptimizer] 样本风格覆盖不足（仅 %s），"
                "建议等待更多市场周期数据后再优化",
                regimes_covered,
            )
        else:
            logger.info(
                "[StrategyOptimizer] 样本覆盖市场风格: %s，共 %d 条",
                regimes_covered, len(trades),
            )
        return trades

    # ------------------------------------------------------------------
    # 绩效统计（含市场风格分层统计）
    # ------------------------------------------------------------------
    def _calc_stats(self, trades: List[Dict]) -> Dict:
        if not trades:
            return {}
        wins    = [t for t in trades if t.get("outcome") == "win"]
        losses  = [t for t in trades if t.get("outcome") == "loss"]
        pnl_list = [t.get("pnl_pct", 0) for t in trades if t.get("pnl_pct") is not None]

        base = {
            "total_trades": len(trades),
            "win_rate":     round(len(wins) / max(len(trades), 1), 4),
            "avg_win_pct":  round(sum(t.get("pnl_pct", 0) for t in wins)   / max(len(wins), 1),   4),
            "avg_loss_pct": round(sum(t.get("pnl_pct", 0) for t in losses) / max(len(losses), 1), 4),
            "avg_pnl_pct":  round(sum(pnl_list) / max(len(pnl_list), 1), 4),
        }

        # 分市场风格统计
        regime_stats: Dict[str, Dict] = {}
        for t in trades:
            regime = t.get("market_regime", "unknown")
            bucket = regime_stats.setdefault(regime, {"trades": 0, "wins": 0, "pnl": []})
            bucket["trades"] += 1
            if t.get("outcome") == "win":
                bucket["wins"] += 1
            if t.get("pnl_pct") is not None:
                bucket["pnl"].append(t["pnl_pct"])

        for regime, bucket in regime_stats.items():
            n = max(bucket["trades"], 1)
            bucket["win_rate"]    = round(bucket["wins"] / n, 4)
            bucket["avg_pnl_pct"] = round(sum(bucket["pnl"]) / max(len(bucket["pnl"]), 1), 4)
            del bucket["pnl"]

        base["by_regime"] = regime_stats
        return base

    def _calc_regime_distribution(self, trades: List[Dict]) -> Dict[str, int]:
        dist: Dict[str, int] = {}
        for t in trades:
            regime = t.get("market_regime", "unknown")
            dist[regime] = dist.get(regime, 0) + 1
        return dist

    # ------------------------------------------------------------------
    # 权重边界裁剪 + 归一化
    # ------------------------------------------------------------------
    def _clamp_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """
        强制每维度权重在 [WEIGHT_LOWER_BOUND, WEIGHT_UPPER_BOUND]，
        裁剪后重新归一化使总和 = 1.0。
        """
        clipped: Dict[str, float] = {}
        for dim in DIMENSIONS:
            raw = weights.get(dim, 0.25)
            clipped[dim] = max(WEIGHT_LOWER_BOUND, min(WEIGHT_UPPER_BOUND, raw))
        total = sum(clipped.values())
        normalized = {d: round(v / total, 6) for d, v in clipped.items()}
        logger.debug("[StrategyOptimizer] 权重裁剪归一化: %s -> %s", weights, normalized)
        return normalized

    def _weights_valid(self, weights: Dict) -> bool:
        """基础结构校验（字段完整性）"""
        required = set(DIMENSIONS)
        return required.issubset(weights.keys())

    def _next_version(self) -> str:
        return f"v_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
