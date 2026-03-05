from astrbot.api import logger
from typing import cast

from .base import BaseBangumiService
from .contracts import CalendarDay


class CalendarService(BaseBangumiService):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

    async def get_calendar(self) -> list[CalendarDay]:
        url = f"{self.base_url}/calendar"
        data = await self._request(url, method="GET")

        if not isinstance(data, list):
            logger.warning(f"get_calendar 返回了非 list 类型: {type(data)}")
            return []

        normalized: list[CalendarDay] = []
        for item in data:
            if isinstance(item, dict):
                normalized.append(cast(CalendarDay, item))
            else:
                logger.warning(f"get_calendar 列表元素类型异常: {type(item)}")

        return normalized
