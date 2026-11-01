# 手机上直接打开网站玩

网页版保留完整 RPG。网站部署后可用手机浏览器打开，或在浏览器菜单中添加到主屏幕；更新无需重新安装 APK。先用平台提供的 HTTPS 域名，不必购买域名。原电脑/手机存档用 JSON 导出、导入迁移；同一网站后端上的存档可在不同设备读取。

## 较省费用：Fly.io 按需运行

`fly.toml` 默认东京区、单实例 512 MB 内存、1 GB 存档卷；空闲后停机，访问时唤醒。512 MB 是运行内存，1 GB 是磁盘购买容量，并非游戏预计会占满。存档、配置、登录签名保存在 /data。

Fly 的计算按运行时间收费，停机仍有根镜像和卷存储费用；卷按预留容量计费，当前标准价格为 0.15 美元/GB/月，东京计算与流量按其区域价格计算。不是完全免费，也不承诺固定月费。对于偶尔玩一下的个人站，按需启停可降低常开实例费用。依据：https://fly.io/pricing/ ，https://fly.io/docs/launch/autostop-autostart/ 。不要为了减少这几角钱把存档放到临时磁盘。

安装官方 flyctl、登录自己的账户后，在项目根目录执行 `fly launch --no-deploy`，使用本项目配置，选择一个唯一应用名；确认只建立一个实例。通过 Fly Secrets 设置 `WUJI_SITE_PASSWORD`（至少 12 字符），然后运行 `fly deploy --ha=false`。平台会显示 fly.dev HTTPS 地址。密码通过平台的密钥管理输入，不要写进仓库或聊天。

如平台未按配置自动创建卷，可在控制台创建 `wuji_data`，1 GB、同一区域。Docker 入口会为非 root 游戏进程准备数据目录。后续用同一应用/同一卷部署，不要删除卷。按需唤醒会有短暂等待。

自动更新可以通过 Fly 官方 GitHub Actions 部署：在 GitHub 仓库 Secrets 配置限定该应用的 `FLY_API_TOKEN`，在 Variables 配置 `FLY_APP_NAME`，再使用 `deploy-fly.yml`。只有两个值都配置后才启用部署；主分支测试通过后更新，亦可手动触发。API Key 在首次登录网站后填写，保存在持久化配置中。

## 配置更简单：Render

[部署当前试玩分支](https://render.com/deploy?repo=https://github.com/yoyuyoyu123/my-rpg/tree/codex/mobile-web)

连接自己的 GitHub 仓库，审阅 `render.yaml` 的服务、价格与磁盘设置，设置网站密码后再确认付费部署。默认新加坡、单实例、512 MB 内存、1 GB 持久化磁盘。当前入门实例 7 美元/月，磁盘 0.25 美元/GB/月，AI 调用费另计。免费实例不能挂持久化磁盘，因此此配置选用了付费实例。

平台会提供 onrender.com HTTPS 地址。登录网站后，在原来的“后端 Key”面板填写自己的模型 Key。初次试玩部署 codex/mobile-web 分支；正式合并后，可将 Render 服务部署分支切到 main。`autoDeployTrigger: checksPass` 让测试通过的代码自动上线。挂盘服务重新部署可能短暂断开连接，已提交存档会保留。

没有连接你的托管账户、没有确认平台计费前，以上配置不会自动创建付费服务。本仓库不包含任何真实密码或 Key。

## Gemini 与 GPT-6 Luna

- Gemini：在 https://aistudio.google.com/ 的 API Keys 页面创建 Key。部分模型有免费层，额度以账户和模型页面为准；免费层并不保证所有模型或无限请求。官方：https://ai.google.dev/gemini-api/docs/api-key ，https://ai.google.dev/gemini-api/docs/pricing 。当前兼容入口默认 `gemini-3.8-flash`，官方兼容接口仍为 beta。
- OpenAI GPT-6 Luna：在 https://platform.openai.com/api-keys 创建项目 Key，并在 API 平台 Billing 检查可用额度。ChatGPT 订阅与 API 计费分开；符合条件的 Pro、Business 用户目前可在账单设置中关联自己的 API 组织领取额度，先查看此权益再决定充值：https://developers.openai.com/api/docs/guides/chatgpt-api-credits 。模型 ID 为 `gpt-6-luna`；游戏默认以 `reasoning_effort: none` 使用其采样参数，使用 `max_completion_tokens` 控制预算。官方：https://developers.openai.com/api/docs/models/gpt-6-luna ，https://developers.openai.com/api/docs/guides/latest-model 。

在游戏连接页填入对应 Key，点“保存到后端”，再在模型选择框选 Gemini 或 Luna。不要将 Key 发给其他人。模型调用未使用真实账户测试，具体可用性与额度以自己的控制台为准。建议用同开局、同行动对照；“均衡”模式比“双稿”模式减少调用，原有“传统单稿”也可用于比较。

## 更新和存档

网页发现新版本时显示“保存并更新”；当前回合进行中或存档写入失败时不刷新。网页 HTML、API、存档与模型响应不经过离线缓存。离线仅显示重连提示，不会伪造可继续调用 AI。站点适用于站主私用；如以后开放给朋友，需要独立账号和独立存档隔离。
