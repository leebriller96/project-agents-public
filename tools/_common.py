# _common.py — tools/*.py 가 함께 쓰는 경로 해석·파일 잠금·번호 발급 유틸리티
#
# 배경: rr.py·gate.py·status.py 가 workspace 경로 계산을 각자 복사해 쓰고 있었고,
#       RR·OI 채번이 "최대 번호 + 1 → 덮어쓰기" 방식이라 병렬 에이전트가 동시에 호출하면
#       같은 번호를 받아 서로 덮어썼다(6건 동시 생성 → RR 4건·OI 2건만 남음, 2026-09-28 재현).
#       여기서는 OS 공통(Windows·Linux·macOS)으로 동작하는 잠금 파일 방식과 배타적 생성으로 이를 막는다.
#
# 의존성: pyyaml

import contextlib
import errno
import os
import re
import sys
import time

try:
    import yaml
except ImportError:
    sys.exit("[tools] pyyaml 패키지가 필요합니다. 설치: python -m pip install pyyaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 잠금 대기 한도(초)와, 이보다 오래된 잠금 파일은 죽은 프로세스가 남긴 것으로 보고 회수하는 기준(초)
LOCK_TIMEOUT = 60.0
LOCK_STALE = 300.0


def fix_console_encoding():
    """Windows 콘솔(cp949)에서도 한글이 깨지지 않도록 출력 인코딩을 UTF-8 로 고정한다."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_yaml(path):
    """YAML 파일을 읽는다. 비어 있으면 빈 dict."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dump_yaml(path, data):
    """YAML 을 원자적으로 쓴다(임시 파일에 쓴 뒤 교체). 쓰는 도중 중단돼도 원본이 반쯤 잘리지 않는다."""
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    atomic_write_text(path, text)


def atomic_write_text(path, text):
    """같은 디렉토리의 임시 파일에 쓰고 os.replace 로 교체한다."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    # Windows 에서 다른 프로세스가 대상 파일을 잠깐 열고 있으면 PermissionError 가 날 수 있어 짧게 재시도한다
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    os.replace(tmp, path)


def safe_relpath(path, start):
    """start 기준 상대경로(구분자 /). Windows 에서 드라이브가 다르면(C: 와 D:) 상대경로가 없으므로 절대경로를 돌려준다."""
    try:
        return os.path.relpath(path, start).replace(os.sep, "/")
    except ValueError:
        return os.path.abspath(path).replace(os.sep, "/")


def config():
    """config/project.yaml 을 읽는다. 없거나 깨졌으면 빈 dict."""
    try:
        return load_yaml(os.path.join(ROOT, "config", "project.yaml"))
    except Exception:
        return {}


def workspace():
    """workspace/<project>/ 경로. 프로젝트명은 config 의 project.name, 없으면 workspace/ 바로 아래(구 구조)."""
    name = (config().get("project") or {}).get("name")
    return os.path.join(ROOT, "workspace", name) if name else os.path.join(ROOT, "workspace")


def target_dir():
    """생성 소스가 들어가는 target_dir 절대경로. 설정이 없으면 None."""
    td = (config().get("project") or {}).get("target_dir")
    if not td:
        return None
    return td if os.path.isabs(td) else os.path.normpath(os.path.join(ROOT, td))


@contextlib.contextmanager
def file_lock(path, timeout=LOCK_TIMEOUT, stale=LOCK_STALE):
    """`<path>.lock` 을 배타적으로 만들어 잠근다. 병렬 에이전트의 읽기-수정-쓰기 경합을 막는다.

    fcntl/msvcrt 대신 O_EXCL 파일 생성을 쓰는 이유: 두 OS 에서 동일하게 동작하고,
    잠금 보유자가 비정상 종료해도 stale 기준으로 회수할 수 있다.
    """
    lock = f"{path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock)), exist_ok=True)
    deadline = time.monotonic() + timeout
    delay = 0.01
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except OSError as ex:
            if ex.errno not in (errno.EEXIST, errno.EACCES):
                raise
            try:
                if time.time() - os.path.getmtime(lock) > stale:
                    os.remove(lock)   # 죽은 프로세스가 남긴 잠금 회수
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError(f"잠금 대기 시간 초과: {lock} (다른 프로세스가 잡고 있거나 남은 잠금 파일)")
            time.sleep(delay)
            delay = min(delay * 2, 0.2)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def numbering_start(prefix):
    """config 의 `numbering.<prefix 소문자>_start` — 채번 시작 번호. 없으면 1.

    배경(실측): 번호(OI·JD·RR·CR)는 target 소스 주석에 박히는 순간 **그 저장소의 공용 자원**이 된다.
    그런데 이력이 담긴 workspace 는 작업 환경마다 다르다. 환경을 옮기면 max+1 채번이 1 부터 다시 시작해
    이미 다른 뜻으로 쓰인 번호와 **정면 충돌**한다(2026-10-05 실측: oi import 가 매긴 번호 3개가
    target 주석의 같은 번호와 충돌). 그래서 "그쪽 최대 번호 + 여유" 를 시작 번호로 적어 둔다.
    """
    try:
        n = ((config().get("numbering") or {}).get(f"{prefix.lower()}_start"))
        return int(n) if n else 1
    except Exception:
        return 1


def next_number(names, prefix, width=4, start=None):
    """이름 목록에서 `<prefix>-NNNN` 의 최대값 + 1 을 돌려준다.

    `start`(없으면 config 의 numbering) 보다 작으면 `start` 를 쓴다 — 빈 환경에서 1 로 돌아가지 않게.
    """
    pat = re.compile(rf"^{re.escape(prefix)}-(\d{{{width}}})$")
    nums = [int(m.group(1)) for n in names for m in [pat.match(str(n))] if m]
    nxt = (max(nums) + 1) if nums else 1
    return max(nxt, start if start is not None else numbering_start(prefix))


def create_numbered_file(directory, prefix, ext=".yaml", width=4, start=None):
    """`<prefix>-NNNN<ext>` 파일을 배타적으로 만들고 (id, path) 를 돌려준다.

    잠금 안에서 번호를 정하고, 생성도 O_EXCL 로 해 이미 있는 파일은 절대 덮어쓰지 않는다.
    """
    os.makedirs(directory, exist_ok=True)
    with file_lock(os.path.join(directory, f".{prefix.lower()}-seq")):
        stems = [os.path.splitext(n)[0] for n in os.listdir(directory) if n.endswith(ext)]
        n = next_number(stems, prefix, width, start)
        while True:
            rid = f"{prefix}-{n:0{width}d}"
            path = os.path.join(directory, rid + ext)
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return rid, path
            except FileExistsError:
                n += 1
