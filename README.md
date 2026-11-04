# Event Horizon · 客户端

把你自己的 Agent，接到你自己的浏览器。

EH 将网页中可见的内容和操作目标整理成结构化信息，再把执行状态交给 Agent。Chrome 在本机运行，网页采样需要发送到云端处理；模型与 Agent 由你选择。

版本：`0.25.7-lab.20261104.1`。本仓库是 Python 标准库薄客户端，包含本机控制台、浏览器连接器和 MCP Skill；使用配套在线服务需要有效订阅。

解压后可直接启动。用户文档见 [docs/README.md](docs/README.md)。

## 想先看看

[EH demo](https://github.com/Boundprogress/event-horizon-demo) 保留了历史实测、视频和失败记录。那些结果对应当时版本与部署，不是本版的效果保证。

## 能力与公开演示

支持页面结构读取、条件输入、筛选排序、分页详情、弹窗和关联页等交互，再由 Agent 决定下一步。demo 的六题连续实况覆盖了这些组合；对应合成站点与驾驶配置，详见 [六题说明与核对入口](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/README.md)。历史演示不构成当前所有站点的交付保证。

## 想用

在解压后包含 eh.py 的目录中运行以下命令。

准备 Python 3.10+、Chrome，以及能访问本机文件、加载 MCP 工具的 Agent。

```sh
git clone https://github.com/Boundprogress/event-horizon-subscription.git
cd event-horizon-subscription

python3 -I -S -B eh.py start
```

Windows PowerShell 使用：

```powershell
py -3 -I -S -B eh.py start
```

如果本机只有 `python` 命令，运行 `python -I -S -B eh.py start`。

不需要 `pip install .`。启动会打开本机控制台，终端需要保持运行。

1. 注册并验证邮箱，阅读服务协议。
2. 通过运营渠道购买激活码，在“购买与激活”中激活。
3. “准备本机使用” → “连接浏览器”。
4. “复制一句话接入” → 交给可信的本机 Agent。
5. 等 Agent 实际检查工具与连接，再提出任务。

无需选择宿主产品。复制指令只准备本机资料，宿主加载成功才算接通；API Key 和设备凭据不需要粘贴到聊天。服务是否开放、配套版本、套餐与余额，以运营公布及账号实际状态为准。

## 接上以后

任务结果在当前 Agent 中查看；遇到未确认操作，沿原请求号查回，不反复提交。关键操作需要明确授权，结果仍要对照页面核实。

公开 HTTP(S) 站点不要求精确白名单，敏感站点和私有网络入口受限制。浏览器在本机，页面采样仍会经过云端；请先阅读控制台中的服务协议。

客户端不自动保存或回放任务历史正文。服务端正文只作有界短暂交付；用户显式导出、Agent 对话或文件、浏览器 profile 与下载由用户管理。运行目录与凭据保存在源码目录外，不要提交 `launch.json`、Key 或设备文件。

忘记账号或密码可用已验证邮箱找回；账号受限可在“账号申诉”提交说明和查询结果。

## 更新与退出

先结束当前 EH 会话、断开专属浏览器、退出控制台和宿主的 EH 工具连接，再获取发布者确认的版本。保留自己的未提交修改，更新后重新启动并加载 EH 连接。关闭网页标签不等于退出客户端，终端 Ctrl-C 也可请求正常退出。

Skill 位于 [skills/eh-subscription-browser/SKILL.md](skills/eh-subscription-browser/SKILL.md)，由一句话接入流程准备。Skill 本身不代替 MCP 配置或浏览器连接。

`CLIENT_MANIFEST.json` 用于核对文件是否变化，不是发布者身份或签名证明。可运行本地文件审计：

```sh
python3 -I -S -B client.py audit --package-dir . --json-only
```

## 交流与反馈

邮箱：[eventhorizontest@163.com](mailto:eventhorizontest@163.com)。提供版本、错误代码和脱敏复现步骤，不发送密码、验证码、Key、设备凭据或网页私密内容。

## 代码许可

代码采用 **GNU Affero General Public License v3.0 only（AGPL-3.0-only）**，见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。第三方材料保留各自许可；使用在线订阅服务另行适用控制台展示的服务协议。

如果需要私有本地部署请联系[eventhorizontest@163.com](mailto:eventhorizontest@163.com)
