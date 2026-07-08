import os
import sys
import json
import asyncio

# 确保以当前文件夹作为模块加载的第一优先级路径（实现 ai_mcp 独立目录可用）
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# 直接从同级目录下导入自包含依赖
from native_mcp import NativeMCP
from stock_sdk import StockDBClient

# 1. 实例化本地纯异步 NativeMCP 服务器
mcp = NativeMCP("StockDB-Native-Server")

# 2. 实例化股票数据库客户端
client = StockDBClient(host="127.0.0.1", port=7899)

# 3. 注册行情查询工具给大语言模型
@mcp.tool()
async def get_market_kline(
    code: str,
    start: str = None,
    end: str = None,
    frequency: str = "1d",
    fields: str = "date,code,open,high,low,close,volume",
    limit: int = 100
) -> str:
    """
    获取A股股票行情K线数据。
    支持的周期(frequency): 
      - '1d'(日K), '1m'(1分K)
      - '5m'(5分K), '15m'(15分K), '30m'(30分K), '60m'(60分K)
      - '1w'(周K), '1M'(月K)
    参数说明:
      - code: 6位数字股票代码 (例如 "600633")
      - start: 开始日期，8位格式 (例如 "20260620", 可选)
      - end: 结束日期，8位格式 (例如 "20260626", 可选)
      - frequency: 周期频率，可选 1d/1m/5m/15m/30m/60m/1w/1M
      - fields: 投影字段，以逗号分隔，可选 date,code,name,open,high,low,close,volume,amount,pct_chg 等
      - limit: 限制返回结果条数上限 (默认 100)
    """
    try:
        # 调用同级目录下 stock_sdk 暴露的异步 get_data_async 接口
        data = await client.get_data_async(
            code=code,
            start=start,
            end=end,
            frequency=frequency,
            fields=fields,
            limit=limit
        )
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return f"获取数据失败，原因: {str(e)}"

# 4. 执行异步 stdin/stdout 消息循环
if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
