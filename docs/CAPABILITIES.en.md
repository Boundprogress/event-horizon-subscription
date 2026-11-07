# EH browser automation: actions, checks, and delivery

[中文](CAPABILITIES.md) | English

EH provides browser automation and web automation tools to AI agents over MCP: read pages, search and click, fill forms, filter and navigate, then return action status and page evidence to the agent. The model understands the task, plans, and chooses the next step; EH supplies current page information and executes browser actions.

## What does zero site-specific rules mean?

When using the general browser workflow, users do not need to write selectors, page templates, or fixed click scripts for each website before their agent attempts a task from the current page. The same tools carry over to another site, letting you focus on what to find, which constraints matter, and how to check the result.

This describes the workflow, not a website success-rate guarantee. Controls, access restrictions, and model decisions can still cause failures. No prewritten site rules does not mean no task description, authorization, or acceptance checks.

## How the capabilities appear in tasks

| Capability | How you can use it | Example from the public demo |
| --- | --- | --- |
| Page structure reading | Read text, fields, lists, and interactive objects by section | Read dashboard statistics, then open an explanatory dialog |
| Filtering and sorting | Enter conditions, switch options, sort, and check the result | Filter product categories and new items; find a target by price |
| Forms with multiple conditions | Combine dates, locations, time windows, numbers, and checkboxes | Query a route, departure time, fare limit, and available seats |
| Pagination, details, and related pages | Open details from a list and continue to related objects | Find a notice through pagination, then check fields on a related product |
| Dynamic page changes | Handle dialogs and new pages, then decide from the updated state | Read a schedule-change notice before collecting normal opening hours |
| Information across sites | Put information from different sites into one problem with constraints | Check transfer and arrival times after querying flights and trains |

These task types have appeared in public runs. See [historical evidence and review materials](DEMO_EVIDENCE.en.md) for the specific conditions and results. They do not guarantee completion on any website.

## The action loop

1. Read the current page's structure, layout, and control state to give the agent current information.
2. The agent chooses a target and action based on the goal and constraints.
3. Check the relevant conditions before execution. Return a status the agent can inspect if the target is stale, not editable, or blocked.
4. Return the action receipt and subsequent page information so the agent can continue, read the page again, narrow its conclusion, or stop.

When a target cannot be operated, access is restricted, or the result is unconfirmed, explain the blockage and unfinished work to the user. Before continuing, check the current page and authorization. Check an unconfirmed request using its original ID.

Page redesigns, dialog changes, and scrolling can all change which objects are available. An old reference should not be reused just because it was clicked previously. Action completion, task delivery, and correctness of every result field require separate checks.

## From actions to results you can check

Tell your agent which objects, conditions, and fields you want delivered—for example, “filter departures for this date, then list the times, prices, and sources.” An explicit result helps guide search, filtering, and detail checks.

- **Actions:** check action receipts and page feedback to establish current progress.
- **Delivery:** receive the organized answer or extracted content in your current agent. Check unconfirmed requests using their original IDs.
- **Acceptance:** check objects, counts, fields, dates, and sources against the pages. State missing or uncertain items explicitly.

EH provides page information and execution status throughout this process. Your agent still organizes the answer. Receiving a result and establishing that it is entirely correct are different conclusions.

## Suitable uses

- Queries, filtering, forms, and research that mix several sites or interaction types.
- Tasks with explicit requirements for sources, counts, fields, or timing between steps.
- Workflows that need to adapt to real page changes and stop to check unconfirmed results.

For large-scale extraction of a fixed structure from one site, an official API or authorized data interface is often more direct. EH's interactive reading and model decisions both add overhead. A few demos cannot establish speed or cost across all tasks.

The local console supports Chinese and English through its language switch. Your choice of interface language does not change the task's authorization or the scope of its acceptance checks.

## Limits to test first

Content inside Canvas, icons without recognizable semantics, complex linked controls, virtual scrolling, and changes in login or CAPTCHA state can all interrupt tasks. These are not presented as generally solved capabilities. After changing your model or host, re-test planning, stopping, and delivery quality.

Action permissions and restrictions on sensitive sites and private networks remain in effect. Results from public, read-only tasks do not establish complete protection for transactions, deletion, payment, authorization, or prompt-injection scenarios.

The current client does not provide a task-history page or automatically save or replay task-content history. An agent can still check an operation's status using its original request ID. This is separate from the experimental materials preserved in the demo repository.

For the shared background of browser automation discussions and EH's product choices, see [from browser actions to verifiable delivery](BROWSER_USE_COMPARISON.en.md).

## Sources

This page draws on current client interfaces and the demo's public mechanisms and task descriptions. Historical materials are pinned to demo commit [`ac0236cd`](https://github.com/Boundprogress/event-horizon-demo/tree/ac0236cd19560efa5f43ba350bbc599ff4158fc4): [Q&A](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/QA.md) and [experiment report](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/blog.md). Refer to the originals for historical models, environments, and authorization scopes.
