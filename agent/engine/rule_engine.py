"""
Monitor_v2 — Rule Engine
Load rules.yaml → match incoming OEM event → trả về rule matched.
"""

import os
from typing import Optional

import structlog
import yaml

log = structlog.get_logger()


class RuleEngine:
    def __init__(self, rules_path: str):
        self.rules_path = rules_path
        self._rules = self._load()

    def _load(self) -> list:
        with open(self.rules_path) as f:
            config = yaml.safe_load(f)
        rules = config.get("rules", [])
        log.info("rule_engine.loaded", count=len(rules))
        return rules

    def reload(self):
        self._rules = self._load()
        log.info("rule_engine.reloaded")

    def match(self, event: dict) -> Optional[dict]:
        """
        Tìm rule đầu tiên match event.
        Match theo: metric_name (exact) + severity (exact hoặc list).
        Trả về rule dict hoặc None nếu không match.
        """
        for rule in self._rules:
            cond = rule.get("match", {})

            # Match metric_name
            if "metric_name" in cond:
                if event.get("metric_name", "").lower() != cond["metric_name"].lower():
                    continue

            # Match severity (string hoặc list)
            if "severity" in cond:
                allowed = cond["severity"]
                if isinstance(allowed, str):
                    allowed = [allowed]
                if event.get("severity", "").upper() not in [s.upper() for s in allowed]:
                    continue

            # Optional numeric lower bound for percentage/usage rules.
            # Non-numeric metric_value does not match bounded rules.
            if "metric_value_min" in cond:
                try:
                    raw_value = str(event.get("metric_value", "")).strip().rstrip("%")
                    metric_value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                if metric_value < float(cond["metric_value_min"]):
                    continue

            log.info("rule_engine.matched", rule_id=rule["id"], event_metric=event.get("metric_name"))
            return rule

        log.debug("rule_engine.no_match", event_metric=event.get("metric_name"))
        return None
