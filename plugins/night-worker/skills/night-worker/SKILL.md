# Night Worker

Automate long-running overnight tasks. Use this skill when the user wants to
set up, monitor, or manage batch jobs that run while they are away.

## Capabilities

- Queue a list of tasks to run sequentially or in parallel
- Monitor running background processes and report status
- Retry failed tasks with exponential backoff
- Summarize results when the user returns

## Usage

Trigger: The user asks to "run overnight", "batch process", "queue up work",
or wants to schedule tasks for unattended execution.

## Instructions

1. Gather the list of tasks from the user.
2. Validate each task can run non-interactively (no prompts, no GUI).
3. Execute tasks using background processes, capturing stdout and stderr.
4. On failure, retry up to 3 times with exponential backoff (2s, 4s, 8s).
5. Write a summary report to `night-worker-report.md` when all tasks complete.
6. If the user returns mid-run, provide a live status overview on request.
