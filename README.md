# DualAI

하나의 질문을 기존 ChatGPT와 Gemini 웹서비스에 전달하는 Windows 개인용 도구입니다.
OpenAI/Gemini API, 자체 백엔드, 대화 저장 DB를 사용하지 않습니다.

## 실행

빌드된 **dist/DualAI.exe**를 더블클릭하세요. Python이나 터미널은 필요하지 않습니다.
PC에 Chrome 또는 Microsoft Edge가 설치되어 있어야 합니다.

1. 상단 DualAI 입력창과 좌우 브라우저 창이 열립니다.
2. 왼쪽 ChatGPT와 오른쪽 Gemini에 **직접 로그인**하세요.
3. 공통 질문을 입력하고 **둘 다 전송** 또는 **Ctrl+Enter**를 누르세요.
4. 답변, 모델 선택, 기존 대화, 검색, 첨부는 각 서비스의 원래 화면에서 사용하세요.
5. 실패한 서비스의 **실패 재시도**는 해당 서비스에 마지막으로 요청한 질문만 다시 보냅니다.

Enter와 Shift+Enter는 모두 줄바꿈입니다. 한글 조합 중 Enter가 질문을 전송하지 않습니다.
공통 입력창은 전송 후 유지됩니다. 같은 질문의 성공한 서비스는 중복 전송을 건너뜁니다.
전송 여부가 불확실하면 해당 서비스 전송을 잠급니다. 실제 화면을 확인하고 새 대화를 시작하면 잠금이 해제됩니다.
새 대화는 선택한 서비스의 시작 주소로 이동합니다. 기존 대화 기록을 삭제하지 않습니다.
서비스에 직접 작성 중인 다른 글이 있으면 덮어쓰지 않고 실패로 표시합니다.

## 화면과 세션

하나의 네이티브 웹뷰 창이 아니라 **공통 입력창 + 실제 브라우저 창 2개**입니다.
상단 **화면 정렬**로 입력창이 있는 모니터에 다시 배치합니다.
좌우 비율 슬라이더를 드래그해 30:70~70:30으로 조절하며 기본값은 50:50입니다.
운영체제의 개별 창 최소화/이동은 가능합니다. 세 창의 최소화가 함께 연동되지는 않습니다.
프로그램을 종료하면 전용 브라우저도 종료합니다. 일반 브라우저 창은 건드리지 않습니다.

전용 프로필: `%LOCALAPPDATA%/DualAI/Chrome` 또는 `%LOCALAPPDATA%/DualAI/Edge`.
최초 로그인 후 브라우저가 쿠키와 정상 세션을 유지합니다. 서비스의 만료/보안 정책에 따라 재로그인이 필요할 수 있습니다.
기존 일반 브라우저 프로필에서 쿠키나 비밀번호를 복사하지 않습니다.
비밀번호를 앱이 수집하지 않습니다. 브라우저 자체 암호 저장 안내는 사용자가 선택합니다.
질문과 전송 결과는 앱 메모리에만 존재하고 종료 시 사라집니다.
브라우저의 방문 기록/캐시 및 서비스 자체의 대화 보관 정책은 그대로 적용됩니다.
설정 파일에는 좌우 비율만 저장합니다.

## 기술 선택

- Python + Tkinter: 가벼운 네이티브 입력창, Windows 단일 exe 패키징.
- 설치된 Chrome/Edge: 일반 브라우저 로그인/팝업/첨부 흐름 사용.
- 전용 프로필 + 임의의 localhost CDP 포트: 기존 개인 프로필과 분리.
- Playwright CDP 연결: DOM의 입력창, 접근 가능한 버튼 이름, 안정적인 속성을 순서대로 탐색.
- 서비스별 어댑터: `dualai/adapters.py`의 SITES에서 선택자와 새 대화 주소를 관리.
- 전송 후 새 사용자 메시지 또는 입력창 초기화 + 생성 중 상태로 전달 여부 확인.
- 서비스별 독립 비동기 전송. 실제 버튼 클릭 이후 불확실한 상태에서는 자동 재시도 없음.
- 브라우저 자동화 감지를 숨기거나 인증 제한을 우회하지 않습니다.

임베디드 웹뷰는 Google 로그인 제한 가능성이 있어 선택하지 않았습니다.
Chrome 136 이후 CDP는 기본 사용자 프로필 대신 별도 user-data-dir가 필요합니다.
로컬 CDP는 이 앱의 전용 브라우저를 제어할 수 있는 권한입니다. localhost에만 연결하며 앱 종료 시 닫습니다.
사이트가 UI/로그인 정책을 바꾸면 어댑터 수정이 필요할 수 있으며, 로그인 성공을 모든 계정에서 보장할 수는 없습니다.

근거:
- [Google OAuth 정책](https://developers.google.com/identity/protocols/oauth2/policies)
- [Chrome 원격 디버깅과 전용 프로필](https://developer.chrome.com/blog/remote-debugging-port)
- [Playwright CDP 연결](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)

## 개발 및 빌드

Python 3.11 이상, Windows, Chrome/Edge가 필요합니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py
.venv/Scripts/python.exe -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File build.ps1
```

`dist/DualAI.exe`만 다른 Windows PC로 복사할 수 있습니다. 서명되지 않은 개인용 빌드입니다.
브라우저 바이너리는 포함하지 않으며 설치된 브라우저를 사용합니다.

## 검증 범위

테스트는 로컬 HTML을 실제 Edge/Chrome 엔진에 공급합니다. 실제 서비스로 질문을 전송하지 않습니다.
한글/영문/긴 질문/줄바꿈/코드/특수문자, 버튼 탐색 대안, 기존 초안 보존,
생성 중 차단, 한쪽 실패 격리, 불확실한 전송 중복 방지, 새 대화를 검증합니다.
실제 계정 로그인, 구독 모델, 실제 질문에 대한 응답과 재실행 후 로그인 유지 여부는 사용자 계정으로 별도 확인해야 합니다.

## 확장 위치

- 서비스 추가: SITES와 Adapter의 서비스 특화 로직 확장
- 창/프로필 제어: dualai/browser.py
- 공통 입력, 실패 상태, 재시도: dualai/app.py

답변 수집/비교, 공통 첨부, 히스토리는 MVP에 포함하지 않았습니다.
