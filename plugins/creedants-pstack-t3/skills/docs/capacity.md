# Capacity of this machine

Forty idle Haiku agents fit on this host on 2026-10-05, with 5.9 GiB of memory still available. A rerun later that morning held forty Haiku agents again and ran four copies of this repo's build and unit suite. Each copy completed one passing iteration during the sample window. A heavier follow-up, four copies of the unit suite with no pause, also completed one passing iteration per copy. Swap, load, and the root HTTP probe stayed inside the stop lines. Both runs stopped because the plan stopped, with memory still available.

## Hardware

The CPU is an AMD Ryzen 7 7735HS, 8 cores and 16 threads, with a max clock of 4830 MHz. `nproc` is 16.

MemTotal is 27421264 KiB, 26.2 GiB. The 2026-10-04 estimate calls this machine 26 GB of RAM. SwapTotal is 54842712 KiB, 52.3 GiB.

The machine had been up for about 2 days at both baselines.

## What was measured

`scripts/measure_capacity.py` prints one TSV row per sample. It uses the Python standard library only.

Memory used is MemTotal minus MemAvailable, in KiB. MemAvailable is what the kernel will give a new allocation without swapping. Swap used is SwapTotal minus SwapFree. `load1` is the first field of `/proc/loadavg`. `psi_full_avg10` is the 10-second full memory-stall average from `/proc/pressure/memory`.

The responsiveness probe is one HTTP GET of `/` on 127.0.0.1. It measures that root HTML response only. It does not measure any other T3 operation. The process is the `t3code` command line that contains `bin.mjs` and does not contain `acp-mcp-bridge`. On these runs the port was 3773. `probe_ok` is 1 when the status is 200 and the body starts with `<!doctype html>`. The timeout is 5 seconds.

`sessions` counts a live process from the NUL-separated arguments in `/proc/<pid>/cmdline`. The basename of argv[0] is `grok` and argv[1] is `agent`, or the basename of argv[0] is `claude` and a later element is `--model` or begins with `--model=`. An argv[0] value that contains whitespace has no argument boundary, so it does not count. `claude-desktop` and the `codex` app-server hosts do not match those basenames. A shell whose script text only mentions these words counts zero.

`build_procs` counts a Python process whose argv[1] is `scripts/build.py` or a path ending in `/scripts/build.py`, or whose argv[1] is `-m` and argv[2] is `unittest`. A direct exec of that build script counts too. A shell whose script text only mentions those strings counts zero. The count shows that those processes existed. Exit status in the loop log is what shows that an iteration passed. The idle-ramp table is the exception. Its `sessions` and `build_procs` cells came from the older substring counter, which that section names.

Each official step is five samples, five seconds apart.

```bash
python3 skills/landing/scripts/land.py slot --exclusive -- python3 scripts/measure_capacity.py --label <name> --samples 5 --interval 5
```

The exclusive slot holds every governor slot for the duration of that command, so other governed builds and tests wait. `load1` is a one-minute average, so five samples inside one minute are not five independent load readings. The median is the summary.

Stop a ramp when swap used exceeds half of swap total, or when a probe fails or takes longer than 2000 ms. A step is past the line this run treated as degradation when MemAvailable drops under 1 GiB, when `load1` exceeds 16, or when the probe median is both over 100 ms and over five times the baseline median.

## Idle agents on the first ramp

The agents were T3 child tasks on provider `claudeAgent`, model `claude-haiku-4-5`, with thinking set to false. The catalog also has Cursor `gpt-5.4-nano` with reasoning `none`. This measurement used Haiku, because the Claude driver was already starting sessions on this host.

The pilot was asked to run `sleep 2400` and to do nothing else. The harness refused a standalone sleep. The Claude process stayed after the turn ended. The other 39 were asked to reply with the single word idle and not to use tools. Their processes stayed too. Samples for 10, 20, and 40 started about 60 seconds after the new processes were up.

The baseline already included other work. Workers were running in the `pstack-t3-d1` and `pstack-t3-d2` worktrees. The baseline `sessions` value is 8. After the baseline, the background session count dropped by one and held. The later counts are 17, 27, and 47, which is that background plus 10, 20, and 40 Haiku processes.

Those `sessions` and `build_procs` cells were produced by an older counter that searched the command text for substrings. The memory, swap, load, and probe columns are kernel and HTTP readings, and a review checked their arithmetic. The idle-10 row whose `build_procs` cell is 2 is a substring match. It is not evidence that a build ran. The first attempt's four-loop rows are omitted here. That counter could not show that the loops were the processes it counted, and the loops left no exit status.

```
label	ts	mem_used_kib	mem_available_kib	swap_used_kib	swap_total_kib	load1	probe_ms	probe_ok	probe_port	sessions	build_procs	psi_full_avg10
baseline	2026-10-05T01:57:06Z	16008772	11412492	2276392	54842712	1.67	0.7	1	3773	8	0	0.00
baseline	2026-10-05T01:57:11Z	15927416	11493848	2276392	54842712	1.70	1.5	1	3773	8	0	0.00
baseline	2026-10-05T01:57:16Z	15900124	11521140	2276392	54842712	1.64	4.9	1	3773	8	0	0.00
baseline	2026-10-05T01:57:21Z	15949180	11472084	2276392	54842712	1.51	1.7	1	3773	8	0	0.00
baseline	2026-10-05T01:57:26Z	15955284	11465980	2276392	54842712	1.47	1.7	1	3773	8	0	0.00
idle-10	2026-10-05T02:00:49Z	17459968	9961296	2318492	54842712	1.76	0.7	1	3773	17	0	0.00
idle-10	2026-10-05T02:00:54Z	17494056	9927208	2318492	54842712	2.02	2.1	1	3773	17	0	0.00
idle-10	2026-10-05T02:00:59Z	17511608	9909656	2318492	54842712	1.86	1.6	1	3773	17	0	0.00
idle-10	2026-10-05T02:01:05Z	17468356	9952908	2318492	54842712	1.79	56.5	1	3773	17	0	0.00
idle-10	2026-10-05T02:01:10Z	17434496	9986768	2318492	54842712	1.65	1.6	1	3773	17	2	0.00
idle-20	2026-10-05T02:02:59Z	18916076	8505188	2382888	54842712	1.56	1.7	1	3773	27	0	0.00
idle-20	2026-10-05T02:03:04Z	18941104	8480160	2382888	54842712	1.44	1.5	1	3773	27	0	0.00
idle-20	2026-10-05T02:03:09Z	18932912	8488352	2382888	54842712	1.32	1.3	1	3773	27	0	0.00
idle-20	2026-10-05T02:03:14Z	18854256	8567008	2382888	54842712	1.22	1.7	1	3773	27	0	0.00
idle-20	2026-10-05T02:03:19Z	18879136	8542128	2382888	54842712	1.12	2.1	1	3773	27	0	0.00
idle-40	2026-10-05T02:05:05Z	21312392	6108872	2505096	54842712	1.34	0.7	1	3773	47	0	0.00
idle-40	2026-10-05T02:05:10Z	21234544	6186720	2505096	54842712	1.36	6.1	1	3773	47	0	0.00
idle-40	2026-10-05T02:05:16Z	21318680	6102584	2505096	54842712	1.25	1.5	1	3773	47	0	0.00
idle-40	2026-10-05T02:05:21Z	21167752	6253512	2505096	54842712	1.15	2.1	1	3773	47	0	0.00
idle-40	2026-10-05T02:05:26Z	21160608	6260656	2505096	54842712	1.14	1.6	1	3773	47	0	0.00
```

| Step | Memory used KiB | Available KiB | Swap used KiB | load1 | Probe ms | Sessions | Build procs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 15949180 | 11472084 | 2276392 | 1.64 | 1.7 | 8 | 0 |
| idle-10 | 17468356 | 9952908 | 2318492 | 1.79 | 1.6 | 17 | 0 |
| idle-20 | 18916076 | 8505188 | 2382888 | 1.32 | 1.7 | 27 | 0 |
| idle-40 | 21234544 | 6186720 | 2505096 | 1.25 | 1.6 | 47 | 0 |

Every `probe_ok` value in these rows was 1. Every `psi_full_avg10` value was 0.00.

From the baseline median to the idle-40 median, available memory fell by 5285364 KiB. Dividing by the 40 added agents gives 132134 KiB, which is 129 MiB. That 129 MiB figure is this ramp's average net change in MemAvailable. It is not a measured cost of one more agent, and it does not set a ceiling. The per-step averages were 148 MiB at 10 agents and 145 MiB at 20. The average fell as the count rose. Nothing in this run measured shared file pages, so that drop stays unexplained. A snapshot of anonymous RSS taken just after the idle-40 samples is a different number and is not used here.

Swap grew by 228704 KiB, 223 MiB, from 4.2 percent to 4.6 percent. The stop line is 50 percent. `load1` at idle-40 was 1.25, range 1.14 to 1.36. The probe median stayed at 1.6 ms, range 0.7 to 6.1. One idle-10 probe sample was 56.5 ms. The other four were 0.7, 2.1, 1.6, and 1.6 ms.

RAM is the resource that moved. At 40 agents, 5.9 GiB was still available. The step count was the bound of the test.

While the last 20 agents were still starting, two curls of the same root URL, outside the sampler, took 148 ms and 90 ms. The idle-40 samples, taken after a 60 second wait, were back near 1 ms.

A projection, not a measurement. Another 39 agents at 129 MiB of MemAvailable each would put available memory near 1 GiB. This ramp did not start them.

## Forty agents with builds on the rerun

The rerun used the same agent method. Forty child tasks, provider `claudeAgent`, model `claude-haiku-4-5`, thinking false, asked to reply with the single word idle and not to use tools. The new baseline below was taken before those tasks existed. Forty `claude` processes whose arguments contained `haiku` were up, the root probe was checked, and the samples started about 60 seconds later.

The four loops ran in four copies of the tree, so they did not write this worktree. Each loop was started with `LAND_SLOT` unset. The first workload ran `python3 scripts/build.py` and then `python3 -m unittest discover -s tests`, with no pause, and appended one unbuffered status line per finished iteration. The sample window is the first sample timestamp through the last. An iteration counts when its end timestamp falls inside that window.

The builds-4 window was 2026-10-05T02:31:53Z through 02:32:13Z. Each of the four loops completed one iteration in that window. Every `build_exit` was 0 and every `unittest_exit` was 0. The suite log for each copy says `Ran 85 tests` and `OK`, in 32.384 to 32.526 seconds. `build_procs` was 4 on every row.

The suite-4 window was 2026-10-05T02:32:38Z through 02:32:58Z. Each loop ran only the unit suite, again with no pause. Each completed one iteration in the window, `unittest_exit` 0, `Ran 85 tests` and `OK`, in 32.771 to 32.789 seconds. `build_procs` was 4 on the first three rows and 5 on the last two. The fifth process was not a fifth completed loop.

```
label	ts	mem_used_kib	mem_available_kib	swap_used_kib	swap_total_kib	load1	probe_ms	probe_ok	probe_port	sessions	build_procs	psi_full_avg10
baseline	2026-10-05T02:28:48Z	16106004	11315260	2505092	54842712	2.19	0.7	1	3773	9	0	0.00
baseline	2026-10-05T02:28:53Z	16091272	11329992	2505092	54842712	2.26	1.9	1	3773	9	0	0.00
baseline	2026-10-05T02:28:58Z	16097460	11323804	2505092	54842712	2.15	1.3	1	3773	9	0	0.00
baseline	2026-10-05T02:29:03Z	16106004	11315260	2505092	54842712	2.06	1.5	1	3773	9	0	0.00
baseline	2026-10-05T02:29:08Z	16112848	11308416	2505092	54842712	1.98	1.7	1	3773	9	0	0.00
builds-4	2026-10-05T02:31:53Z	21370728	6050536	4122676	54842712	3.35	2.1	1	3773	49	4	0.00
builds-4	2026-10-05T02:31:58Z	21346292	6074972	4122676	54842712	3.57	2.2	1	3773	49	4	0.00
builds-4	2026-10-05T02:32:03Z	21376708	6044556	4122676	54842712	3.84	2.7	1	3773	49	4	0.00
builds-4	2026-10-05T02:32:08Z	21265876	6155388	4122676	54842712	4.17	5.3	1	3773	49	4	0.00
builds-4	2026-10-05T02:32:13Z	21280036	6141228	4122676	54842712	3.92	1.5	1	3773	49	4	0.00
suite-4	2026-10-05T02:32:38Z	20988460	6432804	4122676	54842712	4.33	1.4	1	3773	49	4	0.00
suite-4	2026-10-05T02:32:43Z	20623628	6797636	4122676	54842712	4.62	27.5	1	3773	48	4	0.00
suite-4	2026-10-05T02:32:48Z	20639812	6781452	4122676	54842712	4.65	5.6	1	3773	48	4	0.00
suite-4	2026-10-05T02:32:53Z	20596260	6825004	4122676	54842712	4.84	1.7	1	3773	48	5	0.00
suite-4	2026-10-05T02:32:58Z	20649108	6772156	4122676	54842712	4.53	3.7	1	3773	48	5	0.00
```

| Step | Memory used KiB | Available KiB | Swap used KiB | load1 | Probe ms | Sessions | Build procs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 16106004 | 11315260 | 2505092 | 2.15 | 1.5 | 9 | 0 |
| builds-4 | 21346292 | 6074972 | 4122676 | 3.84 | 2.2 | 49 | 4 |
| suite-4 | 20639812 | 6781452 | 4122676 | 4.62 | 3.7 | 48 | 4 |

Every `probe_ok` value was 1. Every `psi_full_avg10` value was 0.00.

One reading 60 seconds after the 40 Haiku processes were up, and before the loops started, showed 6054728 KiB available, swap still 4122676 KiB, `load1` 2.40, 49 sessions, and 0 build processes. The builds-4 available median is 6074972 KiB, 20 MiB from that reading. The drop from the rerun baseline happened when the agents arrived. The four running suites did not take a further bite that shows up between that reading and the builds-4 median.

From the rerun baseline median to the builds-4 median, available memory fell 5240288 KiB. Forty Haiku processes were the processes that had been added. Dividing the drop by 40 gives 128 MiB. That is this rerun's average net change, the same kind of figure as the first ramp's 129 MiB. Swap grew 1617584 KiB, 1.54 GiB, from 4.6 percent to 7.5 percent, and that growth was already present before the loops started. During both build windows swap stayed at 4122676 KiB.

`load1` during builds-4 had median 3.84 and range 3.35 to 4.17. During suite-4 the median was 4.62 and the range was 4.33 to 4.84. The suite window started less than a minute after the first loops stopped, so its `load1` still overlaps that earlier work. Sixteen threads were not full. `psi_full_avg10` stayed 0.00.

The builds-4 probe median was 2.2 ms, range 1.5 to 5.3. The suite-4 median was 3.7 ms. One suite sample was 27.5 ms and the other four were 1.4, 5.6, 1.7, and 3.7 ms. All of them were the root HTML response.

Available memory's median was 706480 KiB higher in the suite-4 window than in the builds-4 window. Swap did not change. This run did not isolate which process released that memory.

At builds-4, 5.8 GiB was still available. Swap was 7.5 percent. The stop line is 50 percent. The lowest available sample in the rerun was 6044556 KiB, still above 1 GiB.

## Comparison with the 2026-10-04 estimate

The estimate was about 40 idle agents, or about 25 agents with 4 builds running, on 26 GB of RAM.

Forty idle Haiku agents on the first ramp had 5.9 GiB available, swap at 4.6 percent, `load1` at 1.25, and the root probe at 1.6 ms. The rerun held 40 Haiku processes plus four running unit suites with 5.8 GiB available, swap at 7.5 percent, `load1` at 3.84, and the root probe at 2.2 ms. Both points are inside the stop lines. They are the top step that was run, not a measured ceiling. The root probe says the HTML endpoint answered. It does not say that interactive T3 use stayed responsive.

The 129 MiB figure is the first ramp's average net change in available memory across 40 added agents. The rerun's matching average is 128 MiB. Neither one was measured as the cost of a single extra agent, and neither one was checked against shared file pages. Using 129 MiB to project a 1 GiB floor at about 79 agents remains a projection. Those agents were not started.

The estimate's figure of about 25 agents with 4 builds describes a heavier build than `scripts/build.py` plus this unit suite. Each suite here took about 33 seconds and passed 85 tests. Four of them left `load1` under 5 on 16 threads and did not move swap during the window. That does not confirm the estimate, and it does not refute it. A heavier build would be a different measurement. Cursor `gpt-5.4-nano` with reasoning `none` was not measured.
