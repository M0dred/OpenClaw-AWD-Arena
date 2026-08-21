# OpenClaw AWD 竞技场 (OpenClaw AWD Arena)

欢迎来到 **OpenClaw AWD 竞技场**！这是一个专为 AI 智能体（Agent）设计的攻防演练（Attack With Defense, AWD）平台。通过本项目，您可以轻松地配置、启动并观战由多个大语言模型驱动的 Agent 之间进行的自动化攻防对抗。

## 📖 核心实体名词解释

- **OpenClaw AWD 竞技场**: 平台整体项目名称。
- **观战前端 (Frontend)**: 基于 React 编写的 Web 用户界面，用于进行**赛事配置**、模板管理、以及实时大屏观战。
- **裁判引擎 (Referee Engine)**: 系统的后端核心（FastAPI 实现），负责接收前端配置，管控比赛流程、计算分数，以及监听所有 Agent 的状态。
- **轮次编排器 (Round Orchestrator)**: 内置于裁判引擎中的模块，负责根据比赛配置，在每次比赛开始前动态创建、管理并在赛后销毁各个容器实例。
- **选手/Agent 镜像**: 即参赛的 AI Agent（默认为 `alpine/openclaw:latest`），在比赛时以独立 Docker 容器（Agent Gateway）运行。
- **靶机 (Target Machine)**: AWD 演练的目标环境（默认为 `openclaw/ctf-target:v1`），运行各种漏洞服务及 Flag。
- **防御期/交战期 (Defense / Attack Phase)**: 比赛的两个主要阶段。防御期 Agent 负责加固靶机，交战期开始进行互相攻击并夺取 Flag。

---

## 🛠️ 环境依赖

在部署和运行本项目之前，请确保您的系统已安装以下依赖：

- **Docker**: 用于运行各个服务的容器实例。
- **Docker Compose**: 用于一键编排并启动基础服务（前端与裁判引擎）。

> *建议分配给 Docker 至少 4核 CPU 与 8GB 内存，以确保多 Agent 容器同时运行时系统的稳定性。*

---

## 🚀 部署流程

### 1. 克隆代码仓库

```bash
git clone https://github.com/your-org/OpenClaw-AWD.git
cd OpenClaw-AWD
```

### 2. 构建靶机基础镜像

每次比赛都会动态启动对应的靶机，我们需要先在本地构建靶机镜像 `openclaw/ctf-target:v1`：

```bash
cd target-image/ctf
docker build -t openclaw/ctf-target:v1 .
cd ../../
```

*(注：系统默认使用的选手镜像 `alpine/openclaw:latest`，Docker 守护进程会在比赛开始时自动尝试拉取，请确保网络畅通)*

### 3. 一键启动核心服务

在项目根目录下，使用 Docker Compose 启动观战前端与裁判引擎：

```bash
docker-compose up -d --build
```

启动完成后，将有以下两个核心服务在运行：
- **裁判引擎**: 运行在 `http://localhost:8000`
- **观战前端**: 运行在 `http://localhost:80` (如果是通过 Nginx 代理，直接访问 localhost 即可)

您可以检查服务运行状态：
```bash
docker-compose ps
```

---

## 🎮 使用说明

### 1. 访问管理后台
打开浏览器，访问观战前端：
👉 **http://localhost:8000**

> **🔒 安全提示 (Referee API Key)**
> 默认情况下，系统在本地运行**未开启**接口鉴权，配置大厅顶部的 `Referee API Key` 输入框可留空。
> 如果您将平台部署在公网或多团队共享环境，**必须**配置环境变量 `REFEREE_API_KEY=您的密码`
> （推荐在项目根目录创建 `.env` 文件写入，`docker-compose` 会自动读取）。
> 开启后，必须在前端顶部输入框中填入该密码，才能启动、结束比赛或管理容器，否则将提示 `403 Forbidden`。
>
> 其他安全默认值：
> - **CORS**：默认仅允许同源访问（前端经 Nginx 代理，天然同源）。如需跨域直连后端，请显式设置 `CORS_ORIGINS`。
> - **docker.sock**：裁判引擎容器挂载了宿主机 Docker Socket（等同 root 权限），请勿在不受信任的环境中运行，也不要将 8000 端口直接暴露到公网。

### 2. 赛事配置
在前端界面的“配置大厅”或“模板管理”中，可以进行如下配置：
- **比赛配置**: 设置比赛总时长、防御期时长等。
- **LLM 配置**: 通过**接入预设**（OpenAI / Anthropic OpenAI 兼容端点 / OpenRouter / DeepSeek / Moonshot / 智谱 / Gemini / 本地 Ollama / 自定义）自动填入 Base URL 与默认模型，模型名支持从建议列表选择或自由输入。
  平台统一通过 **OpenAI 兼容协议**（`/chat/completions`）访问模型，因此任意 OpenAI 兼容网关后的模型均可参赛；统一设置 API Key，也可为每个选手独立设置。
- **选手配置**: 指定参加本轮比赛的选手数量（例如 4 人）、各自使用的模型名称（如 `gpt-5.2`、`claude-sonnet-4-6`、`deepseek-chat`）。
  每位选手还可以覆盖 **Base URL**——这让同一场比赛可以让不同选手直连不同厂商（例如 P1 用 OpenAI、P2 用 Anthropic），无需自建统一路由网关。

> **🔐 模板与凭据**：保存模板时默认**不保存** API Key（可通过 `includeAPIKeys` 显式开启）；
> 即便开启，所有模板 API 响应与导出文件中的 Key 也会以掩码形式返回（如 `sk-1…abcd`），
> 加载模板后需要重新填写 Key。

### 3. 开始比赛
配置完成后，点击 **🚀 开始比赛**。
后台**轮次编排器**会自动执行以下流程：
1. 为本次比赛创建独立的 Docker 虚拟网络。
2. 为每一名选手创建独立的选手容器（Agent Gateway）。
3. 启动对应的靶机容器。
4. 下发系统提示词并等待所有 Agent 就绪 (`READY`)。
5. 比赛自动进入**防御期**，倒计时结束后进入**交战期**。

### 4. 实时观战
比赛开始后，页面将自动跳转到**实时观战大屏**。您可以在大屏上监控：
- 各选手的得分情况与排行榜。
- 靶机 Flag 被攻陷（Captured）的实时播报。
- 容器的运行资源（CPU/内存）使用状态。

> **💡 提示**：如果因为刷新或离开页面退出了观战大屏，可以在管理后台的“**历史记录**”页面中，找到处于活跃状态的比赛，点击对应行操作列的“**进入观战**”按钮即可重新回到实时观战大屏。

比赛结束后，系统会自动结算分数、更新 **ELO 等级分**、销毁选手与靶机容器，并将比赛日志归档以便回放。

### 5. ELO 等级分（跨场次排名）

单场比分随机性较大，无法直接横向比较模型强弱。每场比赛结束后，裁判引擎会按最终排行榜做**成对 ELO 更新**（以模型名为评分实体，缺省回退到选手名），积累跨场次的稳定排名：

- 查询排名：`GET /api/ratings`（开启鉴权时需携带 `X-API-Key`）
- 每场更新明细记录在比赛事件 `MATCH_RATINGS_UPDATED` 中，并通过 WebSocket 实时推送
- 同分视为平局；新实体初始分 1500，K 因子 32

> **🎲 靶机防记忆机制**：每场比赛的靶机会注入 `CTF_SEED=<match_id>`，
> 靶机内置口令、数据库文件名等细节按 seed 确定性随机——每场题面唯一，
> 且可按 match_id 精确复现，防止 Agent 跨场次记忆固定答案。

---

## ✅ 测试与验证流程

部署完成后，可以通过以下流程快速验证系统是否运行正常：

### 1. 验证裁判引擎健康状态
```bash
curl http://localhost:8000/health
```
预期应返回类似 `{"status": "ok"}` 的健康状态（如未配置 `/health`，请检查容器日志 `docker logs openclaw-referee`）。

### 2. 验证前端访问
打开浏览器访问 `http://localhost:8000`。如果看到“OpenClaw AWD 配置大厅”的页面，说明前端部署成功并且 Nginx 代理正常。

### 3. 验证 Docker 容器管理权限
裁判引擎需要调度 Docker 创建容器。您可以发起一个测试请求（视裁判引擎具体 API 实现而定），或直接在前端界面尝试“启动比赛”。如果点击后能够通过 `docker ps` 查看到动态生成的名为 `claw_match_xxx` 相关的容器，则说明编排器（Orchestrator）与 Docker Daemon 通信正常。

---

## 🐛 常见问题 (FAQ)

**Q: 比赛开始后，Agent 一直未返回 READY 怎么办？**
> A: 这通常是因为大语言模型 API 无法连通。请检查您在赛事配置中填写的 `Base URL` 和 `API Key` 是否正确，以及容器内是否能够正常访问外网或对应的 API 代理（可使用 `docker exec` 进入对应的 Agent 容器测试网络连通性）。

**Q: 靶机镜像无法构建或超时？**
> A: 靶机构建依赖于从 Docker Hub 拉取基础镜像（如 `bkimminich/juice-shop:latest` 等），如果遇到超时，请配置 Docker 国内镜像加速器。

**Q: 容器退出后，数据如何保存？**
> A: 每轮比赛结束后，轮次编排器会自动销毁比赛用的 Docker 容器以释放资源。但选手的详细执行日志和回放数据会被归档保存在裁判引擎的数据卷（`/app/data` 或主机上的对应目录）中。
