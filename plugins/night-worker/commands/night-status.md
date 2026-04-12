# /night-status

Show the current status of queued night-worker tasks.

When invoked, check for any running background processes started by the
night-worker plugin and report:

- Number of tasks completed vs remaining
- Current task name and elapsed time
- Any failures encountered so far

If no tasks are running, report that the queue is empty.
