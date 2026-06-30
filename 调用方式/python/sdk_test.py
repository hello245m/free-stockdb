from stock_sdk import StockDBClient


def main():
    client = StockDBClient(host="127.0.0.1", port=7899)

    #查询get_data:
    
    k = client.get_data(
        "600633", 
        start="20260625", 
        end="20260625", 
        frequency="5m", 
        fields="code,volume,amount,close,date",
        fq="qfq"
    )
    print(k)

if __name__ == "__main__":
    main()


    """
    #参数说明：
        k = rd.get_data(
            code="600633",                   # 【必须】单股"600633" 或 批量列表["600633", "600422"]
            start="20260625",                # 【可选】默认None(查全量)。8位日期"YYYYMMDD" 或 14位日期(到秒)
            end="20260625",                  # 【可选】默认None(查全量)。8位日期"YYYYMMDD" 或 14位日期
            frequency="5m",                  # 【可选】默认'1d'。可选: 1d(日K), 1m/5m/15m/30m/60m(分钟), 1w(周), 1M(月)
            fields="date,code,volume,close", # 【可选】默认None(全字段dict)。可选: 字段逗号拼接串 或 列表
            limit=100,                       # 【可选】默认None(不限)。限制返回的最大记录条数
            desc=False,                      # 【可选】默认False(升序)。True(时间降序) / False(时间升序)
            as_df=False                      # 【可选】默认False(返回list)。True(返回 Pandas DataFrame) / False
            fq="qfq"                         # 【可选】默认qfq(返回前复权)。hfq(返回 后复权) / None返回 不复权
        )
        print(k)
    """


    """
    ##异步##get_data_async

    k = await client.get_data_async(.....)

    """