# EH usage and capabilities: frequently asked questions

[中文](FAQ.md) | English

This page adapts common questions from the demo for the current client. To check historical numbers, see the [historical evidence](DEMO_EVIDENCE.en.md). Older statements about test access, installation, screenshots, and licensing in the original [demo Q&A](https://github.com/Boundprogress/event-horizon-demo/blob/ac0236cd19560efa5f43ba350bbc599ff4158fc4/QA.md) do not directly apply to this version.

## Are these prerecorded click scripts for each task?

In the public demos, the driver model chose its next step from the page at that moment. The same task could follow different paths. The current client provides tools to your own agent over MCP; the agent remains responsible for the goal, planning, and decision to stop.

This does not mean every site works without further adaptation. Page structure, control semantics, complex interactions, and frontend changes can still affect results and need testing.

## Does zero site-specific rules mean every website will work?

No. It means users do not need to write selectors, page templates, or click scripts for each site when using the general browser workflow. The agent chooses its next step from the current page and task.

Not needing prewritten rules is separate from whether a page can be read, a control can be operated, or a task can be completed. Canvas, complex controls, login verification, and access restrictions can still interrupt a task. Test your specific tasks.

## How should I choose between EH, Browser Use (browser-use / browseruse), and Playwright MCP?

Start with your host, target pages, and delivery requirements, then use real tasks to assess connection, actions, results, and cost. EH focuses on zero site-specific rules, keeping your own agent through MCP, and checking action status separately from final results.

Past community discussions about action feedback and result verification provide shared background here. See [from browser actions to verifiable delivery](BROWSER_USE_COMPARISON.en.md) for EH's product choices.

## Does it read screenshots or page structure?

The agent primarily receives visible content, page layout, and control state organized by EH. Screenshot OCR is not the primary input. Website implementations and control changes can still affect results.

The online service's current default runtime path has page screenshots disabled. Interpret the demo's historical recordings, page evidence, and capture settings according to each experiment's materials.

## Which tasks suit it best?

Authorized tasks with clear goals and constraints, such as queries with multiple steps, filtering, reading lists and details together, form interactions, and organizing information across sites. The six-task live demo gives examples of pagination, sorting, dialogs, and related-page navigation.

For repeated extraction at scale from a fixed site, an official API or authorized data interface may fit better. Each page read and model decision adds overhead; one demo cannot establish speed or cost across all tasks.

## Will a different model or local model work equally well?

The integration protocol is reusable, but model capability, the host environment, prompts, budgets, and stopping strategies all affect delivery. The host must be able to access local files and load MCP tools. Test the usable scope of smaller models and different environments separately.

## How do execution success, a passed delivery check, and factual correctness differ?

Execution success means the corresponding action received an execution receipt. Passing a delivery check means meeting a particular set of delivery criteria. Factual correctness still requires checking the page, sources, counts, dates, and other requirements individually. These are different conclusions; a run's end record or a model saying “done” cannot stand in for all of them.

If a result is uncertain, check its current status using the original request ID. Do not repeat the operation under a new ID.

## Which scenarios cannot be promised to work?

Content inside Canvas, icons without reliable semantics, complex dynamic controls, virtual scrolling, and changes in login or CAPTCHA state can cause gaps or interruptions. EH does not provide a way to bypass login, CAPTCHAs, access restrictions, or platform rules.

Read-only query demos do not establish complete protection for every transaction, payment, deletion, authorization, or prompt-injection scenario. Task authorization and current product restrictions always apply.

## Does page data stay on my computer? Is there task history?

The browser runs locally, but page samples must still be sent to EH in the cloud for processing. The current client has no task-history page and does not automatically save or replay task-content history. Server-side content is available only for bounded, temporary delivery. Request-status retrieval by original ID and minimal deduplication metadata remain available.

You manage your agent's conversations, explicit exports, and browser data. See the “EH 订阅服务使用协议” displayed inside the client for the specific scope.

## Can I switch the client interface to English?

Yes. Use the **中文 / English** language switch in the local console. The interface supports both languages. The service agreement remains in its original language; switching the interface does not replace the agreement with a translation.

## Will website login state survive closing and reopening the browser?

On the same computer, the same EH account and service address reuse a dedicated browser profile directory. Persistent cookies and local storage saved by websites remain after a normal disconnect or exit. When you connect again, login state that has not expired can be reused. Different EH accounts have separate profiles; they do not share your everyday Chrome profile or sync across computers.

The browser's debugging port is still assigned dynamically by the system. This does not affect login data in the profile directory. Continued login depends on the website's expiry, session, and security policies. A login valid only for the current browser session may require verification again after reopening.

Upgrades from 0.25.4 or earlier do not automatically merge older temporary browser directories. Sign in to websites again the first time; the account's dedicated profile is retained afterward. Keep using your existing data directory when updating the client. Changing the data directory creates a new browser profile. Signing out of EH does not delete saved website login state.

## How do I get the free trial allowance?

EH is currently in public testing. New accounts automatically receive **1,000 free frames** when registration succeeds, without an email request or activation code. This is a one-time total allowance with no expiry. It does not reset monthly, and usage stops when the balance is exhausted.

Check your actual remaining balance and access status on the client's account page. If you have a permanent-frame activation code, redeem it there to add frames. For unexpected balance or access issues, contact [eventhorizontest@163.com](mailto:eventhorizontest@163.com). The test version may produce errors or interruptions; important actions and outputs still need manual checking. Your own model, host, or other third-party services may incur separate charges. Read the service agreement displayed in the client first.

## How do I confirm that the client has exited?

After you choose to exit the client, the page first shows cleanup progress and then waits for the local console to shut down. It reports that the client has exited only after receiving the cleanup-complete receipt and observing console shutdown. You can then close the page or restart; account data and website login profiles are retained.

If the page says the console has closed but browser shutdown is unconfirmed, restart the client and check the exit status in connection diagnostics. If the exit result is unconfirmed, check the launch terminal and old client processes first. An unresponsive page alone does not prove a successful exit. The exit page stops polling; after restarting, use the new page opened by the launcher.

## The work browser is closed, but its exit is still awaiting verification. What should I do?

After updating, keep your existing data directory, open connection diagnostics, and choose the option to verify exit and restore the connection. The client checks the old connector, browser processes, and profile directory. Once exit is confirmed, it removes the connection restriction. Return to the overview and connect the browser again. Tasks are not automatically replayed; your account, credentials, and website login profile are retained.

If verification fails, close the old EH work browser and stop any old EH client connection still running, then verify again. If it still fails, preserve the data directory and provide the diagnostic summary. Do not delete the profile directory or manually edit cleanup state.

An agent reporting successful session finalization describes the task's submission status. It does not mean the browser process has shut down normally. Passing a local configuration check does not replace exit verification either.

## The browser closes immediately, or I cannot connect after changing computers. What should I do?

Start with connection diagnostics. If the cloud rejects the connection, device credentials may have been reissued on another computer, or another instance of the same account may still be connected. Stop EH browser connections on other computers before trying again locally.

If you intend to use this computer instead, explicitly choose the option to reissue local device credentials in diagnostics. Reissuing invalidates older device credentials saved on other devices and requires confirmation. Signing in or reissuing an API key does not restore device credentials at the same time. Downloading the client again also continues to use existing local account data.

Passing local configuration and network checks does not prove device authentication or browser connection success. After credentials are reissued, you must still connect the browser and wait for the connected state. If a response is unconfirmed, follow the prompts to check it instead of repeatedly reissuing credentials.

## How can I discuss private deployment or enterprise workflows?

Email your environment, model integration, target sites, network and data boundaries, action authorization, and desired delivery scope so the specific requirements can be discussed. Historical exploration of an office-automation sandbox shows only that those paths were explored; it does not mean all enterprise workflows are verified today.

Contact [eventhorizontest@163.com](mailto:eventhorizontest@163.com). See [LICENSE](../LICENSE) for the code license. Online service conditions and the code license apply separately.
