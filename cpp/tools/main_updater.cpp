#include "stockdb/updater.hpp"
#include <iostream>
#include <fstream>
#include <string>

namespace {

std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::string read_source_config(const std::string& config_path) {
    std::ifstream input(config_path);
    std::string line;
    while (std::getline(input, line)) {
        line = trim(line);
        if (!line.empty() && line.front() != '#') return line;
    }
    return {};
}

}  // namespace

void print_usage() {
    std::cout << "Usage: stockdb_updater [options]\n"
              << "Options:\n"
              << "  --source <path|url> Local snapshot directory or HTTP(S) mirror\n"
              << "  --config <path>     Source config file (default: ./sync_url.txt)\n"
              << "  --target <path>     Target data directory (default: ./data)\n"
              << "  --sync              Synchronize files listed in manifest.txt\n"
              << "  --verify            Verify synchronized files against manifest.txt\n"
              << "  --help              Display this help message\n";
}

int main(int argc, char* argv[]) {
    std::cout << "===============================================\n"
              << "  StockDB Local Data Update & Sync Utility v1.0\n"
              << "===============================================\n";

    if (argc < 2) {
        print_usage();
        return 0;
    }

    std::string source_path;
    std::string config_path = "./sync_url.txt";
    std::string target_path = "./data";
    bool do_sync = false;
    bool do_verify = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--source" && i + 1 < argc) {
            source_path = argv[++i];
        } else if (arg == "--config" && i + 1 < argc) {
            config_path = argv[++i];
        } else if (arg == "--target" && i + 1 < argc) {
            target_path = argv[++i];
        } else if (arg == "--sync") {
            do_sync = true;
        } else if (arg == "--verify") {
            do_verify = true;
        } else if (arg == "--help") {
            print_usage();
            return 0;
        }
    }

    if (source_path.empty()) source_path = read_source_config(config_path);
    if (source_path.empty()) {
        std::cerr << "[!] No data source configured. Add one URL or local path to "
                  << config_path << ", or pass --source.\n";
        return 2;
    }

    stockdb::StockDbUpdater updater;
    updater.set_data_source(source_path);
    updater.set_target_db_path(target_path);

    if (do_verify) {
        return updater.verify_synced_files() ? 0 : 1;
    }

    if (do_sync) {
        std::cout << "[+] Starting local data sync process...\n";
        auto stats = updater.sync_incremental(stockdb::KType::DAY);

        std::cout << "\n===============================================\n"
                  << " Sync Summary:\n"
                  << "  - Files in manifest:      " << stats.total_files << "\n"
                  << "  - Updated files:          " << stats.updated_files << "\n"
                  << "  - Failed files:           " << stats.failed_files << "\n"
                  << "  - Transferred bytes:      " << stats.transferred_bytes << "\n"
                  << "  - Time Elapsed:           " << stats.time_elapsed_sec << " seconds\n"
                  << "===============================================\n";
    }

    return 0;
}
