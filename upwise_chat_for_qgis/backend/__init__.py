"""백엔드 계층 (설계 S2, 0.5.5 어댑터 경계).

백엔드 CLI 를 서브프로세스로 띄우고, 그 표준 출력을 UI 가 쓸 수 있는
형태로 넘기는 층이다. 모듈 경계는 설계 7-4 리포 레이아웃을 따른다.

    adapter.py          백엔드 어댑터 계약(docs/7 2-10). 구체 백엔드 무의존
    adapter_claude.py   Claude Code CLI 결박. 고유 리터럴이 여기 모인다
    adapter_registry.py 등록·선택. 제2 백엔드가 들어오는 자리
    posture.py  플래그 조립(설계 5)과 기동 자기점검 게이트(설계 3-4)
    logbook.py  stdout 전 줄 jsonl 녹화와 진단 로그(설계 7-4)
    process.py  spawn, 리더/라이터 스레드, 50 ms 드레인, 트리 종료, 재시작(설계 2)
    protocol.py stream-json 파싱, 이벤트 모델, cat -n 제거(설계 4-2, 4-3, 4-4)
    machine.py  턴 상태머신, 전사 블록, 도구 카드, 거부 묶음(설계 4-1 ~ 4-5)

이 층은 Qt 위젯을 모른다. protocol.py 와 machine.py 는 Qt 조차 import 하지
않는다. 녹화본 재생 검증이 QGIS 없이 돌아야 하기 때문이다(설계 10 보조 원칙).

0.5.5 부터 `process.py`·`machine.py` 와 제품 조립 지점(`plugin.py`)은
**어떤 백엔드를 띄우는지 모른다.** 실행 파일 탐지·argv 플래그·입력 직렬화·
이벤트 스키마·게이트 항목을 어댑터에 물어 본다. 그래서 제2 백엔드(OpenAI
Codex CLI)는 `adapter_codex.py` 하나와 레지스트리 등록 한 줄로 들어온다.
`detect.py`·`posture.py`·`protocol.py` 는 Claude 어댑터가 묶는 Claude 쪽
구현이고, 제2 백엔드는 자기 구현을 가져온다(docs/7 2-10, 4-1).
"""
