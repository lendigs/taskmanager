#include "colors.hpp"
#include "type_aliases.hpp"
#include <expected>
#include <fstream>
#include <nlohmann/json.hpp>
#include <print>
#include <scn/scan.h>
#include <vector>

using nlohmann::json;
using scn::prompt;

const std::string file_path = "tasks.json";

enum class TaskStatus { Done, Pending };
enum class RemoveAllStatus {Empty, SaveFailed, Success};

struct Task {
    std::string title;
    u32 id;
    TaskStatus status;
};

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(Task, id, title, status);

enum class TaskError { NotFound, SaveFailed };

class TaskManager {
private:
    std::vector<Task> tasks;
    u32 next_id = 1;

public:
    bool save() const {
        json j;
        j["next_id"] = next_id;
        j["tasks"] = tasks;

        try {
            std::ofstream file(file_path);
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
        std::ifstream file(file_path);
        if (!file) {
            return;
        }
        try {
            json j = json::parse(file);
            if (j.contains("next_id")) {
                next_id = j["next_id"].get<decltype(next_id)>();
            }
            if (j.contains("tasks") && j["tasks"].is_array()) {
                tasks = j["tasks"].get<std::vector<Task>>();
            }
        } catch (const json::exception& e) {
            std::println("Error while parsing data from file: {}", e.what());
        }
    }

    bool new_task(std::string title) {
        tasks.push_back(
            Task{.title = std::move(title), .id = next_id, .status = TaskStatus::Pending});
        ++next_id;
        if (!save()) {
            tasks.pop_back();
            --next_id;
            return false;
        }
        return true;
    }

    void list() const {
        if (tasks.empty()) {
            std::println("{}There are no available tasks!{}", color::yellow, color::reset);
        }
        for (const auto& x : tasks) {
            auto [status_str, status_color] = x.status == TaskStatus::Done
                                                  ? std::pair{"[Done]", color::green}
                                                  : std::pair{"[Pending]", color::yellow};
            std::println("{}{} (ID: {}) {}{}", status_color, status_str, x.id, color::reset,
                         x.title);
        }
    }

    std::expected<void, TaskError> remove(u32& id_) {
        auto backup = tasks;
        if (std::erase_if(tasks, [&](const Task& t) { return t.id == id_; }) == 0) {
            return std::unexpected(TaskError::NotFound);
        }

        if (!save()) {
            tasks = std::move(backup);
            return std::unexpected(TaskError::SaveFailed);
        }

        return {};
    }
    // bool remove_all() {
    //     if (tasks.empty()) {
            
    //     }
    //     auto backup = tasks;
    //     tasks.erase(tasks.begin(), tasks.end());

    //     if (!save()) {
    //         tasks = std::move(backup);
    //         return false;
    //     }
    //     return true;
    // }
    RemoveAllStatus remove_all() {
        if (tasks.empty()) {
            return RemoveAllStatus::Empty;
        }
        auto backup = tasks;
        tasks.erase(tasks.begin(),tasks.end());
        if (!save()) {
            return RemoveAllStatus::SaveFailed;
        }
        return RemoveAllStatus::Success;
    }
    std::expected<void, TaskError> mark_as_done(u32& id_) {
        auto it = std::ranges::find(tasks, id_, &Task::id);
        if (it == tasks.end()) {
            return std::unexpected(TaskError::NotFound);
        }

        auto prev_status = it->status;
        it->status = TaskStatus::Done;

        if (!save()) {
            it->status = prev_status;
            return std::unexpected(TaskError::SaveFailed);
        }
        return {};
    }
};

int main() {
    std::print("\033[H\033[2J");
    TaskManager tm;
    tm.load();
    std::println("{}Welcome to small task manager!{}", color::green, color::reset);

    while (true) {
        std::println("====================================");
        std::println("1. Add task\n2. Task list\n3. Mark task as done\n4. Remove task\n5. Remove all tasks\n0. Exit");

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
                continue;
            }

            std::string title = result->value();
            auto result_new_task = tm.new_task(title);
            if (result_new_task) {
                std::println("{}Succesfully saved task!{}", color::green, color::reset);
            } else {
                std::println("{}Failed to save task!{}", color::red, color::reset);
            }
        } else if (choice_ == 2) {
            tm.list();
        } else if (choice_ == 3) {
            auto result = prompt<u32>("Enter id of a task you want to mark as done: ", "{}");
            if (!result) {
                std::println("Error while reading line: {}", result.error().msg());
                continue;
            }
            auto id_ = result->value();
            auto result_done = tm.mark_as_done(id_);
            if (!result_done) {
                switch (result_done.error()) {
                case TaskError::NotFound:
                    std::println("{}Error: Task with this id not found!{}", color::red,
                                 color::reset);
                    break;
                case TaskError::SaveFailed:
                    std::println("{}Error: Failed to save data!{}", color::red, color::reset);
                }
            } else {
                std::println("{}Succesfully marked task as done!{}", color::green, color::reset);
            }
        }

        else if (choice_ == 4) {
            auto result = prompt<u32>("Enter id of a task to remove: ", "{}");
            if (!result) {
                std::println("Invalid task format! [Error:{}]", result.error().msg());
                continue;
            }

            u32 id = result->value();
            auto result_remove = tm.remove(id);
            if (!result_remove) {
                switch (result_remove.error()) {
                case TaskError::NotFound:
                    std::println("{}Error: Task with this id not found!{}", color::red,
                                 color::reset);
                    break;
                case TaskError::SaveFailed:
                    std::println("{}Error: Failed to save data!{}", color::red, color::reset);
                    break;
                }
            } else {
                std::println("{}Task removed successfully!{}", color::green, color::reset);
            }
        } else if (choice_ == 5) {
            auto remove_result = tm.remove_all();
            switch (remove_result) {
                case RemoveAllStatus::Success:
                    std::println("{}Successfully removed tasks!{}", color::green, color::reset);
                    break;
                case RemoveAllStatus::Empty:
                    std::println("{}Task list is empty, nothing to remove{}", color::red, color::reset);
                    break;
                case RemoveAllStatus::SaveFailed:
                    std::println("{}Error while saving data!{}", color::red, color::reset);
                    break;
            }
        }
        else if (choice_ == 0) {
            std::print("{}Bye!{}", color::red, color::reset);
            break;
        } else {
            std::print("Unknown command!\n");
        }
    }

    return 0;
}
