"""
Monitor_v2 — OEM REST API Client
Wrap OEM 13.5 REST endpoints. Tất cả query đi qua đây, không call thẳng OEM từ handler.
"""

import os
from typing import Optional
from urllib.parse import quote

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from db.models import get_db_pool

log = structlog.get_logger()

OEM_BASE_URL = os.getenv("OEM_BASE_URL", "https://oem-server:7803/em")
OEM_USER = os.getenv("OEM_USERNAME", "sysman")
OEM_PASS = os.getenv("OEM_PASSWORD", "")
SSL_VERIFY = os.getenv("OEM_SSL_VERIFY", "true").lower() != "false"
LICENSE_CACHE_TTL = int(os.getenv("LICENSE_CACHE_TTL", 3600))


class OEMClient:
    """
    OEM REST API client với:
    - Basic auth (sysman)
    - Retry với exponential backoff
    - License gate check với cache
    """

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=OEM_BASE_URL,
            auth=(OEM_USER, OEM_PASS),
            verify=SSL_VERIFY,
            timeout=30.0,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def _resolve_target(self, target_name: str, target_type: str = "oracle_database") -> Optional[dict]:
        """Resolve OEM target by name/type from /websvcs/restful/targets.

        Returns the target object (contains id/name/type/status/links...) or None.
        """
        resp = await self._client.get("/websvcs/restful/targets", params={"limit": 200})
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        for item in items:
            if item.get("name") == target_name and item.get("type") == target_type:
                return item

        # Common user input is the DB/host short name (e.g. "flex") while OEM's
        # database target name is often "flex_flex". Prefer exact oracle_database
        # match above, then fall back to display/contains matches.
        candidates = [item for item in items if item.get("type") == target_type]
        for item in candidates:
            if item.get("displayName") == target_name:
                return item
        matches = [
            item for item in candidates
            if target_name.lower() in str(item.get("name", "")).lower()
            or target_name.lower() in str(item.get("displayName", "")).lower()
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            # Prefer database target named <short>_<short> (e.g. flex_flex), then
            # target ending with _<shortname>. This avoids selecting emdb_flex
            # when the user asks for the primary DB target "flex".
            preferred_name = f"{target_name.lower()}_{target_name.lower()}"
            for item in matches:
                if str(item.get("name", "")).lower() == preferred_name:
                    return item
            for item in matches:
                if str(item.get("name", "")).lower().endswith(f"_{target_name.lower()}"):
                    return item
        return None

    async def _target_properties(self, target_name: str, target_type: str = "oracle_database") -> list[dict]:
        target = await self._resolve_target(target_name, target_type)
        if not target:
            raise LookupError(f"Không tìm thấy target '{target_name}' ({target_type}) trong OEM")
        target_id = target["id"]
        resp = await self._client.get(f"/websvcs/restful/targets/{quote(target_id)}/properties")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    async def _target_status_payload(self, target_name: str, target_type: str = "oracle_database") -> dict:
        target = await self._resolve_target(target_name, target_type)
        if not target:
            raise LookupError(f"Không tìm thấy target '{target_name}' ({target_type}) trong OEM")
        target_id = target["id"]
        resp = await self._client.get(f"/websvcs/restful/targets/{quote(target_id)}")
        resp.raise_for_status()
        return resp.json()

    async def _target_tablespace_summary(self, target_name: str, target_type: str = "oracle_database") -> dict:
        """Fallback lightweight tablespace summary from target properties.

        Some OEM deployments do not expose /emws/db/storage/tablespacelist.
        In that case, return a compact property-based summary so command remains useful.
        """
        props = await self._target_properties(target_name, target_type)
        prop_map = {p.get("name"): p.get("value") for p in props if isinstance(p, dict)}
        keys = [
            "DBName", "Version", "OpenMode", "InstanceName", "HostName",
            "TotalSpaceAllocated", "TotalUsedSpace", "TotalFreeSpace",
        ]
        summary = {k: prop_map.get(k) for k in keys if prop_map.get(k) is not None}
        return {
            "source": "oem_target_properties_fallback",
            "target_name": target_name,
            "target_type": target_type,
            "summary": summary,
        }

    @staticmethod
    def _has_diag_pack_in_properties(properties: list[dict]) -> bool:
        """Best-effort diagnostic pack detection from target properties list."""
        for prop in properties:
            name = str(prop.get("name", "")).lower()
            value = str(prop.get("value", "")).lower()
            if "diagnostic" in name and "pack" in name:
                return value in {"true", "yes", "1", "enabled"}
        return False

    @staticmethod
    def _is_target_up(status_payload: dict) -> bool:
        status = str(status_payload.get("status", "")).upper()
        code = status_payload.get("statusCode")
        return status == "UP" or code == 1

    async def close(self):
        await self._client.aclose()

    # ── License Gate ──────────────────────────────────────────────────────────

    async def has_diagnostic_pack(self, target_name: str) -> bool:
        """
        Kiểm tra target có Diagnostic & Tuning Pack không.
        Cache trong PostgreSQL TTL=1h để tránh overhead.
        CẢNH BÁO: Không bao giờ query AWR/ASH nếu trả về False.
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT has_diag_pack FROM target_license_cache
                WHERE target_name=$1
                  AND checked_at > now() - interval '1 second' * $2
                """,
                target_name, LICENSE_CACHE_TTL,
            )
            if row is not None:
                return row["has_diag_pack"]

            # Cache miss — query OEM
            has_pack = await self._check_license_from_oem(target_name)

            await conn.execute(
                """
                INSERT INTO target_license_cache(target_name, has_diag_pack, checked_at)
                VALUES($1, $2, now())
                ON CONFLICT(target_name) DO UPDATE
                SET has_diag_pack=$2, checked_at=now()
                """,
                target_name, has_pack,
            )
            return has_pack

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def _check_license_from_oem(self, target_name: str) -> bool:
        """Query OEM target properties để check diagnostic_pack."""
        try:
            props = await self._target_properties(target_name, "oracle_database")
            return self._has_diag_pack_in_properties(props)
        except Exception as e:
            log.warning("oem.license_check.failed", target=target_name, error=str(e))
            return False  # Fail safe: không assume có license

    # ── Target Status ──────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_target_status(self, target_name: str) -> dict:
        """Lấy availability status của target.

        Uses OEM's available /websvcs/restful/targets/{id} API on this
        deployment instead of the unavailable legacy /emws path.
        """
        return await self._target_status_payload(target_name, "oracle_database")

    # ── AWR/ASH — chỉ gọi sau khi check license ───────────────────────────────

    async def get_awr_summary(self, target_name: str, hours: int = 1) -> dict:
        """
        Lấy AWR summary dạng JSON/text.
        CẢNH BÁO: Chỉ gọi nếu has_diagnostic_pack() = True.
        """
        if not await self.has_diagnostic_pack(target_name):
            raise PermissionError(
                f"Target '{target_name}' không có Diagnostic Pack license. AWR không khả dụng."
            )

        resp = await self._client.get(
            "/websvcs/restful/emws/db/performance/awrsummary",
            params={
                "target_name": target_name,
                "target_type": "oracle_database",
                "hours": hours,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_ash_top_sql(self, target_name: str, minutes: int = 30) -> dict:
        """
        Lấy ASH top SQL consumers.
        CẢNH BÁO: Chỉ gọi nếu has_diagnostic_pack() = True.
        """
        if not await self.has_diagnostic_pack(target_name):
            raise PermissionError(
                f"Target '{target_name}' không có Diagnostic Pack license. ASH không khả dụng."
            )

        resp = await self._client.get(
            "/websvcs/restful/emws/db/performance/ashtopsql",
            params={
                "target_name": target_name,
                "target_type": "oracle_database",
                "minutes": minutes,
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ── Tablespace ─────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_tablespace_usage(self, target_name: str) -> dict:
        """Lấy tablespace usage — không cần license.

        This OEM deployment does not expose the legacy /emws/db/storage path.
        Return a property-based DB summary fallback instead of failing 404.
        """
        return await self._target_tablespace_summary(target_name, "oracle_database")

    # ── Incidents từ OEM ───────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def get_open_incidents(self, target_name: Optional[str] = None) -> dict:
        """Lấy danh sách open incidents từ OEM."""
        params = {"status": "open", "limit": 20}
        if target_name:
            params["target_name"] = target_name
        resp = await self._client.get(
            "/websvcs/restful/emws/events/incidents",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()


# Singleton instance
_oem_client: Optional[OEMClient] = None


def get_oem_client() -> OEMClient:
    global _oem_client
    if _oem_client is None:
        _oem_client = OEMClient()
    return _oem_client
