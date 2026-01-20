from astrbot.api import logger
import asyncio

from playwright.async_api import async_playwright
from playwright.async_api import ViewportSize


class Renderer:
    """
    渲染器基类
    """

    async def retry(self, func, retries: int = 3, delay: float = 1.0, *args, **kwargs):
        """
        通用重试方法
        :param func: 需要重试的异步函数
        :param retries: 重试次数
        :param delay: 重试间隔(秒)
        """
        last_exception = None
        for i in range(retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(f"渲染任务执行失败 (尝试 {i + 1}/{retries}): {e}")
                if i < retries - 1:
                    await asyncio.sleep(delay)

        logger.error(f"渲染任务在 {retries} 次尝试后最终失败")
        if last_exception:
            raise last_exception

    async def create_page(
        self,
        headless: bool = True,
        width: int = 1024,
        height: int = 768,
        scale_factor: int = 3,
    ):
        try:
            # 启动 Playwright
            playwright = await async_playwright().start()

            # 浏览器启动参数，适配 Docker 环境
            chrome_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--disable-extensions",
                "--disable-default-apps",
            ]

            browser = await playwright.chromium.launch(
                headless=headless,
                args=chrome_args,
            )

            # 创建上下文
            context = await browser.new_context(
                viewport=ViewportSize(width=width, height=height),
                device_scale_factor=scale_factor,
                is_mobile=False,
                has_touch=False,
            )
            page = await context.new_page()
            __original_close = page.close

            async def close_all(*args, **kwargs):
                page.close = __original_close
                try:
                    await browser.close()
                    await playwright.stop()
                except Exception as e:
                    logger.error(f"唔…关闭页面的时候出错了{e}")

            page.close = close_all
            return page
        except Exception as e:
            logger.error(f"初始化浏览器失败:{e}")
            return None
