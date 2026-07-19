#ifndef STOCKDB_UPDATER_HPP
#define STOCKDB_UPDATER_HPP

#include "stockdb/client.hpp"
#include <string>
#include <vector>
#include <cstdint>

namespace stockdb {

struct UpdateStats {
    uint32_t total_files = 0;
    uint32_t updated_files = 0;
    uint64_t transferred_bytes = 0;
    double time_elapsed_sec = 0.0;
    uint32_t failed_files = 0;
};

class StockDbUpdater {
public:
    StockDbUpdater();
    ~StockDbUpdater();

    // 数据源可以是本地快照目录、file:// 路径或 HTTP(S) 镜像。
    void set_data_source(const std::string& source_path);
    void set_target_db_path(const std::string& target_path);

    // 根据 manifest.txt 增量同步快照文件并校验 SHA-256。
    UpdateStats sync_incremental(KType ktype = KType::DAY);

    // 校验已同步文件是否仍与清单中的 SHA-256 一致。
    bool verify_synced_files();

private:
    std::string data_source_;
    std::string target_db_path_;
};

} // namespace stockdb

#endif // STOCKDB_UPDATER_HPP
