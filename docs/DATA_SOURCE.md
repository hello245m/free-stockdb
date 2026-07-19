# 数据源与镜像协议

`stockdb_updater` 不内置任何数据地址。它从 `sync_url.txt` 的第一条有效配置，或命令行 `--source` 参数读取镜像根目录。

支持的镜像根目录：

- 本地目录，例如 `D:/stockdb-mirror`
- `file://` URL，例如 `file:///D:/stockdb-mirror`
- HTTP(S) URL，例如 `https://data.example.com/stockdb`

## 镜像清单

镜像根目录必须包含 UTF-8 文本文件 `manifest.txt`。每一行格式为：

```text
<sha256> <size-in-bytes> <relative-path>
```

示例：

```text
# sha256 size path
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 0 CURRENT
1d5e4a2b3c4d5e6f718293a4b5c6d7e8f90123456789abcdef0123456789abcd 4096 000001.ldb
```

路径必须是相对路径，不能包含 `..`。同步器先下载或复制到 `*.part` 临时文件，验证大小和 SHA-256 后再替换目标文件。已存在且校验一致的文件会跳过。

## 生成清单

镜像发布者应在完成数据快照后，列出需要同步的全部文件，并为每个文件生成 SHA-256 和字节数。发布新快照时先上传数据文件，最后更新 `manifest.txt`，避免客户端读取到半完成清单。

当镜像中包含 LevelDB 数据库文件时，清单必须包含同一快照中的 `CURRENT`、`MANIFEST-*`、`.ldb` 和必要日志文件。同步期间应停止本地服务，待同步完成后再启动服务。

## 安全建议

- 公网镜像必须使用 HTTPS；HTTP 仅适用于隔离内网。
- SHA-256 能发现传输损坏和不匹配内容，但不能代替对镜像发布者的信任。
- 数据源的授权、频率限制、再分发条款由使用者和镜像发布者负责确认。
