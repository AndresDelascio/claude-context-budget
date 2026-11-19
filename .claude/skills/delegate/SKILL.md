---
name: delegate
description: Hand one focused job to a subagent on the cheapest model that fits, with a short brief. Use when the user types /delegate.
argument-hint: "[haiku|sonnet|opus] <job>"
---

# Delegate one job

The job: $ARGUMENTS

Hand this job to ONE subagent. Do not do the job yourself, and do not change the model of this conversation.

## 1. Pick the model

If the job starts with `haiku`, `sonnet` or `opus`, use that model and drop the word from the job.
Otherwise pick the first row that fits:

| Job | Model |
|---|---|
| Find, list, count, look up, read and summarize, run a command and report | haiku |
| A well-specified edit, writing tests or docs, a refactor with a clear target | sonnet |
| Hard debugging, design, or a job where a wrong answer is costly | opus |

Never let the subagent inherit this conversation's model by default. If no row fits, use sonnet.

## 2. Write the brief

The subagent knows nothing about this conversation. Give it, in under 200 words:

- **Goal:** one sentence.
- **Where:** the files or folders to read, by path. Do not paste their contents.
- **Already known:** what is ruled out or decided, so it does not redo it.
- **Done when:** the check that shows the job is finished.
- **Reply:** at most 15 lines, the answer first, with `file:line` for every claim about code.
- **Limits:** do not start other agents. Change only the files named above. If the job is read-only, say so.

## 3. Run it

Start one subagent with the Agent tool, with `model` set to the model you picked and the brief as its prompt.
Wait for its reply. Do not run the same job yourself in the meantime.

## 4. Check, then report

The reply is a report, not proof. Open one or two of the `file:line` references, or run the check from "Done when".
Then tell the user, in this order:

1. The answer.
2. `Ran on: <model>.` and what you checked.
3. Anything the subagent could not do.
