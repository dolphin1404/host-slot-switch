# Host Slot Switch

[English](https://github.com/dolphin1404/host-slot-switch/blob/main/README.md)

장치의 물리 선택 버튼을 누르지 않고 키보드 단축키로 호스트 슬롯을 바꾸는
독립 오픈소스 도구입니다. Logitech® MX Vertical™ Advanced Ergonomic
Mouse의 Easy-Switch™ 호스트 슬롯으로 테스트했습니다.

기본 설정은 다음과 같습니다.

| 단축키 | 대상 | 슬롯 |
| --- | --- | ---: |
| `Ctrl+Shift+1` | 노트북 | 1 |
| `Ctrl+Shift+2` | Linux 데스크톱 | 2 |
| `Ctrl+Shift+3` | 세 번째 호스트 | 3 |

Linux에서는 검증된 Solaar CLI와 GNOME 전역 단축키를 사용합니다. Windows에서는
HIDAPI로 Logitech 전용 HID 컬렉션에 접근하고 사용자 권한의 작은 전역 단축키
리스너를 실행합니다. 관리자 권한은 필요하지 않습니다.

## 꼭 알아둘 점

전환 명령은 **마우스가 현재 연결된 컴퓨터**에서만 보낼 수 있습니다.
왕복하려면 양쪽에 도구가 있어야 합니다.

```text
Linux 슬롯 2  -- Ctrl+Shift+1 -->  노트북 슬롯 1
노트북 슬롯 1 -- Ctrl+Shift+2 -->  Linux 슬롯 2
```

왕복하려면 Linux와 Windows 양쪽에 설치합니다. Windows 백엔드는 수신기 장치
인덱스와 `0x1814` 기능 인덱스를 실행 시점에 조회하며 고정값을 사용하지 않습니다.
Windows 구현은 실제 장치·펌웨어 조합에 따른 검증이 더 필요한 실험 단계입니다.

## 빠른 설치 (Ubuntu/Debian)

GitHub 릴리스 wheel을 별도 가상환경에 설치합니다.

```bash
sudo apt install solaar python3-venv
python3 -m venv ~/.local/share/host-slot-switch/venv
~/.local/share/host-slot-switch/venv/bin/pip install https://github.com/dolphin1404/host-slot-switch/releases/download/v0.2.1/host_slot_switch-0.2.1-py3-none-any.whl
~/.local/share/host-slot-switch/venv/bin/host-slot-switch config init
~/.local/share/host-slot-switch/venv/bin/host-slot-switch doctor
```

## 빠른 설치 (Windows 10/11)

Python 3.10 이상을 설치한 뒤 v0.2.1 릴리스의 `install-windows.ps1`을
다운로드합니다. 마우스가 Windows에 연결된 상태에서 PowerShell로 실행하세요.

```powershell
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

사용자 폴더에 설치되며 관리자 권한은 필요 없습니다. 검사 과정에서 HID 장치를
열지 못하면 Logi Options+를 잠시 종료하고 다시 실행하세요.

v0.2.1부터 직접 Bluetooth 연결에서는 Windows의 응답 확인형 HID 제어 출력
경로를 사용합니다. 일반 HIDAPI 쓰기가 성공으로 표시되고도 BLE 장치에 전달되지
않는 Windows 동작을 피하기 위한 처리입니다.

`sudo`는 위의 첫 번째 `apt` 명령에만 사용합니다. 그 뒤의 `pip`,
`host-slot-switch`, Solaar 명령은 모두 로그인한 데스크톱 사용자로 실행하세요.
hidraw 장치를 `MODE=0666`으로 여는 규칙을 추가하지 말고 배포판의 Solaar
udev 규칙을 사용합니다.

`doctor`의 `offline`은 원인이 하나로 확정됐다는 뜻이 아닙니다. 마우스가
절전 중이거나 꺼져 있거나, 통신 범위를 벗어났거나, 다른 호스트에 연결된
상태일 수 있습니다. 먼저 마우스를 깨우고 움직여 보세요. 계속 offline이면
최초 소프트웨어 전환 시험 전에 하단 버튼으로 이 컴퓨터의 슬롯을 한 번
선택합니다.

단축키를 설치하기 전에 반드시 `doctor`를 실행하고, 의도한 장치 하나만
식별되며 `change-host`가 확인될 때만 진행하세요. 장치 선택자가 모호하다는
오류가 나오면 `solaar show`에서 해당 마우스의 serial을 확인한 뒤 설정의
`device` 필드에 넣거나 아래처럼 override를 검증하고 설치 명령에 유지합니다.

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch --device SERIAL doctor
~/.local/share/host-slot-switch/venv/bin/host-slot-switch --device SERIAL hotkeys install --dry-run
~/.local/share/host-slot-switch/venv/bin/host-slot-switch --device SERIAL hotkeys install
```

로그를 공유할 때 장치 serial은 비공개 정보로 취급하세요.

GNOME 단축키 변경 내용을 먼저 확인한 후 설치합니다.

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch hotkeys install --dry-run
~/.local/share/host-slot-switch/venv/bin/host-slot-switch hotkeys install
```

보안을 위해 단축키 설치기는 그룹 또는 모든 사용자가 수정할 수 있는 실행
파일을 거부합니다. 가상환경을 만든 뒤 이 오류가 나오면 실행 파일 권한을
안전하게 바꾸고 다시 설치하세요.

```bash
chmod go-w ~/.local/share/host-slot-switch/venv/bin/host-slot-switch
~/.local/share/host-slot-switch/venv/bin/host-slot-switch hotkeys install
```

기존 사용자 단축키 목록은 유지합니다. 이 도구가 소유하는 dconf 경로는
아래 세 개뿐입니다.

```text
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/host-slot-switch-slot-1/
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/host-slot-switch-slot-2/
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/host-slot-switch-slot-3/
```

이 도구는 이름이 `host-slot-switch-`로 시작하기만 하는 비슷한 경로는 지우지
않습니다. 위 앱 소유 단축키를 지우려면:

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch hotkeys uninstall
```

GNOME이 아니라면 데스크톱 환경의 단축키 설정에서 아래 명령을 직접
연결하면 됩니다.

```bash
~/.local/share/host-slot-switch/venv/bin/host-slot-switch switch laptop
~/.local/share/host-slot-switch/venv/bin/host-slot-switch switch linux
```

## 설정

Linux는 `~/.config/host-slot-switch/config.json`, Windows는
`%LOCALAPPDATA%\HostSlotSwitch\config.json`에 장치 이름, 슬롯, 단축키를
저장합니다.

```json
{
  "device": "MX Vertical",
  "backend": "auto",
  "profiles": {
    "laptop": {"slot": 1, "hotkey": "<Control><Shift>1"},
    "linux": {"slot": 2, "hotkey": "<Control><Shift>2"},
    "slot3": {"slot": 3, "hotkey": "<Control><Shift>3"}
  }
}
```

`host-slot-switch switch 1`처럼 번호로 직접 실행할 수도 있습니다. 사용자가
보는 슬롯 번호는 1부터 시작하며 내부 HID++의 0 기반 값으로 바꾸는 일은
Solaar가 담당합니다.

설정 파일은 1 MiB 이하의 일반 파일이어야 하며 현재 사용자 소유이고
group/world 쓰기 권한이 없어야 합니다. 심볼릭 링크는 거부합니다.
`config init`이 만든 파일은 `0600`, 앱 디렉터리는 `0700`입니다. JSON 키의
오타나 중복도 오류로 처리해 잘못된 기본 슬롯으로 조용히 전환하지 않습니다.

단축키는 슬롯당 최대 하나이며 `<Control><Shift>1`과 `Ctrl+Shift+1` 형식을
모두 지원합니다. JSON에서 이름·슬롯·단축키를 바꾼 뒤 `hotkeys install`을
다시 실행하면 반영됩니다. `hotkey`를 지우면 해당 프로필은 등록하지 않습니다.
설치 전 `--dry-run` 결과를 확인하세요.
기존 GNOME 사용자 단축키와 의미상 같은 키 조합이 있으면 어떤 설정도
쓰기 전에 충돌 오류로 중단합니다.

## 안전성과 동작 방식

- Linux에서는 shell을 거치지 않고 인자 배열로 Solaar를 실행합니다.
- Windows에서는 공개 HID++ 기능 테이블을 조회하고 `0x1814` 명령만 보냅니다.
- 설정한 MX 장치에 `change-host` 한 종류의 명령만 보냅니다.
- 프로그램 자체는 root 권한을 요청하지 않습니다.
- 성공하면 장치 연결이 즉시 끊기므로 응답이 없는 것이 정상입니다.
- timeout이면 명령 전달 여부가 불확실합니다. 단축키를 다시 누르거나 자동
  재시도하지 말고 먼저 대상 호스트에 마우스가 도착했는지 확인합니다.
- 어느 호스트에서도 마우스를 사용할 수 없으면 하단 Easy-Switch 버튼으로
  복구합니다.

테스트는 `make test`로 실행하며 실제 마우스를 전환하지 않습니다. 프로토콜
근거와 출처는 [프로토콜 문서](https://github.com/dolphin1404/host-slot-switch/blob/main/docs/PROTOCOL.md)에
정리되어 있습니다.

## 보안 취약점 신고

비공개 신고는 이 GitHub 저장소의 **Security → Report a vulnerability**
폼을 이용하세요. 자세한 절차는 [보안 정책](https://github.com/dolphin1404/host-slot-switch/blob/main/SECURITY.md)에 있습니다.
공개 이슈에 exploit 세부 내용, 장치 serial, 로그를 올리지 마세요.
비공개 신고 버튼이 없으면 민감한 내용을 뺀 공개 이슈를 열고
유지관리자에게 비공개 연락 채널을 요청하세요.

## 라이선스·독립성·상표

MIT 라이선스입니다. Logitech 소프트웨어·펌웨어·로고·제품 이미지를 포함하지
않으며 Solaar 코드를 복사하거나 링크하지 않습니다. Solaar는 별도로 설치하는
GPL-2.0 프로그램이며 명령줄 인터페이스로만 호출합니다. Windows에서는 별도
라이선스의 HIDAPI Python 패키지를 설치합니다. 자세한 내용은
[NOTICE.md](https://github.com/dolphin1404/host-slot-switch/blob/main/NOTICE.md)에 있습니다.

Host Slot Switch는 Logitech과 제휴하거나 Logitech의 후원·보증을 받는 제품이
아닙니다. Logitech, Logi 및 해당 로고는 미국 및 기타 국가에서 Logitech
Europe S.A. 및/또는 그 계열사의 상표 또는 등록상표입니다. MX Vertical과
Easy-Switch는 각 소유자의 상표이며 제품명은 호환성 식별 목적으로만 사용합니다.
