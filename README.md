# FIIO Air Link Control

FIIO Air Link Control (FALC) — Windows-контроллер для FIIO Air Link на Python с
Backend-Driven UI. Python
формирует декларативное JSON-дерево интерфейса и обрабатывает actions, а
универсальный renderer отображает его через системный WebView2 (`pywebview`).
Доступ к USB HID выполняется через `hidapi`. Node.js, Electron и WebHID не
используются.

Интерфейс запускается на английском языке. В header можно переключиться на
русский; выбор сохраняется в `%LOCALAPPDATA%\FIIO Air Link Control\settings.json`.

Поддерживается только FIIO Air Link:

- USB vendor ID: `0x2972`;
- USB product ID: `0x0158`;
- HID report ID: `7`;
- аппаратно проверенная прошивка: `1.4.0`.

Приложение автоматически обнаруживает Air Link, подключается при запуске и
восстанавливает сессию после повторного USB-подключения. Кнопка `Отключить`
приостанавливает auto-connect до ручного запуска новой сессии.

Раздел `Диагностика` показывает параметры HID-интерфейса, build provenance,
счётчики transport/lifecycle и время последнего ответа. При запуске с
`FIIO_AIR_LINK_DEBUG=1` доступен кольцевой журнал последних 250 пакетов.
Диагностический JSON сохраняется в `Downloads`; payload пакетов всегда полностью
редактируется перед экспортом.

Кодеки включаются и выключаются напрямую. Для включённых LDAC и aptX Adaptive
доступен выбор режима качества; каждая запись подтверждается отдельным GET.

Для каждого сопряжённого устройства доступно прямое подключение и отключение.
Интерфейс меняет статус только после подтверждения новым списком устройств.

Кнопка `Добавить новое устройство` включает поиск на 60 секунд. Найденные
устройства приходят через discovery events и отображаются отдельным списком.
После выбора приложение выполняет pair action `18` и подтверждает результат через
event `0x83` и paired-device list readback.

Протокол и ограничения описаны в `docs/FIIO_AIR_LINK_HANDOFF.md`.

## Структура

- `fiiocontrol/` — Python-пакет приложения и BDUI renderer в `web/`.
- `tests/` — unit-тесты протокола, lifecycle и UI documents.
- `scripts/` — hardware smoke-test и Windows-сборка.
- `docs/` — протокол, ограничения и roadmap.
- `release/` — локальный результат сборки, не входит в Git.

## Запуск

Требуется Python 3.11 или новее.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m fiiocontrol
```

После установки также доступна команда `fiio-air-link-control`.

## Проверка

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Unit-тесты не требуют подключённого устройства. Для вывода HID-пакетов установите
`FIIO_AIR_LINK_DEBUG=1` перед запуском приложения.

Безопасный аппаратный smoke-test:

```powershell
.\.venv\Scripts\python.exe scripts\hardware_smoke.py
```

Проверка уже подтверждённой записи кодеков без изменения текущей конфигурации:

```powershell
.\.venv\Scripts\python.exe scripts\hardware_smoke.py --verify-codec-write
```

Проверка записи текущих режимов качества без изменения выбранных значений:

```powershell
.\.venv\Scripts\python.exe scripts\hardware_smoke.py --verify-quality-write
```

Проверка отключения и обязательного повторного подключения текущего приёмника:

```powershell
.\.venv\Scripts\python.exe scripts\hardware_smoke.py --verify-connection-actions
```

Проверка запуска и немедленной остановки manual pairing mode:

```powershell
.\.venv\Scripts\python.exe scripts\hardware_smoke.py --verify-pairing-mode
```

## Windows-сборка

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe scripts\build_windows.py
```

Результат: `release/FIIO-Air-Link-Control.exe`. Файл пока не подписан, поэтому
Microsoft SmartScreen может показать предупреждение.

Для Microsoft Store используется one-folder PyInstaller payload внутри MSIX:

```powershell
.\.venv\Scripts\python.exe scripts\build_msix.py
```

Store автоматически переподписывает прошедший сертификацию MSIX сертификатом
Microsoft. Production identity из Partner Center хранится в публичном файле
`packaging/store_identity.json`; это не секретные данные.

Так как Store запрещает нулевую первую часть package version, версия приложения
`0.2.0` упаковывается как MSIX version `1.2.0.0`; это не меняет отображаемую
версию FALC.

Workflow `Microsoft Store Package` запускается после push в `main` и вручную,
собирает production MSIX artifact для загрузки в Partner Center. GitHub Releases
не используются для распространения unsigned Windows binaries.
