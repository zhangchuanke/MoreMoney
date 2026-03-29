"""
LLM 规则生成边界检查模块

自我迭代模块（ReflectionAgent / StrategyOptimizer）在将 LLM 输出的
交易规则写入记忆之前，必须通过此模块的过滤，以防止 LLM 生成触及
市场操纵、异常交易、虚假申报等违规意图的交易规则被持久化并影响
后续决策。

设计原则：
  - 关键词黑名单（快速过滤）
  - 语义模式正则（结构化检测）
  - 拒绝后记录审计日志，不静默丢弃
  - 不走 LLM 二次判断，避免绕过风险
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple

logger = logging.getLogger("compliance.rule_boundary")


# ---------------------------------------------------------------------------
# 违规意图分类定义
# (category_name, keyword_list, regex_pattern_list)
# ---------------------------------------------------------------------------
_VIOLATION_CATEGORIES: List[Tuple[str, List[str], List[str]]] = [
    (
        "市场操纵",
        [
            "拉抬", "打压", "操纵", "控盘", "坐庄", "洗盘",
            "对倒", "做多做空", "联合持仓", "抱团", "逼空", "轧空",
            "拉高出货", "砸盘", "养套", "掌控价格",
        ],
        [
            r"(人为|故意|刻意).{0,10}(推高|压低|拉高|砸低)",
            r"(联合|协同|配合).{0,10}(买入|卖出|持仓)",
            r"(控制|操控).{0,10}(股价|价格|涨跌)",
        ],
    ),
    (
        "虚假申报",
        [
            "幌骗", "虚假申报", "挂单欺骗", "撤单诱导",
            "快速挂撤", "刷单", "假挂单",
        ],
        [
            r"(挂单|报单).{0,10}(诱导|欺骗|引诱).{0,10}(撤单|取消)",
            r"(快速|频繁|反复).{0,10}(报单|撤单).{0,10}(制造|营造|形成).{0,10}(假象|错觉|误导)",
            r"(大量|批量).{0,10}(挂单|报单).{0,10}(不成交|不打算成交)",
        ],
    ),
    (
        "高频异常交易",
        [
            "高频刷单", "超高频", "毫秒级报撤", "秒级报撤",
            "频繁报撤", "大量报撤",
        ],
        [
            r"(每秒|每分钟).{0,5}(报单|撤单).{0,5}(\d+).{0,5}(次|笔)",
            r"(\d+).{0,5}(次|笔).{0,5}(报撤|报单撤单).{0,10}(秒|分钟)",
        ],
    ),
    (
        "内幕交易",
        [
            "内幕", "内线", "知情人", "消息灵通", "提前知道",
            "未公开信息", "内部消息", "窗口指导前",
        ],
        [
            r"(利用|基于).{0,10}(内幕|未公开|非公开).{0,10}(信息|消息).{0,10}(买入|卖出|交易)",
            r"(公告|消息).{0,5}(发布|披露).{0,5}(前|之前).{0,10}(建仓|买入|布局)",
        ],
    ),
    (
        "价格操纵意图",
        [
            "影响收盘价", "影响开盘价", "锁定涨停", "封涨停",
            "堆砌买盘", "制造涨停", "人为封板",
        ],
        [
            r"(影响|推动|制造).{0,10}(涨停|跌停|涨停板|跌停板)",
            r"(人为|故意).{0,10}(封板|封涨停|封跌停)",
            r"(尾盘|收盘前).{0,10}(拉抬|打压|影响).{0,10}(股价|价格|收盘价)",
        ],
    ),
]

# 预编译正则，提升性能
_COMPILED_PATTERNS: List[Tuple[str, List[re.Pattern]]] = [
    (
        cat,
        [re.compile(p, re.UNICODE) for p in patterns],
    )
    for cat, _, patterns in _VIOLATION_CATEGORIES
]


# ---------------------------------------------------------------------------
# 结果数据类
# ---------------------------------------------------------------------------
@dataclass
class RuleBoundaryResult:
    rule: str
    is_compliant: bool
    violations: List[str] = field(default_factory=list)   # 违规描述列表
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __str__(self) -> str:
        if self.is_compliant:
            return f"[PASS] {self.rule[:60]}"
        return f"[REJECT] {self.rule[:60]} | 原因: {'; '.join(self.violations)}"


# ---------------------------------------------------------------------------
# 规则边界检查器
# ---------------------------------------------------------------------------
class RuleBoundaryChecker:
    """
    对 LLM 输出的交易规则文本进行合规边界检查。

    用法::

        checker = RuleBoundaryChecker()
        result = checker.check(rule_text)
        if not result.is_compliant:
            # 拒绝写入，记录审计日志
            ...
    """

    def check(self, rule: str) -> RuleBoundaryResult:
        """
        检查单条规则文本。
        返回 RuleBoundaryResult，is_compliant=False 时禁止写入。
        """
        if not rule or not rule.strip():
            return RuleBoundaryResult(rule=rule, is_compliant=True)

        violations: List[str] = []
        rule_lower = rule.strip()

        # 1. 关键词黑名单扫描
        for cat_name, keywords, _ in _VIOLATION_CATEGORIES:
            for kw in keywords:
                if kw in rule_lower:
                    violations.append(f"{cat_name}（关键词: {kw}）")
                    break  # 同一分类命中一次即够

        # 2. 语义正则模式扫描
        for cat_name, patterns in _COMPILED_PATTERNS:
            for pat in patterns:
                if pat.search(rule_lower):
                    # 避免与关键词检查重复记录同一分类
                    desc = f"{cat_name}（语义模式）"
                    if desc not in violations:
                        violations.append(desc)
                    break

        result = RuleBoundaryResult(
            rule=rule,
            is_compliant=len(violations) == 0,
            violations=violations,
        )

        # 3. 审计日志
        if not result.is_compliant:
            logger.warning(
                "[RuleBoundaryChecker] 规则被拒绝写入 | 原因: %s | 规则内容: %s",
                "; ".join(violations),
                rule[:200],
            )
        else:
            logger.debug(
                "[RuleBoundaryChecker] 规则通过合规检查: %s", rule[:80]
            )

        return result

    def filter_rules(self, rules: List[str]) -> Tuple[List[str], List[RuleBoundaryResult]]:
        """
        批量过滤规则列表。

        Returns:
            compliant_rules: 通过检查的规则列表
            rejected_results: 被拒绝的 RuleBoundaryResult 列表（供审计）
        """
        compliant: List[str] = []
        rejected: List[RuleBoundaryResult] = []

        for rule in rules:
            result = self.check(rule)
            if result.is_compliant:
                compliant.append(rule)
            else:
                rejected.append(result)

        if rejected:
            logger.warning(
                "[RuleBoundaryChecker] 批量过滤：%d 条规则被拒绝，%d 条通过",
                len(rejected),
                len(compliant),
            )

        return compliant, rejected
