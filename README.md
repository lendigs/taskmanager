# taskmanager — C++23 / Clang / xmake

## Команды

| Команда | Что делает |
|---|---|
| `cxx run` | Настроить текущий профиль, собрать и запустить main |
| `cxx run --release` | Собрать и запустить Release один раз |
| `cxx run -- --help` | Передать --help твоему приложению |
| `cxx build` | Собрать без запуска |
| `cxx build --mode tsan` | Сборка с ThreadSanitizer |
| `cxx check` | Собрать Analyze и запустить полный clang-tidy |
| `cxx fmt` | Отформатировать src/ и include/ |
| `cxx fmt --check` | Проверить стиль без изменения файлов |
| `cxx doctor` | Инструменты, флаги, sanitizer compile/link |
| `cxx doctor --runtime` | Также запустить временные sanitizer control-программы |
| `cxx check-editor` | Проверить clangd на main.cpp |
| `cxx db` | Экспорт compilation database текущего режима |
| `cxx clean` | Очистить результаты сборки через xmake |
| `cxx config` | Показать сохранённые настройки |

Команды работают из корня проекта и его подпапок: xmake.lua ищется вверх от cwd.
После установки не требуется писать python3 или пути к скриптам.
Если команды ещё не установлены, доступны `python3 tools/cxx.py run` и прочие
эквивалентные подкоманды. На чистой машине: `python3 tools/cxx.py install --shell fish`.

## Структура

| Путь | Назначение |
|---|---|
| `src/` | cpp-исходники; вложенные папки автоматически собираются |
| `include/` | свои заголовки, затем папки модулей |
| `tools/cxx.py` | автономная копия утилиты; позволяет переустановить команды |
| `xmake.lua` | общий профиль targets и четыре понятные ветки режимов |
| `.cxx.json` | сохранённые defaults mode/lifetime/werror/lld; храни в git |
| `.clangd` | clangd использует настоящие команды xmake |
| `.clang-tidy` | выбранные статические проверки |
| `.clang-format` | форматирование |
| `build/` | результаты, разделённые по платформе/архитектуре/режиму |
| `compile_commands.json` | актуальные команды для редактора; не хранится в git |

src/main.cpp — минимальная точка входа, без демонстраций и тестов.
Для новых модулей используй src/module и include/module.
Добавление своей библиотеки: новый xmake target с project_settings() и add_deps.
Для thread targets передай -pthread при компиляции и линковке.
C/shared targets требуют отдельного переноса sanitizer flags на нужные стадии.

## Сохранённые настройки

```sh
cxx config --mode debug
cxx config --lifetime
cxx config --werror
cxx config --no-lifetime --no-werror
```

config записывает defaults в .cxx.json. build/run читают эти defaults.
Опции конкретного вызова, например `cxx run --release --no-lifetime`, временные;
defaults не меняются. `cxx check` временно использует Analyze.
Чтобы включить lifetime, проверь обе LLVM-программы:

```sh
cxx doctor --lifetime
cxx config --lifetime
cxx build
cxx check-editor
```

Если checks не поддержаны, ошибка остаётся видимой; флаги молча не отбрасываются.
Для lld: установить пакет lld, затем `cxx doctor --lld` и `cxx config --lld`.

## Режимы

Debug: -O0, -g, ASan+UBSan. Release: -O2, NDEBUG, без санитайзеров.
TSan: -O1, -g, отдельный ThreadSanitizer и PIE. Analyze: -O1, -g, полный tidy отдельно.
Lifetime suggestions включаются только в Analyze с включённой опцией lifetime.
В редакторе запускаются только быстрые tidy checks; clang-analyzer проверяется пакетно.
Lifetime не является borrow checker. Статические checks неполны; санитайзеры
проверяют только исполненный инструментированный код. ASan/UBSan не заменяют MSan.
Doctor проверяет распознавание флагов и работу runtime-контроля, не доказывает
способность обнаружить все ошибки на произвольном коде.

## Редактор и воспроизводимость

Открой корень проекта и запускай clangd с --enable-config --clang-tidy.
После build/run/check база обновляется позиционной командой:
`xmake project -k compile_commands --lsp=clangd .`.
Она отражает последнюю конфигурацию сборки. После check/Release верни Debug через
`cxx build`, если он выбран в .cxx.json.
Для нестандартного cwd: `cxx --project /путь/к/проекту run`.
Утилита ищет clang/clang++/xmake в PATH и передаёт найденные пути явно в xmake.

Нужны Linux, Python 3.10+, Clang/clangd/tidy/format и xmake 3.1.1+.
На CachyOS, если инструменты отсутствуют:
`sudo pacman -Syu --needed clang llvm compiler-rt xmake gcc python`.
Скрипт не использует sudo, не скачивает и не устанавливает system packages сам.
Фиксируй версии LLVM, xmake, glibc, libstdc++ и recipe/package versions при добавлении
зависимостей. Нет обещания bit-for-bit воспроизводимости после произвольного обновления ОС.

## Новые проекты и установка

`xmake_create_project` открывает меню. Также работает без меню:

```sh
xmake_create_project ../next_app --name next_app
xmake_create_project ../offline_app --name offline_app --no-build
```

Создаётся только новая папка; существующие файлы проекта не перезаписываются.
Обычно сразу выполняются первая сборка и экспорт database. Если сборка не прошла,
исходники остаются, команда сообщает причину и возвращает ошибку.

Установщик создаёт команды в ~/.local/bin и собственную копию в ~/.local/share/cxx-tools.
В fish пишет отдельный conf.d/cxx-tools.fish; в bash/zsh добавляет один отмеченный блок
в startup-файл. Повторная установка обновляет только свои файлы и блок.
Чужой файл с тем же именем не перезаписывается. После установки открой новый терминал.
Команда `cpp` не создаётся: это имя системного C-препроцессора.
