"""UPWISE Chat for QGIS 배포 산출물 빌더 (S8).

무엇을 만드는가
    1. `upwise_chat_for_qgis.<version>.zip` - QGIS 플러그인 관리자가 "ZIP 에서
       설치" 로 바로 읽는 압축본. 최상위에 패키지 폴더 하나만 들어간다.
    2. `plugins.xml` - 커스텀 플러그인 저장소 피드. `packaging/plugins.xml.tmpl`
       을 metadata.txt 값으로 채운다.

단일 출처
    버전, 설명, 저자, 저장소 URL 등 모든 값은 `upwise_chat_for_qgis/metadata.txt`
    에서 읽는다. 이 스크립트는 metadata 에 없는 값(배포 호스팅 base URL)만
    상수로 가진다. 같은 사실을 두 곳에 적지 않기 위함이다.

재현성
    멤버 순서를 arcname 으로 정렬하고 압축 내부 타임스탬프를 ZIP 규격 하한
    (1980-01-01)으로 고정한다. 그래서 같은 입력이면 zip 바이트가 같다. QGIS
    설치기는 압축 내부 mtime 을 판정에 쓰지 않으므로 고정해도 설치에 영향이
    없다. 빌드마다 md5 가 달라지면 "무엇이 바뀌었나" 를 추적할 수 없다.

로그
    저장소 규칙대로 결과를 내는 코드는 CSV 파일 로그를 남긴다
    (`outputs/_logs/s8_zip_<시각>.csv`, 항목마다 즉시 flush).

실행
    "C:/Program Files/QGIS 3.44.14/bin/python-qgis-ltr.bat" packaging/build_zip.py
    (표준 라이브러리만 쓰므로 일반 python 으로도 돈다)

설계 정본: docs/1.mvp_design_v1.md 7-4(배포), 2(라이선스)
"""

import argparse
import csv
import datetime as dt
import hashlib
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

# ----------------------------------------------------------------------
# 경로와 상수
# ----------------------------------------------------------------------

PKG_NAME = "upwise_chat_for_qgis"

# 이 파일은 <repo>/packaging/build_zip.py 다. 프로젝트 절대경로를 박지 않는다
# (저장소 Python 경로 규칙).
REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / PKG_NAME
METADATA_FILE = PKG_DIR / "metadata.txt"
TEMPLATE_FILE = Path(__file__).resolve().parent / "plugins.xml.tmpl"

# zip 안 패키지 루트에 함께 넣을 리포 루트 파일. GPL 배포는 라이선스 전문을
# 받는 사람 손에 같이 주어야 하고, 설치본만 받은 사용자는 리포를 안 본다.
ROOT_FILES_IN_ZIP = ("LICENSE", "NOTICE")

# 배포 호스팅 base URL. metadata.txt 에 없는 값이라 여기 상수로 둔다.
# 근거: 사용자 확정 배포 채널 - plugins.xml 과 zip 을 같은 경로에 올린다
# (upwise.co.kr = upwise-edu.github.io Pages 커스텀 도메인).
DOWNLOAD_BASE_URL = "https://upwise.co.kr/plugins/"

# 제외 규칙. 컴파일 캐시와 숨김 파일은 설치본에 들어갈 이유가 없다.
EXCLUDE_DIR_NAMES = ("__pycache__",)
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".pyd")

# 압축 내부 타임스탬프 고정값. ZIP 규격이 1980 년 이전을 못 담는다.
ZIP_FIXED_DATETIME = (1980, 1, 1, 0, 0, 0)
# 0o644 (rw-r--r--). 유닉스에서 풀 때 실행 비트가 붙지 않게 고정한다.
ZIP_FILE_MODE = 0o644

# plugins.xml 에 채울 필드와 그 출처(metadata.txt 의 키).
# file_name 과 download_url 은 빌드 결과에서 조립하므로 여기에 없다.
XML_FIELD_FROM_METADATA = {
    "name": "name",
    "version": "version",
    "description": "description",
    "about": "about",
    "qgis_minimum_version": "qgisMinimumVersion",
    "qgis_maximum_version": "qgisMaximumVersion",
    "homepage": "homepage",
    "icon": "icon",
    "author_name": "author",
    "experimental": "experimental",
    "deprecated": "deprecated",
    "repository": "repository",
    "tracker": "tracker",
}


# ----------------------------------------------------------------------
# 로거
# ----------------------------------------------------------------------


class BuildLog:
    """빌드 한 줄을 즉시 flush 하는 CSV 로거."""

    COLUMNS = ["ts", "step", "item", "status", "detail"]

    def __init__(self, path):
        """로그 파일을 열고 헤더를 쓴다.

        Args:
            path: CSV 경로. 부모 폴더는 호출자가 만든다.
        """
        self.path = Path(path)
        self._fh = open(self.path, "w", encoding="utf-8", newline="")
        self._w = csv.writer(self._fh)
        self._w.writerow(self.COLUMNS)
        self._fh.flush()

    def row(self, step, item, status, detail=""):
        """한 줄 기록. 매 줄 flush 한다."""
        self._w.writerow([
            dt.datetime.now().isoformat(timespec="milliseconds"),
            step, item, status, str(detail).replace("\n", " | ")[:1500],
        ])
        self._fh.flush()
        say("[%s] %s %s %s" % (status, step, item, str(detail)[:120]))

    def close(self):
        """로그 파일을 닫는다."""
        self._fh.close()


def say(text):
    """콘솔 출력. cp949 콘솔에서 죽지 않게 폴백을 둔다."""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", "replace"))
        sys.stdout.flush()


def md5_of(path):
    """파일 md5."""
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


# ----------------------------------------------------------------------
# metadata.txt
# ----------------------------------------------------------------------


def parse_metadata(path):
    """metadata.txt 의 `[general]` 섹션을 dict 로 읽는다.

    configparser 를 쓰지 않는 이유: `about` 값에 콜론과 괄호가 섞인 긴 문장이
    들어가고, QGIS 자신도 단순 key=value 로 읽는다. 첫 `=` 만 분리한다.

    Args:
        path: metadata.txt 경로.

    Returns:
        dict: 키 -> 값(문자열). 값의 앞뒤 공백은 떼어낸다.
    """
    meta = {}
    in_general = False
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_general = line == "[general]"
            continue
        if not in_general or "=" not in line:
            continue
        key, value = line.split("=", 1)
        meta[key.strip()] = value.strip()
    return meta


def zip_file_name(version):
    """배포 zip 파일명. 버전은 metadata.txt 가 유일한 출처다."""
    return "%s.%s.zip" % (PKG_NAME, version)


# ----------------------------------------------------------------------
# zip
# ----------------------------------------------------------------------


def collect_members():
    """zip 에 담을 (원본 경로, arcname) 목록을 arcname 정렬로 돌려준다.

    Returns:
        list: [(Path, str)]. arcname 은 항상 `upwise_chat_for_qgis/...` 로
        시작하고 구분자는 슬래시다(zip 규격).
    """
    members = []
    for path in PKG_DIR.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(PKG_DIR)
        parts = rel.parts
        if any(part in EXCLUDE_DIR_NAMES for part in parts):
            continue
        if path.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        # 숨김 파일/폴더 제외. 윈도우 숨김 속성이 아니라 이름 규칙으로 가른다
        # (.gitignore, .DS_Store 같은 것이 설치본에 섞이지 않게).
        if any(part.startswith(".") for part in parts):
            continue
        members.append((path, "%s/%s" % (PKG_NAME, "/".join(parts))))

    # LICENSE, NOTICE 사본을 패키지 루트에 넣는다.
    for name in ROOT_FILES_IN_ZIP:
        src = REPO_ROOT / name
        if not src.is_file():
            raise RuntimeError("missing required root file: %s" % src)
        members.append((src, "%s/%s" % (PKG_NAME, name)))

    members.sort(key=lambda item: item[1])
    return members


def write_zip(target, members):
    """멤버를 결정적(deterministic) 순서와 타임스탬프로 zip 에 쓴다.

    Args:
        target: 만들 zip 경로.
        members: collect_members() 결과.
    """
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in members:
            info = zipfile.ZipInfo(arc, date_time=ZIP_FIXED_DATETIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ZIP_FILE_MODE << 16
            zf.writestr(info, src.read_bytes())


def verify_zip(target):
    """만든 zip 이 QGIS 설치 규격을 지키는지 자체 점검한다.

    Args:
        target: 검사할 zip 경로.

    Returns:
        list: 멤버 arcname 목록(정렬됨).

    Raises:
        RuntimeError: CRC 손상, 최상위 폴더가 1개가 아님, 금지 파일 포함,
            metadata.txt 위치 어긋남 중 하나라도 걸릴 때.
    """
    with zipfile.ZipFile(target) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("corrupt archive: %s" % target)
        names = sorted(zf.namelist())

    tops = sorted({n.split("/")[0] for n in names})
    if tops != [PKG_NAME]:
        raise RuntimeError("zip must hold exactly one top folder %r, got %r"
                           % (PKG_NAME, tops))
    junk = [n for n in names
            if "__pycache__" in n
            or n.lower().endswith(EXCLUDE_SUFFIXES)
            or any(part.startswith(".") for part in n.split("/"))]
    if junk:
        raise RuntimeError("excluded files leaked into the zip: %r" % junk)
    if "%s/metadata.txt" % PKG_NAME not in names:
        raise RuntimeError("metadata.txt must sit at the package root")
    return names


# ----------------------------------------------------------------------
# plugins.xml
# ----------------------------------------------------------------------


def render_plugins_xml(meta, zip_name):
    """plugins.xml 본문을 만든다.

    Args:
        meta: parse_metadata() 결과.
        zip_name: 같은 빌드에서 만든 zip 파일명.

    Returns:
        tuple: (치환이 끝난 XML 문서 문자열, 채워 넣은 필드 dict).

    Raises:
        RuntimeError: metadata.txt 에 필요한 키가 없거나 템플릿에 미치환
            치환자가 남았을 때.
    """
    values = {}
    missing = []
    for field, meta_key in XML_FIELD_FROM_METADATA.items():
        if meta_key not in meta:
            missing.append(meta_key)
            continue
        values[field] = meta[meta_key]
    if missing:
        raise RuntimeError("metadata.txt is missing keys: %r" % missing)

    # 이 두 값만 metadata 밖에서 온다. file_name 은 빌드 결과이고,
    # download_url 은 호스팅 상수 + 그 파일명이다.
    values["file_name"] = zip_name
    values["download_url"] = DOWNLOAD_BASE_URL + zip_name

    text = TEMPLATE_FILE.read_text(encoding="utf-8")
    for field, value in values.items():
        # XML 특수문자를 이스케이프한다. about 문장에 & 나 < 가 들어올 수 있다.
        text = text.replace("{{%s}}" % field, xml_escape(value))
    if "{{" in text:
        leftover = text[text.index("{{"):text.index("{{") + 40]
        raise RuntimeError("unreplaced placeholder in template: %r" % leftover)
    return text, values


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------


def default_dirs():
    """산출물과 로그의 기본 폴더.

    산출물은 플러그인 리포 밖(모노리포 `outputs/`)에 둔다. 배포 zip 을 리포
    트리에 넣으면 커밋 대상과 산출물이 섞인다. 모노리포 밖에서 clone 해 쓸
    때는 그 폴더가 없으므로 리포 안 `dist/` 로 떨어뜨린다.

    Returns:
        tuple: (out_dir, log_dir)
    """
    mono_outputs = REPO_ROOT.parent / "outputs"
    if mono_outputs.is_dir():
        return (mono_outputs / "s8_package", mono_outputs / "_logs")
    return (REPO_ROOT / "dist", REPO_ROOT / "dist" / "_logs")


def build(out_dir=None, log_dir=None):
    """zip 과 plugins.xml 을 만들고 경로를 돌려준다.

    Args:
        out_dir: 산출물 폴더. None 이면 default_dirs().
        log_dir: 로그 폴더. None 이면 default_dirs().

    Returns:
        dict: zip, xml, log, members, values 키를 가진 결과 요약.
    """
    default_out, default_log = default_dirs()
    out_dir = Path(out_dir) if out_dir else default_out
    log_dir = Path(log_dir) if log_dir else default_log
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    stamp = dt.datetime.now().strftime("%y%m%d_%H%M%S")
    log = BuildLog(log_dir / ("s8_zip_%s.csv" % stamp))
    try:
        log.row("param", "repo_root", "INFO", str(REPO_ROOT))
        log.row("param", "out_dir", "INFO", str(out_dir))
        log.row("param", "python", "INFO", sys.version.split()[0])

        meta = parse_metadata(METADATA_FILE)
        version = meta.get("version")
        if not version:
            raise RuntimeError("metadata.txt has no version")
        log.row("meta", "version", "INFO", version)
        log.row("meta", "metadata.txt md5", "INFO", md5_of(METADATA_FILE))
        if meta.get("email", "").startswith("TODO"):
            # 공개 배포 전에 반드시 채워야 하는 값이다. 빌드를 막지는 않는다.
            log.row("meta", "email", "WARN",
                    "email=%s - 공개 배포 전 필수(plugins.qgis.org 요구)"
                    % meta.get("email"))

        zip_name = zip_file_name(version)
        zip_path = out_dir / zip_name
        members = collect_members()
        write_zip(zip_path, members)
        names = verify_zip(zip_path)
        log.row("zip", zip_name, "OK",
                "members=%d bytes=%d md5=%s"
                % (len(names), zip_path.stat().st_size, md5_of(zip_path)))
        for name in names:
            log.row("zip", name, "MEMBER", "")

        xml_text, values = render_plugins_xml(meta, zip_name)
        xml_path = out_dir / "plugins.xml"
        xml_path.write_text(xml_text, encoding="utf-8", newline="\n")
        log.row("xml", "plugins.xml", "OK",
                "bytes=%d md5=%s" % (xml_path.stat().st_size, md5_of(xml_path)))
        for field in sorted(values):
            log.row("xml", field, "FIELD", values[field])

        return {"zip": zip_path, "xml": xml_path, "log": log.path,
                "members": names, "values": values}
    finally:
        log.close()


def main(argv=None):
    """CLI 진입점."""
    parser = argparse.ArgumentParser(
        description="Build the QGIS-installable ZIP and plugins.xml feed.")
    parser.add_argument("--out-dir", default=None,
                        help="output folder (default: monorepo outputs/s8_package)")
    parser.add_argument("--log-dir", default=None,
                        help="CSV log folder (default: monorepo outputs/_logs)")
    args = parser.parse_args(argv)
    result = build(args.out_dir, args.log_dir)
    say("zip=%s" % result["zip"])
    say("xml=%s" % result["xml"])
    say("log=%s" % result["log"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
