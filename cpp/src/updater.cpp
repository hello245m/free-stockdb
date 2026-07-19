#include "stockdb/updater.hpp"

#include <curl/curl.h>
#include <openssl/evp.h>

#include <chrono>
#include <cctype>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string_view>
#include <vector>

namespace stockdb {
namespace {

namespace fs = std::filesystem;

struct ManifestEntry {
    std::string sha256;
    std::uintmax_t size = 0;
    fs::path relative_path;
};

bool is_http_url(const std::string& value) {
    return value.rfind("http://", 0) == 0 || value.rfind("https://", 0) == 0;
}

std::string local_source_path(std::string value) {
    constexpr std::string_view file_prefix = "file://";
    if (value.rfind(file_prefix, 0) == 0) value.erase(0, file_prefix.size());
    if (value.size() >= 3 && value[0] == '/' && std::isalpha(static_cast<unsigned char>(value[1])) && value[2] == ':') {
        value.erase(0, 1);
    }
    return value;
}

bool is_safe_relative_path(const fs::path& path) {
    if (path.empty() || path.is_absolute()) return false;
    for (const auto& component : path) {
        if (component == "..") return false;
    }
    return true;
}

std::string sha256_file(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) return {};

    EVP_MD_CTX* context = EVP_MD_CTX_new();
    if (context == nullptr) return {};

    std::string result;
    if (EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1) {
        std::vector<char> buffer(64 * 1024);
        while (input.good()) {
            input.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
            const auto count = input.gcount();
            if (count > 0 && EVP_DigestUpdate(context, buffer.data(), static_cast<size_t>(count)) != 1) {
                EVP_MD_CTX_free(context);
                return {};
            }
        }

        unsigned char digest[EVP_MAX_MD_SIZE];
        unsigned int length = 0;
        if (EVP_DigestFinal_ex(context, digest, &length) == 1) {
            std::ostringstream hex;
            for (unsigned int i = 0; i < length; ++i) {
                hex << std::hex << std::setw(2) << std::setfill('0')
                    << static_cast<unsigned int>(digest[i]);
            }
            result = hex.str();
        }
    }

    EVP_MD_CTX_free(context);
    return result;
}

bool parse_manifest(const std::string& text, std::vector<ManifestEntry>* entries) {
    std::istringstream stream(text);
    std::string line;
    std::size_t line_number = 0;

    while (std::getline(stream, line)) {
        ++line_number;
        if (line.empty() || line.front() == '#') continue;

        std::istringstream fields(line);
        ManifestEntry entry;
        std::string path;
        if (!(fields >> entry.sha256 >> entry.size >> path) || entry.sha256.size() != 64) {
            std::cerr << "[Updater] Invalid manifest entry at line " << line_number << "\n";
            return false;
        }
        std::transform(entry.sha256.begin(), entry.sha256.end(), entry.sha256.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        entry.relative_path = fs::path(path).lexically_normal();
        if (!is_safe_relative_path(entry.relative_path)) {
            std::cerr << "[Updater] Unsafe manifest path at line " << line_number << "\n";
            return false;
        }
        entries->push_back(std::move(entry));
    }

    return !entries->empty();
}

size_t write_to_string(char* data, size_t size, size_t count, void* user_data) {
    auto* output = static_cast<std::string*>(user_data);
    output->append(data, size * count);
    return size * count;
}

struct FileWriter {
    std::ofstream output;
    bool failed = false;
};

size_t write_to_file(char* data, size_t size, size_t count, void* user_data) {
    auto* writer = static_cast<FileWriter*>(user_data);
    const auto bytes = size * count;
    writer->output.write(data, static_cast<std::streamsize>(bytes));
    if (!writer->output) {
        writer->failed = true;
        return 0;
    }
    return bytes;
}

bool download_to_string(const std::string& url, std::string* output) {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return false;
    CURL* curl = curl_easy_init();
    if (curl == nullptr) {
        curl_global_cleanup();
        return false;
    }

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_FAILONERROR, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_to_string);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, output);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "free-stockdb-updater/1.0");
    const bool ok = curl_easy_perform(curl) == CURLE_OK;
    curl_easy_cleanup(curl);
    curl_global_cleanup();
    return ok;
}

bool download_to_file(const std::string& url, const fs::path& target) {
    FileWriter writer{std::ofstream(target, std::ios::binary), false};
    if (!writer.output) return false;

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return false;
    CURL* curl = curl_easy_init();
    if (curl == nullptr) {
        curl_global_cleanup();
        return false;
    }

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_FAILONERROR, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_to_file);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &writer);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "free-stockdb-updater/1.0");
    const bool ok = curl_easy_perform(curl) == CURLE_OK && !writer.failed;
    curl_easy_cleanup(curl);
    curl_global_cleanup();
    writer.output.close();
    return ok;
}

bool load_manifest(const std::string& source, std::string* manifest) {
    if (is_http_url(source)) {
        const std::string base = source.back() == '/' ? source.substr(0, source.size() - 1) : source;
        return download_to_string(base + "/manifest.txt", manifest);
    }

    std::ifstream input(fs::path(local_source_path(source)) / "manifest.txt", std::ios::binary);
    if (!input) return false;
    *manifest = std::string(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
    return true;
}

bool fetch_entry(const std::string& source, const ManifestEntry& entry, const fs::path& temp_file) {
    if (is_http_url(source)) {
        const std::string base = source.back() == '/' ? source.substr(0, source.size() - 1) : source;
        return download_to_file(base + "/" + entry.relative_path.generic_string(), temp_file);
    }

    std::error_code error;
    fs::copy_file(fs::path(local_source_path(source)) / entry.relative_path, temp_file,
                  fs::copy_options::overwrite_existing, error);
    return !error;
}

}  // namespace

StockDbUpdater::StockDbUpdater() = default;
StockDbUpdater::~StockDbUpdater() = default;

void StockDbUpdater::set_data_source(const std::string& source_path) {
    data_source_ = source_path;
}

void StockDbUpdater::set_target_db_path(const std::string& target_path) {
    target_db_path_ = target_path;
}

UpdateStats StockDbUpdater::sync_incremental(KType ktype) {
    (void)ktype;
    UpdateStats stats;
    const auto started = std::chrono::steady_clock::now();

    std::string manifest_text;
    std::vector<ManifestEntry> entries;
    if (data_source_.empty() || target_db_path_.empty() || !load_manifest(data_source_, &manifest_text) ||
        !parse_manifest(manifest_text, &entries)) {
        std::cerr << "[Updater] Could not load a valid manifest.txt from the configured source.\n";
        stats.failed_files = 1;
        return stats;
    }

    std::error_code error;
    fs::create_directories(target_db_path_, error);
    if (error) {
        std::cerr << "[Updater] Cannot create target directory: " << error.message() << "\n";
        stats.failed_files = static_cast<uint32_t>(entries.size());
        return stats;
    }

    stats.total_files = static_cast<uint32_t>(entries.size());
    for (const auto& entry : entries) {
        const fs::path target = fs::path(target_db_path_) / entry.relative_path;
        const std::string expected_hash = entry.sha256;
        if (fs::exists(target, error) && !error && fs::file_size(target, error) == entry.size &&
            !error && sha256_file(target) == expected_hash) {
            continue;
        }

        fs::create_directories(target.parent_path(), error);
        const fs::path temporary = target.string() + ".part";
        fs::remove(temporary, error);
        if (error || !fetch_entry(data_source_, entry, temporary) || fs::file_size(temporary, error) != entry.size ||
            error || sha256_file(temporary) != expected_hash) {
            std::cerr << "[Updater] Failed integrity check: " << entry.relative_path.generic_string() << "\n";
            fs::remove(temporary, error);
            ++stats.failed_files;
            continue;
        }

        fs::rename(temporary, target, error);
        if (error) {
            fs::remove(target, error);
            error.clear();
            fs::rename(temporary, target, error);
        }
        if (error) {
            std::cerr << "[Updater] Failed to replace target: " << entry.relative_path.generic_string() << "\n";
            fs::remove(temporary, error);
            ++stats.failed_files;
            continue;
        }

        ++stats.updated_files;
        stats.transferred_bytes += entry.size;
    }

    stats.time_elapsed_sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    return stats;
}

bool StockDbUpdater::verify_synced_files() {
    std::string manifest_text;
    std::vector<ManifestEntry> entries;
    if (data_source_.empty() || target_db_path_.empty() || !load_manifest(data_source_, &manifest_text) ||
        !parse_manifest(manifest_text, &entries)) {
        std::cerr << "[Updater] Could not load a valid manifest.txt from the configured source.\n";
        return false;
    }

    bool valid = true;
    for (const auto& entry : entries) {
        const fs::path path = fs::path(target_db_path_) / entry.relative_path;
        std::error_code error;
        if (!fs::exists(path, error) || error || fs::file_size(path, error) != entry.size || error ||
            sha256_file(path) != entry.sha256) {
            std::cerr << "[Updater] Verification failed: " << entry.relative_path.generic_string() << "\n";
            valid = false;
        }
    }
    return valid;
}

}  // namespace stockdb
