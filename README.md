<div align="center">

# Bangumi 搜索插件使用指南
[![repo](https://img.shields.io/badge/repo-v1.3-blue.svg)](https://github.com/united-pooh/astrbot_plugin_bangumi)
[![License](https://img.shields.io/badge/license-Apacha2.0-green.svg)](LICENSE-2.0)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.0.0-orange.svg)](https://github.com/Soulter/AstrBot)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)

**和 AI 一起追番**

</div>

> [!NOTE]  
> 本项目在[astrbot_plugin_bangumi](https://github.com/Amatsutsumi/astrbot_plugin_bangumi) 的基础上进行二次开发

## 📌 核心命令

### 1. 基础搜索 (图文卡片)
| 命令 | 功能 | 参数 | 示例 |
|------|------|------|------|
| `/bgm搜索` | 全类别搜索 | `<关键词\|ID> [top_k]` | `/bgm搜索 进击的巨人 3` |
| `/bgm番剧` | 仅搜索 TV 动画 | `<关键词\|ID> [top_k]` | `/bgm番剧 命运石之门` |
| `/bgm剧场版` | 仅搜索剧场版动画 | `<关键词\|ID> [top_k]` | `/bgm剧场版 凉宫春日的消失` |
| `/bgm漫画` | 仅搜索漫画条目 | `<关键词\|ID> [top_k]` | `/bgm漫画 迷宫饭` |

- `top_k` (可选): 返回结果的数量，默认为 1。

### 2. 放送与订阅
| 命令 | 功能 | 参数 | 示例 |
|------|------|------|------|
| `/today` | 获取今日番剧放送表 | 无 | `/today` |
| `/追番` | 订阅番剧，更新时自动通知 | `<关键词\|ID>` | `/追番 进击的巨人` |

**功能亮点**：
- **精美卡片**: 自动生成包含封面、评分、排名、简介及剧集进度的图文卡片。
- **每日放送**: 渲染精美的每日放送时刻表。
- **自动追番**: 订阅后自动监控集数更新并实时推送通知。

## 🛠️ 配置参数

在 AstrBot 的管理面板或配置文件中设置：

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `access_token` | string | 无 | Bangumi API 令牌（建议配置以获得更高配额） |
| `user_agent` | string | 自动生成 | API 请求头 User-Agent，无需手动配置 |
| `proxy_http` | string | 无 | HTTP 代理地址 (例如 `127.0.0.1`) |
| `port` | int | 无 | HTTP 代理端口 (例如 `7890`) |

### Access Token 获取
虽然不强制，但建议配置 Access Token 以避免 API 限流。
1. 注册/登录 [Bangumi](https://bgm.tv/)
2. 访问 [个人令牌页面](https://next.bgm.tv/demo/access-token/create) 创建新令牌。
3. 将生成的 Token 填入插件配置的 `access_token` 字段。

## 📦 环境依赖

插件首次运行时会自动检查并安装以下依赖：
- **Playwright 浏览器内核**: 用于渲染卡片图片。

如果遇到环境问题，可尝试手动安装：
```bash
pip install -r requirements.txt
playwright install chromium
```