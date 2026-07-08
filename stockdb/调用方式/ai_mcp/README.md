# StockDB Native MCP Server 使用指南

本目录实现了一个基于 `native_mcp`（纯标准库编写，零第三方依赖）的股票行情数据库 MCP 服务器。它可以将本地股票数据库的 K 线查询能力直接暴露给 AI 大模型（如 Claude Desktop 或 Cursor）。

---

## 1. 配置文件路径说明

如果您使用的是 **Claude Desktop**，请打开以下路径的配置文件：
`C:\Users\您的用户名\AppData\Roaming\Claude\claude_desktop_config.json`

（如果文件不存在，可以直接手动创建一个，确保内容为标准的 JSON 格式）。

---

## 2. 写入配置内容

在 `mcpServers` 部分加入本项目 MCP 服务器的运行配置：

```json
{
  "mcpServers": {
    "stockdb-native": {
      "command": "python",
      "args": [
        "-u",
        "C:/Users/elonm/stockdb/stockdb/调用方式/ai_mcp/stock_mcp_server.py"
      ]
    }
  }
}
```

> **注意**：
> 1. 请确认配置中的 `python` 可以在您的系统环境变量（PATH）中被直接调用。若不行，可替换为具体的 Python 绝对路径（例如 `C:/Users/用户名/miniconda3/python.exe`）。
> 2. 请确认本地 `stockdb.exe` 数据库服务已经在后台开启运行（监听 `7899` 端口）。

---

## 3. 测试与日常对话调用

配置并重启 Claude Desktop 后，您可以在聊天窗口的右下角工具箱（Plug 图标）中看到名为 `StockDB-Native-Server` 的工具已被加载。

您可以直接向 AI 提出如下的自然语言指令进行交互测试：

* **指令 1 (查日K)**：
  > "获取 600633 在 20260620 到 20260626 期间的日K线收盘价，并帮我分析走势。"
* **指令 2 (查 5分钟分时线并计算)**：
  > "帮我拉取 600422 在 20260625 全天的 5分钟K 线数据，计算全天成交均价并画一个简易走势图。"
* **指令 3 (周K合成分析)**：
  > "查询 600633 在 20260601 到 20260626 之间的周K线，帮我分析近期的换手率和涨跌幅趋势。"
