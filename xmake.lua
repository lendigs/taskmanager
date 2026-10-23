set_xmakever("3.1.1")
set_project("taskmanager")
set_version("0.1.0")
set_languages("c++23")
set_allowedplats("linux")
set_allowedmodes("debug", "release", "tsan", "analyze")
set_defaultmode("debug")
set_toolchains("clang")
set_policy("check.auto_ignore_flags", false)
add_rules("plugin.compile_commands.autoupdate", {outputdir = "."})

-- REQUIRES
add_requires("scnlib")
add_requires("nlohmann_json")
-- REQUIRES


option("lifetime")
    set_default(false)
    set_showmenu(true)
    set_description("Lifetime-анализ Clang; неизвестные флаги вызывают ошибку")
option_end()

option("werror")
    set_default(false)
    set_showmenu(true)
    set_description("Все предупреждения собственного кода считать ошибками")
option_end()

option("lld")
    set_default(false)
    set_showmenu(true)
    set_description("Использовать установленный LLVM lld")
option_end()

-- Общие настройки собственных targets: пакеты имеют свою политику сборки.
local function project_settings()
    add_includedirs("include")
    add_cxxflags(
        "-Wall", "-Wextra", "-Wpedantic", "-Wconversion", "-Wsign-conversion",
        "-Wshadow", "-Wdangling", "-Warray-bounds", "-Wuninitialized",
        "-Werror=return-type", "-Werror=uninitialized", "-Werror=array-bounds",
        "-Werror=unknown-warning-option", "-Werror=unused-command-line-argument",
        "-fdiagnostics-show-template-tree", "-fno-elide-type",
        "-fdiagnostics-show-option", "-fdiagnostics-absolute-paths")

    if has_config("werror") then
        add_cxxflags("-Werror")
    end
    if has_config("lifetime") then
        -- Явная опция: поддержку проверяй командами doctor и check-editor.
        add_cxxflags("-Wlifetime-safety")
        if is_mode("analyze") then
            add_cxxflags("-Wlifetime-safety-suggestions")
        end
    end
    if has_config("lld") then
        add_ldflags("-fuse-ld=lld")
    end

    -- Debug: ASan + UBSan, без оптимизаций для пошаговой отладки.
    if is_mode("debug") then
        set_symbols("debug")
        set_optimize("none")
        add_cxxflags("-fno-omit-frame-pointer", "-fsanitize=address,undefined",
            "-fsanitize-address-use-after-scope", "-fno-sanitize-recover=all")
        add_ldflags("-fsanitize=address,undefined", "-fno-sanitize-recover=all")

    -- Release: обычная оптимизированная сборка, без санитайзеров.
    elseif is_mode("release") then
        set_symbols("none")
        set_optimize("faster") -- -O2
        add_defines("NDEBUG")

    -- TSan: отдельная сборка для гонок; никогда не смешиваем с ASan.
    elseif is_mode("tsan") then
        set_symbols("debug")
        set_optimize("fast") -- -O1
        add_cxxflags("-fno-omit-frame-pointer", "-fsanitize=thread", "-fPIE")
        add_ldflags("-fsanitize=thread", "-pie")

    -- Analyze: режим для полного clang-tidy, без runtime-инструментирования.
    elseif is_mode("analyze") then
        set_symbols("debug")
        set_optimize("fast") -- -O1
        add_cxxflags("-fno-omit-frame-pointer")
    end

    -- Отдельные выходные папки для Debug / Release / TSan / Analyze.
    set_targetdir("build/$(plat)/$(arch)/$(mode)")
    set_objectdir("build/.objs/$(plat)/$(arch)/$(mode)/$(target)")
end

target("main")
    set_kind("binary")
    add_files("src/**.cpp")

    -- PACKAGES
    add_packages("scnlib")
    add_packages("nlohmann_json")

    project_settings()
target_end()
