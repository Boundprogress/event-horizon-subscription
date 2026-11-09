# Event Horizon · Browser Automation for AI Agents

[中文](README.md) | English

**Zero site-specific rules. Let your agent operate the browser, check results, and deliver the task.**

Event Horizon (EH) connects your existing AI agent to **browser automation and web automation over MCP (Model Context Protocol)**: search, click, fill forms, filter and sort, navigate pages and details, then return extracted results and page evidence to your agent. There are zero site-specific rules to author. You describe the task; your agent plans it; EH supplies page information, executes actions, and returns their status.

Chrome runs locally; page samples are sent to the cloud for processing. You choose your model and agent. **Zero site-specific rules** means users do not need to write selectors or click scripts for each site when using the general browser workflow. It does not mean every website or task will succeed. See [capabilities and limits](docs/CAPABILITIES.en.md).

Version: `0.27.1-lab.20261109.1`. This repository contains a thin client built with the Python standard library, including a local console, browser connector, and MCP skill. New accounts automatically receive 1,000 free trial frames when registration succeeds.

Start the client directly after extracting the package. See the [user documentation](docs/README.en.md). The local console supports **Chinese and English**; use the language switch to select your preferred interface language.

## Public testing and free trial

**EH is currently in public testing. New accounts automatically receive 1,000 free frames when registration succeeds, without an email request or activation code.** This is a one-time total allowance with no expiry. It does not reset monthly, and usage stops when the balance is exhausted.

Check your actual remaining balance and access status on the client's account page. If you have a permanent-frame activation code, you can redeem it there to add frames. Your own model, agent host, or other third-party services may incur separate charges.

This test version may produce errors, interruptions, or incomplete results. It does not guarantee completion on any particular website or task. Test only within your authorized access and action scope, manually check important actions and outputs, and read the service agreement displayed in the client. This notice does not affect any liability that cannot lawfully be excluded or limited.

## Three core capabilities

| Capability | What it means for your task |
| --- | --- |
| **Zero site-specific rules** | Use the same tools across sites without writing selectors or fixed click scripts for each one. The usable scope of each page still needs to be tested. |
| **Real browser actions** | Search, click, fill forms, filter, navigate pages, and handle dialogs on the actual website. Action receipts and page state help you check blocked or unconfirmed operations. |
| **Results you can check** | Your agent organizes lists, fields, and sources into an answer, states what is complete and what is missing, and can check an unconfirmed request using its original ID. |

Use a host that can load local MCP tools, with your own model and agent. The dedicated browser retains login state that a website allows to persist; expiry and re-verification remain subject to that website.

**A successful click is one step; the task result is what matters.** EH gives your agent page state and action receipts to help it choose the next step. The objects, fields, counts, and sources in the final answer still need to be checked individually.

If a task is blocked or its result is unconfirmed, the agent should explain the blockage and missing items, then check the status before choosing its next step.

## Tasks to give your agent

- **Queries with multiple conditions:** enter dates, locations, or price limits; filter and sort; open details; and organize matching items.
- **Data extraction across pages:** find specified notices through pagination, follow related pages, and collect fields with their sources.
- **Form filling:** fill authorized inputs, check current values and page feedback, then decide whether to proceed.
- **Comparing information across sites:** bring together prices, times, or conditions from different pages and return a comparison supported by sources.

These are examples of how to describe tasks. Completion depends on the website, model, and authorization scope. For large-scale web scraping of a fixed structure, also consider official APIs or authorized data interfaces.

## Capabilities and public demos

EH supports page structure reading, condition entry, filtering and sorting, pagination and details, dialogs, and related pages. Your agent decides what comes next. The demo's six consecutive tasks show combinations of these interactions on synthetic sites with a particular driver configuration. See the [task descriptions and review materials](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/video/testsite_live_0921/README.md). Historical demos do not guarantee delivery on current websites.

The [EH demo repository](https://github.com/Boundprogress/event-horizon-demo) preserves historical experiments, videos, and failure records. [Historical evidence and review materials](docs/DEMO_EVIDENCE.en.md) distinguish a completed run, a delivery check, and field-by-field factual verification so you can assess results under their original conditions.

## Choosing Browser Use (browser-use / browseruse), Playwright MCP, or other tools

Your integration, target pages, and result requirements determine whether a browser automation tool fits your task. Start with three checks: can it work with your existing agent, does changing sites require script maintenance, and can the returned result be checked against page evidence?

EH focuses on **zero site-specific rules, real browser actions, and results you can check**. It connects to your agent over MCP and performs website tasks in local Chrome. For the shared discussion background and EH's product choices, see [from browser actions to verifiable delivery](docs/BROWSER_USE_COMPARISON.en.md).

## Get started

Run these commands in the extracted directory containing `eh.py`.

You need Python 3.10+, Chrome, and an agent that can access local files and load MCP tools.

```sh
git clone https://github.com/Boundprogress/event-horizon-subscription.git
cd event-horizon-subscription

python3 -I -S -B eh.py start
```

In Windows PowerShell, use:

```powershell
py -3 -I -S -B eh.py start
```

If your system only provides the `python` command, run `python -I -S -B eh.py start`.

You do not need `pip install .`. Startup opens the local console; keep the terminal running. Select **English** in the console's language switch if needed.

1. Read the service agreement and register an account. Verify your email so it can be used for account recovery.
2. Registration automatically grants a one-time total of 1,000 frames. Check it on the account page. The allowance has no expiry or monthly reset; usage stops when the balance is exhausted.
3. Prepare local setup, then connect the browser.
4. Copy the setup instruction and give it to a trusted local agent.
5. Wait for the agent to actually check the tools and connection before giving it a task.

You do not need to choose a host product in the console. Copying the instruction only prepares local materials; the connection is ready once the host has successfully loaded them. Do not paste API keys or device credentials into chat. Service availability, compatible versions, trial allowance, and access status are subject to operational announcements and the actual account display.

## After connecting

View task results in your current agent. Check unconfirmed operations using the original request ID instead of submitting them repeatedly. Important actions require explicit authorization, and results still need to be checked against the page.

The registration allowance is a one-time total of 1,000 frames. The account page shows your actual remaining balance and access status. If you need more frames, redeem a permanent-frame activation code to add to the balance. If access is unavailable, email operations for assistance.

Public HTTP(S) sites do not require an exact allowlist, but sensitive sites and private-network destinations are restricted. The browser runs locally while page samples still pass through the cloud. Read the service agreement in the console first.

The client does not automatically save or replay task-content history. Server-side content is available only for bounded, temporary delivery. You manage any explicit exports, agent conversations or files, browser profiles, and downloads. Runtime data and credentials are stored outside the source directory; do not commit `launch.json`, keys, or device files.

Use your verified email address to recover your account or password. If your account is restricted, use the account appeal page to submit an explanation and check the result.

## Updating and exiting

End the current EH session, disconnect the dedicated browser, exit the console and the host's EH tool connection, then obtain a version confirmed by the publisher. Preserve your own uncommitted changes. Restart and reload the EH connection after updating. Closing a web tab does not exit the client; Ctrl-C in the terminal also requests a normal shutdown.

The skill is in [skills/eh-subscription-browser/SKILL.md](skills/eh-subscription-browser/SKILL.md) and is prepared by the setup-instruction flow. The skill does not replace MCP configuration or the browser connection.

`CLIENT_MANIFEST.json` checks whether files have changed; it is not proof of publisher identity or a signature. Run a local file audit with:

```sh
python3 -I -S -B client.py audit --package-dir . --json-only
```

## Contact and feedback

Email [eventhorizontest@163.com](mailto:eventhorizontest@163.com). Include your version, error code, and sanitized reproduction steps. Do not send passwords, verification codes, keys, device credentials, or private page content.

## License

The code is licensed under the **GNU Affero General Public License v3.0 only (AGPL-3.0-only)**; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Third-party materials retain their respective licenses. Use of the online service is separately governed by the service agreement displayed in the console.

For private local deployment inquiries, contact [eventhorizontest@163.com](mailto:eventhorizontest@163.com).
