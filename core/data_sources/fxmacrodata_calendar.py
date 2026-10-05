from __future__ import annotations

import os
from typing import Dict, List, Optional

import aiohttp

from core.data_sources.market_feeds.connector_base import ConnectorBase


class FXMacroDataCalendarConnector(ConnectorBase):
    """Async connector for FXMacroData economic-release calendars."""

    BASE_URL = "https://api.fxmacrodata.com/v1"
    RATE_LIMIT_ID = "fxmacrodata_calendar"

    def __init__(self, api_key: Optional[str] = None, session: Optional[aiohttp.ClientSession] = None):
        super().__init__(session=session)
        self.api_key = api_key if api_key is not None else os.getenv("FXMD_API_KEY")
        self.register_rate_limit(self.RATE_LIMIT_ID, max_requests=30, time_window_seconds=60)

    async def get_calendar(
        self,
        currency: str = "usd",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        top_tier_only: bool = False,
    ) -> List[Dict]:
        params: Dict[str, str] = {}
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        payload = await self._make_request(
            "GET",
            f"{self.BASE_URL}/calendar/{currency.lower()}",
            params=params,
            headers=headers,
            limit_id=self.RATE_LIMIT_ID,
            # aiohttp would carry the X-API-Key header to a redirect target, so do not follow.
            allow_redirects=False,
        )
        if payload is None:
            return []
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            detail = payload.get("detail") if isinstance(payload, dict) else None
            self.logger.error(f"Unexpected FXMacroData calendar response: {detail or 'missing data'}")
            return []
        rows = [row for row in data if isinstance(row, dict)]
        if top_tier_only:
            rows = [row for row in rows if row.get("top_tier_for_currency") or row.get("market_tier") == 1]
        return rows

    def get_exchange_trading_pair(self, trading_pair: str) -> str:
        return trading_pair
