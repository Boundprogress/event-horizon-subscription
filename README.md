# Event Horizon · Browser Automation for AI Agents

[中文](README.md) | [English](README.en.md)

**0 条站点规则，让你的 Agent 操作浏览器、核对结果、交付任务。**

Event Horizon（EH）通过 **MCP（Model Context Protocol）** 为你已有的 AI Agent 接入网页自动化（browser automation）：搜索、点击、填写表单、筛选排序、翻页进详情，再把采集结果与页面依据交回当前 Agent。你提出任务，Agent 负责规划，EH 提供页面信息、执行操作并返回状态。

Browser automation and web automation over MCP, with zero site-specific rules to author. Bring your own AI agent to search, click, fill forms, and extract data in your local Chrome, then return results with page evidence.

Chrome 在本机运行，网页采样需要发送到云端处理；模型与 Agent 由你选择。**0 条站点规则**指使用通用网页操作流程时，无需用户逐站编写选择器或点击脚本；不代表任意网站、任意任务都能完成。[能力与边界](docs/CAPABILITIES.md)

版本：`0.27.1-lab.20261109.1`。本仓库是 Python 标准库薄客户端，包含本机控制台、浏览器连接器和 MCP Skill；新账号注册成功即自动获得 1000 帧免费试用额度。

解压后可直接启动。用户文档见 [docs/README.md](docs/README.md)。本机控制台支持**中文 / English**，可通过语言切换选择界面语言。

## 公开测试与免费试用

**EH 当前处于公开测试阶段，新账号注册成功即自动获得 1000 帧免费额度，无需邮件申请或填写激活码。** 这是一次性总额度，永久有效，用完即止，不按月重置。

可在客户端账号页核对实际剩余额度与有效状态；如另有永久总帧数激活码，可在账号页兑换以追加额度。自带模型、宿主或其他第三方服务可能另行产生费用。

测试版本可能出现错误、中断或结果不完整，不保证特定网站或任务均能完成。请仅在有权访问和操作的范围内试用，对关键操作与输出结果进行人工核对，并阅读客户端展示的服务协议。本说明不影响依法不得排除或限制的责任。

## 三个核心能力

| 核心能力 | 对你的任务意味着什么 |
| --- | --- |
| **0 条站点规则** | 换站沿用同一套工具，无需用户逐站预写选择器或固定点击脚本。具体页面的可用范围仍需验证。 |
| **真实操作** | 在网页上搜索、点击、填写、筛选、翻页和处理弹窗；操作后返回回执与页面状态，受阻或未确认时据此核对。 |
| **交付可核对** | Agent 将列表、字段与来源整理为答案，说明已完成什么、还缺什么；未确认的请求可沿原编号查回。 |

接入能加载本机 MCP 工具的宿主，沿用自己的模型与 Agent。专属浏览器保留网站允许持久保存的登录态；过期与重新验证由网站决定。

**点击成功只是一步，用户要的是任务结果。** EH 把页面状态与操作回执交给 Agent，帮助它判断下一步；最终答案的对象、字段、数量和来源仍须逐项核对。

任务受阻或结果未确认时，Agent 应说明阻塞与缺项，查回状态后再决定下一步。

## 可以交给 Agent 的任务

- **多条件查询**：输入日期、地点或价格条件，筛选排序后打开详情，整理符合要求的条目。
- **跨页资料整理（data extraction）**：翻页查找指定公告，进入关联页，汇总字段并附上来源。
- **网页表单（form filling）**：填写授权范围内的输入项，核对当前值与页面反馈，再决定是否继续。
- **跨站信息比较**：把不同网页读到的价格、时间或条件放在一起，给出有依据的比较结果。

这些是任务表达示例，完成情况取决于目标网页、模型与授权范围。批量固定结构的数据采集（web scraping），可同时评估正式 API 或授权数据接口。

## 能力与公开演示

支持页面结构读取、条件输入、筛选排序、分页详情、弹窗和关联页等交互，再由 Agent 决定下一步。demo 的六题连续实况覆盖了这些组合；对应合成站点与驾驶配置，详见 [六题说明与核对入口](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/README.md)。历史演示不构成当前所有站点的交付保证。

[EH demo](https://github.com/Boundprogress/event-horizon-demo) 保留了历史实测、视频和失败记录。[历史实测与核对入口](docs/DEMO_EVIDENCE.md) 区分了运行结束、交付判定与逐字段事实核验，便于按原始条件判断。

## 选择 Browser Use（browser-use / browseruse）、Playwright MCP 等工具时

接入方式、目标网页和结果要求，决定了 browser automation 工具是否适合你的任务。可以从三件事开始核对：能否接入已有 Agent、换站是否需要维护脚本、交回结果是否有页面依据。

EH 聚焦 **0 条站点规则、真实操作、交付可核对**，通过 MCP 接入你的 Agent，在本机 Chrome 完成网页任务。关于已有社区讨论与 EH 的产品选择，见 [从网页操作到可核对的交付](docs/BROWSER_USE_COMPARISON.md)。

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

1. 阅读服务协议并注册账号，完成邮箱验证以便找回账号。
2. 注册成功即自动获得 1000 帧一次性总额度，可在账号页查看；永久有效，用完即止，不按月重置。
3. “准备本机使用” → “连接浏览器”。
4. “复制一句话接入” → 交给可信的本机 Agent。
5. 等 Agent 实际检查工具与连接，再提出任务。

无需选择宿主产品。复制指令只准备本机资料，宿主加载成功才算接通；API Key 和设备凭据不需要粘贴到聊天。服务开放情况、配套版本、试用额度与有效状态，以运营公布及账号实际显示为准。

## 接上以后

任务结果在当前 Agent 中查看；遇到未确认操作，沿原请求号查回，不反复提交。关键操作需要明确授权，结果仍要对照页面核实。

注册赠送额度为一次性总额 1000 帧，账号页显示实际剩余额度与有效状态。额度不足时，可兑换永久总帧数激活码追加额度；无法使用时，可邮件联系运营核对。

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

代码采用 **GNU Affero General Public License v3.0 only（AGPL-3.0-only）**，见 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)。第三方材料保留各自许可；使用在线服务另行适用控制台展示的服务协议。

如果需要私有本地部署请联系[eventhorizontest@163.com](mailto:eventhorizontest@163.com)
