import os
import aiohttp
from collections.abc import AsyncGenerator

from astrbot.api import logger
from astrbot.api.all import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

# 导入配置与管理
from astrbot.api.star import StarTools
from .src.config.config_manager import ConfigManager
from .src.utils.scheduler import SchedulerManager

# 导入逻辑服务
from .src.services import BangumiService
from .src.services.search import SearchService
from .src.services.subscription import SubscriptionService
from .src.db import BangumiRepository
from .src.utils.env_manager import EnvManager


@register(
    "astrbot_plugin_bangumi_enhance",
    "united_pooh",
    "AstrBot Bangumi 增强版：为 AstrBot 打造的一站式 Bangumi 追番助手。支持番剧/漫画图文搜索、每日放送时刻表查看及集数更新自动提醒。",
    "v1.1.0",
    "https://github.com/united-pooh/astrbot_plugin_bangumi",
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

    @filter.command("bgm")
    async def search(
        self, event: AstrMessageEvent, query: str, top_k: int = 1
    ) -> AsyncGenerator[object, None]:
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
        if not self.search_service:
            yield event.plain_result("❌ 搜索服务未就绪")
            return
        async for result in self.search_service.handle_subject_search(
            event, query, top_k, subject_type=[1], subject_tags=["漫画"]
        ):
            yield result

    @filter.command("today")
    async def calendar(self, event: AstrMessageEvent) -> AsyncGenerator[object, None]:
        if not self.search_service:
            yield event.plain_result("❌ 搜索服务未就绪")
            return
        async for result in self.search_service.handle_calendar(event):
            yield result

    @filter.command("追番")
    async def subscribe(
        self, event: AstrMessageEvent, query: str
    ) -> AsyncGenerator[object, None]:
        if not self.subscription_service:
            yield event.plain_result("❌ 订阅服务未就绪")
            return

        group_id: str | None = getattr(event, "session_id", None)
        if hasattr(event, "message_obj") and hasattr(event.message_obj, "group_id"):
            group_id = event.message_obj.group_id

        if not group_id:
            yield event.plain_result("❌ 无法获取群组ID")
            return

        result = await self.subscription_service.subscribe(group_id, query)
        yield event.plain_result(result)

    @filter.command("弃坑")
    async def unsubscribe(
        self, event: AstrMessageEvent, query: str
    ) -> AsyncGenerator[object, None]:
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
