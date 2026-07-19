#ifndef STOCKDB_SERVER_HPP
#define STOCKDB_SERVER_HPP

#include <string>
#include <vector>
#include <map>
#include <memory>
#include <functional>
#include "stockdb/client.hpp"

namespace stockdb {

struct ServerConfig {
    std::string host = "127.0.0.1";
    uint16_t port = 7899;
    std::string data_dir = "./data";
    std::string password = "";
    int thread_count = 4;
    // LevelDB tuning (maps to stockdb.conf [leveldb] section)
    int cache_size = 500;           // MB
    int write_buffer_size = 16;     // MB
    int block_size = 32;            // KB
    bool compression = true;
};

class StockDbServerImpl;

class StockDbServer {
public:
    explicit StockDbServer(const ServerConfig& config = ServerConfig());
    ~StockDbServer();

    StockDbServer(const StockDbServer&) = delete;
    StockDbServer& operator=(const StockDbServer&) = delete;

    StockDbServer(StockDbServer&&) noexcept;
    StockDbServer& operator=(StockDbServer&&) noexcept;

    // 启动/停止服务
    bool start();
    void stop();
    bool is_running() const;

    // HTTP / Socket 消息路由与查询处理
    std::string handle_http_request(const std::string& method, const std::string& path, const std::string& query_string);

    // 核心底层交互方法 (兼容 rd.get 协议)
    std::string process_cmd_get(const std::string& key_expr);
    std::string process_zb_get(const std::string& name, const std::string& codes, const std::string& start, const std::string& end);
    std::string process_bk_get(const std::string& target, int category);

private:
    std::unique_ptr<StockDbServerImpl> pimpl_;
};

} // namespace stockdb

#endif // STOCKDB_SERVER_HPP
