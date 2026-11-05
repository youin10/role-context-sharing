# live runs summary: live/runs/final-9ec4e836cb48/a2

runs 66, judge PASS 66, raw NC ok 66, disk 15040 KiB

core snapshot(s): ['9ec4e836cb48fc2744a2b65496c042b8942e8d6e1f387c7247006ed6fa138973']
live snapshot(s): ['3519caba6fdd51cdfd7b6202f0d3067c3e1f1cc8e7ae77db5e65c6411fe71cce']

| scenario | arm | PASS | NC ok | exit 0 | reps identical | same hashes | exp+ | calls | kinds | decisions | rejected | msgs | settle med/max s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K | a | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'assert': 5, 'update': 0, 'retract': 2} | [0, 0, 0] | [0, 0, 0] | [65, 65, 65] | 0.1184/0.1276 |
| K | d | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'assert': 5, 'update': 0, 'retract': 2} | [0, 0, 0] | [0, 0, 0] | [16, 16, 16] | 0.11635/0.1284 |
| P1 | a | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'assert': 4, 'update': 0, 'retract': 3} | [5, 5, 5] | [0, 0, 0] | [91, 91, 91] | 0.1148/0.1268 |
| P1 | d | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'assert': 4, 'update': 0, 'retract': 3} | [5, 5, 5] | [0, 0, 0] | [44, 44, 44] | 0.1128/0.1223 |
| T | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 1, 'retract': 0} | [0, 0, 0] | [5, 5, 5] | [51, 51, 51] | 0.11725/0.123 |
| T | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 1, 'retract': 0} | [0, 0, 0] | [5, 5, 5] | [11, 11, 11] | 0.1169/0.1347 |
| contract/CT1 | a | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'assert': 3, 'update': 0, 'retract': 0} | [0, 0, 0] | [0, 0, 0] | [32, 32, 32] | 0.1147/0.1193 |
| contract/CT1 | d | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'assert': 3, 'update': 0, 'retract': 0} | [0, 0, 0] | [0, 0, 0] | [8, 8, 8] | 0.11485000000000001/0.1226 |
| contract/CT2 | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 0, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [13, 13, 13] | 0.11055000000000001/0.1178 |
| contract/CT2 | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 0, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [5, 5, 5] | 0.10994999999999999/0.1209 |
| contract/CT3 | a | 3/3 | 3/3 | True | True | True | 5 | [5, 5, 5] | {'assert': 2, 'update': 1, 'retract': 2} | [0, 0, 0] | [0, 0, 0] | [37, 37, 37] | 0.11295/0.1221 |
| contract/CT3 | d | 3/3 | 3/3 | True | True | True | 5 | [5, 5, 5] | {'assert': 2, 'update': 1, 'retract': 2} | [0, 0, 0] | [0, 0, 0] | [12, 12, 12] | 0.1123/0.1265 |
| contract/CT4 | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 0, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [30, 30, 30] | 0.1141/0.1208 |
| contract/CT4 | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 0, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [26, 26, 26] | 0.109/0.1174 |
| contract/CT5 | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 0, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [37, 37, 37] | 0.1145/0.1192 |
| contract/CT5 | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'assert': 1, 'update': 0, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [25, 25, 25] | 0.11285/0.1205 |
| contract/CT6 | a | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'assert': 1, 'update': 1, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [28, 28, 28] | 0.11624999999999999/0.1215 |
| contract/CT6 | d | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'assert': 1, 'update': 1, 'retract': 1} | [0, 0, 0] | [0, 0, 0] | [8, 8, 8] | 0.11380000000000001/0.1319 |
| contract/CT7-cfg0 | a | 3/3 | 3/3 | True | True | True | 0 | [0, 0, 0] | {'assert': 0, 'update': 0, 'retract': 0} | [3, 3, 3] | [0, 0, 0] | [3, 3, 3] | 0.0619/0.1343 |
| contract/CT7-cfg0 | d | 3/3 | 3/3 | True | True | True | 0 | [0, 0, 0] | {'assert': 0, 'update': 0, 'retract': 0} | [3, 3, 3] | [0, 0, 0] | [3, 3, 3] | 0.0597/0.1197 |
| contract/CT7-cfg1 | a | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'assert': 2, 'update': 0, 'retract': 1} | [3, 3, 3] | [0, 0, 0] | [28, 28, 28] | 0.1107/0.1213 |
| contract/CT7-cfg1 | d | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'assert': 2, 'update': 0, 'retract': 1} | [3, 3, 3] | [0, 0, 0] | [6, 6, 6] | 0.0609/0.127 |
