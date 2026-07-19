#include "stockdb/server.hpp"
#include <iostream>
#include <string>
#include <thread>
#include <chrono>

void print_banner() {
    std::cout << "=====================================================\n"
              << "   StockDB High-Performance Time-Series Database Server\n"
              << "   Version: 1.0.0 (Fully Open-Source C++ Edition)\n"
              << "=====================================================\n";
}

void print_help() {
    std::cout << "Usage: stockdb [options]\n"
              << "Options:\n"
              << "  --host <ip>        Listening IP address (default: 127.0.0.1)\n"
              << "  --port <port>      Listening HTTP/TCP port (default: 7899)\n"
              << "  --data <dir>       Path to local stock data directory (default: ./data)\n"
              << "  --help             Display this help message\n";
}

int main(int argc, char* argv[]) {
    print_banner();

    stockdb::ServerConfig config;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--host" && i + 1 < argc) {
            config.host = argv[++i];
        } else if (arg == "--port" && i + 1 < argc) {
            config.port = static_cast<uint16_t>(std::stoi(argv[++i]));
        } else if (arg == "--data" && i + 1 < argc) {
            config.data_dir = argv[++i];
        } else if (arg == "--help") {
            print_help();
            return 0;
        }
    }

    stockdb::StockDbServer server(config);
    if (!server.start()) {
        std::cerr << "[!] Failed to start StockDB Server. Exiting.\n";
        return 1;
    }

    std::cout << "\n[+] StockDB Server is now running. Press Ctrl+C to stop.\n";

    // 维持主线程运行
    while (server.is_running()) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }

    return 0;
}
