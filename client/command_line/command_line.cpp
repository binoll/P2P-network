#include "command_line.hpp"

CommandLine::CommandLine(std::string& path) : connection(path) {
	std::cout << "Welcome to file sharing app!" << std::endl;

	while (true) {
		std::string work_path;

		std::cout << "Write the dir: ";
		std::cin >> work_path;

		if (this->update_dir(work_path) == -1) {
			std::cout << "Try again! [-]" << std::endl;
			continue;
		}

		std::cout << "Dir is correct! [+]" << std::endl;
		break;
	}

	std::cout << "The connection is established! [+]" << std::endl;
}

void CommandLine::run() {
	std::string command;
	int8_t choice;

	while (true) {
		std::cout << "+------------------------------------------------+" << std::endl;
		std::cout << "Write the command (for help - \"help\"): ";
		std::cin >> command;

		choice = processing_command(command);

		switch (choice) {
			case 0: {
				this->exit();
				break;
			}
			case 1: {
				this->help();
				continue;
			}
			case 2: {
				std::list<std::string> list;

				if (this->connection.list(list)) {
					std::cout << "Try again! [-]" << std::endl;
					continue;
				}

				if (list.empty()) {
					std::cout << "No files available. Try again! [-]" << std::endl;
					continue;
				}

				std::cout << "Commands list: " << std::endl;

				for (auto& item : list) {
					std::cout << "\t" << item;
				}

				std::cout << std::endl;
				continue;
			}
			case 3: {
				std::filesystem::path filename;
				std::regex regex("get\\s+(\\S+)");
				std::smatch match;

				if (std::regex_search(command, match, regex)) {
					filename = match[1];
				}

				if (this->connection.get(filename)) {
					std::cout << "Try again! [-]" << std::endl;
				}
				continue;
			}
			default: {
				std::cout << "This command does not exist! Try again! [-]" << std::endl;
				continue;
			}
		}
		break;
	}
}

int8_t CommandLine::update_dir(const std::string& path) {
	return this->connection.update_dir(path);
}

void CommandLine::exit() {
	std::cout << "Goodbye!" << std::endl;
}

void CommandLine::help() {
	std::cout << "Commands list: " << std::endl
			<< "\t1. exit" << std::endl
			<< "\t2. help" << std::endl
			<< "\t3. list" << std::endl
			<< "\t4. get [filename]" << std::endl;
}

int8_t CommandLine::processing_command(const std::string& command) {
	int8_t index = -1;

	if (command.empty()) { return -1; }

	for (auto& item : this->commands) {
		++index;

		if (command.find(item) == 0) {
			return index;
		}
	}

	return -1;
}