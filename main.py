import os
import asyncio
from typing import Optional
import tempfile

from astrbot.api.message_components import Plain, Image as AstrImage
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import AstrBotConfig
from astrbot.api import logger

# 导入配置管理器
from .src.config.config_manager import ConfigManager

# 导入我们重构后的统一API类
from .src.core import BangumiService

# 导入异常
from .src.core.exceptions import NoSubjectFound, BangumiRateLimitError

# 导入工具
from .method import get_img_changeFormat, TEMP_DIR


@register(
    "astrbot_plugin_bangumi",
    "Gemini",
    "一个用于查询Bangumi条目信息的插件",
    "1.2.0",
    "https://github.com/bangumi/api",
)
class BangumiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.config_manager = ConfigManager(config)

        # 配置项读取
        self.use_forward_msg = self.config.get("use_forward", "关闭") == "开启"
        self.use_filesystem = self.config.get("if_fromfilesystem", "关闭") == "开启"
        self.max_fuzzy_results = 10  # 假设的默认值

        try:
            # 初始化聚合后的API类
            self.service = BangumiService(
                self.config_manager.get_access_token(),
                self.config_manager.get_user_agent(),
            )
            logger.info("Bangumi插件初始化成功")
        except ValueError as e:
            logger.error(f"插件初始化失败: {e}")
            self.service = None

    # --- 命令处理区 ---

    @filter.command("bgm搜索")
    async def accurate_search(self, event: AstrMessageEvent):
        if not self.service:
            yield event.plain_result("❌ 配置未完成")

        query = (
            event.message_str.split(maxsplit=1)[1].strip()
            if len(event.message_str.split()) > 1
            else ""
        )
        if not query:
            yield event.plain_result("❌ 用法: /bgm搜索 <关键词|ID>")

        yield event.plain_result(f"{query}")