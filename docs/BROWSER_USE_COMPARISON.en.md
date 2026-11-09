# From browser actions to verifiable delivery

[中文](BROWSER_USE_COMPARISON.md) | English

**Zero site-specific rules · Real browser actions · Results you can check**

Browser automation is valuable when the user receives the requested result: finding the target, setting conditions, opening details, and bringing back the required fields and sources.

## Shared background from existing discussions

Past public discussions in the Browser Use community have covered action feedback, session continuity, and result verification. These provide shared background for browser automation in practice. Its [official output documentation](https://docs.browser-use.com/open-source/customize/agent/output-format) also distinguishes a task ending from the agent reporting success, and advises checking important external outcomes.

The basic requirements used here are: **actions return feedback, results have supporting evidence, and unfinished work is explained.** These historical discussions do not establish how the current version of Browser Use performs. Test actual capability with the relevant version, model, configuration, and tasks.

## What experience does EH provide?

EH gives an existing AI agent browser tools. You describe the goal and conditions; the agent chooses the next step from the current page, then returns status, page evidence, and organized results to your current conversation.

| Your need | EH's workflow |
| --- | --- |
| **Change sites with less rule maintenance** | Zero prewritten site rules: users do not write selectors or fixed click scripts for each site. The same tools work across pages. |
| **Perform real website actions** | Search, click, fill forms, filter and sort, navigate pages and details, and interact with dialogs. Actions return receipts and subsequent page information. |
| **Receive results you can check** | The agent organizes the requested objects, fields, counts, and sources, checking action progress separately from the final answer. |
| **Know where a blocked task stopped** | When a target cannot be operated or a result is unconfirmed, explain the status and missing items. Check the original request ID before continuing or returning control to the user. |
| **Keep your existing tools and login state** | Connect over MCP to an agent that can load local tools. Dedicated Chrome retains login state that a website allows to persist. |

These are EH's product priorities. Your agent still plans the task, chooses actions, and organizes the answer.

## Choose with a real task

If you are evaluating Browser Use, Playwright MCP, or another browser automation tool, start with a task that has explicit result requirements—for example, “filter items by date and price, open details to check the fields, and include sources.”

Check four practical questions:

1. **Can it connect?** Can the host load the tools, and is the browser connected?
2. **Can it act?** Can it read the target page, and are the required controls usable?
3. **Can it deliver?** Does the result meet the requirements for objects, fields, counts, and sources?
4. **Is continued use worthwhile?** Are elapsed time, model charges, service usage, and manual review effort suitable?

Evaluate the combined experience on your own pages and tasks. [Public testing and free trial](../README.en.md#public-testing-and-free-trial) · [Start and connect](../README.en.md#get-started)

## Limits to understand before use

- **Zero site-specific rules describes the workflow:** users do not write rules for each site. Page changes, complex controls, Canvas, login verification, and access restrictions can still affect completion.
- **Local browser, cloud processing:** Chrome runs locally, while page samples must be sent to EH in the cloud. EH is currently in public testing. New accounts automatically receive a one-time total of 1,000 free frames on successful registration, with no expiry or monthly reset. Usage stops when the balance is exhausted.
- **Results still need acceptance checks:** action receipts, task delivery, and factual correctness of every field require separate checks. They cannot stand in for one another.
- **Understand the record scope:** the client does not automatically save or replay task-content history. Checking an original request ID is different from long-term historical replay.

See [capabilities and workflow](CAPABILITIES.en.md) for scope and the [FAQ](FAQ.en.md) for usage questions. [Historical public demos](DEMO_EVIDENCE.en.md) retain their own versions, samples, and verification conditions; they do not guarantee results on current tasks.
