# 服务器纪念站

基于 Pixel Eco（MIT）的 VitePress 静态站。GitHub Pages 提供页面，独立 Python 服务直接查询 Velocity。仓库初始内容为空，等待你配置实际入口和导入审核通过的内容。

## 启动与部署

- Node.js 22+：`npm ci`，然后 `npm run dev`。本地生产构建用 `npm run build`。
- 在 `src/data/site.json` 设置 `wikiUrl`（GitHub 的 HTML 文件或目录链接）、`mcApi`（无尾斜杠的 API HTTPS origin），可选填欢迎语、公开的旧主页链接和相对于站点根目录的 Logo 路径。
- 把本项目放入你的 GitHub 仓库，在 Pages 设置中选择 **GitHub Actions**。推送到 `main` 后工作流部署，项目子路径由 Pages 自动提供。
- Python 3.10+：把 `backend/config.example.json` 复制为 `backend/config.local.json`，填 Velocity 域名、端口和 Pages origin。执行 `python backend/server.py`。若域名依赖 SRV，请填实际目标及端口，并把玩家使用的域名填入 `handshakeHost`。
- 用常驻服务管理器运行**单个采集进程**，将 HTTPS 反向代理转发到 `127.0.0.1:8787`。若由本地代理转发，设置 `trustedProxies` 为代理地址，由代理覆盖 `X-Real-IP` 为真实客户端 IP（例如 Nginx 的 `proxy_set_header X-Real-IP $remote_addr;`）。这样 IP 限流使用访客地址。缓存位于采集进程内，服务重启会立即探测并重建缓存。
- 页面读取 `GET /api/servers`，手动查询调用 `POST /api/servers/{id}/refresh`。共享冷却 60 秒，按 IP 每滚动 60 秒最多提交 5 次。只有配置中的服务器能被探测。

## 导入纪事

在本机把 GitHub Issue 导出为数组。每项包含 `number` 和 `comments`，每条评论需要作者登录名、ISO 时间、`body`。接受 GitHub CLI 的 `author.login` / `createdAt` 或 REST 的 `user.login` / `created_at`。如果原始导出没有完整评论，请先补全评论分页。把导出和审核工作文件放到已忽略的 `private/`。

```sh
python scripts/import_data.py candidates private/issues.json YOUR_LOGIN private/review.json
python scripts/import_data.py chronicle private/review.json
```

先编辑 review 文件，补一句 `quote`，检查 `body`，把脱敏后的本地图片加入 `images`（格式为 `{"file":"screenshots/example.png","alt":"说明"}`，路径相对 review 文件），再将选中的条目标为「公开」。重新导入会更新公开数据，并清理已下架条目的公开图片。如果已发布过内容，旧版本副本仍可能留在 Git 历史或外部缓存。

## 导入皮肤站存档

从现有 Upptime 历史和故障 Issue 整理出可公开的日级摘要。若有私有仓库的完整本地克隆，可以先运行 `python scripts/import_data.py upptime PATH_TO_CLONE private/services.json private/archive.json`。services.json 是 `[{"slug":"skin","name":"皮肤站"}]` 形式的服务清单。脚本从指定服务的 Git 历史读取已记录的探测，保留观测到异常的日期。然后在 private/archive.json 中补上允许公开的故障 Issue 摘要、确知的中断时段或完整覆盖数据。按北京时间划分日期。只有事件记录的日期可用 `unknown` 并附事件。事件持续多天时，在每个受影响日放同一条事件。没有可靠的完整覆盖时段时省略时长字段。

```json
{
  "cutoff": "2025-05-02T16:10:00+08:00",
  "services": [{
    "id": "skin",
    "name": "皮肤站",
    "days": {
      "2025-05-01": {"state": "ok", "uptimeSeconds": 86400, "coveredSeconds": 86400},
      "2025-05-02": {"state": "degraded", "events": [{
        "title": "皮肤站连接中断",
        "start": "2025-05-02T12:00:00+08:00",
        "end": "2025-05-02T12:15:00+08:00",
        "summary": "已恢复。",
        "chronicleId": 42
      }]}
    }
  }]
}
```

`python scripts/import_data.py archive private/archive.json` 生成公开存档。状态取值为 `ok`、`degraded`、`down`、`unknown`。先导入纪事，再导入存档，以便剔除指向私藏纪事的关联 ID。状态页只在所选区间每天都有完整覆盖数据时显示时长可用率。

## 后端验证

`python -m unittest discover -s backend -v`

Pixel Eco 上游见 https://github.com/Lylighte/pixel-eco。许可证见 LICENSE。

