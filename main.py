import os
import asyncio
from typing import Optional

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

    # --- 辅助方法：统一回复构建 ---
    async def _build_reply(
        self, img_url: Optional[str], info_text: str, event: AstrMessageEvent
    ):
        
        # TODO:使用chain_plain替代
        
        """构建并发送带有图片和文本的回复"""
        message_content = []
        temp_file_path = None

        try:
            if img_url:
                try:
                    img_path = await get_img_changeFormat(img_url, TEMP_DIR)
                    temp_file_path = img_path
                    if self.use_filesystem:
                        message_content.append(AstrImage.fromFileSystem(img_path))
                    else:
                        with open(img_path, "rb") as f:
                            message_content.append(AstrImage.fromBytes(f.read()))
                except Exception as e:
                    logger.warning(f"图片处理失败: {e}")

            message_content.append(Plain(info_text))
            return event.chain_result(message_content)

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                # 异步清理临时文件
                asyncio.create_task(self._cleanup_temp(temp_file_path))

    async def _cleanup_temp(self, path: str):
        await asyncio.sleep(2)
        try:
            os.remove(path)
        except:
            pass

    # --- 命令处理区 ---

    @filter.command("bgm搜索")
    async def accurate_search(self, event: AstrMessageEvent):
        if not self.service:
            return event.plain_result("❌ 配置未完成")

        query = (
            event.message_str.split(maxsplit=1)[1].strip()
            if len(event.message_str.split()) > 1
            else ""
        )
        if not query:
            return event.plain_result("❌ 用法: /bgm搜索 <关键词|ID>")

        try:
            event.plain_result(f"🔍 正在搜索: {query} ...")

            # 逻辑处理
            if query.isdigit():
                subject = await self.service.get_subject_details(int(query))
            else:
                search_data = await self.service.search_subjects(query, limit=1)
                if not search_data.get("data"):
                    raise NoSubjectFound()
                subject = await self.service.get_subject_details(
                    search_data["data"][0]["id"]
                )

            # 格式化与回复
            #TODO:构造图片并回复
            return

        except NoSubjectFound:
            return event.plain_result(f"❌ 未找到: {query}")
        except BangumiRateLimitError:
            return event.plain_result("⚠️ 请求过快")
        except Exception as e:
            logger.exception("搜索异常")
            return event.plain_result(f"❌ 错误: {str(e)}")

    @filter.command("bgm角色")
    async def get_character(self, event: AstrMessageEvent):
        if not self.service:
            return event.plain_result("❌ 配置未完成")
        query = (
            event.message_str.split(maxsplit=1)[1].strip()
            if len(event.message_str.split()) > 1
            else ""
        )

        try:
            # 类似上面的逻辑，调用 self.bgm_api.get_character_details 等
            pass
        except Exception as e:
            pass

    # ... 其他命令同理，逻辑与原本相同，只是调用入口变为了 self.bgm_api ...
