<!-- pipeline-core §16 — 핵심(SKILL.md)의 절 목록에서 가리키는 절. 필요한 작업일 때만 읽는다. -->

## 16. 훅에 의한 강제 (`.claude/settings.json`)

지침은 읽히지 않거나 잊힐 수 있으므로 핵심 원칙은 훅이 도구 호출 시점에 막는다. 훅이 막으면 우회하지 말고 원인을 고친다.

| 훅 | 막는 것 | 대응 |
|---|---|---|
| PreToolUse (쓰기·Bash) | 이모지가 든 쓰기 | 텍스트로 바꿔 다시 쓴다 |
| PreToolUse (쓰기) | **공개본 금지어가 든 쓰기** — 이 저장소의 git 에 올라가는 파일에 고객 식별 문자열 (`config/publish-public/rules.yaml` 의 `deny`). gitignore 대상·저장소 밖·규칙 파일 자신은 보지 않는다 | 일반화해서 다시 쓴다(프로젝트명 `demo`·패키지 `com.example`·시스템명은 유형). 실제 이름은 `workspace/` 에만 둔다 |
| PreToolUse (state.yaml) | 게이트를 통과하지 못한 단계·slice 를 `done` 으로 바꾸는 편집 | 레포트·`pa-meta` 를 고쳐 `gate.py check` 통과 후 `python tools/state.py set ... --value done` 으로 기록, 아니면 `--value blocked --reason` |
| PreToolUse (Bash·PowerShell) | Bash 로 state.yaml 에 쓰기(sed·리다이렉션·python 쓰기). PowerShell 로 보호 대상(state.yaml·잠긴 spec·`specs/`·`visual/` 기록)에 쓰기 — 쓰기 계열 cmdlet 전반(내용 쓰기 `Set-Content`·`Add-Content`·`Clear-Content`·`Out-File`·`Tee-Object`, 생성 `New-Item`, 내보내기 `Export-Csv`·`Export-Clixml`·`Export-Alias`·`Export-FormatData`·`Start-Transcript`·`Compress-Archive`·`Expand-Archive`·`Invoke-WebRequest/RestMethod -OutFile`, 삭제·복사·옮기기 `Remove-Item`·`Copy-Item`·`Move-Item`·`Rename-Item`, 별칭·모듈 한정 이름·매개변수 약어(`-Dest`) 포함), 따옴표 밖 리다이렉션(`>`·`>>`·`2>`·`*>`), `[IO.File]::Write*/Create/Open*` 류, python 쓰기·`sed -i`. 쓰기 대상이 리터럴이 아니면(변수·식·`Join-Path`·파이프 입력) 명령에 보호 대상 이름이 보일 때 보수적으로 막는다. 한계: 정적 판정이라 보호 대상 이름이 명령 어디에도 보이지 않는 간접 쓰기(이름 조립·다른 스크립트 실행)는 못 본다 — 게이트·selfcheck 가 2차 | 상태 값은 `python tools/state.py set` 으로 고친다(이 도구 실행은 막지 않는다 — done 전환에 같은 게이트를 스스로 돌리므로 하네스 밖에서도 지켜진다). 구조 변경만 Edit 도구 |
| PreToolUse (Bash·PowerShell) | 보호 폴더 통째 삭제·이동 — `workspace/<project>/specs`·`visual` 과 그 상위(`workspace`, `workspace/<project>`), 잠긴 파일이 든 상위 폴더, 절대 경로로 적은 target_dir·저장소 루트와 그 상위(파일 시스템 루트 `/`·`/*` 는 판정 제외)를 끝 `/` 유무·대소문자·글자 패턴(`spec*`·`[sv]*`·`work*`)과 관계없이 지우거나 옮기기. Bash 는 `rm`·`rmdir`·`unlink`·`mv`·`git rm`·`git mv`·`find -delete`·`find -exec rm`·`xargs rm`(xargs 는 옵션과 값을 건너뛴 첫 명령 낱말로 판정하고 `git` 이면 git 판정을 따른다)과 앞붙이(`sudo`·`timeout`·`nice`·`env`·`export`·`for`)·`git -C`, `find` 는 시작 경로와 이름 조건(`-name specs`·`-path '*/specs/*'`, 저장소 안을 돌 때), PowerShell 은 `Remove-Item`·`Move-Item`·`Rename-Item`·`[IO.File]`·`[IO.Directory]` 의 `Delete`·`Move`·`git rm`·`git mv`. 상위 폴더 판정은 **지우거나 옮기는 원본**에만 쓴다 — `mv`·`git mv`·`Move-Item` 의 목적지는 `specs`·`visual` 안일 때만 막고 프로젝트 폴더로 넣는 이동은 통과한다(두 셸 판정이 같다). 변수(`$D`·`${D}`)는 같은 명령의 대입값으로 펼치고(`for` 목록 포함), 대상이 파이프 입력·식이면 같은 문장의 경로를 대상으로 본다. PowerShell 은 쉼표 목록과 매개변수 별칭(`-LP`·`-Cf`·`-ea`)을 푼다. **`git clean -x`·`-X`** 는 gitignore 대상인 `workspace/` 를 지워 복구할 수 없으므로 막는다 — `-n`(미리 보기)과 대상이 workspace 밖임이 리터럴로 보이는 경로는 통과. `git -C` 기준 폴더도 같은 기준이라 절대 경로(`git -C /x clean -fdx`)만 통과하고 `..` 로 시작하는 경로(`git -C ../wt clean -fdx`)는 막는다. 읽기·복사 원본·따옴표 안 문구·heredoc 본문(구분자 `E`·`'E'`·`"E"`·`\E`)·작업 트리를 건드리지 않는 `git rm --cached`(`xargs` 입력 포함)·`git clean -fd` 는 막지 않는다. 남는 한계는 표 아래 절 | 지우지 않는다. 잠금은 `spec_lock.py`, 기준 이미지 승인은 `visual.py` 로만 바뀐다 |
| PreToolUse (Bash·PowerShell) | git 훅 우회 — `--no-verify`·`commit -n`·`-c core.hooksPath=…` | 쓰지 않는다. 훅이 막으면 원인을 고치고, 훅이 잘못됐으면 사용자에게 보고한다 |
| SubagentStop | 파이프라인 에이전트가 `pa-agent-result` 블록 없이·깨진 JSON·필수 키 누락·이모지 포함으로 끝내기, 블록 밖 산문 3000자 초과. 블록 머리는 `json pa-agent-result`·`pa-agent-result` 둘 다 받는다. 보고를 인계 도구(SubagentHandback)로 넘겼으면 transcript 의 인계 메시지를 보고로 읽는다 | 블록을 보완하거나 상세를 레포트 파일로 옮기고(`report_file`) 다시 끝낸다 |
| PreToolUse (SubagentHandback) | 인계 보고를 넘기기 전에 블록 결손·깨진 JSON·필수 키 누락·이모지만 막는다. 산문 상한은 막지 않고 경고만 내며 결과 블록을 저장한다(인계로 끝나는 실행은 SubagentStop 이 보고를 못 볼 수 있다). 훅 입력에 에이전트 유형이 없으면 블록의 `agent` 로 판단하므로, 블록이 아예 없는 인계는 SubagentStop 이 2차로 본다 | 블록을 보완해 다시 넘긴다 |
| SubagentStop (받아들인 뒤) | 막지 않음 — 결과 블록을 `workspace/<project>/reports/agent-results/<시각>_<에이전트>_<단계>_<slice>.json` 에 저장. 인계 시점과 SubagentStop 이 같은 보고를 두 번 보면 최근 10분 안에 수정된 파일(최대 30개)과 내용을 비교해 한 파일만 남긴다. 10분이 지난 재실행은 내용이 같아도 새 파일로 남는다. 비교 중 파일이 사라져도 이번 블록은 저장한다 | 오케스트레이터가 `tools/ingest_result.py --json <파일>` 로 옮긴다 |
| PostToolUse (Bash) | 막지 않음 — 6000자를 넘는 출력을 로그 파일로 빼고 앞부분·오류·실패·결과 요약·끝부분만 보인다(§26) | 더 필요하면 로그를 Grep. 전체가 꼭 필요하면 명령에 `PA_FULL_OUTPUT=1` |

**보호 폴더 판정의 한계**: 이 판정은 실수로 나올 만한 명령의 사고를 막는 장치이지 일부러 돌아가는 경로를 막는 보안 경계가 아니다. 아래는 알고 남긴 것이다(잠금 내용은 `spec_lock.py verify`·게이트가 2차로 본다).

- 셸 문법: Bash 명령도 PowerShell 과 같은 토크나이저로 나눈다. 역슬래시 escape·`#` 주석·역따옴표 치환을 모른다. 짝이 안 맞는 따옴표(`echo it\'s; rm -rf …`, 주석 안의 `don't`)가 있으면 뒤의 명령 전체가 문자열로 읽혀 판정이 조용히 빠지고, 역따옴표 안 명령과 `$(…)` 로 만든 대상(`rm -rf $(ls …)`)은 보지 않는다.
- 다른 해석기·메서드: `bash -c`·`cmd /c`(`rd /s /q`·`rmdir /s /q`)·`powershell -Command`·`pwsh -Command`·`Invoke-Expression`·dot 호출(`. Remove-Item`)·`python -c` 와 스크립트 안의 `shutil.rmtree`·`os.remove`·객체 메서드 `(Get-Item …).Delete()`·`.MoveTo()`·`robocopy /MIR`·다른 스크립트 실행·이름 조립은 못 본다.
- 현재 폴더: 훅 입력의 `cwd` 를 쓰지 않고 `cd`·`pushd`·`Set-Location`·`Push-Location` 도 따라가지 않는다. 그 뒤의 상대 이름(`rm -rf specs`·`rm -rf *`·`rm -rf ../specs`)·`rm -rf .`, 앞선 호출에서 바꾼 현재 폴더, 상대 표기의 저장소 루트·target_dir(`rm -rf ../<저장소>`)은 못 본다.
- 삭제 자체를 못 보는 형태(`specs` 를 직접 적어도 통과): 앞붙이의 긴 옵션 값(`sudo --user root rm -rf …/specs`), 괄호 조건을 붙인 `find`(`find …/specs \( -name a -o -name b \) -delete`), `xargs -I {}` 로 부르는 git(`ls … | xargs -I {} git rm {}`, 같은 형태의 `rm` 은 막힌다), `while read` 파이프(`ls …/specs | while read f; do rm -f "$f"; done`). 마지막은 세미콜론에서 문장이 끊기고 Bash 의 모르는 변수를 동적 대상으로 보지 않기 때문이다.
- 상위 폴더까지 못 보는 형태(`specs`·`visual` 경로가 명령에 보이면 막히지만 `workspace/<project>` 는 통과): 여러 줄에 걸친 파이프 입력(`foreach` 본문 등), `[IO.Directory]::Delete` 의 변수 인자.
- 글자 패턴이 앞 구간을 가린 형태: `rm -rf */*/specs`·`rm -rf **/specs`. 별표뿐인 구간은 아무 폴더에나 맞아 판단 근거로 쓰지 않으므로 `workspace` 구간을 찾지 못한다.
- 쓰기: Bash 의 `cp`·리다이렉션·`sed -i` 로 보호 폴더에 쓰는 것은 이 판정 대상이 아니다(잠긴 파일 자체는 잠금 판정이 본다).
- 뒷부분 일치(후속 없음): 상대·저장소 밖 경로는 끝부분으로 판정해 `rm -rf /tmp/x/workspace`·`rm -rf ../wt-a/server/user`·`rm -rf test/java` 가 막히고, 점이 든 프로젝트 이름(`rm -rf workspace/my.proj`)은 파일로 보아 통과한다.
- 보수 판정(후속 없음): 대상이 리터럴이 아니면 명령에 보이는 `specs`·`visual` 경로로 막아 `Remove-Item $tmp; Get-Content …/specs/a.json` 이 막히고, 프로젝트 폴더를 시작점으로 도는 `find workspace/<p> -maxdepth 1 -name '*.tmp' -delete` 도 막힌다. 대상을 리터럴로 쓰면 풀린다.
- 예외(후속 없음): 한 호출의 판정은 하나의 예외 처리 안에 있어 앞선 판정이 예외를 내면 뒤의 판정이 함께 꺼지고, pre-commit 의 스테이지 목록 조회(`git diff`)가 실패하면 빈 목록으로 통과한다.

**git pre-commit 훅 (하네스 밖)**: 위 훅은 Claude Code 에서만 돈다. 다른 에이전트·사람의 커밋에도 같은 기준을 걸도록
`tools/hooks/pre-commit`(검사 본체 `tools/hooks/pre_commit.py`)이 스테이지된 파일의 이모지(`quality.py` NO-EMOJI)와
커밋 금지 경로(`workspace/`·`docs/samples/`·`config/project.yaml`)를 막는다. 작업 사본마다 `python tools/install_hooks.py` 로 한 번 설치하고
(다시 실행해도 같다, 다른 훅이 있으면 덮어쓰지 않고 알린다), 설치 여부는 selfcheck 가 경고로 알린다.
**`git commit --no-verify`·`-n`·`core.hooksPath` 덮어쓰기로 이 훅을 끄지 않는다** — 막히면 원인을 고친다.

PreToolUse·SubagentStop 훅 명령과 git pre-commit 훅은 python 을 `py -3` → `python3` → `python` 순서로 실제 실행해 보고 고른다(PostToolUse 는 PATH 의 `python`·`python3`). Claude Code 훅(guard.py)은 훅 자체 오류로 작업을 막지 않으며, 게이트·selfcheck·CI 가 2차 방어선이다. git pre-commit 훅은 python 을 못 찾으면 경고만 내고 통과시키지만, python 이 있는데 검사 본체가 오류로 끝나면(스테이지 내용을 꺼내지 못함·판정 모듈이 깨짐 포함) **커밋을 막는다** — 통과로 보지 않고 원인을 고친다. gitlink(하위 모듈, mode 160000)는 내용이 없어 이모지 검사만 제외한다.
