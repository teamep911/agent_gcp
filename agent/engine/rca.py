"""
Monitor_v2 — RCA Engine
Generate RCA summary từ matched rule + event data.
Output là dict → persist vào incidents.rca_result.
"""

import structlog

log = structlog.get_logger()


class RCAEngine:
    def analyze(self, event: dict, rule: dict) -> dict:
        """
        Generate RCA result từ rule template.
        """
        rca_config = rule.get("rca", {})

        result = {
            "rule_id": rule.get("id"),
            "rule_name": rule.get("name"),
            "summary": rca_config.get("summary", "Không có thông tin RCA."),
            "check_commands": rca_config.get("check_commands", []),
            "event_context": {
                "target_name": event.get("target_name"),
                "metric_name": event.get("metric_name"),
                "metric_value": event.get("metric_value"),
                "severity": event.get("severity"),
                "message": event.get("message"),
            },
        }

        log.info(
            "rca.generated",
            rule_id=rule.get("id"),
            target=event.get("target_name"),
        )
        return result

    def format_for_telegram(self, rca_result: dict, incident_id: int) -> str:
        """
        Format RCA result thành text message để gửi Telegram.
        """
        ctx = rca_result.get("event_context", {})
        checks = rca_result.get("check_commands", [])
        checks_str = "\n".join(f"  • /{cmd} {ctx.get('target_name', '')}" for cmd in checks) if checks else "  (không có)"

        return (
            f"🔴 *INCIDENT #{incident_id}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Target: `{ctx.get('target_name')}`\n"
            f"📊 Metric: `{ctx.get('metric_name')}` = `{ctx.get('metric_value', 'N/A')}`\n"
            f"⚠️ Severity: `{ctx.get('severity')}`\n"
            f"💬 Message: {ctx.get('message')}\n\n"
            f"📋 *RCA:* {rca_result.get('summary')}\n\n"
            f"🔍 *Recommended checks:*\n{checks_str}"
        )
