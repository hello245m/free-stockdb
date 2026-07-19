#include "stockdb/server.hpp"
#include <iostream>
#include <fstream>
#include <sstream>
#include <thread>
#include <atomic>
#include <chrono>
#include <algorithm>
#include <cmath>
#include <mutex>
#include <map>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <arpa/inet.h>
#endif

// LevelDB Headers
#include "leveldb/db.h"
#include "leveldb/write_batch.h"
#include "leveldb/cache.h"
#include "leveldb/filter_policy.h"
#include "leveldb/comparator.h"

namespace stockdb {

// ---------------------------------------------------------------------------
// LevelDB 存储引擎封装
// ---------------------------------------------------------------------------
class StorageEngine {
public:
    leveldb::DB* db_ = nullptr;
    leveldb::Options options_;
    std::string db_path_;

    explicit StorageEngine(const std::string& path, const ServerConfig& cfg)
        : db_path_(path) {
        options_.create_if_missing = true;
        options_.compression = cfg.compression ? leveldb::kSnappyCompression
                                               : leveldb::kNoCompression;
        options_.write_buffer_size = cfg.write_buffer_size * 1024 * 1024;
        options_.block_size = cfg.block_size * 1024;
        if (cfg.cache_size > 0) {
            options_.block_cache = leveldb::NewLRUCache(
                static_cast<size_t>(cfg.cache_size) * 1024 * 1024);
        }
        options_.filter_policy = leveldb::NewBloomFilterPolicy(10);
    }

    ~StorageEngine() {
        delete db_;
        delete options_.block_cache;
        delete options_.filter_policy;
    }

    bool open() {
        leveldb::Status s = leveldb::DB::Open(options_, db_path_, &db_);
        if (!s.ok()) {
            std::cerr << "[StorageEngine] Failed to open " << db_path_
                      << ": " << s.ToString() << "\n";
            return false;
        }
        std::cout << "[StorageEngine] Opened " << db_path_ << "\n";
        return true;
    }

    // 精确 Get
    bool get(const std::string& key, std::string* value) {
        if (!db_) return false;
        leveldb::Status s = db_->Get(leveldb::ReadOptions(), key, value);
        return s.ok();
    }

    // 写入
    bool put(const std::string& key, const std::string& value) {
        if (!db_) return false;
        return db_->Put(leveldb::WriteOptions(), key, value).ok();
    }

    // 批量写入
    bool write_batch(const std::vector<std::pair<std::string, std::string>>& entries) {
        if (!db_) return false;
        leveldb::WriteBatch batch;
        for (const auto& [k, v] : entries) {
            batch.Put(k, v);
        }
        return db_->Write(leveldb::WriteOptions(), &batch).ok();
    }

    // 前缀范围扫描 (核心查询路径: 日k:600519:* / 复权:* / 板块:*)
    std::vector<std::pair<std::string, std::string>>
    scan_prefix(const std::string& prefix, int limit = 10000) {
        std::vector<std::pair<std::string, std::string>> results;
        if (!db_) return results;

        leveldb::ReadOptions ro;
        std::unique_ptr<leveldb::Iterator> it(db_->NewIterator(ro));

        for (it->Seek(prefix); it->Valid(); it->Next()) {
            std::string key = it->key().ToString();
            if (key.compare(0, prefix.size(), prefix) != 0) break;
            results.emplace_back(key, it->value().ToString());
            if (static_cast<int>(results.size()) >= limit) break;
        }
        return results;
    }

    // 范围扫描 [start_key, end_key)
    std::vector<std::pair<std::string, std::string>>
    scan_range(const std::string& start_key, const std::string& end_key, int limit = 10000) {
        std::vector<std::pair<std::string, std::string>> results;
        if (!db_) return results;

        leveldb::ReadOptions ro;
        std::unique_ptr<leveldb::Iterator> it(db_->NewIterator(ro));

        for (it->Seek(start_key); it->Valid(); it->Next()) {
            std::string key = it->key().ToString();
            if (!end_key.empty() && key >= end_key) break;
            results.emplace_back(key, it->value().ToString());
            if (static_cast<int>(results.size()) >= limit) break;
        }
        return results;
    }
};

// ---------------------------------------------------------------------------
// Server 实现
// ---------------------------------------------------------------------------
class StockDbServerImpl {
public:
    ServerConfig config;
    std::atomic<bool> running{false};
    std::thread server_thread;
    std::unique_ptr<StorageEngine> engine;

#ifdef _WIN32
    SOCKET listen_fd = INVALID_SOCKET;
#else
    int listen_fd = -1;
#endif

    explicit StockDbServerImpl(const ServerConfig& cfg) : config(cfg) {
        engine = std::make_unique<StorageEngine>(cfg.data_dir, cfg);
    }

    ~StockDbServerImpl() { stop(); }

    bool start() {
        if (running.load()) return true;

        if (!engine->open()) {
            std::cerr << "[Server] Storage engine init failed.\n";
            return false;
        }

#ifdef _WIN32
        WSADATA wsaData;
        if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) return false;
#endif

        listen_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
#ifdef _WIN32
        if (listen_fd == INVALID_SOCKET) { WSACleanup(); return false; }
#else
        if (listen_fd < 0) return false;
#endif

        int opt = 1;
#ifdef _WIN32
        setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));
#else
        setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
#endif

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(config.port);
        inet_pton(AF_INET, config.host.c_str(), &addr.sin_addr);

        if (bind(listen_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            cleanup_socket(); return false;
        }
        if (listen(listen_fd, SOMAXCONN) < 0) {
            cleanup_socket(); return false;
        }

        running.store(true);
        std::cout << "[Server] http://" << config.host << ":" << config.port
                  << "  data=" << config.data_dir << "\n";

        server_thread = std::thread([this]() { accept_loop(); });
        return true;
    }

    void stop() {
        if (!running.load()) return;
        running.store(false);
        cleanup_socket();
        if (server_thread.joinable()) server_thread.join();
#ifdef _WIN32
        WSACleanup();
#endif
    }

private:
    void cleanup_socket() {
#ifdef _WIN32
        if (listen_fd != INVALID_SOCKET) { closesocket(listen_fd); listen_fd = INVALID_SOCKET; }
#else
        if (listen_fd >= 0) { close(listen_fd); listen_fd = -1; }
#endif
    }

    void accept_loop() {
        while (running.load()) {
            sockaddr_in ca{}; socklen_t cl = sizeof(ca);
#ifdef _WIN32
            SOCKET cfd = accept(listen_fd, (struct sockaddr*)&ca, &cl);
            if (cfd == INVALID_SOCKET) { if (!running.load()) break; continue; }
#else
            int cfd = accept(listen_fd, (struct sockaddr*)&ca, &cl);
            if (cfd < 0) { if (!running.load()) break; continue; }
#endif
            char buf[8192] = {0};
            int n = recv(cfd, buf, sizeof(buf) - 1, 0);
            if (n > 0) {
                std::string body = route(std::string(buf, n));
                std::ostringstream resp;
                resp << "HTTP/1.1 200 OK\r\n"
                     << "Content-Type: application/json; charset=utf-8\r\n"
                     << "Access-Control-Allow-Origin: *\r\n"
                     << "Content-Length: " << body.size() << "\r\n"
                     << "Connection: close\r\n\r\n" << body;
                std::string r = resp.str();
                send(cfd, r.c_str(), static_cast<int>(r.size()), 0);
            }
#ifdef _WIN32
            closesocket(cfd);
#else
            close(cfd);
#endif
        }
    }

    std::string route(const std::string& raw) {
        std::istringstream ss(raw);
        std::string method, uri, proto;
        ss >> method >> uri >> proto;

        std::map<std::string, std::string> params;
        size_t qp = uri.find('?');
        if (qp != std::string::npos) {
            std::istringstream qs(uri.substr(qp + 1));
            std::string pair;
            while (std::getline(qs, pair, '&')) {
                size_t eq = pair.find('=');
                if (eq != std::string::npos)
                    params[pair.substr(0, eq)] = pair.substr(eq + 1);
            }
        }

        const std::string& cmd = params["cmd"];
        if (cmd == "get")    return process_cmd_get(params["t"]);
        if (cmd == "set")    return process_cmd_set(params["key"], params["val"]);
        if (cmd == "zb.get") return process_zb_get(params["name"], params["codes"], params["start"], params["end"]);
        if (cmd == "bk.get") return process_bk_get(params["x"], params["category"]);

        return "{\"status\":\"ok\",\"engine\":\"StockDB/LevelDB\"}";
    }

public:
    // cmd=get  对应 rd.get() 协议
    std::string process_cmd_get(const std::string& expr) {
        // 精确匹配
        std::string val;
        if (engine->get(expr, &val)) return val;

        // 通配符前缀扫描
        std::string prefix = expr;
        size_t star = prefix.find('*');
        if (star != std::string::npos) prefix = prefix.substr(0, star);

        auto rows = engine->scan_prefix(prefix);
        if (rows.empty()) return "{\"status\":\"not_found\",\"key\":\"" + expr + "\"}";

        std::ostringstream out;
        out << "[";
        for (size_t i = 0; i < rows.size(); ++i) {
            if (i) out << ",";
            out << "[\"" << rows[i].first << "\"," << rows[i].second << "]";
        }
        out << "]";
        return out.str();
    }

    // cmd=set  对应 pipe.mset() 写入
    std::string process_cmd_set(const std::string& key, const std::string& val) {
        if (key.empty()) return "{\"status\":\"error\"}";
        engine->put(key, val);
        return "{\"status\":\"ok\"}";
    }

    // cmd=zb.get 指标计算
    std::string process_zb_get(const std::string& name, const std::string& codes,
                               const std::string& start, const std::string& end) {
        std::string code = codes.empty() ? "600519" : codes;
        std::string prefix = "日k:" + code + ":";
        std::string sk = start.empty() ? prefix : prefix + start;
        std::string ek = end.empty() ? "" : prefix + end + "~";

        auto rows = engine->scan_range(sk, ek);

        std::vector<double> prices;
        std::vector<std::string> dates;
        for (auto& [k, v] : rows) {
            dates.push_back(k.substr(prefix.size()));
            try { prices.push_back(std::stod(v)); } catch (...) {}
        }

        std::ostringstream out;
        out << "{\"code\":\"" << code << "\",\"indicator\":\"" << name << "\",\"data\":[";
        for (size_t i = 0; i < prices.size(); ++i) {
            if (i) out << ",";
            double ma5 = 0; int w5 = std::min((int)(i+1), 5);
            for (int j = 0; j < w5; ++j) ma5 += prices[i-j];
            ma5 /= w5;
            out << "{\"d\":\"" << dates[i] << "\",\"c\":" << prices[i] << ",\"ma5\":" << ma5 << "}";
        }
        out << "]}";
        return out.str();
    }

    // cmd=bk.get 板块查询
    std::string process_bk_get(const std::string& target, const std::string& cat) {
        if (!target.empty()) {
            std::string val;
            if (engine->get("板块:" + target, &val)) return val;
        }
        auto rows = engine->scan_prefix("板块:");
        std::ostringstream out;
        out << "[";
        for (size_t i = 0; i < rows.size(); ++i) {
            if (i) out << ",";
            out << rows[i].second;
        }
        out << "]";
        return out.str();
    }
};

// Public API 转发
StockDbServer::StockDbServer(const ServerConfig& c) : pimpl_(std::make_unique<StockDbServerImpl>(c)) {}
StockDbServer::~StockDbServer() = default;
StockDbServer::StockDbServer(StockDbServer&&) noexcept = default;
StockDbServer& StockDbServer::operator=(StockDbServer&&) noexcept = default;
bool StockDbServer::start() { return pimpl_->start(); }
void StockDbServer::stop() { pimpl_->stop(); }
bool StockDbServer::is_running() const { return pimpl_->running.load(); }
std::string StockDbServer::handle_http_request(const std::string& m, const std::string& p, const std::string& q) { return pimpl_->process_cmd_get(q); }
std::string StockDbServer::process_cmd_get(const std::string& k) { return pimpl_->process_cmd_get(k); }
std::string StockDbServer::process_zb_get(const std::string& n, const std::string& c, const std::string& s, const std::string& e) { return pimpl_->process_zb_get(n, c, s, e); }
std::string StockDbServer::process_bk_get(const std::string& t, int cat) { return pimpl_->process_bk_get(t, std::to_string(cat)); }

} // namespace stockdb
