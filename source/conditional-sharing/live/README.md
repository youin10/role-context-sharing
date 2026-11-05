# live/ — ROS 2 live 실행 adapter·runner (준비 단계)

상태: 최종 행렬 실행 완료 — `runs/final-c6cef8724cd4/a1/` (66 runs). `runs/smoke-*`(초기 준비)와 `runs/integration/`(통합 smoke)은 결과가 아니다.
CT5 역할 해제 판본(core `cs-core-7ba114d5dcf9`): `runs/role-release-7ba114d5dcf9/a1/` (CT5 × D/A × 3, `scenario.sh`). 이 6회가 CT5의 ROS 2 증거를 대체하며 위 66회에 더하지 않는다. 이전 CT5 6회는 `runs/final-c6cef8724cd4/a1/`에 그대로 보존한다.
지식 알림 판본(core `cs-core-9ec4e836cb48`, assert/update/retract): 최종 행렬 `runs/final-9ec4e836cb48/a2/` (11 시나리오 × D/A × 3 = 66 runs). 시도 `a1`은 실행 중 이 README가 수정되어 마지막 3회의 live 해시가 달라졌으므로(README.md만 다름) 보존만 하고 집계하지 않는다. 위 두 기록은 이전 구현 판본이며 이 행렬과 합산하지 않는다.
소유: 이 디렉터리만. `../src`, `../runner`(api.py), `../inputs`, `../tools/snapshot.py`는 읽기 전용으로 import/mount 한다.

## 1. 구성

| 파일 | 역할 |
|---|---|
| `cslive/proc.py` | 프로세스 진입점. core 클래스를 rclpy 노드에 올리고 core 간 메시지를 DDS topic으로 운반 |
| `cslive/plan.py` | 프로세스 배치(관측 agent당 1 프로세스, 나머지는 producer 프로세스). 조립은 모두 `runner/api.py` (core와 공유) |
| `cslive/wire.py` | topic·QoS (rcs-experiments 7bef3ecd arms/d/wire.py, arms/a/wire.py의 이름 체계) |
| `judge.py` | 독립 판정기. 입력 시나리오(step 일정·관측 roster·decider) + 손으로 쓴 기대표만 신뢰, raw는 증거. src/runner/cslive import 없음, `python3 -I` |
| `nc_raw.py` | raw 음성대조 9종(관측자 log 삭제/비움, step 삭제, call·rx 중복, 순서 교환, end 제거, rx 손실, 값 변조) — judge가 모두 FAIL해야 함 |
| `summarize.py`, `final.sh` | 반복 묶음 통계 / 승인된 최종 행렬(11 시나리오 × D/A × 3) 실행, snapshot 불일치 시 거부 |
| `scenario.sh`, `check_entries.py` | 선택 시나리오의 D/A × 3 반복(final.sh와 같은 절차) / 로그만으로 소비 항목(D 적용 구성, A LTM 구독)을 기대표 `inputs/expected/<시나리오>-entries.yml`과 대조 |
| `run.py` | host runner (stdlib). 프로세스당 컨테이너 1개, 전용 bridge network, 고유 ROS_DOMAIN_ID, 순차 실행 |
| `smoke/ping.py`, `smoke/run_ping.sh` | DDS 최소 ping smoke |

프로세스 (컨테이너 1개씩, hostname = 프로세스명):
- D: `d-sm`(SMCore(generate(EBNF))) · `d-producer`(producer envelope + 미관측 agent의 AgentCore, ack) · `d-agent-<X>`(AgentCore + app) · `driver`(step 제어, 변경 시 generate → `/d/apply`, wire capture)
- A: `a-ltm`(GuardedLTM⊂LTMCore) · `a-producer`(미관측 agent의 AAgentCore, producer는 emit) · `a-agent-<X>` · `driver`(`arms.a.core.dispatch`를 RosBus로 실행)

A의 `Bus`는 `RosBus.send(dest, d)`로 대체한다(같은 인터페이스). D는 `SMCore.report/stage/ack/due`, `AgentCore.handle`의 반환 메시지를 그대로 publish한다. adapter는 routing·조건·view 논리를 갖지 않는다.

Step 프로토콜: driver `arm`(모든 프로세스 step id 설정 후 ready) → `go`(actor 실행) → settle: driver가 모든 프로세스의 topic별 tx/rx 카운터와 core 상태를 probe하여 (1) 보낸 data 메시지를 모든 구독자가 받음(보존), (2) core 완료(D 변경: SMCore pending·staged 없음 & active_seq ≥ seq, 즉 모든 agent commit ACK; A 변경: 모든 target이 해당 request_id ACK; A: 미응답 match 없음), (3) 연속 두 probe 동일 — 일 때 다음 step. step 0 `init`은 A 초기 load(request_id 0). 시간 창(quiet) 가정은 쓰지 않는다.

## 2. 실행 명령

```bash
cd experiments/conditional-sharing
bash live/smoke/run_ping.sh 50                                   # DDS smoke
python3 live/run.py --arm d --scenario contract/CT1 --expected contract/CT1 --label prep --rep 1
python3 live/run.py --arm a --scenario contract/CT1 --expected contract/CT1 --label prep --rep 1
# 반복: --rep 1..N 을 순차 호출 (병렬 금지). 판정 음성대조:
docker run --rm --network none -v $PWD/live/judge.py:/judge.py:ro -v $PWD/inputs:/inputs:ro \
  -v $PWD/live/runs/<run_id>:/run rcs-experiments:jazzy python3 -I /judge.py /run /inputs/expected/contract/CT1.yml --mutate first-call
```

산출: `runs/<run_id>/{plan.json, manifest.json, logs/<proc>.jsonl, logs/<proc>.stdout, judge.json}`.
manifest: image id·base digest·rclpy/RMW/FastDDS 버전 probe, docker 버전, repo HEAD, src/inputs/live 파일별·집계 SHA256, 정확한 docker 명령, domain id, 종료 코드.

## 3. 제약

- 통신 장애 주입·복구 경로 미사용(범위 밖). QoS는 RELIABLE+TRANSIENT_LOCAL depth 10000.
- 각 app call은 원인 inbox 메시지(hash, rx seq)를 기록한다. judge는 그 payload가 다른 host 프로세스에서 같은 step에 정확히 1회 tx됐는지, D wire 종류(assert/update/retract)와 호출 종류의 일치, 보고 원인 알림의 event, 모델 전환 알림의 seq·tr, A notify event/match/load request_id를 검사한다.
- 남는 한계: (2)의 완료는 core가 노출하는 상태(pending/ack) 기준이며, ACK 이후 app 처리 지연은 메시지 보존 검사로만 덮는다. probe 자체도 DDS 메시지라 probe 사이 신규 메시지가 없음을 두 번 확인한 것이지 형식적 종료 증명은 아니다.
- 정리 대상은 label `cslive.run=<run_id>` 컨테이너·network뿐이다.
