# Historical evidence and review materials

[中文](DEMO_EVIDENCE.md) | English

This page selects capability demonstrations from the EH demo and preserves their experimental conditions, metric definitions, and original review materials. It summarizes historical evidence; these experiments have not been rerun on the current client and service.

All references are pinned to demo commit [`ac0236cd19560efa5f43ba350bbc599ff4158fc4`](https://github.com/Boundprogress/event-horizon-demo/tree/ac0236cd19560efa5f43ba350bbc599ff4158fc4). The original videos and records remain in that repository. They are not rewritten or rescored here.

## 1. Six consecutive tasks on a custom test site

On September 21, 2026, the project ran six consecutive tasks on its own site using fixed synthetic data. The driver model is identified in the materials as DeepSeek V4.1 Flash, with OpenCode 1.17.13 as the host at the high setting. The run used a frozen version plus four page-reading fixes. The site had no accounts, payments, or real bookings.

| Task type | Action sequence demonstrated |
| --- | --- |
| Dashboard | Read several statistics, then open and read an explanatory dialog |
| Products | Filter categories and new items, sort prices, open details and related materials |
| Departures | Filter routes, sort fares, and read schedule and available-seat fields |
| Conditional query | Combine date, origin, destination, time window, price, and available-seat conditions |
| Notices | Navigate pages, locate a specified item, follow a related product, and check fields |
| Venues | Read a change notice first, then normal information and related items |

The public materials report **51 actions, 384.3 seconds of combined driver time across the tasks, and 43 delivered items matching the test data source**. The full recording is 492 seconds long and includes intervals for entering tasks, preparation, and restatement. These two time measures must not be conflated.

The project published the review sheet without naming an independent reviewer. This page adds no third-party human review. This one run on synthetic sites cannot establish general performance on real websites.

Review: [run and environment description](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/README.md) · [continuous recording](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/testsite_live_0921_2k.mp4) · [six task results](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/results.md) · [43-item review sheet](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/REVIEW_SHEET_testsite_live_0921.md) · [machine-readable summary](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/summary.json).

## 2. Fifty tasks, 300 runs

The project used 50 task prompts, repeating each three times without experience and three times with experience, for 300 runs in total—not 300 distinct tasks. The driver model is identified in the materials as DeepSeek V4 Flash, run through OpenCode. The records state that no human took over during the runs.

| Public metric | Without experience | With experience | Total and meaning |
| --- | ---: | ---: | --- |
| Ended with a record | 150/150 | 150/150 | All 300 runs have end records |
| Passed the original frozen delivery check | 149/150 | 149/150 | 298/300 under the criteria fixed at the time |
| Sites involved | 46 | 45 | A union of 51 sites after normalization by main domain |

**Passing a delivery check does not mean the answer is factually correct field by field.** The package does not publish a complete item-by-item factual review of all 300 runs. The 51 sites describe historical task coverage, not a current list of fully supported sites. Repeating a task also does not create independent new samples.

Both groups passed the same number of delivery checks, so these results do not support a claim that experience increased the pass rate. Once the task examples are public, they are suitable for development and regression checks, but no longer establish performance on hidden generalization tests.

Review: [experiment report and metric definitions](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/blog.md) · [task set and delivery criteria](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/appendix/nl50_task_sample_20260902.md).

## 3. Six paired runs of one task

This historical comparison asked EH and Browser Use to complete the same market-data and filing-query task. Both sides used DeepSeek V4 Pro according to the materials, with experience disabled, alternating which ran first, and a fixed quality gate.

The public results report that EH passed the gate in 6/6 runs and Browser Use in 1/6. The gate checked completion markers, fields, and some conditions; it did not fact-check every field. Evidence of parity in prompts, budgets, submission mechanisms, and reasoning settings was also incomplete. This is a record of a fixed task under fixed configurations and cannot establish an overall framework ranking.

Review: [conditions and limitations](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/appendix/browser_use_comparison_notes_20260907.md) · [per-run data](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/appendix/browser_use_comparison_data_20260907.json).

## How to review these materials

Start with the task, version, model, and permission conditions. Then examine results and page evidence, followed by time, usage, and evaluation definitions. A hash can identify a file version; it cannot by itself prove an answer correct. High-risk rules remaining untriggered in historical runs do not replace dedicated tests of real high-risk scenarios.

Refer to the [demo repository](https://github.com/Boundprogress/event-horizon-demo/tree/ac0236cd19560efa5f43ba350bbc599ff4158fc4) for attribution and rights statements covering the original text, videos, and records. The current service's deployment, account access, and runtime capabilities need separate verification.
