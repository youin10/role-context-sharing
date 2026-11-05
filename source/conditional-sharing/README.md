# conditional-sharing — core 실험 (1단계, in-process, ROS 없음)

목적: 조건부 공유 모델을 기존 D 생성/SM core와 A(ARBI 방식 재구현) LTM/agent 경로를 재사용해 구현하고, 구현과 독립적으로 작성한 기대표와 대조한다.
**증거 경계:** 이 디렉터리의 결과는 함수·프로세스 내부(core) 실행 증거다. ROS 2/분산/물리 로봇 결과가 아니며 원본 ARBI(native JAR) 실행도 아니다. 기존 제출본 18회·final-3 242회와 합치지 않는다.

## 1. 구성

| 경로 | 내용 |
|---|---|
| `runner/api.py` | core·live 공통 조립 API(rclpy 무의존). 명세 `runner/API.md` |
| `upstream/` | `../rcs-experiments` commit `7bef3ecd`의 tracked 원본 사본(`git show HEAD:<path>`), `upstream/MANIFEST.json`에 sha256 |
| `src/` | 실행 소스. `upstream/` 사본을 수정한 D 경로 + A core. 변경은 `patches/*.diff` |
| `inputs/ontology/` | 술어 서명(`predicates/logistics-cs.ttl`), 클래스 계층(`logistics-classes.ttl`), 개체 타입(`logistics-individuals.ttl`) — 서로 별도 사실 |
| `inputs/models/d/` | D 입력: org 모델(`*.org`)과 binding(`*.yml`, PyYAML로 읽음). 빈 역할 목록(`agent: []`)은 역할 없는 배정이다: agent는 배정·ACK 집합에 남고 reads/changes 항목은 없다 |
| `inputs/models/a/` | A 입력(수동 per-ID): 동일 요구에서 별도로 작성한 GL 역할 계획(`plans/<rev>/<Role>.yml`), `initial-*.yml`, 배포 목록 `changes/<id>.yml` |
| `inputs/models/a-helper/` | A 입력(helper 비교군): A 소유 타입별 threshold `config/`, 배정 `assign/`, `spec.yml` → `tools/build_a_helper.py`가 per-ID 계획·initial·changes 생성(GENERATED 표시) |
| `inputs/scenarios/` | 단계별 입력(report/delete/change/decide) |
| `inputs/expected/` | 구현과 독립적으로 작성한 기대표(구현 출력에서 만들지 않음). `contract/`는 `../../traceability/CONTRACT-SPECIFICATION.md` §2의 계약 명세. 동결 해시 `expected-hashes.json` |
| `runner/` | `core_run.py`(D/A 실행·raw 기록), `plan.py`(고정 판단 코드), `judge.py`(판정기, 구현 import 없음), `variants.py`(negative control 변이), `run_all.py` |
| `tools/` | 기존 88 생성물 회귀, 편집량, 시간, 규모 스윕(`sweep.py`), judge 변이 NC, A helper 빌드, 재실행 비교, 단위 확인, 역할 해제 소비 항목 검사(`check_entries.py`, 기대표 `inputs/expected/contract/CT5-entries.yml`), snapshot |
| `snapshots/` | 동결 tar.gz + sha256 + 파일별 해시 JSON |
| `results/<run>/` | raw JSONL, judgments/x1/grammar/a_static/summary JSON, manifest, edit-diffs, timing |

## 2. 문법 (구현이 받는 EBNF)

```ebnf
model          = { prefix_decl } { role } ;
prefix_decl    = "prefix" PNAME_NS IRIREF ";" ;
role           = "role" IDENT "{" { section } "}" ;          (* reads / changes 각 최대 1회 *)
section        = ( "reads" "{" { read_pattern } "}" ) | ( "changes" "{" { change_pattern } "}" ) ;
change_pattern = PREDICATE "(" VAR { "," VAR } ")" ";" ;    (* changes에는 조건 없음 *)
read_pattern   = PREDICATE "(" [ VAR { "," VAR } ] ")" ( ";" | "{" { line } "}" ) ;
line           = conj { "||" conj } ";" ;
conj           = comparison { "&&" comparison } ;
comparison     = VAR op constant ;
op             = "==" | "!=" | "<" | "<=" | ">" | ">=" ;
constant       = STRING | NUMBER | "true" | "false" | CLASS ;
CLASS          = PNAME | IRIREF ;                           (* prefix:Local 또는 <IRI> *)
```

- `PREDICATE`는 prefix 이름이며 ontology의 `predicateName`과 URI로 대응한다. `VAR`는 위치로 `argumentIndex` i번 인자에 결합된다(첫 인자 포함).
- 줄과 줄은 AND, 한 줄 안에서는 `&&`가 `||`보다 먼저 묶인다. 결과는 DNF(OR of AND)다. 괄호는 없다(G20: `SYNTAX`).
- 같은 역할에서 같은 술어를 두 번 쓰면 `DUPLICATE_READ`(G04). 그래서 이족/바퀴형 두 분기를 한 역할에 쓰려면 한 줄의 `||`가 필요하다(G01, X1).
- 클래스 호환성(`== C`, `!= C` 공통): argumentType과 C가 고정 catalogue 안에서 겹칠 수 있어야 한다 — C와 argumentType 둘 다의 하위 클래스로 선언된 클래스가 있거나(상하 관계는 그 특수한 경우), 둘 다에 속하는 등록 개체가 있으면 유효. 예: `BipedBalance(robot :Biped)`에 `$robot == logistics:Wheeled`는 hybrid1(Biped+Wheeled) 때문에 유효(G22, X2). 어떤 선언 클래스·등록 개체로도 겹칠 수 없으면 `TYPE_MISMATCH`로 거부(G08, G23, G24). 이 거부는 고정 catalogue에 대한 closed-world 판단이며 OWL 서로소 추론이 아니다. 이전 판본은 상하 관계만 허용해 X2 같은 유효 조건을 거부했다(negative control `relation-only-check`).
- 문법 요소: 조건 블록, `;` 줄 구분, 위치 인자 결합, URI predicate/prefix, `""` 문자열 대 prefix 클래스 구분, `||` 분기, `&&` 우선순위 및 DNF 전개.

### 인자 타입별 의미

| argumentType | 허용 비교 | 의미 / 거부 |
|---|---|---|
| xsd 정수·실수 | `== != < <= > >=` 숫자 | 숫자 비교. 문자열 상수·클래스 → `TYPE_MISMATCH` |
| xsd:string | `== !=` 문자열 | 문자열 비교. 순서 비교·클래스 → `TYPE_MISMATCH` |
| ontology 클래스(개체 인자, **위치 무관**) | `== "id"`, `!= "id"` | 개체 ID 동등. ID는 등록 개체이고 argumentType 소속이어야 함(`UNKNOWN_INDIVIDUAL`, `TYPE_MISMATCH`). `"Biped"`처럼 따옴표 쓴 클래스 이름은 ID로 취급되어 거부(G06) |
| 〃 | `== prefix:C` | 개체가 C 또는 C의 하위 클래스 소속(rdfs:subClassOf 추이 폐포). C는 선언된 클래스(`UNKNOWN_CLASS`)이고 argumentType과 호환돼야 함(아래 "클래스 호환성", 아니면 `TYPE_MISMATCH`) |
| 〃 | `!= prefix:C` | **등록된** 개체이면서 C 소속이 아님. 미등록 개체를 참으로 처리하지 않음 |
| 〃 | `< <= > >=`, 숫자 상수 | `TYPE_MISMATCH`(ID 숫자 비교 금지) |

- 타입·계층은 실행 중 고정이다. 동적 타입 변경, 동치·서로소 등 full OWL 추론은 없다.
- 다중 소속(`hybrid1 a :Biped, :Wheeled`)은 두 분기의 OR 합집합이다. 우선순위 없음. 두 분기를 모두 만족해도 assert는 1회(X1, `dup-branch` NC가 검출).
- 실행 시 보고 검증(typed mode): 미등록 개체, 잘못된 타입의 개체, 값 타입 오류, 필드 누락·초과 보고는 SM이 `rejected`로 기록하고 저장·전달하지 않는다. 직전 저장값과 eligible view는 그대로 둔다(T).

## 3. 공통 catalogue와 D/A 규칙 평가의 구분

- **공통 known entity catalogue:** 술어 서명 + 고정 개체 타입(`inputs/ontology`). 보고 검증 함수 `arms.d.ontology.report_error`를 D SM과 A helper(`arms/a/typed.py` `GuardedLTM`)가 같이 쓴다. A 정적 검사 `check_plans`도 같은 catalogue를 쓴다(A-static).
- **D 규칙 평가:** org 모델의 클래스 조건을 SM이 고정 폐포로 평가한다.
- **A 규칙 평가(수동):** 동일 요구에서 별도로 작성한 개체별(per-ID) GL 규칙. 타입은 규칙 작성 시점에 펼쳐 둔다(`Manager.yml` 주석).
- **A 규칙 평가(helper):** A 소유 타입별 threshold 설정을 공통 정적 ontology로 per-ID GL 규칙에 펼치고(`arms/a/expand.py`), 역할 배정·계획 변경에서 배포 target을 계산한다. D EBNF/parser/generator는 호출하지 않는다.
- A의 추가 기능(typed.py, expand.py, build_a_helper.py)과 재구현 core(core.py)는 소스·편집 비용에서 분리 보고한다.

## 4. 어댑터 대응 (wire 메시지 → 응용 호출)

소비자 지식 알림: Assert = 로컬 지식에 사실 추가, Update = 기존 제공 사실의 값 갱신, Retract = 로컬 지식에서 사실 제거. D에서는 Shared Memory(SM)가 알림 종류를 정한다. 직전 저장값이 소비자 조건을 만족했으면 이미 공급된 사실이다. 보고의 저장 변경과 소비자 알림은 별개이며, 조건 이탈·역할 해제 Retract는 저장 사실을 지우지 않는다.

| 의미 | D (SM → AgentCore) | A (LTM notify/match → agent 어댑터) | 응용 기록 |
|---|---|---|---|
| 첫 공급(새 사실·조건 진입·재진입) | `assert` v | 조건 규칙 notify, 미보유 → `on_assert` | `assert` |
| 공급 중 사실의 조건 안 갱신 | `update` v | 조건 규칙 notify, 보유 중 → `on_update` | `update` |
| 공급 중 사실의 원본 삭제 | `retract` e | tombstone 규칙 notify → `on_retract` | `retract` |
| 조건 이탈(사실은 저장소에 존재) | `retract` n | 개체 감시 규칙 notify, 조건 불만족 → `on_retract` | `retract` |
| 구성 변경으로 획득(저장 사실 첫 공급) | `assert`(tr) | 계획 재적재 → match, 미보유 → `on_assert` | `assert` |
| 구성 변경으로 상실(남은 요구 없음) | `retract`(tr) | 재적재 → context 상실 → `on_retract` | `retract` |
| 두 구성에서 계속 필요 | 없음 | 없음 | 없음 |

A의 LTM 연산명(`assert`/`update`/`retract` 보고, `subscribe`, `notify`, `match`, `load`)은 원 프레임워크 이름 그대로이며, 대응은 AAgentCore가 응용을 호출하는 경계에서만 한다. `commit`/ACK/`sync`와 재시작 재동기화 `snapshot`은 제어·동기화 메시지다. `snapshot` 값은 AgentCore가 보유 여부에 따라 `on_assert`/`on_update`로, `sync`의 삭제 목록과 스냅샷에 없는 보유 사실은 `on_retract`로 반영한다.

판정은 응용 기록·eligible view·저장 최신값·고정 판단만 비교한다. commit/ack 같은 wire 메시지는 비교하지 않는다. core의 in-process FIFO bus는 이 하네스의 성질일 뿐이며 ROS 2/DDS의 전달 순서를 일반적으로 보장한다는 뜻이 아니다.

판정기(`runner/judge.py <raw> <expected> <scenario>`): observer roster와 step 순서를 scenario 파일에서 가져온다(raw의 start.observe에 의존하지 않음). start/end 형식, step 누락·중복·순서·예상 밖 step, 관측자 view 누락, 빈 roster, 예상 밖 rejection, 비교된 양성 호출 수가 표의 양성 수와 다르거나 0(제거 대조는 `no_positive_calls: true` 명시)이면 FAIL. 변이 NC는 `tools/judge_mutation_nc.py`.

## 5. 재현

```bash
cd experiments/conditional-sharing
python3 -m venv .venv && .venv/bin/pip install PyYAML==6.0.2
.venv/bin/python tools/snapshot.py extract <snapshot_id> <dir>     # 동결 판본 복원 + 해시 검증
./run.sh <run_id> .venv/bin/python <snapshot_id>                    # 실행 전후 동결 검증 포함
.venv/bin/python runner/judge.py results/<run>/raw/main/B1__D__main.jsonl inputs/expected/B1.yml inputs/scenarios/B1.yml
```

결과 디렉터리는 덮어쓰지 않는다. 각 결과의 `manifest.json`에 파일별 해시·환경·명령이 있고, 판본이 다른 과거 결과(host-1/2/3, docker-1, dry-1)에 새 판본을 소급하지 않는다.

## 6. 규모 스윕과 복잡도 (`tools/sweep.py`)

차원: R(개체, 홀수=Biped/짝수=Wheeled), M(소비 agent), C(소비자당 조건 역할; 역할 j = Biped≤30−j ∨ Wheeled≤20−j). 값 1·4·16·64를 한 차원씩(나머지 4) + 대각 1·16. 부하는 D/A 동일: 4 round × R 보고 + 재배포 1회(Wheeled +10). 정답은 닫힌 식으로 만들며 구현을 import하지 않는다. 시간은 공유 host의 perf_counter이며 환경 한정 탐색값이다(로봇 규모 성능으로 일반화 금지).

실제 루프 기준 상한(이 하네스 구현의 성질):
- D check: 역할×reads×조건, 클래스 조건마다 호환성 O(K+I)(K 클래스, I 개체). generate: 소비자 대안 중복 제거가 O((2C)²)이므로 O(M·C²).
- D 보고 1건: 문맥 소비자 M명 × 대안 2C의 조건 평가 → O(M·C); 전체 4R건 → O(R·M·C).
- D 재배포(stage): agent × 저장 항목 R × 대안 → O(M·R·C) (+ 생성).
- A 초기 적재: 소비자마다 C·R 규칙 구독 + match → O(M·C·R).
- A 보고 1건: LTM이 모든 구독 S≈M·(C·R+감시+tombstone)을 선형 탐색 → O(M·C·R); 전체 O(R²·M·C). 이는 재구현 LTM의 선형 탐색에서 오며 ARBI 일반 성질로 확대하지 않는다.
- A 재배포: 바뀐 규칙 구독 해제·재구독 O(M·C·R) + match.
