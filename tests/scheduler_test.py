import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.scheduler import SchedulerManager


async def main():
    """
    一个简单的测试函数，验证调度器的循环任务功能。
    """
    print("开始测试循环任务调度器...")
    scheduler_manager = SchedulerManager()

    # 使用列表作为可变对象来在任务函数内部修改计数器
    counter = [0]

    # 定义一个简单的循环任务
    async def looping_task():
        counter[0] += 1
        print(f"[{datetime.now()}] -> 循环任务第 {counter[0]} 次执行！")

    print(f"当前时间: {datetime.now()}")
    print("任务将立即开始，并每秒循环执行一次。")

    # 使用 'interval' trigger 来安排一个循环任务
    job_id = scheduler_manager.add_job(looping_task, 'interval', seconds=1)

    if job_id:
        print(f"循环任务 '{job_id}' 已成功添加。")
    else:
        print("任务添加失败。")
        scheduler_manager.shutdown()
        return

    # 等待3.5秒，以观察任务执行3次
    print("等待3.5秒以观察循环执行...")
    await asyncio.sleep(3.5)

    # 取消任务并关闭调度器
    scheduler_manager.cancel_job(job_id)
    scheduler_manager.shutdown()
    
    print(f"\n测试结束。任务总共执行了 {counter[0]} 次。")


if __name__ == "__main__":
    asyncio.run(main())
