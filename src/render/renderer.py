import sys
import subprocess
from astrbot.api import logger
import asyncio

class Renderer:
    """
    渲染器基类
    负责初始化 Playwright 环境和安装浏览器内核
    """
    def __init__(self):
        try:
            logger.info("正在检查并安装 Playwright 浏览器内核 (Chromium)...")
            # 安装 chromium 内核
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("正在检查并安装 Playwright 依赖")
            # 安装 chromium 依赖
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install-deps"]
            )
            logger.info("Playwright 浏览器内核检查完成。")
        except subprocess.CalledProcessError as e:
            logger.error(f"安装 Playwright 浏览器内核失败: {e}")
            raise e

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
                logger.warning(f"渲染任务执行失败 (尝试 {i+1}/{retries}): {e}")
                if i < retries - 1:
                    await asyncio.sleep(delay)
        
        logger.error(f"渲染任务在 {retries} 次尝试后最终失败")
        if last_exception:
            raise last_exception