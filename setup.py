from setuptools import setup, find_packages
from setuptools.command.install import install
import subprocess
import sys
import os


class PostInstall(install):
    """
    运行pip install -r requirements.txt后自动安装browser
    """
    def run(self):
        install.run(self)
        pw = os.path.join(sys.base_exec_prefix,
                          'Scripts' if os.name == 'nt' else 'bin',
                          'playwright')
        subprocess.check_call([pw, 'install', 'chromium'])   # 只装谷歌内核

setup(
    name='astrbot_plugin_bangumi',
    version='1.2.0',
    author='united_pooh',
    description='A tiny cli tool with playwright',
    packages=find_packages(),           # 自动包含 mytool/
    python_requires='>=3.8',
    install_requires=['playwright>=1.44'],   # 运行时依赖
    entry_points={                       # 生成命令行
        'console_scripts': [
            'mytool = mytool.cli:main',
        ]
    },
    cmdclass={'install': PostInstall},    # 关键：挂钩 post-install
)