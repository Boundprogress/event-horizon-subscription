# 历史实测与核对入口

[中文](DEMO_EVIDENCE.md) | [English](DEMO_EVIDENCE.en.md)

本页精选 EH demo 的能力展示材料，并保留实验条件、统计口径和原始核对入口。它是历史资料整理，没有在当前订阅版上重新运行这些实验。

引用版本固定为 demo 提交 [`ac0236cd19560efa5f43ba350bbc599ff4158fc4`](https://github.com/Boundprogress/event-horizon-demo/tree/ac0236cd19560efa5f43ba350bbc599ff4158fc4)。原视频与原始记录仍在原仓库，不在这里改写或重新计分。

## 一、自建测试站：六题连续运行

2026-09-21，项目方在使用固定合成数据的自建站点连续执行六题。驾驶模型为材料中标记的 DeepSeek V4.1 Flash，宿主 OpenCode 1.17.13、high 档；使用冻结版本加四处页面读取修正。站点没有账号、支付或真实预订。

| 题目类型 | 展示的操作链 |
| --- | --- |
| 工作台 | 读取多个统计项，打开并读取说明弹窗 |
| 商品 | 类别和新品筛选、价格排序、详情及关联资料 |
| 班次 | 路线筛选、票价排序、时刻和余位字段 |
| 条件查询 | 日期、起终点、时段、价格及余位条件组合 |
| 公告 | 分页、指定条目、关联商品跳转与字段核对 |
| 展示点 | 先处理调整公告，再读取常规信息和关联项 |

公开材料报告：**51 次动作，各题驾驶用时合计 384.3 秒，43 个交付项与测试数据源核对一致**。录像总长 492 秒，包含输入、准备和复述等间隔，不能把两种时间口径混为一谈。

核对清单由项目方公开，没有标注具名独立审查者。本页没有另做第三方人审；合成站点的这一轮结果，也不能推导真实网站的普遍表现。

查看：[实况与环境说明](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/README.md) · [连续录像](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/testsite_live_0921_2k.mp4) · [六题结果](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/results.md) · [43 项核对表](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/REVIEW_SHEET_testsite_live_0921.md) · [机器汇总](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/summary.json)。

## 二、50 题、300 次运行

项目方使用 50 条任务原句，在无经验和有经验两种条件下各重复三次，共 300 次运行；不是 300 道不同的题。驾驶模型为材料中标记的 DeepSeek V4 Flash，经 OpenCode 执行；记录称运行期间未由人工接管。

| 公开指标 | 无经验组 | 经验组 | 合计与含义 |
| --- | ---: | ---: | --- |
| 执行结束并留下记录 | 150/150 | 150/150 | 300 次都有结束记录 |
| 原冻结交付判定通过 | 149/150 | 149/150 | 298/300，采用当时固定口径 |
| 涉及站点 | 46 | 45 | 主域名归一后的并集 51 个 |

**交付判定通过不等于答案逐字段事实正确。** 全部 300 次的完整逐项事实复核材料没有在该资料包中公开。51 个站点是历史任务覆盖范围，不是当前整站支持清单；同一题的重复运行也不等于独立新样本。

两组交付判定数量相同，不能宣传“经验提高了通过率”。公开样题之后只适合开发与回归，不能继续承担隐藏泛化测试的证明作用。

查看：[实验正文与统计口径](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/blog.md) · [任务集及判定说明](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/appendix/nl50_task_sample_20260902.md)。

## 三、六对同题对照

历史对照让 EH 与 Browser Use 完成同一道行情和申报文件查询任务。材料中的两边均使用 DeepSeek V4 Pro，关闭经验、交替先手，并使用固定质量门。

公开结果为 EH 6/6、Browser Use 1/6 通过质量门。该门检查完成标记、字段和部分条件，没有完成全部字段的事实核验；双方提示、预算、提交机制和推理档位证据也未完全对齐。因此这是一组固定任务、固定配置的记录，不能单独解释为框架总体能力排名。

查看：[条件与限制](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/appendix/browser_use_comparison_notes_20260907.md) · [逐轮数据](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/appendix/browser_use_comparison_data_20260907.json)。

## 怎样核对这些材料

先读任务、版本、模型与权限条件，再看结果及页面依据，最后核对时间、计量和判定口径。哈希能确认文件版本，不能单独证明答案正确。历史记录中的高风险规则未触发，也不能替代真实高风险场景的专项验证。

原项目的文字、视频及记录署名与权利说明，以 [demo 仓库](https://github.com/Boundprogress/event-horizon-demo/tree/ac0236cd19560efa5f43ba350bbc599ff4158fc4) 为准。当前订阅版的部署、账号权益和运行能力需分别核验。
