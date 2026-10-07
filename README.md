# QQ 志愿活动秒级提醒系统

监听指定 QQ 群里**指定发送者**发的活动消息（真实活动消息通常是**一张纯二维码图、一个文字都没有**），
在 **约 0.2 秒**内弹出一个全屏二维码窗口并响铃，同时把活动摘要推送到**手机微信**。

解决的实际问题：志愿活动名额先到先得。等你自己刷到群里那条消息时，名额往往已经没了。

> ⚠️ **使用前务必读 [`安全约束.md`](安全约束.md)**：本系统对 QQ 是**纯只读监听**，代码中不存在任何发送群消息的能力。

---

## 工作流程

```
QQ 客户端
   │  NapCat 注入挂载
   ▼
NapCat / OneBot 11
   │  HTTP POST → http://127.0.0.1:18080/        ← 事件只上报，单向
   ▼
app/main.py            接收事件
   │
   ├─ app/filter.py    判定：群号 / 发送者 / 关键词 / 图片数 / 图片域名
   │        │
   │        ├── 命中 ──┬─► app/popup.py   全屏二维码弹窗 + 响铃
   │        │          └─► Server酱       推送摘要到手机微信
   │        └── 未命中 ──► 只写日志，静默忽略
   │
   └─ logs/all-*.jsonl   全量消息      logs/hit-*.jsonl  命中记录

tools/watchdog.py       看门狗：链路失效时告警（日志 + 弹窗 + 手机）
```

**为什么不能靠关键词判定**：真实活动消息是一张图，提取不到任何文字。
所以判定用三条**并列**条件，满足任意一条即命中：

| 触发条件 | 说明 |
|---|---|
| 图片数量达标 | 图片数 ≥ `多图触发阈值`（默认 `1`，即关键发送者发的任何图都提醒） |
| 图片域名白名单 | 图片 URL 域名在 `活动图域名` 里，用于精确锁定报名系统的图 |
| 关键词命中 | 文字里出现 `关键词` 里的词，用于带文字说明的活动消息 |

默认阈值 `1` 是**有意的取舍：宁可多弹一次，也绝不漏掉名额**。误报多时可以调成 `2` 或填 `活动图域名`。

## 实测延迟

| 环节 | 耗时 |
|---|---|
| 消息到达监听服务 → 弹窗进程启动 | **15 ms** |
| 弹窗进程启动 → 窗口出现在屏幕 | **176 ms** |
| 手机推送 | 与弹窗**并行**，互不等待 |
| 加上 QQ 服务器 → 你电脑的网络延迟 | 端到端约 **0.6 ～ 0.9 秒** |

---

## 目录结构

```
qq-watcher/
├── config.json            所有设置（**不入库**，见下方「配置」）
├── config.example.json    配置模板，复制成 config.json 再改
├── requirements.txt       依赖（只有 Pillow）
├── start-watcher.bat      启动监听服务（带窗口，看日志用）
├── 启动监听服务.vbs         静默启动监听 + 看门狗
├── 一键启动NapCat.vbs       启动 QQ + NapCat（会弹 UAC）
├── 启动NapCat-管理员.bat    上面那个 VBS 的实际执行体
├── 开机启动.bat            开机自启入口
├── install-autostart.bat  安装 / 卸载开机自启
├── app/                   核心程序
│   ├── main.py            接收事件 + 判定 + 触发动作
│   ├── filter.py          筛选逻辑 + CQ 码解析
│   ├── popup.py           全屏二维码弹窗
│   ├── config.py          配置加载（支持热重载）
│   └── jsonio.py          容错 JSON 读取（兼容记事本写出的 BOM）
├── tools/                 工具与测试脚本
├── samples/               测试用素材（simulate.py 需要）
├── images/                命中的活动原图，自动按时间命名（不入库）
├── logs/                  运行日志与消息记录（不入库）
└── napcat/                NapCat 本体，约 90 MB（**不入库**，用工具重新获取）
```

### `tools/` 里的脚本

**平时会用到的：**

| 脚本 | 用途 |
|---|---|
| `preflight.py` | 全面体检：环境 / 依赖 / 配置 / 端口 / NapCat，一次全查 |
| `watchdog.py` | 链路失效检测，`--once` 单次体检 |
| `show_qrcode.py` | 登录失效时显示二维码（自动刷新） |
| `pushtest.py` | 测试手机推送通道 |
| `simulate.py` | 不用真消息就能跑端到端测试 |
| `test_judge.py` | 判定逻辑回归测试（**改完筛选逻辑先跑这个**） |
| `test_formats.py` | 消息格式容错测试（数组 / CQ 字符串等各种写法） |

**只在重装 / 排障时用：**

| 脚本 | 用途 |
|---|---|
| `fetch_napcat.py` | 重新下载 NapCat（分段并行 + SHA256 校验） |
| `setup_napcat.py` | 解压并写入 OneBot 配置 |
| `sync_napcat_config.py` | 重新同步上报配置到 NapCat |
| `check_live.py` | 一键判定「登录 + 上报链路」是否正常 |
| `wait_login.py` / `wait_online.py` | 等待登录 / 上线并验证链路 |

---

## 环境要求

- **Windows 10 / 11**（依赖 `tkinter`、`winsound`；`filter.py` 之外无跨平台保证）
- **Python 3.9+**，安装时必须勾选 **tcl/tk** 组件
- **Pillow**：`pip install -r requirements.txt`
- **QQ 客户端 + NapCat**（走 OneBot 11 协议挂载 QQ）

## 快速开始

1. **装依赖**

   ```powershell
   pip install -r requirements.txt
   ```

2. **准备配置**

   ```powershell
   copy config.example.json config.json
   ```

   然后编辑 `config.json`，至少填 `监听.群号`、`监听.关键发送者`，
   手机推送要填 `手机推送.ServerChanSendKey`（从 <https://sct.ftqq.com> 获取，见
   [`Server酱注册指引.md`](Server酱注册指引.md)）。

3. **先干跑观察**（强烈建议）

   保持 `行为.干跑模式 = true`，先跑一两天，翻 `logs\watcher.log` 看判定结果：

   ```
   命中 ✓ 群1034761242 用户2108873477 | ['群号 ... 匹配', '发送者 ... 匹配', '含 1 张图片']
   忽略 群1034761242 用户123456789 | ['发送者 123456789 不是关键发送者']
   ```

   确认该命中的都命中、不该命中的没误报，再改成 `false`。

4. **获取 NapCat**（本仓库不含，约 90 MB）

   ```powershell
   python tools\fetch_napcat.py
   python tools\setup_napcat.py
   ```

5. **启动**

   ```powershell
   python tools\preflight.py        # 先体检
   start-watcher.bat                # 启动监听
   ```

   看到 `已就绪，等待 NapCat 推送事件…` 就成了。

6. **端到端自测**（不用等真消息）

   ```powershell
   python tools\simulate.py real      # 管理员单张纯图无文字（最贴近真实）
   python tools\simulate.py real3     # 管理员连发 3 张图无文字
   python tools\simulate.py nomatch   # 不含图无关键词，应该被忽略
   ```

   连跑两次 `real` 可以验证**去重**（第二次只记录不弹窗）。

### 自检与回归测试

```powershell
python tools\test_judge.py       # 判定逻辑，改配置后必跑
python tools\preflight.py        # 环境/依赖/端口/NapCat 全查
python tools\watchdog.py --once  # 只看监控链路是否活着
```

---

## 配置说明

全部设置都在 `config.json`，**改完保存即生效，不用重启**（`config.py` 支持热重载）。

| 键 | 说明 |
|---|---|
| `监听.群号` | 只监听这些群，其余全部忽略 |
| `监听.关键发送者` | 只有这些 QQ 号发的消息才可能命中 |
| `监听.关键词` | 带文字的活动消息用 |
| `监听.必须含图片` | 报名入口是二维码图，建议保持 `true` |
| `监听.接收端口` | 默认 `18080`，要和 NapCat 的 `httpClients` 对上 |
| `监听.活动图域名` | 图片域名白名单，留空则只用阈值判断 |
| `监听.多图触发阈值` | 图片数达到这个值就算活动消息，默认 `1` |
| `行为.干跑模式` | `true` = 只记录不弹窗不推送（首次部署先用它） |
| `行为.全屏弹窗` / `播放声音` | 弹窗与响铃开关 |
| `行为.记录所有群消息` | 写 `logs/all-*.jsonl`，排查误报用 |
| `手机推送.启用` / `ServerChanSendKey` | 手机微信推送 |
| `手机推送.推送二维码原图到QQ` | 默认 `false`；即便打开也只走**私聊**，不发群 |

**调参**：漏报 → 调小 `多图触发阈值` 或补 `关键词`；误报多 → 调大阈值或填 `活动图域名`。

**内置防打扰**：同一张活动图 **10 分钟内只提醒一次**（NapCat 断线重连、管理员重发都不会糊屏）。

---

## 安全与风险

### 硬性约束：绝不发群消息

该志愿者群处于全员禁言状态，即使将来解禁也**不得**发送任何消息。
代码中已审计确认零 `send_group_msg`，且监听链路是单向的（NapCat → 本服务）。
详见 [`安全约束.md`](安全约束.md)。

### 关于 `Smart App Control`

Windows 11 的 Smart App Control 会拦截 NapCat 未签名的注入组件。
本项目的部署过程**曾按用户要求关闭它**——这是**单向操作**，只能靠重装 / 重置 Windows 恢复。
换机器部署前请先掂量这个代价，记录见 `logs/sac-backup.txt`。

### 已知风险

NapCat 通过修改 QQ 客户端挂载，**不符合腾讯用户协议，理论上有封号风险**。这是使用前必须知道的代价。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [`交付说明.md`](交付说明.md) | 交付状态、实测验证结果、**8 条排障记录**（含 Smart App Control、`Content-Length: 0`、keep-alive、CQ 码、批处理编码等踩过的坑） |
| [`使用说明.md`](使用说明.md) | 完整技术说明、判定原理、调参方法、常见问题 |
| [`安全约束.md`](安全约束.md) | 「绝不发群消息」硬约束与代码审计结论 |
| [`Server酱注册指引.md`](Server酱注册指引.md) | 手机推送通道的注册与验证 |

---

## 关于本仓库不含的东西

| 未入库 | 原因 | 怎么恢复 |
|---|---|---|
| `config.json` | 含 Server酱 SendKey（拿到就能往你微信发推送） | 复制 `config.example.json` 填写 |
| `napcat/` | 约 90 MB 第三方程序，且含 NapCat WebUI token | `python tools/fetch_napcat.py` + `setup_napcat.py` |
| `logs/` `images/` | 含**他人**聊天内容与活动二维码原图，属隐私数据 | 运行时自动生成 |

> 如果你打算把这个仓库设为**公开**，请注意文档里写有真实的群号与 QQ 号，建议先做脱敏。
