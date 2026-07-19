cmake_minimum_required(VERSION 3.14)
project(stockdb_cpp_sdk VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_path(LEVELDB_INCLUDE_DIR leveldb/db.h)
find_library(LEVELDB_LIBRARY NAMES leveldb)
if (NOT LEVELDB_INCLUDE_DIR OR NOT LEVELDB_LIBRARY)
    message(FATAL_ERROR "LevelDB headers and library are required. Set LEVELDB_INCLUDE_DIR and LEVELDB_LIBRARY if necessary.")
endif()
find_package(CURL REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

# Library target
add_library(stockdb_sdk STATIC
    src/client.cpp
    src/updater.cpp
    src/server.cpp
)

target_include_directories(stockdb_sdk PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
    PRIVATE ${LEVELDB_INCLUDE_DIR}
)

target_link_libraries(stockdb_sdk PUBLIC
    ${LEVELDB_LIBRARY}
    CURL::libcurl
    OpenSSL::Crypto
    Threads::Threads
)

if (WIN32)
    target_link_libraries(stockdb_sdk PUBLIC ws2_32)
endif()

# Core Database Server Target (Generates stockdb.exe)
add_executable(stockdb
    tools/main_server.cpp
)
target_link_libraries(stockdb PRIVATE stockdb_sdk)

# Example executable target (Client Demo & Benchmark)
add_executable(stockdb_example
    examples/main.cpp
)
target_link_libraries(stockdb_example PRIVATE stockdb_sdk)

# Local data synchronization utility
add_executable(stockdb_updater
    tools/main_updater.cpp
)
target_link_libraries(stockdb_updater PRIVATE stockdb_sdk)

# Installation target setup
install(TARGETS stockdb_sdk stockdb stockdb_example stockdb_updater
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)
install(DIRECTORY include/ DESTINATION include)
