import os
import asyncio
from dataclasses import dataclass, field
from typing import List
import astrbot.api.message_components as Comp
from astrbot.api import logger

@dataclass
class RenderResult:
    """封装渲染结果和资源清理逻辑"""
    images: List[Comp.Image] = field(default_factory=list)
    subject_ids: List[str] = field(default_factory=list)
    temp_files: List[str] = field(default_factory=list)

    async def cleanup(self):
        """清理临时文件"""
        if not self.temp_files:
            return
            
        # 稍作等待确保发送完成（如果是在发送后立即调用）
        await asyncio.sleep(1)
        
        for path in self.temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"清理临时文件失败 {path}: {e}")
        self.temp_files.clear()
