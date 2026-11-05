# live runs summary: live/runs/final-c6cef8724cd4/a1

runs 66, judge PASS 66, raw NC ok 66, disk 15048 KiB

core snapshot(s): ['c6cef8724cd494454931b343ff1c4eb56622a960f21b7db3acff22e908946843']
live snapshot(s): ['ead7a9cb133af02bbfc7100812a254b3be7613738757b4276df5f5d19d3bd3c9']

| scenario | arm | PASS | NC ok | exit 0 | reps identical | same hashes | exp+ | calls | kinds | decisions | rejected | msgs | settle med/max s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K | a | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'deliver': 5, 'delete': 1, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [65, 65, 65] | 0.12079999999999999/0.1275 |
| K | d | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'deliver': 5, 'delete': 1, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [16, 16, 16] | 0.11779999999999999/0.1257 |
| P1 | a | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'deliver': 3, 'delete': 1, 'current': 1, 'revoke': 2} | [5, 5, 5] | [0, 0, 0] | [91, 91, 91] | 0.1147/0.1324 |
| P1 | d | 3/3 | 3/3 | True | True | True | 7 | [7, 7, 7] | {'deliver': 3, 'delete': 1, 'current': 1, 'revoke': 2} | [5, 5, 5] | [0, 0, 0] | [44, 44, 44] | 0.1143/0.1204 |
| T | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 2, 'delete': 0, 'current': 0, 'revoke': 0} | [0, 0, 0] | [5, 5, 5] | [51, 51, 51] | 0.1183/0.1243 |
| T | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 2, 'delete': 0, 'current': 0, 'revoke': 0} | [0, 0, 0] | [5, 5, 5] | [11, 11, 11] | 0.11904999999999999/0.1252 |
| contract/CT1 | a | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'deliver': 3, 'delete': 0, 'current': 0, 'revoke': 0} | [0, 0, 0] | [0, 0, 0] | [32, 32, 32] | 0.11699999999999999/0.1197 |
| contract/CT1 | d | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'deliver': 3, 'delete': 0, 'current': 0, 'revoke': 0} | [0, 0, 0] | [0, 0, 0] | [8, 8, 8] | 0.115/0.1191 |
| contract/CT2 | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 1, 'delete': 0, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [13, 13, 13] | 0.11565/0.121 |
| contract/CT2 | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 1, 'delete': 0, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [5, 5, 5] | 0.11485000000000001/0.1196 |
| contract/CT3 | a | 3/3 | 3/3 | True | True | True | 5 | [5, 5, 5] | {'deliver': 3, 'delete': 1, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [37, 37, 37] | 0.11515/0.1227 |
| contract/CT3 | d | 3/3 | 3/3 | True | True | True | 5 | [5, 5, 5] | {'deliver': 3, 'delete': 1, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [12, 12, 12] | 0.11565/0.1209 |
| contract/CT4 | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 0, 'delete': 0, 'current': 1, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [30, 30, 30] | 0.1164/0.1211 |
| contract/CT4 | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 0, 'delete': 0, 'current': 1, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [26, 26, 26] | 0.1142/0.1232 |
| contract/CT5 | a | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 1, 'delete': 0, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [37, 37, 37] | 0.1159/0.1174 |
| contract/CT5 | d | 3/3 | 3/3 | True | True | True | 2 | [2, 2, 2] | {'deliver': 1, 'delete': 0, 'current': 0, 'revoke': 1} | [0, 0, 0] | [0, 0, 0] | [25, 25, 25] | 0.1137/0.1161 |
| contract/CT6 | a | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'deliver': 2, 'delete': 1, 'current': 0, 'revoke': 0} | [0, 0, 0] | [0, 0, 0] | [28, 28, 28] | 0.11545/0.1218 |
| contract/CT6 | d | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'deliver': 2, 'delete': 1, 'current': 0, 'revoke': 0} | [0, 0, 0] | [0, 0, 0] | [8, 8, 8] | 0.11465/0.1223 |
| contract/CT7-cfg0 | a | 3/3 | 3/3 | True | True | True | 0 | [0, 0, 0] | {'deliver': 0, 'delete': 0, 'current': 0, 'revoke': 0} | [3, 3, 3] | [0, 0, 0] | [3, 3, 3] | 0.0605/0.1176 |
| contract/CT7-cfg0 | d | 3/3 | 3/3 | True | True | True | 0 | [0, 0, 0] | {'deliver': 0, 'delete': 0, 'current': 0, 'revoke': 0} | [3, 3, 3] | [0, 0, 0] | [3, 3, 3] | 0.0617/0.1191 |
| contract/CT7-cfg1 | a | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'deliver': 2, 'delete': 0, 'current': 0, 'revoke': 1} | [3, 3, 3] | [0, 0, 0] | [28, 28, 28] | 0.112/0.1188 |
| contract/CT7-cfg1 | d | 3/3 | 3/3 | True | True | True | 3 | [3, 3, 3] | {'deliver': 2, 'delete': 0, 'current': 0, 'revoke': 1} | [3, 3, 3] | [0, 0, 0] | [6, 6, 6] | 0.0605/0.1169 |
