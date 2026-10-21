#!/usr/bin/env python3
"""C++23 project generator and tooling commands; Python 3.10+, no third-party modules."""
import argparse
import os
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

TEMPLATES = {'xmake.lua': 'set_xmakever("3.1.1")\n'
              'set_project("@PROJECT@")\n'
              'set_version("0.1.0")\n'
              'set_languages("c++23")\n'
              'set_allowedplats("linux")\n'
              'set_allowedmodes("debug", "release", "tsan", "analyze")\n'
              'set_defaultmode("debug")\n'
              'set_toolchains("clang")\n'
              'set_policy("check.auto_ignore_flags", false)\n'
              'add_rules("plugin.compile_commands.autoupdate", {outputdir = "."})\n'
              '\n'
              'option("lifetime")\n'
              '    set_default(false)\n'
              '    set_showmenu(true)\n'
              '    set_description("Lifetime-анализ Clang; неизвестные флаги вызывают ошибку")\n'
              'option_end()\n'
              '\n'
              'option("werror")\n'
              '    set_default(false)\n'
              '    set_showmenu(true)\n'
              '    set_description("Все предупреждения собственного кода считать ошибками")\n'
              'option_end()\n'
              '\n'
              'option("lld")\n'
              '    set_default(false)\n'
              '    set_showmenu(true)\n'
              '    set_description("Использовать установленный LLVM lld")\n'
              'option_end()\n'
              '\n'
              '-- Общие настройки собственных targets: пакеты имеют свою политику сборки.\n'
              'local function project_settings()\n'
              '    add_includedirs("include")\n'
              '    add_cxxflags(\n'
              '        "-Wall", "-Wextra", "-Wpedantic", "-Wconversion", "-Wsign-conversion",\n'
              '        "-Wshadow", "-Wdangling", "-Warray-bounds", "-Wuninitialized",\n'
              '        "-Werror=return-type", "-Werror=uninitialized", "-Werror=array-bounds",\n'
              '        "-Werror=unknown-warning-option", "-Werror=unused-command-line-argument",\n'
              '        "-fdiagnostics-show-template-tree", "-fno-elide-type",\n'
              '        "-fdiagnostics-show-option", "-fdiagnostics-absolute-paths")\n'
              '\n'
              '    if has_config("werror") then\n'
              '        add_cxxflags("-Werror")\n'
              '    end\n'
              '    if has_config("lifetime") then\n'
              '        -- Явная опция: поддержку проверяй командами doctor и check-editor.\n'
              '        add_cxxflags("-Wlifetime-safety")\n'
              '        if is_mode("analyze") then\n'
              '            add_cxxflags("-Wlifetime-safety-suggestions")\n'
              '        end\n'
              '    end\n'
              '    if has_config("lld") then\n'
              '        add_ldflags("-fuse-ld=lld")\n'
              '    end\n'
              '\n'
              '    -- Debug: ASan + UBSan, без оптимизаций для пошаговой отладки.\n'
              '    if is_mode("debug") then\n'
              '        set_symbols("debug")\n'
              '        set_optimize("none")\n'
              '        add_cxxflags("-fno-omit-frame-pointer", "-fsanitize=address,undefined",\n'
              '            "-fsanitize-address-use-after-scope", "-fno-sanitize-recover=all")\n'
              '        add_ldflags("-fsanitize=address,undefined", "-fno-sanitize-recover=all")\n'
              '\n'
              '    -- Release: обычная оптимизированная сборка, без санитайзеров.\n'
              '    elseif is_mode("release") then\n'
              '        set_symbols("none")\n'
              '        set_optimize("faster") -- -O2\n'
              '        add_defines("NDEBUG")\n'
              '\n'
              '    -- TSan: отдельная сборка для гонок; никогда не смешиваем с ASan.\n'
              '    elseif is_mode("tsan") then\n'
              '        set_symbols("debug")\n'
              '        set_optimize("fast") -- -O1\n'
              '        add_cxxflags("-fno-omit-frame-pointer", "-fsanitize=thread", "-fPIE")\n'
              '        add_ldflags("-fsanitize=thread", "-pie")\n'
              '\n'
              '    -- Analyze: режим для полного clang-tidy, без runtime-инструментирования.\n'
              '    elseif is_mode("analyze") then\n'
              '        set_symbols("debug")\n'
              '        set_optimize("fast") -- -O1\n'
              '        add_cxxflags("-fno-omit-frame-pointer")\n'
              '    end\n'
              '\n'
              '    -- Отдельные выходные папки для Debug / Release / TSan / Analyze.\n'
              '    set_targetdir("build/$(plat)/$(arch)/$(mode)")\n'
              '    set_objectdir("build/.objs/$(plat)/$(arch)/$(mode)/$(target)")\n'
              'end\n'
              '\n'
              'target("main")\n'
              '    set_kind("binary")\n'
              '    add_files("src/**.cpp")\n'
              '    project_settings()\n'
              'target_end()\n',
 '.clangd': '# xmake owns language, include paths, defines and warnings.\n'
            'CompileFlags:\n'
            '  CompilationDatabase: .\n'
            'Diagnostics:\n'
            '  UnusedIncludes: Strict\n'
            '  MissingIncludes: None\n'
            '  ClangTidy:\n'
            '    FastCheckFilter: Strict\n'
            '    # Full path-sensitive analysis belongs in the batch clang-tidy run.\n'
            '    Remove: [clang-analyzer-*]\n',
 '.clang-tidy': '---\n'
                'InheritParentConfig: false\n'
                'Checks: >-\n'
                '  -*,\n'
                '  clang-analyzer-*,\n'
                '  bugprone-use-after-move,\n'
                '  bugprone-dangling-handle,\n'
                '  bugprone-sizeof-expression,\n'
                '  bugprone-suspicious-memset-usage,\n'
                '  bugprone-suspicious-semicolon,\n'
                '  bugprone-argument-comment,\n'
                '  bugprone-integer-division,\n'
                '  bugprone-narrowing-conversions,\n'
                '  bugprone-undefined-memory-manipulation,\n'
                '  bugprone-unused-return-value,\n'
                '  cppcoreguidelines-init-variables,\n'
                '  cppcoreguidelines-slicing,\n'
                '  cppcoreguidelines-virtual-class-destructor,\n'
                '  cppcoreguidelines-pro-type-member-init,\n'
                '  modernize-use-nullptr,\n'
                '  modernize-use-override,\n'
                '  modernize-use-equals-default,\n'
                '  modernize-use-equals-delete,\n'
                '  modernize-loop-convert,\n'
                '  performance-for-range-copy,\n'
                '  performance-unnecessary-copy-initialization,\n'
                '  performance-unnecessary-value-param,\n'
                '  performance-move-const-arg,\n'
                '  readability-inconsistent-declaration-parameter-name,\n'
                '  readability-misleading-indentation,\n'
                '  readability-redundant-smartptr-get\n'
                "WarningsAsErrors: ''\n"
                "HeaderFilterRegex: '(^|/)(src|include)/'\n"
                'SystemHeaders: false\n',
 '.clang-format': '---\n'
                  'BasedOnStyle: LLVM\n'
                  'Language: Cpp\n'
                  'Standard: Latest\n'
                  'IndentWidth: 4\n'
                  'ContinuationIndentWidth: 4\n'
                  'TabWidth: 4\n'
                  'UseTab: Never\n'
                  'ColumnLimit: 100\n'
                  'BreakBeforeBraces: Attach\n'
                  'NamespaceIndentation: None\n'
                  'AccessModifierOffset: -4\n'
                  'PointerAlignment: Left\n'
                  'ReferenceAlignment: Left\n'
                  'DerivePointerAlignment: false\n'
                  'AllowShortFunctionsOnASingleLine: Empty\n'
                  'AllowShortIfStatementsOnASingleLine: Never\n'
                  'AllowShortLoopsOnASingleLine: false\n'
                  'FixNamespaceComments: true\n',
 '.gitignore': '.xmake/\nbuild/\ncompile_commands.json\n',
 'src/main.cpp': 'int main() {\n    return 0;\n}\n',
 'README.md': '# @PROJECT@ — C++23 / Clang / xmake\n'
              '\n'
              '## Команды\n'
              '\n'
              '| Команда | Что делает |\n'
              '|---|---|\n'
              '| `cxx run` | Настроить текущий профиль, собрать и запустить main |\n'
              '| `cxx run --release` | Собрать и запустить Release один раз |\n'
              '| `cxx run -- --help` | Передать --help твоему приложению |\n'
              '| `cxx build` | Собрать без запуска |\n'
              '| `cxx build --mode tsan` | Сборка с ThreadSanitizer |\n'
              '| `cxx check` | Собрать Analyze и запустить полный clang-tidy |\n'
              '| `cxx fmt` | Отформатировать src/ и include/ |\n'
              '| `cxx fmt --check` | Проверить стиль без изменения файлов |\n'
              '| `cxx doctor` | Инструменты, флаги, sanitizer compile/link |\n'
              '| `cxx doctor --runtime` | Также запустить временные sanitizer control-программы |\n'
              '| `cxx check-editor` | Проверить clangd на main.cpp |\n'
              '| `cxx db` | Экспорт compilation database текущего режима |\n'
              '| `cxx clean` | Очистить результаты сборки через xmake |\n'
              '| `cxx config` | Показать сохранённые настройки |\n'
              '\n'
              'Команды работают из корня проекта и его подпапок: xmake.lua ищется вверх от cwd.\n'
              'После установки не требуется писать python3 или пути к скриптам.\n'
              'Если команды ещё не установлены, доступны `python3 tools/cxx.py run` и прочие\n'
              'эквивалентные подкоманды. На чистой машине: `python3 tools/cxx.py install --shell '
              'fish`.\n'
              '\n'
              '## Структура\n'
              '\n'
              '| Путь | Назначение |\n'
              '|---|---|\n'
              '| `src/` | cpp-исходники; вложенные папки автоматически собираются |\n'
              '| `include/` | свои заголовки, затем папки модулей |\n'
              '| `tools/cxx.py` | автономная копия утилиты; позволяет переустановить команды |\n'
              '| `xmake.lua` | общий профиль targets и четыре понятные ветки режимов |\n'
              '| `.cxx.json` | сохранённые defaults mode/lifetime/werror/lld; храни в git |\n'
              '| `.clangd` | clangd использует настоящие команды xmake |\n'
              '| `.clang-tidy` | выбранные статические проверки |\n'
              '| `.clang-format` | форматирование |\n'
              '| `build/` | результаты, разделённые по платформе/архитектуре/режиму |\n'
              '| `compile_commands.json` | актуальные команды для редактора; не хранится в git |\n'
              '\n'
              'src/main.cpp — минимальная точка входа, без демонстраций и тестов.\n'
              'Для новых модулей используй src/module и include/module.\n'
              'Добавление своей библиотеки: новый xmake target с project_settings() и add_deps.\n'
              'Для thread targets передай -pthread при компиляции и линковке.\n'
              'C/shared targets требуют отдельного переноса sanitizer flags на нужные стадии.\n'
              '\n'
              '## Сохранённые настройки\n'
              '\n'
              '```sh\n'
              'cxx config --mode debug\n'
              'cxx config --lifetime\n'
              'cxx config --werror\n'
              'cxx config --no-lifetime --no-werror\n'
              '```\n'
              '\n'
              'config записывает defaults в .cxx.json. build/run читают эти defaults.\n'
              'Опции конкретного вызова, например `cxx run --release --no-lifetime`, временные;\n'
              'defaults не меняются. `cxx check` временно использует Analyze.\n'
              'Чтобы включить lifetime, проверь обе LLVM-программы:\n'
              '\n'
              '```sh\n'
              'cxx doctor --lifetime\n'
              'cxx config --lifetime\n'
              'cxx build\n'
              'cxx check-editor\n'
              '```\n'
              '\n'
              'Если checks не поддержаны, ошибка остаётся видимой; флаги молча не отбрасываются.\n'
              'Для lld: установить пакет lld, затем `cxx doctor --lld` и `cxx config --lld`.\n'
              '\n'
              '## Режимы\n'
              '\n'
              'Debug: -O0, -g, ASan+UBSan. Release: -O2, NDEBUG, без санитайзеров.\n'
              'TSan: -O1, -g, отдельный ThreadSanitizer и PIE. Analyze: -O1, -g, полный tidy '
              'отдельно.\n'
              'Lifetime suggestions включаются только в Analyze с включённой опцией lifetime.\n'
              'В редакторе запускаются только быстрые tidy checks; clang-analyzer проверяется '
              'пакетно.\n'
              'Lifetime не является borrow checker. Статические checks неполны; санитайзеры\n'
              'проверяют только исполненный инструментированный код. ASan/UBSan не заменяют MSan.\n'
              'Doctor проверяет распознавание флагов и работу runtime-контроля, не доказывает\n'
              'способность обнаружить все ошибки на произвольном коде.\n'
              '\n'
              '## Редактор и воспроизводимость\n'
              '\n'
              'Открой корень проекта и запускай clangd с --enable-config --clang-tidy.\n'
              'После build/run/check база обновляется позиционной командой:\n'
              '`xmake project -k compile_commands --lsp=clangd .`.\n'
              'Она отражает последнюю конфигурацию сборки. После check/Release верни Debug через\n'
              '`cxx build`, если он выбран в .cxx.json.\n'
              'Для нестандартного cwd: `cxx --project /путь/к/проекту run`.\n'
              'Утилита ищет clang/clang++/xmake в PATH и передаёт найденные пути явно в xmake.\n'
              '\n'
              'Нужны Linux, Python 3.10+, Clang/clangd/tidy/format и xmake 3.1.1+.\n'
              'На CachyOS, если инструменты отсутствуют:\n'
              '`sudo pacman -Syu --needed clang llvm compiler-rt xmake gcc python`.\n'
              'Скрипт не использует sudo, не скачивает и не устанавливает system packages сам.\n'
              'Фиксируй версии LLVM, xmake, glibc, libstdc++ и recipe/package versions при '
              'добавлении\n'
              'зависимостей. Нет обещания bit-for-bit воспроизводимости после произвольного '
              'обновления ОС.\n'
              '\n'
              '## Новые проекты и установка\n'
              '\n'
              '`xmake_create_project` открывает меню. Также работает без меню:\n'
              '\n'
              '```sh\n'
              'xmake_create_project ../next_app --name next_app\n'
              'xmake_create_project ../offline_app --name offline_app --no-build\n'
              '```\n'
              '\n'
              'Создаётся только новая папка; существующие файлы проекта не перезаписываются.\n'
              'Обычно сразу выполняются первая сборка и экспорт database. Если сборка не прошла,\n'
              'исходники остаются, команда сообщает причину и возвращает ошибку.\n'
              '\n'
              'Установщик создаёт команды в ~/.local/bin и собственную копию в '
              '~/.local/share/cxx-tools.\n'
              'В fish пишет отдельный conf.d/cxx-tools.fish; в bash/zsh добавляет один отмеченный '
              'блок\n'
              'в startup-файл. Повторная установка обновляет только свои файлы и блок.\n'
              'Чужой файл с тем же именем не перезаписывается. После установки открой новый '
              'терминал.\n'
              'Команда `cpp` не создаётся: это имя системного C-препроцессора.\n'}

def execute(command, cwd, capture=False):
    print('$ ' + shlex.join([str(x) for x in command]), flush=True)
    return subprocess.run([str(x) for x in command], cwd=cwd, text=True,
                          capture_output=capture, check=False)


def need(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f'Не найден {name}. Для CachyOS: sudo pacman -Syu --needed clang llvm compiler-rt xmake gcc python')
    return str(Path(path).absolute())


def project_root(value):
    if value:
        root = Path(value).expanduser().resolve()
        if not (root / 'xmake.lua').is_file():
            raise RuntimeError(f'В {root} нет xmake.lua')
        return root
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / 'xmake.lua').is_file():
            return candidate
    script = Path(__file__).resolve()
    if script.parent.name == 'tools' and (script.parent.parent / 'xmake.lua').is_file():
        return script.parent.parent
    raise RuntimeError('Открой терминал в проекте либо укажи --project /путь/к/проекту перед командой.')


def checked(command, root):
    result = execute(command, root)
    if result.returncode:
        raise RuntimeError(f'Команда завершилась с кодом {result.returncode}: {shlex.join(command)}')


def database(root):
    # xmake 3.1.1 takes outputdir as a POSITIONAL argument. There is no -o.
    checked([need('xmake'), 'project', '-k', 'compile_commands', '--lsp=clangd', '.'], root)
    path = root / 'compile_commands.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not rows:
        raise RuntimeError('compile_commands.json пуст: проверь add_files в xmake.lua')
    print('Обновлён compile_commands.json', flush=True)


def sources(root):
    extensions = {'.cpp', '.cc', '.cxx', '.hpp', '.h', '.hh', '.hxx'}
    return sorted(p for folder in ('src', 'include') for p in (root / folder).rglob('*')
                  if p.is_file() and p.suffix in extensions)


def doctor(root, lifetime=False, runtime=False, lld=False):
    issues = []
    for name in ('clang', 'clang++', 'clangd', 'clang-tidy', 'clang-format', 'xmake'):
        try:
            checked([need(name), '--version'], root)
        except RuntimeError as error:
            issues.append(str(error))
    if issues:
        raise RuntimeError('\n'.join(issues))
    compiler = need('clang++')
    checked([need('clang-tidy'), '--verify-config', str(root / 'src/main.cpp'),
             '--', '-std=c++23', '-I' + str(root / 'include')], root)
    checked([need('clang-format'), '--style=file', '--dump-config'], root)
    active = set(re.findall(r'"(-[^"\n]+)"', (root / 'xmake.lua').read_text(encoding='utf-8')))
    active |= {'-std=c++23', '-O0', '-O1', '-O2', '-g', '-DNDEBUG'}
    if not lifetime:
        active -= {'-Wlifetime-safety', '-Wlifetime-safety-suggestions'}
    if not lld:
        active.discard('-fuse-ld=lld')
    with tempfile.TemporaryDirectory(prefix='cppenv-doctor-') as temporary:
        temp = Path(temporary)
        source = temp / 'control.cpp'
        source.write_text('int main() { return 0; }\n', encoding='utf-8')
        for flag in sorted(active):
            linking = flag in {'-pie', '-fuse-ld=lld'}
            context = ['-fsanitize=address'] if flag == '-fsanitize-address-use-after-scope' else []
            command = [compiler, '-std=c++23', '-Werror=unknown-warning-option',
                       '-Werror=unused-command-line-argument', *context, flag]
            if not linking:
                command.append('-c')
            command += [str(source), '-o', str(temp / ('control' if linking else 'control.o'))]
            result = execute(command, root, capture=True)
            if result.returncode:
                issues.append(flag + '\n' + result.stdout + result.stderr)
        profiles = {
            'asan-ubsan': ['-O0', '-g', '-fno-omit-frame-pointer',
                           '-fsanitize=address,undefined', '-fsanitize-address-use-after-scope',
                           '-fno-sanitize-recover=all'],
            'tsan': ['-O1', '-g', '-fno-omit-frame-pointer', '-fsanitize=thread', '-fPIE', '-pie']}
        for profile, flags in profiles.items():
            executable = temp / profile
            result = execute([compiler, '-std=c++23', *flags, str(source), '-o', str(executable)], root, capture=True)
            if result.returncode:
                issues.append(profile + ': ошибка compile/link\n' + result.stdout + result.stderr)
            elif runtime:
                result = execute([str(executable)], root, capture=True)
                if result.returncode:
                    issues.append(profile + ': ошибка запуска runtime\n' + result.stdout + result.stderr)
    if issues:
        raise RuntimeError('Проверка не пройдена:\n' + '\n'.join(issues))
    print('Распознавание флагов, схемы tidy/format и sanitizer compile/link проверены.')
    print('Runtime: ' + ('контрольные программы запущены.' if runtime else 'не запускался; используй doctor --runtime.'))
    print('Поведение диагностик на ошибочном коде и гарантии безопасности эта команда не проверяет.')


MANAGED = 'CXX_TOOLS_MANAGED_V1'
MODES = ('debug', 'release', 'tsan', 'analyze')
DEFAULTS = {'mode': 'debug', 'lifetime': False, 'werror': False, 'lld': False}


def write_atomic(path, text, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
        if mode is not None:
            Path(temporary).chmod(mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def settings(root):
    path = root / '.cxx.json'
    values = DEFAULTS.copy()
    if path.exists():
        saved = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(saved, dict) or set(saved) - set(DEFAULTS):
            raise RuntimeError('Неверная структура .cxx.json')
        values.update(saved)
    if values['mode'] not in MODES or any(type(values[key]) is not bool for key in ('lifetime', 'werror', 'lld')):
        raise RuntimeError('Неверные значения в .cxx.json')
    return values


def effective(root, args, analysis=False):
    values = settings(root)
    for key in DEFAULTS:
        value = getattr(args, key, None)
        if value is not None:
            values[key] = value
    if getattr(args, 'release', False):
        values['mode'] = 'release'
    if analysis:
        values['mode'] = 'analyze'
    return values


def build_project(root, values):
    compiler = need('clang++')
    checked([need('xmake'), 'f', '-m', values['mode'], '--toolchain=clang',
             '--cc=' + need('clang'), '--cxx=' + compiler, '--ld=' + compiler,
             *['--' + key + '=' + ('y' if values[key] else 'n')
               for key in ('lifetime', 'werror', 'lld')]], root)
    checked([need('xmake'), 'build', 'main'], root)
    database(root)


def choose(label, options, default=1):
    print('\n' + label)
    for index, value in enumerate(options, 1):
        print(f'  {index}. {value}')
    while True:
        answer = input(f'Выбор [{default}]: ').strip() or str(default)
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer)
        print('Введи номер из меню.')


def new_project(args):
    values = DEFAULTS.copy()
    if args.path is None:
        if not sys.stdin.isatty():
            raise RuntimeError('Для меню нужен терминал. Либо укажи: xmake_create_project /путь --name my_app')
        print('\nC++23 · Clang · xmake\nСоздание проекта')
        default_name = args.name or 'my_app'
        while True:
            name = input(f'Имя проекта [{default_name}]: ').strip() or default_name
            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', name):
                break
            print('Используй латинские буквы, цифры, _, -; начни с буквы или _.')
        parent = input(f'Родительская папка [{Path.cwd()}]: ').strip()
        destination = (Path(parent).expanduser() if parent else Path.cwd()) / name
        values['mode'] = MODES[choose('Начальный режим', [
            'Debug — ASan + UBSan (рекомендуется)', 'Release — оптимизированная сборка',
            'TSan — отдельная проверка гонок', 'Analyze — статический анализ']) - 1]
        profile = choose('Строгость диагностики', [
            'Базовая — warnings и санитайзеры (рекомендуется)',
            'Lifetime — дополнительно lifetime-анализ Clang',
            'Строгая — lifetime и все warnings как errors'])
        values['lifetime'] = profile >= 2
        values['werror'] = profile == 3
    else:
        destination = Path(args.path).expanduser()
        name = args.name or destination.name
        for key in DEFAULTS:
            value = getattr(args, key, None)
            if value is not None:
                values[key] = value
    # Explicit CLI flags override menu choices too.
    for key in DEFAULTS:
        value = getattr(args, key, None)
        if value is not None:
            values[key] = value
    destination = destination.absolute()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', name):
        raise RuntimeError('Укажи ASCII-имя через --name my_app. Путь может содержать кириллицу и пробелы.')
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f'Папка уже существует: {destination}. Её содержимое не изменено.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.cxx-new-', dir=destination.parent))
    try:
        for folder in ('src', 'include', 'tools'):
            (staging / folder).mkdir()
        for relative, contents in TEMPLATES.items():
            (staging / relative).write_text(contents.replace('@PROJECT@', name), encoding='utf-8')
        (staging / 'tools/cxx.py').write_bytes(Path(__file__).read_bytes())
        (staging / '.cxx.json').write_text(json.dumps(values, indent=2) + '\n', encoding='utf-8')
        destination.mkdir()
        for entry in staging.iterdir():
            shutil.move(str(entry), str(destination / entry.name))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print('\nПроект создан: ' + str(destination))
    if not args.no_build:
        print('Первая сборка и подготовка clangd...')
        try:
            build_project(destination, values)
        except (OSError, RuntimeError, ValueError) as error:
            raise RuntimeError(f'Файлы проекта созданы в {destination}, но первая сборка не прошла:\n{error}\nИсправь причину и выполни cxx build в этой папке.') from error
    print('\nДальше:\n  cd ' + shlex.quote(str(destination)) + '\n  cxx run')


def install(args, installation_home=None):
    if sys.platform != 'linux':
        raise RuntimeError('Этот установщик предназначен для Linux.')
    home = Path(installation_home) if installation_home is not None else Path.home()
    bindir = home / '.local/bin'
    payload = home / '.local/share/cxx-tools/cxx.py'
    shell = args.shell
    if shell == 'auto':
        shell = Path(os.environ.get('SHELL', '')).name
        if shell not in ('fish', 'bash', 'zsh'):
            shell = 'fish' if shutil.which('fish') else 'bash'
    python = str(Path(sys.executable).absolute())
    writes = {payload: (Path(__file__).read_text(encoding='utf-8'), 0o644)}
    for command, extra in [('cxx', []), ('xmake_create_project', ['new'])]:
        content = '#!/bin/sh\n# ' + MANAGED + '\nexec ' + shlex.join([python, str(payload), *extra]) + ' "$@"\n'
        writes[bindir / command] = (content, 0o755)
    if shell == 'fish':
        config_home = str(home / '.config') if installation_home is not None else os.environ.get('XDG_CONFIG_HOME', str(home / '.config'))
        confdir = Path(config_home) / 'fish/conf.d'
        writes[confdir / 'cxx-tools.fish'] = ('# ' + MANAGED + '\nfish_add_path --global "$HOME/.local/bin"\n', 0o644)
    elif shell in ('bash', 'zsh'):
        rc = home / ('.bashrc' if shell == 'bash' else '.zshrc')
        start, end = '# >>> ' + MANAGED, '# <<< ' + MANAGED
        old = rc.read_text(encoding='utf-8') if rc.exists() else ''
        stanza = (start + '\ncase ":$PATH:" in\n'
                  '  *":$HOME/.local/bin:"*) ;;\n'
                  '  *) export PATH="$HOME/.local/bin:$PATH" ;;\nesac\n' + end + '\n')
        if start in old:
            if end not in old:
                raise RuntimeError(f'Незавершённый блок установки в {rc}; исправь его вручную.')
            content = re.sub(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', stanza, old, flags=re.S)
        else:
            content = old + ('\n' if old and not old.endswith('\n') else '') + '\n' + stanza
        # Preserve permissions of an existing shell startup file.
        writes[rc] = (content, rc.stat().st_mode & 0o777 if rc.exists() else 0o644)
    # Validate every destination before changing anything.
    for path in writes:
        if path.is_symlink():
            raise RuntimeError(f'Не перезаписываю symlink: {path}')
        if path.exists() and path.name not in ('.bashrc', '.zshrc'):
            if not path.is_file() or MANAGED not in path.read_text(encoding='utf-8', errors='replace'):
                raise RuntimeError(f'Путь занят чужим файлом: {path}')
    for path, (content, mode) in writes.items():
        write_atomic(path, content, mode)
    print('Установлены команды: xmake_create_project и cxx. Без sudo.')
    print('Открой новый терминал.')
    if shell == 'fish':
        print('Или в текущем fish выполни: fish_add_path ~/.local/bin')
    elif shell in ('bash', 'zsh'):
        print('Или в текущем терминале: export PATH="$HOME/.local/bin:$PATH"')
    else:
        print('Добавь ~/.local/bin в PATH своего shell.')


def build_options(parser):
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--mode', choices=MODES)
    modes.add_argument('--release', action='store_true')
    for key in ('lifetime', 'werror', 'lld'):
        parser.add_argument('--' + key, action=argparse.BooleanOptionalAction, default=None)


def main():
    parser = argparse.ArgumentParser(description='CXX Tools: создание и повседневная работа с C++23 / Clang / xmake.')
    parser.add_argument('--project', help='Явный путь к проекту; обычно ищется вверх от текущей папки')
    parser.add_argument('--version', action='version', version='cxx-tools 1.0.1')
    commands = parser.add_subparsers(dest='command')
    setup = commands.add_parser('install', help='Установить команды для своего пользователя')
    setup.add_argument('--shell', choices=['auto', 'fish', 'bash', 'zsh', 'none'], default='auto')
    new = commands.add_parser('new', help='Интерактивное создание проекта')
    new.add_argument('path', nargs='?')
    new.add_argument('--name')
    new.add_argument('--mode', choices=MODES)
    for key in ('lifetime', 'werror', 'lld'):
        new.add_argument('--' + key, action=argparse.BooleanOptionalAction, default=None)
    new.add_argument('--no-build', action='store_true', help='Только создать файлы, без первой сборки')
    for name, help_text in [('build', 'Настроить, собрать и обновить database'),
                            ('run', 'Собрать и запустить программу')]:
        sub = commands.add_parser(name, help=help_text)
        build_options(sub)
        if name == 'run':
            sub.add_argument('arguments', nargs=argparse.REMAINDER)
    fmt = commands.add_parser('fmt', help='Форматирование src/include')
    fmt.add_argument('--check', action='store_true', help='Проверка без изменения файлов')
    check = commands.add_parser('check', help='Сборка Analyze и полный clang-tidy')
    for key in ('lifetime', 'werror', 'lld'):
        check.add_argument('--' + key, action=argparse.BooleanOptionalAction, default=None)
    config = commands.add_parser('config', help='Показать или сохранить настройки проекта')
    config.add_argument('--mode', choices=MODES)
    for key in ('lifetime', 'werror', 'lld'):
        config.add_argument('--' + key, action=argparse.BooleanOptionalAction, default=None)
    commands.add_parser('db', help='Обновить database текущего режима')
    commands.add_parser('clean', help='Удалить результаты сборки через xmake')
    commands.add_parser('check-editor', help='Проверить clangd на main.cpp')
    doc = commands.add_parser('doctor', help='Проверить LLVM tools, флаги и sanitizer compile/link')
    for key in ('lifetime', 'lld'):
        doc.add_argument('--' + key, action=argparse.BooleanOptionalAction, default=None)
    doc.add_argument('--runtime', action='store_true')
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    if args.command == 'install':
        install(args)
        return
    if args.command == 'new':
        new_project(args)
        return
    root = project_root(args.project)
    if args.command in ('build', 'run'):
        build_project(root, effective(root, args))
        if args.command == 'run':
            arguments = args.arguments
            if arguments and arguments[0] == '--':
                arguments = arguments[1:]
            sys.exit(execute([need('xmake'), 'run', 'main', *arguments], root).returncode)
    elif args.command == 'config':
        values = effective(root, args)
        if any(getattr(args, key, None) is not None for key in DEFAULTS):
            write_atomic(root / '.cxx.json', json.dumps(values, indent=2) + '\n')
        print(json.dumps(values, ensure_ascii=False, indent=2))
    elif args.command == 'db':
        database(root)
    elif args.command == 'clean':
        checked([need('xmake'), 'clean'], root)
    elif args.command == 'fmt':
        paths = sources(root)
        if not paths:
            raise RuntimeError('Нет исходников для форматирования.')
        flags = ['--dry-run', '--Werror'] if args.check else ['-i']
        checked([need('clang-format'), '--style=file', *flags, *map(str, paths)], root)
    elif args.command == 'check':
        build_project(root, effective(root, args, analysis=True))
        units = set()
        for row in json.loads((root / 'compile_commands.json').read_text(encoding='utf-8')):
            source = Path(row['file'])
            if not source.is_absolute():
                source = Path(row['directory']) / source
            source = source.resolve()
            if source.is_relative_to(root / 'src'):
                units.add(source)
        if not units:
            raise RuntimeError('В database нет исходников из src/.')
        checked([need('clang-tidy'), '-p=' + str(root), '--warnings-as-errors=*',
                 *map(str, sorted(units))], root)
    elif args.command == 'check-editor':
        if not (root / 'compile_commands.json').exists():
            raise RuntimeError('Сначала выполни cxx build.')
        result = execute([need('clangd'), '--enable-config', '--clang-tidy',
                          '--check=' + str(root / 'src/main.cpp'), '--log=verbose'], root, capture=True)
        output = result.stdout + result.stderr
        print(output)
        if result.returncode or re.search(r'config (warning|error)|unknown warning option', output, re.I):
            raise RuntimeError('Ошибка/предупреждение конфигурации clangd, смотри вывод выше.')
    elif args.command == 'doctor':
        values = effective(root, args)
        doctor(root, values['lifetime'], args.runtime, values['lld'])


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, EOFError) as error:
        print('Ошибка: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nОтменено.', file=sys.stderr)
        sys.exit(130)
