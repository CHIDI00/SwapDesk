# SwapDesk: neatHack Build Plan

Prepared for the neatHack team, October 10, 2026

## Overview

SwapDesk is a customer support agent that resolves tickets instead of only answering them. It reads a customer's message, looks up the order and the business's policy, and picks one of four outcomes: resolve the issue, ask the customer a question, deny the request under policy, or escalate to a human with a short summary. When it resolves a ticket, it takes real actions through tools, such as reserving a replacement, creating a return and making a shipping label, and it records each action with an operation ID. If a step times out or fails, it checks what already happened before it tries again, so nothing is done twice. Before it replies, it compares the saved records with what it is about to say. The policy, tools and database form a swappable setup, and an online shoe store is the one we build and demo.

The hackathon scores evidence of reliability more than novelty: the tools, the demo and building in public make up 60% of the score. SwapDesk is built to produce that evidence. Every test ticket has a known correct outcome, so a checker script scores each run, and the failures we inject (a label timeout, a sold-out size, a worker crash) give us a recovery run to show. We run a weak first version on about 30 test cases, read the neatlogs traces, fix what broke, and run again, which gives the before and after numbers the judges ask for. We code through OpenCode with Entire on, so each fix has a checkpoint, and we price the agent per resolved ticket in cfo.ai. The originality score will be low because customer support is a crowded category. We accept that trade for a build we can finish and prove.

## How well SwapDesk fits

SwapDesk fits well, and it is a better version of the plain refund idea. Exchanges involve several actions that change state (reserve stock, create a return, create a label), so duplicate actions and mid-run failures are real problems and not staged ones. That is exactly what the "state" and "recovery" criteria reward. The checker design is also solid.

Three things to fix before building:

1. Cut the scope in layers. Build exchange plus refund-or-deny first. Add the worker-restart failure last, because it is the hardest. If time runs short, drop it and keep the timeout and sold-out failures.
2. Make "the explanation matches saved state" checkable. Have the agent output a structured list of the actions it claims it took, and let the checker compare that list to the database. Do not try to parse the customer reply.
3. Test early that traces survive a crash. If you kill the worker mid-run, check that neatlogs still has the spans up to that point. This is unverified, so test it in the first few hours.

## What the agent does

A customer writes, "These shoes don't fit, I need a size 43." The agent:

1. Looks up the order and the return policy.
2. Decides whether the request is eligible: exchange, refund, deny, or escalate to a human.
3. For an exchange, finds stock, reserves the replacement, creates the return and the label, and records each step with an operation ID.
4. Runs a verification step that checks the saved state against what it intends to tell the customer.
5. Replies with what actually happened.

If a step fails, it checks the operation status before trying again. It never repeats an action blindly.

## Benchmark and numbers

Make about 30 cases: clean exchanges, out-of-window requests, sold-out sizes, duplicate requests, vague tickets, label timeouts, and a mid-run crash.

Track four numbers:

- Completion rate on recoverable cases
- Duplicate-action rate
- Wrongful-action rate
- Cost per case

Save the baseline V1 numbers first, then V2 after the fix.

## How the three tools win points

### neatlogs

- What to do: turn it on in the first commit. Name your runs "v1 baseline" and "v2 fixed."
- Evidence to save: trace links for the duplicate-label failure, the recovery run, and the fixed run, plus the numbers you compared.

### Entire

- What to do: enable it before your first commit and commit through OpenCode. Test one commit right away.
- Evidence to save: a screenshot of the checkpoint for the safe-retry fix.

### cfo.ai

- What to do: sign up now, since the card step can fail. Feed it your cost per case from neatlogs.
- Evidence to save: the business plan file.

One story to build the video around: a failed trace in neatlogs, then a coding-agent session that fixes it (Entire records it), then a clean second run. neatlogs lists an MCP integration, which could let your coding agent read the trace directly. This is unconfirmed for OpenCode, so check in the first hour. If it does not work, paste the trace into the coding agent by hand.

For cfo.ai, build three scenarios: base, growth, and "bad reliability," where retries and duplicates push the cost per case up. That shows reliability is your margin, which is the strongest link between the agent and the business plan. Label the $49 per store per month and $0.50 per extra case pricing as assumptions, not facts.

## Order of work

1. Hour 0 to 1: tool setup and a test commit.
2. Hours 1 to 6: build the mock shop, then the checker, before the agent.
3. Hours 6 to 10: V1 agent and the baseline run.
4. Hours 10 to 24: add the failures, read traces, fix, and rerun.
5. Day 2: cfo.ai plan, a simple screen showing a live run, and repo cleanup.
6. Oct 12 afternoon: record the video, with plenty of time before submission opens at 7 PM IST.

Post on X with #neatHack at about hours 1, 6, 14, 24 and 40. Each post should show a trace or a checker result.

## What to watch

- The demo plan covers 1:40 of agent behavior. The 3-minute video must also explicitly cover neatlogs, Entire and cfo.ai, so plan about 1:20 for the tools.
- If the agent passes everything on run 1, there is no before/after story. Make a few cases hard enough to fail.
- The originality score will be low. The edge is execution evidence, and that is what the time allows.

## PRD: Problem, goals and scope

**Problem.** Support staff spend their time coordinating order history, return policies, inventory and shipping to finish one request. Agents that only chat leave that work undone, and agents that act can double-charge, double-ship or claim success they did not achieve. A customer support agent is only useful if it finishes the job correctly and knows when to stop.

**Product.** SwapDesk is a customer support resolution agent. The core agent is general. The business setup (policy document, tool definitions, database) is swappable. The demo setup is a fictional online shoe store.

**Goals**

1. Resolve eligible tickets end to end with correct state in the database.
2. Recover from tool failures without repeating any committed action.
3. Escalate or ask when it cannot safely resolve, and say so honestly.
4. Produce measurable before and after results, a recovery run, traces, checkpoints and a business plan, as the judges require.

**Non-goals**

- Real payments, real shipping or real customer data.
- A polished chatbot experience. The completed transaction is the product.
- Working for any business. We claim it works on the shoe store and is built so tools and policies can be swapped.
- A second store, unless the first one is finished early. A small second setup with about 5 tickets is a stretch goal only.

**Users**

- Shop customers, who write a ticket in plain language.
- Support staff, who receive escalations with a summary and can see what the agent did.

**Scope for v1**

- One item per request.
- Request types: exchange, refund eligibility, and escalation. Refunds and exchanges are simulated.
- Mock services: orders, sizes and inventory, return rules, shipping labels.

## PRD: Agent behavior

**Workflow**

1. Read the ticket and identify the order and item.
2. Fetch the order and the return policy.
3. Decide the outcome: resolve, ask the customer, deny, or escalate.
4. For an exchange, find stock, reserve the replacement, create the return and create the label. Each action gets an operation ID.
5. Verify: compare saved state with the planned reply.
6. Reply with what actually happened.

**Outcome rules**

- **Resolve** only when the request is within policy and every action is confirmed in saved state.
- **Ask** when the ticket is too vague to act on, such as a missing size or unclear order.
- **Deny** when the request is outside policy, with no action taken and a clear reason given.
- **Escalate** when the agent cannot complete or verify the action, with a short summary for a human.

**Tools**

- `get_order`, `get_return_policy`
- `find_exchange_stock`, `reserve_replacement`
- `create_return`, `create_label`
- `get_operation_status`, `verify_exchange`

**Failure handling requirements**

1. If `create_label` succeeds but the response times out, the agent calls `get_operation_status` and does not create a second label.
2. If the requested size sells out before reservation, the agent rereads stock and offers an allowed alternative. It never changes the size silently.
3. If the worker stops after a reservation, a restart resumes from saved progress and does not reserve twice. This is built last and dropped first if time runs short.
4. Retries are bounded. After the limit, the agent escalates.

## PRD: Verification and metrics

A separate checker script, not the agent, decides whether a run passed. It reads the final database state and asserts:

- The correct order and item were handled, and the request was within policy.
- The replacement size matches the customer's request.
- Exactly one reservation, one return and one label exist for an exchange.
- Inventory never goes negative.
- The agent's list of claimed actions matches the saved state. The agent outputs that list in a structured form so the checker does not have to read the customer reply.
- An ineligible request caused no action.

The test set is about 30 tickets: clean exchanges, out-of-window requests, sold-out sizes, duplicate requests, vague tickets, label timeouts and a mid-run crash. Several must be hard enough that a simple first version fails them.

| Metric | Definition | Why it matters |
|---|---|---|
| Completion rate | Share of recoverable cases ending in the correct final state | Main agent score |
| Duplicate-action rate | Share of runs with more than one reservation, return or label | Safety under retries |
| Wrongful-action rate | Share of ineligible requests where the agent took an action | Safety under policy |
| False-resolution rate | Share of runs where the agent says resolved but the checker disagrees | Trust when unwatched |
| Cost per case | Model and tool cost per ticket from neatlogs | Feeds the cfo.ai plan |

Record V1 and V2 numbers from real runs. No target is set in advance, and nothing is reported that the runs did not produce.

## PRD: Sponsor tool requirements

- **neatlogs:** on from the first commit. Runs are named "v1 baseline" and "v2 fixed." We save trace links for the duplicate-label failure, the recovery run and the fixed run, with the numbers compared.
- **Entire:** enabled before the first commit, with all commits made through OpenCode. We save a screenshot of the checkpoint for the safe-retry fix.
- **cfo.ai:** signed up early because the card step can fail. We model stores times subscription price, case volume times cost per case, support costs and runway, in three scenarios: base, growth and bad reliability. The business plan file goes in the submission.
- **Public evidence:** a public repo with commits dated during the event, and posts on X tagged #neatHack with a trace or checker result in each.

## PRD: Business assumptions

These are assumptions to test in cfo.ai, not facts.

- Price: $49 per store per month including 100 resolved cases, then $0.50 per extra case.
- Cost drivers: model tokens per case, retries, hosting and database, merchant onboarding and support.
- Shipping and refunds are merchant expenses. They are not our revenue or our software cost.
- Reliability is the margin: more retries and duplicates raise the cost per case, which the bad-reliability scenario shows.

## PRD: Risks and open questions

- **Chatbot risk:** the agent becomes a chatbot with decorative tools. The checker must judge the database, not the wording of the reply.
- **No before/after story:** if V1 passes everything, there is nothing to improve. Seed hard cases.
- **Originality:** low, since customer support is crowded. We rely on execution evidence.
- **Unverified:** whether neatlogs keeps spans when the worker crashes, and whether OpenCode can connect to the neatlogs MCP. Both are tested in the first hours.
- **Video time:** the 3-minute video must cover neatlogs, Entire and cfo.ai explicitly, so about 1:20 goes to the tools.
- **Open question:** which model runs the agent, and what cost per case that implies.
