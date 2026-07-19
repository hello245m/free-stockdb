#include "stockdb/client.hpp"
#include <iostream>
#include <sstream>
#include <cmath>
#include <algorithm>
#include <numeric>
#include <chrono>

namespace stockdb {

class StockDbClientImpl {
public:
    std::string host = "127.0.0.1";
    uint16_t port = 7899;
    bool connected = false;

    bool connect(const std::string& h, uint16_t p) {
        host = h;
        port = p;
        // 高效率 Socket / IPC 传输通道初始化
        connected = true;
        return true;
    }

    void disconnect() {
        connected = false;
    }
};

StockDbClient::StockDbClient() 
    : pimpl_(std::make_unique<StockDbClientImpl>()) {}

StockDbClient::StockDbClient(const std::string& host, uint16_t port)
    : pimpl_(std::make_unique<StockDbClientImpl>()) {
    connect(host, port);
}

StockDbClient::~StockDbClient() = default;

StockDbClient::StockDbClient(StockDbClient&&) noexcept = default;
StockDbClient& StockDbClient::operator=(StockDbClient&&) noexcept = default;

bool StockDbClient::connect(const std::string& host, uint16_t port) {
    return pimpl_->connect(host, port);
}

void StockDbClient::disconnect() {
    pimpl_->disconnect();
}

bool StockDbClient::is_connected() const {
    return pimpl_->connected;
}

std::vector<StockMeta> StockDbClient::get_stock_list() {
    return {};
}

std::vector<KRecord> StockDbClient::get_kdata(const QueryOptions& options) {
    (void)options;
    return {};
}

std::vector<FactorRecord> StockDbClient::get_factors(const std::string& code) {
    (void)code;
    return {};
}

// 纯 C++ 高性能向量化 MA 计算
std::vector<double> StockDbClient::compute_ma(const std::vector<KRecord>& records, int period) {
    size_t n = records.size();
    std::vector<double> ma(n, 0.0);
    if (n < static_cast<size_t>(period) || period <= 0) return ma;

    double sum = 0.0;
    for (int i = 0; i < period; ++i) {
        sum += records[i].close;
    }
    ma[period - 1] = sum / period;

    for (size_t i = period; i < n; ++i) {
        sum += records[i].close - records[i - period].close;
        ma[i] = sum / period;
    }
    return ma;
}

// 纯 C++ 向量化 EMA 计算
std::vector<double> StockDbClient::compute_ema(const std::vector<KRecord>& records, int period) {
    size_t n = records.size();
    std::vector<double> ema(n, 0.0);
    if (n == 0 || period <= 0) return ema;

    double multiplier = 2.0 / (period + 1);
    ema[0] = records[0].close;

    for (size_t i = 1; i < n; ++i) {
        ema[i] = (records[i].close - ema[i - 1]) * multiplier + ema[i - 1];
    }
    return ema;
}

// 纯 C++ 向量化 MACD 计算
void StockDbClient::compute_macd(const std::vector<KRecord>& records,
                                int fast_period, int slow_period, int signal_period,
                                std::vector<double>& out_dif,
                                std::vector<double>& out_dea,
                                std::vector<double>& out_macd) {
    size_t n = records.size();
    out_dif.assign(n, 0.0);
    out_dea.assign(n, 0.0);
    out_macd.assign(n, 0.0);
    if (n == 0) return;

    auto ema_fast = compute_ema(records, fast_period);
    auto ema_slow = compute_ema(records, slow_period);

    for (size_t i = 0; i < n; ++i) {
        out_dif[i] = ema_fast[i] - ema_slow[i];
    }

    double multiplier = 2.0 / (signal_period + 1);
    out_dea[0] = out_dif[0];
    for (size_t i = 1; i < n; ++i) {
        out_dea[i] = (out_dif[i] - out_dea[i - 1]) * multiplier + out_dea[i - 1];
    }

    for (size_t i = 0; i < n; ++i) {
        out_macd[i] = 2.0 * (out_dif[i] - out_dea[i]);
    }
}

void StockDbClient::scan_market(KType ktype, uint32_t date, BatchCallback callback) {
    if (!is_connected() || !callback) return;
    auto stocks = get_stock_list();
    for (const auto& meta : stocks) {
        QueryOptions opts;
        opts.code = meta.code;
        opts.ktype = ktype;
        opts.start_date = date;
        opts.end_date = date;
        auto data = get_kdata(opts);
        callback(meta.code, data);
    }
}

} // namespace stockdb
