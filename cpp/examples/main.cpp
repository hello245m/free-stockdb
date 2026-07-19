#include "stockdb/client.hpp"
#include <iostream>
#include <chrono>
#include <iomanip>

int main() {
    std::cout << "==========================================" << std::endl;
    std::cout << "  StockDB C++ High-Performance Client Test" << std::endl;
    std::cout << "==========================================" << std::endl;

    stockdb::StockDbClient client;
    if (!client.connect("127.0.0.1", 7899)) {
        std::cerr << "Failed to connect to stockdb server at 127.0.0.1:7899" << std::endl;
        return 1;
    }
    std::cout << "[+] Connected to StockDB local engine successfully." << std::endl;

    // 1. 获取股票列表
    auto stocks = client.get_stock_list();
    std::cout << "[+] Stock list size: " << stocks.size() << std::endl;
    for (const auto& s : stocks) {
        std::cout << "    - Code: " << s.code << " | Name: " << s.name 
                  << " | Market: " << s.market << std::endl;
    }

    // 2. 基准测试与吞吐量验证
    std::cout << "\n[+] Running Benchmark: Vectorized Indicator Computation..." << std::endl;
    std::vector<stockdb::KRecord> records;
    records.reserve(50000);
    
    // 生成 50000 根线测试 C++ 引擎向量化算力
    for (size_t i = 0; i < 50000; ++i) {
        stockdb::KRecord rec;
        rec.datetime = 20200101 + (uint32_t)(i % 365);
        rec.close = 100.0f + static_cast<float>(i % 50);
        rec.open = rec.close - 1.0f;
        rec.high = rec.close + 2.0f;
        rec.low = rec.close - 2.0f;
        rec.volume = 10000.0 + i;
        rec.amount = rec.volume * rec.close;
        records.push_back(rec);
    }

    auto start = std::chrono::high_resolution_clock::now();
    
    // 计算 MA5, MA20
    auto ma5 = stockdb::StockDbClient::compute_ma(records, 5);
    auto ma20 = stockdb::StockDbClient::compute_ma(records, 20);
    
    // 计算 MACD(12, 26, 9)
    std::vector<double> dif, dea, macd;
    stockdb::StockDbClient::compute_macd(records, 12, 26, 9, dif, dea, macd);

    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> duration = end - start;

    std::cout << "[+] Calculated MA5, MA20, MACD for 50,000 K-line records in " 
              << std::fixed << std::setprecision(3) << duration.count() << " ms." << std::endl;
    std::cout << "[+] Throughput: " << std::fixed << std::setprecision(0)
              << (50000.0 / (duration.count() / 1000.0)) << " records/sec" << std::endl;

    std::cout << "\n==========================================" << std::endl;
    std::cout << "  Benchmark Complete." << std::endl;
    std::cout << "==========================================" << std::endl;

    return 0;
}
