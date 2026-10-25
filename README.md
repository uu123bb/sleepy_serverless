> [!CAUTION]
> 本分支的修改部分由 `DeepSeek V4.1 Flash` 生成

> [!IMPORTANT]
> 这是 [`uu123bb/sleepy_serverless`](https://github.com/uu123bb/sleepy_serverless)，从 [`wyf9/sleepy`](https://github.com/wyf9/sleepy) 分出的个人分支。
> **上游的功能与文档保持不变，本分支只做「部署到 Vercel 等无状态平台」所需的改动**，详见下方。

## 本分支改动

面向 **Serverless（无持久磁盘）** 环境改造，同时不影响本地 / VPS 部署：

| 文件                                             | 改动                                                                                                                                                                                       |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [`storage.py`](./storage.py)                     | **新增**存储后端抽象：`FileStorage`（本地 `data.json`，原子写入）与 `UpstashStorage`（Upstash Redis REST，无额外依赖）。配置 `UPSTASH_REDIS_REST_URL` / `_TOKEN`（或 Vercel 自动注入的 `KV_REST_API_URL` / `KV_REST_API_TOKEN`）即启用 Redis，否则回退到 `data.json` |
| [`data.py`](./data.py)                           | 读写改走后端；远端模式下每个读请求先 `refresh()`，解决多实例内存副本不一致；存储不可用时降级为内存中的模板数据，而不是拒绝启动                                                            |
| [`server.py`](./server.py)                       | **修复鉴权**：`Authorization` 头缺失时不再返回 500（改为 401）；未配置 `SLEEPY_SECRET` 时直接返回 503，避免空密钥绕过                                                                        |
| [`server.py`](./server.py)                       | `/set` 同步更新 `last_updated` 并立即落盘，**SSE 才能感知状态变更**（原先需刷新页面才可见）                                                                                                 |
| [`server.py`](./server.py)                       | Serverless 环境下 `/events` 返回 204（前端自动回退到 `/query` 轮询），并跳过定时存盘线程                                                                                                    |
| [`vercel.json`](./vercel.json)                   | 改用现代 `functions` 配置，排除 `client/` `doc/` `tools/` 以缩小函数体积                                                                                                                    |
| 其它                                             | 新增 `.python-version`（3.12）、`.gitattributes`（统一 LF）、[`tools/mock_upstash.py`](./tools/mock_upstash.py)（离线模拟 Upstash，用于验证 Redis 后端）                                      |

### 部署注意

- **Vercel Hobby 只能部署「个人账号」下的私有仓库**，GitHub 组织下的私有库需要 Pro 计划（或改为公开仓库）。
- 部署到 Vercel **必须配置外部 KV**（Upstash）：`/tmp` 中的 `data.json` 会随函数实例销毁而丢失，状态会不定期重置为模板值。
- 环境变量请在 Vercel 项目设置中配置，**不要**提交 `.env`。
- Serverless 下 `/metrics` 的访问计数只在单个实例内存中累加，**不跨实例统计、也不持久化**（避免读请求回写覆盖状态并浪费 KV 额度）。

---

# sleepy

一个用于 ~~*视奸*~~ 查看个人在线状态 (以及正在使用软件) 的 Flask 应用，让他人能知道你不在而不是故意吊他/她

[**功能**](#功能) / [**演示**](#preview) / [**部署**](#部署--更新) / [**使用**](#使用) / [**Client**](#client) / [**API**](#api) / [**关于**](#关于)

## 功能

- [x] 自行设置在线状态 *(活着 / 似了 等, 也可 **[自定义](./setting/README.md#status_listjson)** 状态列表)*
- [x] 实时更新设备使用状态 *(包括 是否正在使用 / 打开的应用名, 通过 **[client](./client/README.md)** 主动推送)*
- [x] 美观的展示页面 [见 [Preview](#preview)]
- [x] 开放的 Query / Metrics [接口](./doc/api.md), 方便统计

> [!TIP]
> **最新 开发进度 / TODOs 见: [Discord](https://discord.gg/DyBY6gwkeg)** / [Telegram](https://t.me/wyf9_sleepy) / [QQ](https://qm.qq.com/q/uItkv96Wn6)<br/>
> 如有 Bug / 建议, 可 [issue](https://github.com/wyf9/sleepy/issues/new) 或 *[More contact](https://wyf9.top/#/contact) (注明来意)*.

### Preview

演示站 (*较*稳定): [sleepy.wyf9.top](https://sleepy.wyf9.top) ![](https://uptime.wyf9.top/api/badge/9/status) ![](https://uptime.wyf9.top/api/badge/9/uptime)

开发预览 (*不保证可用*): [sleepy-preview.wyf9.top](https://sleepy-preview.wyf9.top) ![](https://uptime.wyf9.top/api/badge/10/status) ![](https://uptime.wyf9.top/api/badge/10/uptime)

HuggingFace 部署预览: [wyf9-sleepy.hf.space](https://wyf9-sleepy.hf.space) ![](https://uptime.wyf9.top/api/badge/22/status) ![](https://uptime.wyf9.top/api/badge/22/uptime)

Vercel 部署预览: [sleepy-vercel.wyf9.top](https://sleepy-vercel.wyf9.top) ![](https://uptime.wyf9.top/api/badge/23/status) ![](https://uptime.wyf9.top/api/badge/23/uptime)

> 区别: 演示站为 wyf9 个人站点; 预览站允许测试 API，且直接运行开发版本 (**密钥均为 `wyf9test`**)

> [!WARNING]
> *不要拿演示站做坏事 (比如 js 注入，已由 DeepSeek 强力修复) ~~，没准哪天我会加访问日志~~*

## 部署 / 更新

请移步 **[部署教程](./doc/deploy.md)** 或 **[更新教程](./doc/update.md)** *(多图警告)*

## Client

如果你想直接开始使用，可在 **[`/client`](./client/README.md)** 找到客户端 (用于**手动更新状态**/**自动更新设备打开应用**)

## API

详细的 API 文档见 [doc/api.md](./doc/api.md).

## 优化站点

见 [Best Practice](./doc/best_practice.md).

> [!TIP]
> 想自定义你的状态列表 / metrics 统计白名单? **[见 `setting` 目录](./setting/README.md)**

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=wyf9/sleepy&type=Date)](https://star-history.com/#wyf9/sleepy&Date)

## 关于

本项目灵感由 Bilibili UP [@WinMEMZ](https://space.bilibili.com/417031122) 而来: **[site](https://maao.cc/sleepy/)** / **[blog](https://www.maodream.com/archives/192/)** / **[repo: `maoawa/sleepy`](https://github.com/maoawa/sleepy)**, 并~~部分借鉴~~使用了前端代码, 在此十分感谢。

[`templates/steam-iframe.html`](./templates/steam-iframe.html) 来自 repo **[gamer2810/steam-miniprofile](https://github.com/gamer2810/steam-miniprofile).**

---

对智能家居 / Home Assistant 感兴趣的朋友，一定要看看 WinMEMZ 的 [sleepy 重生版](https://maao.cc/project-sleepy/): **[maoawa/project-sleepy](https://github.com/maoawa/project-sleepy)!**

感谢 [@1812z](https://github.com/1812z) 的 B 站视频推广~ **([BV1LjB9YjEi3](https://www.bilibili.com/video/BV1LjB9YjEi3))**
