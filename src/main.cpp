#include "colors.hpp"
#include "type_aliases.hpp"
#include <fstream>
#include <nlohmann/json.hpp>
#include <print>
#include <scn/scan.h>
#include <vector>
#include <filesystem>

using nlohmann::json;
using scn::prompt;

enum class TaskStatus { Done, Pending };

struct Task {
    std::string title;
    u32 id;
    TaskStatus status;
};

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Task, id, title, status);

class TaskManager {
private:
    std::vector<Task> tasks;
    u32 next_id = 1;

public:
    bool save() {
        json j;
        j["next_id"] = next_id;
        j["tasks"] = tasks;

        try {
            std::ofstream file("tasks.json");
            if (!file) {
                return false;
            }
            file << j.dump(4);
            file.close();
            if (!file) {
                return false;
            }
            return true;
        } catch (const json::exception& e) {
            std::println("Error while saving: {}", e.what());
            return false;
        }
    }

    void load() {
        std::ifstream file("tasks.json");
        if (!file) {
            return;
        }
        try {
            json j = json::parse(file);
            if (j.contains("next_id")) {
                next_id = j["next_id"].get<u32>();
            }
            if (j.contains("tasks") && j["tasks"].is_array()) {
                tasks = j["tasks"].get<std::vector<Task>>();
            }
            std::println("[DEBUG] Loaded data from tasks.json!");
        } catch (const json::exception& e) {
            std::println("Error while parsing data from file: {}", e.what());
        }
    }

    void new_task(std::string title_) {
        if (tasks.empty()) {
            next_id = 1;
        }
        tasks.emplace_back(
            Task{.title = std::move(title_), .id = next_id, .status = TaskStatus::Pending});
        next_id += 1;
        save();
    }

    void list() const {
        if (tasks.empty()) {
            std::println("{}There are no avaliable tasks!{}", color::yellow, color::reset);
        }
        for (const auto& x : tasks) {
            auto [status_str, status_color] = x.status == TaskStatus::Done
                                                  ? std::pair{"[Done]", color::green}
                                                  : std::pair{"[Pending]", color::yellow};
            std::println("{}{} (ID: {}) {}{}", status_color, status_str, x.id, color::reset,
                         x.title);
        }
    }

    bool remove(u32 id_) {
        if (std::erase_if(tasks, [&](const Task& t) { return t.id == id_; })) {
            save();
            return true;
        } else {
            std::println("Task with this id not found.");
            return false;
        }
    }
};

int main() {
    std::print("\033[H\033[2J");
    std::println("[DEBUG] Current Working Directory: {}",std::filesystem::current_path().string());
    TaskManager tm;
    tm.load();
    std::println("{}Welcome to small task manager!{}", color::green, color::reset);

    while (true) {
        std::println("====================================");
        std::println("1. Add task\n2. Task list\n3. Remove task\n0. Exit");

        auto result_ = prompt<u16>("Your choice: ", "{}");
        if (!result_) {
            std::println("Error while reading line, Error: {}", result_.error().msg());
            break;
        }

        u16 choice_ = result_->value();

        if (choice_ == 1) {
            auto result = prompt<std::string>("Enter title: ", " {:[^\n]}");
            if (!result) {
                std::println("Error while reading line: {}", result.error().msg());
                break;
            }

            std::string title = result->value();
            tm.new_task(title);
            std::println("{}Succesfully added task!{}", color::green, color::reset);
        } else if (choice_ == 2) {
            tm.list();
        } else if (choice_ == 3) {
            auto result = prompt<u32>("Enter id of a task to remove: ", "{}");
            if (!result) {
                std::println("Invalid task format! [Error:{}]", result.error().msg());
                break;
            }

            u32 id = result->value();
            tm.remove(id);
        } else if (choice_ == 0) {
            std::print("{}Bye!{}", color::red, color::reset);
            break;
        } else {
            std::print("Unknown command!");
        }
    }

    return 0;
}
