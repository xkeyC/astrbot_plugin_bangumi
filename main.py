import copy
import datetime
import os
import re
from collections.abc import AsyncGenerator

import aiohttp
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.all import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain, filter

# 导入配置与管理
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.utils.session_waiter import (
    SessionController,
    SessionFilter,
    session_waiter,
)

from .src.bangumi_types import JsonObject
from .src.config import ConfigManager
from .src.db import BangumiRepository

# 导入逻辑服务
from .src.services import (
    BangumiApiError,
    BangumiRateLimitError,
    BangumiService,
    NoSubjectFound,
    SearchService,
    SubscriptionService,
)
from .src.utils import EnvManager, SchedulerManager


@register(
    "astrbot_plugin_bangumi_enhance",
    "xkeyC",
    "AstrBot Bangumi 增强版：支持番剧/漫画图文搜索、每日放送、追番提醒，并提供 LLM 感知番剧信息的工具能力。",
    "v1.2.0",
    "https://github.com/xkeyC/astrbot_plugin_bangumi",
)
class BangumiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        """
        初始化 BangumiPlugin 插件。
        """
        super().__init__(context)
        self.config = config
        self.config_manager = ConfigManager(config)
        self.scheduler_manager = SchedulerManager()

        self.session: aiohttp.ClientSession | None = None
        self.storage: BangumiRepository | None = None
        self.service: BangumiService | None = None
        self.subscription_service: SubscriptionService | None = None
        self.search_service: SearchService | None = None
        self.env_manager: EnvManager | None = None

    async def initialize(self) -> None:
        """
        插件加载时自动运行的初始化方法。
        """
        # 0. 提前获取插件数据目录（必须先于所有依赖 StarTools 的操作）
        plugin_data_dir = StarTools.get_data_dir()

        # 1. 初始化数据库
        try:
            db_path = os.path.join(plugin_data_dir, "data.db")
            self.storage = BangumiRepository(db_path=db_path)
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            logger.error(f"数据库初始化失败: {e}")

        # 2. 初始化网络会话 (Shared Session)
        self.session = aiohttp.ClientSession()

        # 3. 初始化核心 API 服务
        try:
            proxy_url = None
            proxy_host = self.config_manager.get_proxy_http()
            proxy_port = self.config_manager.get_port()
            if proxy_host and proxy_port:
                proxy_url = f"{proxy_host}:{proxy_port}"

            self.service = BangumiService(
                access_token=self.config_manager.get_access_token(),
                user_agent=self.config_manager.get_user_agent(),
                proxy=proxy_url,
                session=self.session,
            )
        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"服务初始化失败: {e}")

        # 4. 初始化业务逻辑服务 (Dependency Injection)
        if self.service:
            # 搜索服务
            self.search_service = SearchService(
                service=self.service,
                config_manager=self.config_manager,
                session=self.session,
            )

            # 订阅服务
            if self.storage:
                self.subscription_service = SubscriptionService(
                    repository=self.storage,
                    service=self.service,
                    config_manager=self.config_manager,
                    session=self.session,
                )

        # 5. 其他初始化流程
        self.env_manager = EnvManager(plugin_data_dir)

        # 检查本地渲染环境
        if not self.env_manager.is_installed():
            logger.info(
                "本地 Playwright 环境未就绪，将优先使用 RPC 渲染（如果已配置）。"
            )

        # 添加定时更新任务
        if self.subscription_service:
            try:
                self.scheduler_manager.add_job(
                    func=self.subscription_service.check_updates,
                    trigger="cron",
                    minute=0,
                )
                logger.info("Bangumi 插件定时更新任务已启动")
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(f"添加定时任务失败: {e}")

        logger.info("Bangumi 插件初始化流程结束")

    # --- 命令处理区 ---

    @staticmethod
    def _resolve_session_key(event: AstrMessageEvent) -> str | None:
        session_key: str | None = getattr(event, "session_id", None)
        if hasattr(event, "message_obj") and hasattr(event.message_obj, "group_id"):
            session_key = event.message_obj.group_id
        return session_key

    @staticmethod
    def _parse_subscribe_selection(raw_text: str) -> int | None:
        match = re.match(r"^/?追番\s+(\d+)\s*$", raw_text.strip())
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @filter.command("bgm")
    async def search(
        self, event: AstrMessageEvent, query: str, top_k: int = 1
    ) -> AsyncGenerator[object, None]:
        """全类别搜索 Bangumi 条目。"""
        if not self.search_service:
            yield event.plain_result("❌ 搜索服务未就绪")
            return
        async for result in self.search_service.handle_subject_search(
            event, query, top_k, subject_type=None
        ):
            yield result

    @filter.command("bgm番剧")
    async def search_anime(
        self, event: AstrMessageEvent, query: str, top_k: int = 1
    ) -> AsyncGenerator[object, None]:
        """仅搜索 TV 动画条目。"""
        if not self.search_service:
            yield event.plain_result("❌ 搜索服务未就绪")
            return
        async for result in self.search_service.handle_subject_search(
            event, query, top_k, subject_type=[2], subject_tags=["TV"]
        ):
            yield result

    @filter.command("bgm剧场版")
    async def search_movie(
        self, event: AstrMessageEvent, query: str, top_k: int = 1
    ) -> AsyncGenerator[object, None]:
        """仅搜索剧场版动画条目。"""
        if not self.search_service:
            yield event.plain_result("❌ 搜索服务未就绪")
            return
        async for result in self.search_service.handle_subject_search(
            event, query, top_k, subject_type=[2], subject_tags=["剧场版"]
        ):
            yield result

    @filter.command("bgm漫画")
    async def search_manga(
        self, event: AstrMessageEvent, query: str, top_k: int = 1
    ) -> AsyncGenerator[object, None]:
        """仅搜索漫画条目。"""
        if not self.search_service:
            yield event.plain_result("❌ 搜索服务未就绪")
            return
        async for result in self.search_service.handle_subject_search(
            event, query, top_k, subject_type=[1], subject_tags=["漫画"]
        ):
            yield result

    @filter.command("today")
    async def calendar(self, event: AstrMessageEvent) -> AsyncGenerator[object, None]:
        """获取今日番剧放送表。"""
        if not self.search_service:
            yield event.plain_result("❌ 搜索服务未就绪")
            return
        async for result in self.search_service.handle_calendar(event):
            yield result

    LLM_TOOL_SERVICE_ERRORS = (
        BangumiApiError,
        BangumiRateLimitError,
        RuntimeError,
        ValueError,
        TypeError,
    )

    @filter.llm_tool(name="search_bangumi_subject")
    async def search_bangumi_subject(
        self, event: AstrMessageEvent, keyword: str, limit: int = 3
    ) -> str:
        """搜索 Bangumi 番剧/动画/漫画条目，获取可供 LLM 总结的候选条目信息。

        Args:
            keyword(string): 搜索关键词，例如番剧、动画、漫画的中文名、日文名或别名。
            limit(number): 返回候选数量，建议 1 到 5，默认 3。
        """
        del event
        if not self.service:
            return "❌ Bangumi 服务未就绪，无法搜索条目。"

        safe_limit = max(1, min(int(limit), 5))
        try:
            search_res = await self.service.search_subjects(
                keyword=keyword,
                limit=safe_limit,
            )
        except NoSubjectFound:
            return f"🔍 未找到与“{keyword}”相关的 Bangumi 条目。"
        except self.LLM_TOOL_SERVICE_ERRORS as e:
            logger.error(f"LLM 搜索 Bangumi 条目失败: {e}")
            return f"❌ 搜索失败: {e}"

        subjects = search_res.get("data", [])[:safe_limit]
        if not subjects:
            return f"🔍 未找到与“{keyword}”相关的 Bangumi 条目。"

        lines = [f"Bangumi 搜索“{keyword}”的候选结果："]
        for index, item in enumerate(subjects, start=1):
            subject_id = item.get("id", "未知")
            name = item.get("name") or "未知标题"
            name_cn = item.get("name_cn") or ""
            subject_type = item.get("type", "未知")
            title = f"{name_cn} / {name}" if name_cn and name_cn != name else name
            lines.append(
                f"{index}. {title} | ID: {subject_id} | 类型: {subject_type} | 链接: https://bgm.tv/subject/{subject_id}"
            )
        return "\n".join(lines)

    @filter.llm_tool(name="get_bangumi_subject")
    async def get_bangumi_subject(
        self, event: AstrMessageEvent, subject_id: str
    ) -> str:
        """获取 Bangumi 条目的详细信息，适合回答番剧简介、评分、排名、标签和集数进度。

        Args:
            subject_id(string): Bangumi 条目 ID，可先用 search_bangumi_subject 搜索获得。
        """
        del event
        if not self.service:
            return "❌ Bangumi 服务未就绪，无法获取条目详情。"

        try:
            subject = await self.service.get_subject_details(subject_id)
        except NoSubjectFound:
            return f"🔍 未找到 ID 为 {subject_id} 的 Bangumi 条目。"
        except self.LLM_TOOL_SERVICE_ERRORS as e:
            logger.error(f"LLM 获取 Bangumi 条目失败: {e}")
            return f"❌ 获取条目失败: {e}"

        if not subject:
            return f"🔍 未找到 ID 为 {subject_id} 的 Bangumi 条目。"

        try:
            episodes_data = await self.service.get_subject_episodes(int(subject_id))
            latest_episode = await self.service.get_latest_episode(int(subject_id))
        except NoSubjectFound:
            episodes_data = {"data": []}
            latest_episode = None
        except self.LLM_TOOL_SERVICE_ERRORS as e:
            logger.warning(
                f"LLM 获取 Bangumi 剧集信息失败 (subject_id={subject_id}): {e}"
            )
            episodes_data = {"data": []}
            latest_episode = None

        title = self._format_subject_title(subject)
        rating = subject.get("rating", {})
        rating_score = self._extract_mapping_value(rating, "score")
        rating_rank = self._extract_mapping_value(rating, "rank")
        rating_total = self._extract_mapping_value(rating, "total")
        tags = self._format_subject_tags(subject)
        infobox = self._format_subject_infobox(subject)
        episodes = episodes_data.get("data", [])

        lines = [
            f"Bangumi 条目：{title}",
            f"ID: {subject.get('id', subject_id)}",
            f"类型: {subject.get('type', '未知')}",
            f"首播/发售日期: {subject.get('date') or subject.get('air_date') or '未知'}",
            f"总集数: {subject.get('eps') or subject.get('total_episodes') or len(episodes) or '未知'}",
            f"评分: {rating_score or '暂无'} | 排名: {rating_rank or '暂无'} | 评分人数: {rating_total or '暂无'}",
            f"标签: {tags or '暂无'}",
            f"链接: https://bgm.tv/subject/{subject.get('id', subject_id)}",
        ]
        if infobox:
            lines.append(f"制作信息: {infobox}")
        summary = str(subject.get("summary") or "").strip()
        if summary:
            lines.append(f"简介: {summary}")
        if latest_episode:
            latest_title = (
                latest_episode.name_cn
                or latest_episode.name
                or f"第 {latest_episode.ep} 集"
            )
            lines.append(
                f"最新已播普通剧集: 第 {latest_episode.ep} 集《{latest_title}》"
                f"，播出日期: {latest_episode.airdate or '未知'}，评论数: {latest_episode.comment}"
            )
        return "\n".join(lines)

    @filter.llm_tool(name="get_bangumi_calendar")
    async def get_bangumi_calendar(
        self, event: AstrMessageEvent, max_items: int = 20
    ) -> str:
        """获取 Bangumi 每日放送时刻表，适合回答今天或一周有哪些番剧更新。

        Args:
            max_items(number): 每天最多返回的条目数量，建议 5 到 20，默认 20。
        """
        del event
        if not self.service:
            return "❌ Bangumi 服务未就绪，无法获取放送表。"

        try:
            calendar_res = await self.service.get_calendar()
        except self.LLM_TOOL_SERVICE_ERRORS as e:
            logger.error(f"LLM 获取 Bangumi 放送表失败: {e}")
            return f"❌ 获取放送表失败: {e}"

        if not calendar_res:
            return "❌ 未获取到 Bangumi 放送数据。"

        safe_max_items = max(1, min(int(max_items), 20))
        today_id = datetime.datetime.now().isoweekday()
        lines = ["Bangumi 每日放送时刻表："]
        for day in self._order_calendar_days_from_today(calendar_res, today_id):
            weekday = day.get("weekday", {})
            day_name = (
                weekday.get("cn") or weekday.get("ja") or weekday.get("en") or "未知"
            )
            is_today = weekday.get("id") == today_id
            today_mark = "（今天）" if is_today else ""
            items = day.get("items", [])
            item_titles = [
                self._format_subject_title(item) for item in items[:safe_max_items]
            ]
            more = f" 等共 {len(items)} 部" if len(items) > safe_max_items else ""
            lines.append(
                f"{day_name}{today_mark}: {', '.join(item_titles) if item_titles else '暂无'}{more}"
            )
        return "\n".join(lines)

    @staticmethod
    def _order_calendar_days_from_today(
        calendar_res: list[JsonObject], today_id: int
    ) -> list[JsonObject]:
        for index, day in enumerate(calendar_res):
            weekday = day.get("weekday", {})
            if isinstance(weekday, dict) and weekday.get("id") == today_id:
                return calendar_res[index:] + calendar_res[:index]
        return calendar_res

    @staticmethod
    def _format_subject_title(subject: JsonObject) -> str:
        name = str(subject.get("name") or "未知标题")
        name_cn = str(subject.get("name_cn") or "").strip()
        if name_cn and name_cn != name:
            return f"{name_cn} / {name}"
        return name

    @staticmethod
    def _extract_mapping_value(value: object, key: str) -> object:
        if isinstance(value, dict):
            return value.get(key)
        return None

    @staticmethod
    def _format_subject_tags(subject: JsonObject) -> str:
        raw_tags = subject.get("tags")
        if not isinstance(raw_tags, list):
            return ""
        names: list[str] = []
        for tag in raw_tags[:10]:
            if isinstance(tag, dict):
                name = tag.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
        return "、".join(names)

    @staticmethod
    def _format_subject_infobox(subject: JsonObject) -> str:
        raw_infobox = subject.get("infobox")
        if not isinstance(raw_infobox, list):
            return ""
        entries: list[str] = []
        for item in raw_infobox[:12]:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            value = item.get("value")
            if not isinstance(key, str) or not key:
                continue
            if isinstance(value, list):
                value_text = "、".join(
                    str(entry.get("v") or entry.get("k") or entry)
                    if isinstance(entry, dict)
                    else str(entry)
                    for entry in value[:5]
                )
            else:
                value_text = str(value or "")
            if value_text:
                entries.append(f"{key}: {value_text}")
        return "；".join(entries)

    @filter.command("追番")
    async def subscribe(
        self, event: AstrMessageEvent, query: str
    ) -> AsyncGenerator[object, None]:
        """订阅番剧，更新时自动通知。"""
        if not self.subscription_service:
            yield event.plain_result("❌ 订阅服务未就绪")
            return

        group_id = self._resolve_session_key(event)
        if not group_id:
            yield event.plain_result("❌ 无法获取群组ID")
            return

        (
            error_msg,
            candidates,
        ) = await self.subscription_service.get_subscribe_candidates(
            keyword=query,
            limit=self.config_manager.get_max_fuzzy_results(),
        )
        if error_msg:
            yield event.plain_result(error_msg)
            return
        if not candidates:
            yield event.plain_result("🔍 未找到相关番剧")
            return

        if len(candidates) == 1:
            result = await self.subscription_service.subscribe_by_subject_id(
                group_id=group_id,
                subject_id=candidates[0]["subject_id"],
            )
            yield event.plain_result(result)
            return

        candidate_lines = ["⚠️ 匹配到多个候选，请使用 `/追番 序号` 确认："]
        for index, candidate in enumerate(candidates, start=1):
            candidate_lines.append(
                f"{index}. {candidate['name']} (ID: {candidate['subject_id']})"
            )
        candidate_lines.append("5分钟内有效；若发送其他命令将自动取消本次确认。")
        yield event.plain_result("\n".join(candidate_lines))

        cancel_commands = {
            "bgm",
            "bgm番剧",
            "bgm剧场版",
            "bgm漫画",
            "today",
            "弃坑",
        }
        session_key = group_id

        class GroupSessionFilter(SessionFilter):
            def filter(self, wait_event: AstrMessageEvent) -> str:
                wait_session_key = BangumiPlugin._resolve_session_key(wait_event)
                return wait_session_key or wait_event.unified_msg_origin

        @session_waiter(timeout=300)
        async def subscribe_confirm_waiter(
            controller: SessionController,
            wait_event: AstrMessageEvent,
        ) -> None:
            incoming_text = wait_event.get_message_str().strip()

            first_token = incoming_text.split(maxsplit=1)[0] if incoming_text else ""
            normalized_token = (
                first_token[1:] if first_token.startswith("/") else first_token
            )
            if normalized_token in cancel_commands:
                new_event = copy.copy(wait_event)
                self.context.get_event_queue().put_nowait(new_event)
                wait_event.stop_event()
                controller.stop()
                return

            selected_index = self._parse_subscribe_selection(incoming_text)
            if selected_index is None:
                if normalized_token == "追番":
                    new_event = copy.copy(wait_event)
                    self.context.get_event_queue().put_nowait(new_event)
                    wait_event.stop_event()
                    controller.stop()
                    return
                controller.keep(timeout=0)
                return
            if selected_index < 1 or selected_index > len(candidates):
                await wait_event.send(
                    MessageChain(
                        [Comp.Plain(f"❌ 序号超出范围，请输入 1-{len(candidates)}。")]
                    )
                )
                controller.keep(timeout=0)
                return

            selected = candidates[selected_index - 1]
            result = await self.subscription_service.subscribe_by_subject_id(
                group_id=session_key,
                subject_id=selected["subject_id"],
            )
            await wait_event.send(MessageChain([Comp.Plain(result)]))
            wait_event.stop_event()
            controller.stop()

        try:
            await subscribe_confirm_waiter(
                event,
                session_filter=GroupSessionFilter(),
            )
        except TimeoutError:
            yield event.plain_result("⏰ 候选确认已过期，请重新使用 `/追番 关键词`。")

    @filter.command("弃坑")
    async def unsubscribe(
        self, event: AstrMessageEvent, query: str
    ) -> AsyncGenerator[object, None]:
        """取消订阅番剧。"""
        if not self.subscription_service:
            yield event.plain_result("❌ 订阅服务未就绪")
            return

        group_id: str | None = getattr(event, "session_id", None)
        if hasattr(event, "message_obj") and hasattr(event.message_obj, "group_id"):
            group_id = event.message_obj.group_id

        if not group_id:
            yield event.plain_result("❌ 无法获取群组ID")
            return

        result = await self.subscription_service.unsubscribe(group_id, query)
        yield event.plain_result(result)

    async def terminate(self) -> None:
        logger.info("正在清理 Bangumi 插件资源...")
        if self.scheduler_manager.scheduler.running:
            self.scheduler_manager.scheduler.shutdown(wait=False)

        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("已关闭共享网络会话")

        await super().terminate()
