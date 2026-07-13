from zhibiao import zb,bk

# 架构
# from zhibiao import bk, zb
# 指标 zb.get 支持  39种指标 *  5种指数
# 板块 bk.get 支持 板块 <-> 股票  双向映射



"""
第一部分：zb.get()
#能力： 支持39种指标 * 5种指数计算
#接口： 一次计算得到  全市场n只股票 * n个指标 * n指定参数单指标
"""


if 1:
    # 一次计算得到             N 只股票      +           N 个参数单指标      +         N 个独立指标 
    # 输出             【"600633", "000007"】  【ma5:xx, ma10:xx, ma20:xx ,  k:xx, d:xx, j:xx ,dif:xx, dea:xx, macd:xx】
    d = zb.get("ma,kdj,macd", ["600633", "000007"], start="20260601", end="20260630", frequency="1d",n=["5,10,20",None,"12,26,9"])
    print(1, d) 
 

    #接上 -> 多股票*多指标 -> 金叉数据 （cross=True）
    d = zb.get("ma,kdj,macd", ["600633", "000007"], start="20260601", end="20260630", frequency="1d",n=["5,10,20",None,"12,26,9"], cross=True)
    print(2, d)


    #接上 -> 多股票*多指标 金叉数据 + 原始指标 （cross="with_value"）
    d = zb.get("ma,kdj,macd", ["600633", "000007"], start="20260601", end="20260630", frequency="1d",n=["5,10,20",None,"12,26,9"], cross="with_value")
    print(3, d)

    #计算单指标（其它参数均为可选）
    d = zb.get("macd","600633",end="N")
    print(4, d[-3:])

    #可变参数格式
    d = zb.get(["ma","kdj","macd"],"600633",end="N")
    print(5, d)

    #指数
    #计算 多股票集合指数 (支持 1平权 + 4种加权指数计算)
    d = zb.get("zhishu", ["600633", "000007"], start="20260601", end="N", frequency="1d",method=1)
    print(6, d[-3:])


"""
第二部分： (板块 <-> 股票  双向映射)
  bk.get(name/code,num,fields) 
  0=概念版块
  1=申万一级
  2=申万二级
  3=申万三级
"""

# 1. 查股票 -> name,code,symbols
if 1:
     d = bk.get("600633", 1)         #查600633 -> 申万一级
     print(0, d)
     #[{'code': '801760.SL', 'name': '传媒', 'source': 'sw', 'type': 'sw_1', 'group': '申万行业指数列表', 'category': '申万一级'}]

     d = bk.get("600633", 1, "group,name")
     print(1, d)
     # [['申万行业指数列表', '传媒']]

     d = bk.get("600633", 0, "name")  #查600633 -> 所属概念
     print(2, d[:8])
     # ['AIGC概念', 'AI应用', 'AI智能体', 'AI视频', 'DeepSeek概念', 'NFT概念', '东数西算(算力)', '云计算']

     d = bk.get(["600633", "000007"], 1, "name")
     print(3, d)
     # {'600633': ['传媒'], '000007': ['通信']}

# 2. 查板块 -> name,code,symbols
if 0:
     d = bk.get("5G", 0, "code")
     print(4, d)
     # 300843.TI

     d = bk.get("5G", 0, "symbols") #查5G概念 -> 对应股票
     print(5, d[:10])
     # ['000016', '000049', '000007', '000066', '000070', '000156', '000409', '000547', '000555', '000586']

     d = bk.get("交通运输", 1, "symbols")
     print(6, d[:10])
     # ['000088', '000089', '000099', '000429', '000520', '000548', '000557', '000582', '000626', '000755']

     d = bk.get("801170.SL")
     print(7, {k: d[k] for k in d if k != "symbols"})
     # {'code': '801170.SL', 'name': '交通运输', 'source': 'sw', 'type': 'sw_1', 'group': '申万行业指数列表', 'category': '申万一级'}

# 3. 模糊匹配
if 0:
     d = bk.get("电池", 0, "name")
     print(8, d[:10])
     # ['BC电池', 'HJT电池', 'TOPCON电池', '动力电池回收', '固态电池', '燃料电池', '钒电池', '钙钛矿电池', '钠离子电池', '铅蓄电池']

     # 4. 取分类全集

     d = bk.get(category=1, fields="name,code")
     print(9, d)
     # ['交通运输', '休闲服务', '传媒', '公用事业', '农林牧渔', '化工', '医药生物', '商业贸易', '国防军工', '家用电器', '建筑材料', '建筑装饰', '房地产', '有色金属', '机械设备', '汽车', '电子', '电气设备', '纺织服装', '综合', '计算机', '轻工制造', '通信', '采掘', '钢铁', '银行', '非银金融', '食品饮料']



"""
1、更多说明: zb.get() 支持 39 种指标/指数计算
 zb.get(...) 负责从 stockdb 取行情、整理矩阵、计算并返回 rows。
 zb.MA(...)、zb.MACD(...)、zb.CROSS(...) 适合临时直接传数字列表计算。
 单股票 codes 传字符串，返回 list；多股票 codes 传 list，返回 {code: list}。
 每只股票内部按 date 升序独立计算，不需要全市场 date 对齐。

2. 通用参数
 name   : 指标名，如 "ma"、"macd"、"kdj"、"boll"、"zhishu"。
 codes  : "600633" 或 ["600633", "000007"]。
 start  : 开始日期，如 "20260601"。不传默认 DEFAULT_START。
 end    : 结束日期，如 "20260630"。必传，否则只能取DEFAULT_START单日。
 frequency   : 周期，默认 "day"。可传 "day"/"1d"/"min"/"1m"/"30m" 等。
 fq     : 复权，默认 "qfq"。可传 None。
 n      : 指标参数。单指标可传 5、"5,10"；多指标需与 name 对齐，如 ["5,10", None, None]。
 fields : ma/ema/sma/wma/dma/std/sum/hhv/llv/ref 可指定 close/high/low/open/volume/amount。
 cross  : False 返回原始指标值；True 只返回金叉信号；"with_value" 返回原始指标值+金叉信号。

3. zhishu 专用参数
 method=1 平权
 method=2 流通市值加权，分钟/30m 无市值
 method=3 成交额加权
 method=4 成交量加权
 method=5 总市值加权，分钟/30m 无市值
 base=1000 指数初始基点

4. 已支持指标
 ma, ema, sma, wma, dma, std, sum, hhv, llv, ref,
 macd, kdj, rsi, wr, bias, boll, psy, cci, atr, bbi,
 dmi, taq, ktn, trix, vr, cr, emv, dpo, brar, dfma,
 mtm, mass, roc, expma, obv, mfi, asi, xsii, zhishu

5. 常用参数示例
 ma   : n=5 或 n="5,10,20"
 macd : n=None 默认 12,26,9
 kdj  : n=None 默认 9,3,3
 rsi  : n=24
 wr   : n="10,6"
 boll : n="20,2"
 bias : n="6,12,24"
 xsii : n="102,7"

6. 金叉信号
 单项信号: 1=金叉，-1=死叉，0=无交叉。
 多指标 cross 字段: 所有单项都是 1 时为 True，否则 False。
"""