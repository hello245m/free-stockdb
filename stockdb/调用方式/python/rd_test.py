#####

#Stockdb v0.1.0
#股票专用数据库
#同步+异步+网络客户端

#K-V存储结构
#table:keyn:keyn_1 -> (int/float/str/dict/list)

# 日k:code:date -> dict
# 分钟k:code:date -> dict
#####


from stockdb import rd,init
import asyncio

#rd=init(host="127.0.0.1",port=7899,password="")


if 1:
    #-------基础------
    print(rd.get("股票代码"))
    #d->{'0': ['000001', '000002'],'6':['600001','600002']......}
    #mycodes=d['6']+d['0']+d['3']+d['1']+d['5']+d['9']
    print(rd.vals("退市*"))
    #->['600421', '600599', '600001', '600002'...]

    print(rd.get("日k:600633:20260625"))  
    print(rd.vals("日k",'600633', '20260625'))
    print(rd.keys("日k",'600633', '202606*')) #匹配
    #dict->{'amount': 189010000, 'amplitude': 2.38, 'close': 10.45, 'code': '600633', 'date': 20260625, 'float_mv': 13251000000, 'float_share': 1268074472, 'high': 10.62, 'is_st': False, 'low': 10.37, 'name': '浙数文化', 'open': 10.45, 'pb': 1.3, 'pct_chg': -0.67, 'pe_ttm': 22.5, 'pre_close': 10.52, 'total_mv': 13251000000, 'total_share': 1268074472, 'turnover': 1.42, 'vol_ratio': 0.9, 'volume': 18031500}

    print(rd.get("分钟k:600422:20260625145200"))
    print(rd.get("分钟k",'600422', '20260625145200').keys())
    print(rd.vals("分钟k",'60042*', '20260625145200').vals()) #匹配
    #dict->{'amount': 428554, 'close': 7.95, 'code': '600422', 'date': 20260625145200, 'high': 7.96, 'low': 7.94, 'open': 7.95, 'volume': 53900}


if 0:
    #------通配符------
    print(rd.vals("日k",'600633', '*'))
    print(rd.get("分钟k",'600422', '20260625*').get("volume"))
    print(rd.vals("日k",'*', '20260625'))
    print(rd.vals("日k",'6*', '20260625').get("amount"))

    #------范围+正反排序+截取------
    print(rd.get("日k",'600633', '20260620<20260626'))
    print(rd.get("日k",'600633', '20260620<N')[:3])
    print(rd.get("日k",'600633', '20260620>20260626')[:3])
    print(rd.vals("日k",'600633', '20260620>20260626')[-3:])


if 0:
    #------同步------
    print(rd.get("日k:600633:20260625"))

    print(rd.get("日k",'600633', '20260625'))

    #dict->{'amount': 189010000, 'amplitude': 2.38, 'close': 10.45, 'code': '600633', 'date': 20260625, 'float_mv': 13251000000, 'float_share': 1268074472, 'high': 10.62, 'is_st': False, 'low': 10.37, 'name': '浙数文化', 'open': 10.45, 'pb': 1.3, 'pct_chg': -0.67, 'pe_ttm': 22.5, 'pre_close': 10.52, 'total_mv': 13251000000, 'total_share': 1268074472, 'turnover': 1.42, 'vol_ratio': 0.9, 'volume': 18031500}

    print(rd.get("分钟k:600422:20260625145200"))

    print(rd.get("分钟k",'600422', '20260625145200'))
    #dict->{'amount': 428554, 'close': 7.95, 'code': '600422', 'date': 20260625145200, 'high': 7.96, 'low': 7.94, 'open': 7.95, 'volume': 53900}

    #------异步------
    print(

        asyncio.run(
            (lambda: rd.get("日k",'600633', '20260625'))()
        ),
        asyncio.run(
            (lambda: rd.get("分钟k",'600422', '20260625145200'))()
        )

    )


if 0:
    #------pipe------
    pp=rd.pipe()
    for i in rd.get("股票代码")['3'][:10]:
        pp.mget("分钟k",i,'20260625145200')
    #同步
    #print(pp)
    #异步
    print(
        asyncio.run(
            (lambda: pp)()
        )
    )

    #--------any-pipe------
    print(rd.vals("日k",'600633', '2026062*').get("code,date,amount,high"))
    #->[['600633', 20260622, 258471420, 11.08], ['600633', 20260623, 213739197, 11.08], ['600633', 20260624, 233130000, 10.83], ['600633', 20260625, 189010000, 10.62], ['600633', 20260626, 212620000, 10.41]]
    print(rd.vals("日k",'600633', '2026062*').get("date"))
    #->[20260622, 20260623, 20260624, 20260625, 20260626]