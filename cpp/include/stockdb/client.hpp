#ifndef STOCKDB_CLIENT_HPP
#define STOCKDB_CLIENT_HPP

#include <string>
#include <vector>
#include <memory>
#include <cstdint>
#include <functional>

namespace stockdb {

enum class KType {
    DAY = 0,
    MIN1 = 1,
    MIN5 = 5,
    MIN15 = 15,
    MIN30 = 30,
    WEEK = 100,
    MONTH = 101
};

enum class AdjustType {
    NONE = 0,
    FORWARD = 1,   // 前复权
    BACKWARD = 2   // 后复权
};

// K线单棒记录 (32字节紧凑对齐，内存映射零拷贝优化)
struct alignas(8) KRecord {
    uint32_t datetime;  // YYYYMMDD 或 YYYYMMDDHHMM 格式时间戳
    float open;
    float high;
    float low;
    float close;
    double volume;      // 成交量
    double amount;      // 成交额
};

// 股票基本元数据
struct StockMeta {
    std::string code;
    std::string name;
    std::string market; // SH / SZ / BJ
    uint32_t list_date;
};

// 除权除息因子记录
struct FactorRecord {
    uint32_t date;
    double song_zhuan; // 送转股比例
    double pai_xi;     // 派息金额
    double peigu_jia;  // 配股价
    double peigu_li;   // 配股比例
};

struct QueryOptions {
    std::string code;
    KType ktype = KType::DAY;
    uint32_t start_date = 0;
    uint32_t end_date = 99999999;
    AdjustType adjust = AdjustType::NONE;
};

class StockDbClientImpl;

class StockDbClient {
public:
    StockDbClient();
    explicit StockDbClient(const std::string& host, uint16_t port);
    ~StockDbClient();

    // 禁用拷贝，允许移动
    StockDbClient(const StockDbClient&) = delete;
    StockDbClient& operator=(const StockDbClient&) = delete;
    StockDbClient(StockDbClient&&) noexcept;
    StockDbClient& operator=(StockDbClient&&) noexcept;

    // 连接管理
    bool connect(const std::string& host = "127.0.0.1", uint16_t port = 7899);
    void disconnect();
    bool is_connected() const;

    // 数据查询 API
    std::vector<StockMeta> get_stock_list();
    std::vector<KRecord> get_kdata(const QueryOptions& options);
    std::vector<FactorRecord> get_factors(const std::string& code);

    // 向量化指标计算扩展接口 (纯 C++ 高性能无开销计算)
    static std::vector<double> compute_ma(const std::vector<KRecord>& records, int period);
    static std::vector<double> compute_ema(const std::vector<KRecord>& records, int period);
    static void compute_macd(const std::vector<KRecord>& records, 
                             int fast_period, int slow_period, int signal_period,
                             std::vector<double>& out_dif, 
                             std::vector<double>& out_dea, 
                             std::vector<double>& out_macd);

    // 批量高效高并发数据并行扫描接口
    using BatchCallback = std::function<void(const std::string& code, const std::vector<KRecord>& data)>;
    void scan_market(KType ktype, uint32_t date, BatchCallback callback);

private:
    std::unique_ptr<StockDbClientImpl> pimpl_;
};

} // namespace stockdb

#endif // STOCKDB_CLIENT_HPP
