import sys
import bisect
import asyncio
import datetime
from typing import Union, List, Dict, Any, Optional
from collections import defaultdict
from stockdb import init, rd

class StockDBClient:
    """
    StockDB 股票数据库的 Python SDK 客户端
    提供统一的 get_data 接口，支持同步/异步操作，并支持在内存中合成周K、月K线。
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 7899, password: str = ""):
        """
        初始化 StockDB 客户端连接
        """
        try:
            # 优先使用连接初始化
            self.rd = init(host=host, port=port, password=password)
            if self.rd is None:
                self.rd = rd
        except ImportError as e:
            raise ImportError(
                "未能成功导入底层的 'stockdb' 二进制模块。请确保 stockdb.pyd 文件位于当前目录或 python 搜索路径中。"
            ) from e

        # 一次性预加载全部复权因子到内存
        self._fq_dates = {}    # {code: [date_str, ...]}  用于二分查找
        self._fq_cums = {}     # {code: [cum_float, ...]}  对应 cum 值
        try:
            tmp = defaultdict(list)
            raw = self.rd.get("复权*").get("cum")
            for item in raw:
                key_str = item[0]
                cum_val = float(item[1])
                parts = key_str.split(":")
                code = parts[1]
                date = parts[2]
                tmp[code].append((date, cum_val))
            # 构建二分查找用的平行数组（LevelDB 天然有序，无需排序）
            for code, pairs in tmp.items():
                self._fq_dates[code] = [p[0] for p in pairs]
                self._fq_cums[code] = [p[1] for p in pairs]
        except Exception:
            pass

    def _build_time_query(self, start: Optional[str], end: Optional[str], desc: bool) -> str:
        """
        根据开始/结束日期和排序方向，构建底层的范围查询表达式
        """
        if not start and not end:
            return "*"
        
        # 精确单日查询优化：如果 start 存在，且 (end 不存在 或 start 与 end 相同)，直接返回日期进行单次点查询
        if start and (not end or start == end):
            return start
            
        op = ">" if desc else "<"
        s_val = start if start else "N"
        e_val = end if end else "N"
        
        return f"{s_val}{op}{e_val}"

    def _filter_fields(self, data_list: List[Dict[str, Any]], fields: Optional[Union[str, List[str]]]) -> List[List[Any]]:
        """
        过滤字典列表中的字段，并将结果转换为二维数值列表（行和列），保持与底层接口一致的天然二维数组结构。
        """
        if not fields:
            return data_list
        
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(',')]
            
        filtered = []
        for item in data_list:
            # 提取指定字段的值列表，保证顺序和 fields 一致
            row = [item.get(f) for f in fields]
            filtered.append(row)
        return filtered

    def _to_dataframe(self, data: Any, is_batch: bool, fields: Optional[Union[str, List[str]]] = None) -> Any:
        """
        将数据转换为 Pandas DataFrame。如果未安装 pandas，将抛出友好错误。
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("未检测到 pandas 库。如需使用 as_df=True，请先运行 'pip install pandas'。")

        # 预先处理 fields 为列表形式
        fields_list = []
        if fields:
            fields_list = fields if isinstance(fields, list) else [f.strip() for f in fields.split(',')] if isinstance(fields, str) else []

        if is_batch:
            # 批量多股票模式下，将各股票的数据合并为一个大 DataFrame，并包含 'code' 列
            all_records = []
            for code, records in data.items():
                for r in records:
                    if isinstance(r, list):
                        # 如果是二维数组行
                        record_dict = dict(zip(fields_list, r))
                    else:
                        # 如果是字典
                        record_dict = r.copy()
                    record_dict['code'] = code
                    all_records.append(record_dict)
            
            if not all_records:
                return pd.DataFrame()
            
            df = pd.DataFrame(all_records)
            # 调整 code 列到最前面
            cols = ['code'] + [col for col in df.columns if col != 'code']
            return df[cols]
        else:
            # 单只股票模式
            if not data:
                return pd.DataFrame()
            
            # 如果是二维列表
            if isinstance(data[0], list):
                return pd.DataFrame(data, columns=fields_list)
            else:
                return pd.DataFrame(data)

    def _merge_to_period(self, daily_data: List[Dict[str, Any]], frequency: str) -> List[Dict[str, Any]]:
        """
        将日K线数据聚合成更长周期的K线数据（支持 '1w'/周K, '1M'/月K）
        """
        if not daily_data:
            return []

        # LevelDB 天然按日期升序，无需排序
        sorted_daily = daily_data

        # 2. 分组归类
        from collections import defaultdict
        grouped = defaultdict(list)

        for item in sorted_daily:
            date_val = item.get('date')
            if not date_val:
                continue
            
            date_str = str(date_val)
            try:
                dt = datetime.datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                # 兼容格式异常的日期，或者分钟K（不过这通常只处理日K）
                continue

            if frequency == '1w':
                # 使用 ISO 纪年与周数作为周K分组键
                iso = dt.isocalendar()
                key = (iso[0], iso[1])  # (year, week)
            elif frequency == '1M':
                # 使用年与月作为月K分组键
                key = (dt.year, dt.month)
            else:
                key = (dt.year, dt.month) # 默认月

            grouped[key].append(item)

        # 3. 聚合计算
        merged_list = []
        sorted_keys = sorted(grouped.keys())

        for idx, key in enumerate(sorted_keys):
            items = grouped[key]
            first_item = items[0]
            last_item = items[-1]

            high = max(x['high'] for x in items if 'high' in x)
            low = min(x['low'] for x in items if 'low' in x)
            volume = sum(x['volume'] for x in items if 'volume' in x)
            amount = sum(x['amount'] for x in items if 'amount' in x)

            # 基础周期K线数据
            merged_item = {
                'date': last_item['date'],  # 以该周期内最后一个交易日日期作为标识
                'code': last_item['code'],
                'name': last_item.get('name', ''),
                'open': first_item['open'],
                'high': high,
                'low': low,
                'close': last_item['close'],
                'volume': volume,
                'amount': amount,
            }

            # 4. 衍生财务与行情指标处理
            # 前收盘价 pre_close 处理
            if idx > 0:
                pre_close = merged_list[-1]['close']
            else:
                pre_close = first_item.get('pre_close', first_item['open'])
            merged_item['pre_close'] = pre_close

            # 涨跌幅与振幅计算
            if pre_close:
                merged_item['pct_chg'] = round(((merged_item['close'] - pre_close) / pre_close) * 100, 3)
                merged_item['amplitude'] = round(((high - low) / pre_close) * 100, 3)
            else:
                merged_item['pct_chg'] = 0.0
                merged_item['amplitude'] = 0.0

            # 换手率加和
            if 'turnover' in last_item:
                merged_item['turnover'] = round(sum(x.get('turnover', 0) for x in items), 3)

            # 量比求均值
            if 'vol_ratio' in last_item:
                merged_item['vol_ratio'] = round(sum(x.get('vol_ratio', 0) for x in items) / len(items), 3)

            # 复制周期末端的截面属性（如市值、ST状态等）
            for field in ['pe_ttm', 'pb', 'total_mv', 'float_mv', 'float_share', 'total_share', 'is_st']:
                if field in last_item:
                    merged_item[field] = last_item[field]

            merged_list.append(merged_item)

        return merged_list

    def _merge_minutes_to_period(self, minute_data: List[Dict[str, Any]], frequency: str) -> List[Dict[str, Any]]:
        """
        将一分钟K线数据聚合成更长周期的分钟K线数据（支持 '5m', '15m', '30m', '60m'）
        """
        if not minute_data:
            return []

        # LevelDB 天然按时间升序，无需排序
        sorted_min = minute_data
        
        interval = int(frequency[:-1]) # '5m' -> 5, '15m' -> 15, '30m' -> 30, '60m' -> 60

        def trading_elapsed(minute_of_day: int) -> Optional[int]:
            if 570 <= minute_of_day <= 690:
                return minute_of_day - 570
            if 780 <= minute_of_day <= 900:
                if minute_of_day == 780:
                    return 121
                return 120 + (minute_of_day - 780)
            return None

        def elapsed_to_minute_of_day(elapsed: int) -> int:
            if elapsed <= 120:
                return 570 + elapsed
            if elapsed > 240:
                elapsed = 240
            return 780 + (elapsed - 120)

        # 2. 分组归类
        from collections import defaultdict
        grouped = defaultdict(list)

        for item in sorted_min:
            date_val = item.get('date')
            if not date_val:
                continue
            
            try:
                date_int = int(date_val)
            except (TypeError, ValueError):
                continue
                
            if date_int < 10000000000000:
                continue

            # 经典时间轴对齐：计算对齐时刻
            ymd = date_int // 1000000
            hour = (date_int // 10000) % 100
            minute = (date_int // 100) % 100
            elapsed = trading_elapsed(hour * 60 + minute)
            if elapsed is None:
                continue

            if elapsed <= 0:
                group_end_elapsed = interval
            else:
                group_idx = (elapsed - 1) // interval
                group_end_elapsed = (group_idx + 1) * interval
            
            # 使用对齐结束时间点作为分组键
            key = (ymd, group_end_elapsed)
            grouped[key].append(item)

        # 3. 聚合计算
        merged_list = []
        sorted_keys = sorted(grouped.keys())

        for idx, key in enumerate(sorted_keys):
            ymd, end_elapsed = key
            items = grouped[key]
            first_item = items[0]
            last_item = items[-1]

            high = max(x['high'] for x in items if 'high' in x)
            low = min(x['low'] for x in items if 'low' in x)
            volume = sum(x['volume'] for x in items if 'volume' in x)
            amount = sum(x['amount'] for x in items if 'amount' in x)

            # 换算回 HHMMSS
            end_minute_of_day = elapsed_to_minute_of_day(end_elapsed)
            end_hour = end_minute_of_day // 60
            end_minute = end_minute_of_day % 60
            
            # 溢出保护
            if end_hour >= 24:
                end_hour = 23
                end_minute = 59
                
            aligned_date_int = ymd * 1000000 + end_hour * 10000 + end_minute * 100

            merged_item = {
                'date': aligned_date_int,
                'code': last_item['code'],
                'name': last_item.get('name', ''),
                'open': first_item['open'],
                'high': high,
                'low': low,
                'close': last_item['close'],
                'volume': volume,
                'amount': amount,
            }

            # 4. 衍生财务与行情指标处理
            if idx > 0:
                pre_close = merged_list[-1]['close']
            else:
                pre_close = first_item.get('pre_close', first_item['open'])
            merged_item['pre_close'] = pre_close

            if pre_close:
                merged_item['pct_chg'] = round(((merged_item['close'] - pre_close) / pre_close) * 100, 3)
                merged_item['amplitude'] = round(((high - low) / pre_close) * 100, 3)
            else:
                merged_item['pct_chg'] = 0.0
                merged_item['amplitude'] = 0.0

            # 复制截面属性
            for field in ['vol_ratio', 'pe_ttm', 'pb', 'total_mv', 'float_mv', 'float_share', 'total_share', 'is_st']:
                if field in last_item:
                    merged_item[field] = last_item[field]

            merged_list.append(merged_item)

        return merged_list

    def _apply_fq_in_memory(self, code: str, records: List[Dict[str, Any]], fq_type: str) -> List[Dict[str, Any]]:
        """
        在内存中对 K 线记录（日K或分钟K）执行动态前复权（qfq）或后复权（hfq）折算
        复权因子已在 __init__ 中预加载到 self._fq_dates / self._fq_cums
        """
        if not records or fq_type not in ('qfq', 'hfq'):
            return records

        dates = self._fq_dates.get(code)
        cums = self._fq_cums.get(code)
        if not dates:
            return records

        # 前复权需要最新因子（列表天然有序，最后一个即最新）
        if fq_type == 'qfq':
            f_latest = cums[-1]

        decimals = 3 if code.startswith(('1', '5')) else 2
        adjusted_records = []

        for r in records:
            # 分钟K线 date 是 14 位整数，如 20260629150000; 日K是 8 位，如 20260629
            r_date_str = str(r.get('date', ''))[:8]
            if not r_date_str:
                adjusted_records.append(r)
                continue

            # 二分查找: 找到 <= r_date_str 的最大除权日对应的 cum
            idx = bisect.bisect_right(dates, r_date_str) - 1
            f_current = cums[idx] if idx >= 0 else 1.0

            # 根据复权类型计算折算比例
            if fq_type == 'qfq':
                ratio = f_latest / f_current
            else:
                ratio = 1.0 / f_current

            if abs(ratio - 1.0) < 1e-6:
                adjusted_records.append(r)
                continue

            # 拷贝记录字典，避免直接修改底层数据库缓存的对象
            r_copy = r.copy()
            for field in ['open', 'high', 'low', 'close', 'pre_close']:
                if field in r_copy and r_copy[field] is not None:
                    try:
                        r_copy[field] = round(float(r_copy[field]) / ratio, decimals)
                    except Exception:
                        pass
            adjusted_records.append(r_copy)

        return adjusted_records

    # ================= 同步接口 =================
    def get_data(
        self,
        code: Union[str, List[str]],
        start: Optional[str] = None,
        end: Optional[str] = None,
        frequency: str = '1d',
        fields: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = None,
        desc: bool = False,
        as_df: bool = False,
        fq: Optional[str] = 'qfq'
    ) -> Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], Any]:
        """
        同步获取 K 线数据（日K、分钟K、周K、月K）
        """
        is_batch = isinstance(code, list)
        codes = code if is_batch else [code]
        
        # 1. 确定底层查询的表名与时间表达式
        # 如果是周K或月K，底层先查询日K数据
        table = "分钟k" if frequency in ('1m', '5m', '15m', '30m', '60m') else "日k"
        time_query = self.build_time_query_for_retrieval(start, end, desc, frequency)

        # 2. 从底层数据库查询数据
        data_dict = {}
        if len(codes) == 1:
            # 单只股票优化查询
            single_code = codes[0]
            res = self.rd.vals(table, single_code, time_query)
            data_dict[single_code] = list(res)
        else:
            # 多只股票采用单路 pipeline 批量查询
            pp = self.rd.pipe()
            for c in codes:
                pp.mget(table, c, time_query)
            raw = pp.do()
            if not isinstance(raw, list):
                raw = [raw]
            
            for c, items in zip(codes, raw):
                data_dict[c] = [items] if isinstance(items, dict) else ([item[1] for item in items if isinstance(item, (list, tuple)) and len(item) > 1] if isinstance(items, list) else [])

        # 3. 处理数据排序、截取、周期合并与字段过滤
        for c in codes:
            records = data_dict[c]
            
            # 剔除无效值（None、空列表等非dict记录）
            records = [r for r in records if isinstance(r, dict)]
            
            # 在内存中执行动态前/后复权折算
            if fq in ('qfq', 'hfq'):
                records = self._apply_fq_in_memory(c, records, fq)
            
            # 运行合并逻辑
            if frequency in ('1w', '1M'):
                records = self._merge_to_period(records, frequency)
            elif frequency in ('5m', '15m', '30m', '60m'):
                records = self._merge_minutes_to_period(records, frequency)
            
            # LevelDB 天然有序，仅在需要降序时反转
            if desc:
                records = records[::-1]
            
            # 限额截取
            if limit is not None:
                records = records[:limit]
                
            # 字段投影过滤
            if fields:
                records = self._filter_fields(records, fields)
                
            data_dict[c] = records

        # 4. 返回格式封装
        if is_batch:
            if as_df:
                return self._to_dataframe(data_dict, is_batch=True, fields=fields)
            return data_dict
        else:
            # 单只股票，去除外层股票代码的 dict 包裹
            single_res = data_dict[codes[0]]
            if as_df:
                return self._to_dataframe(single_res, is_batch=False, fields=fields)
            return single_res

    # ================= 异步接口 =================
    async def get_data_async(
        self,
        code: Union[str, List[str]],
        start: Optional[str] = None,
        end: Optional[str] = None,
        frequency: str = '1d',
        fields: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = None,
        desc: bool = False,
        as_df: bool = False,
        fq: Optional[str] = 'qfq'
    ) -> Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], Any]:
        """
        异步获取 K 线数据（日K、分钟K、周K、月K）
        """
        is_batch = isinstance(code, list)
        codes = code if is_batch else [code]
        
        table = "分钟k" if frequency in ('1m', '5m', '15m', '30m', '60m') else "日k"
        time_query = self.build_time_query_for_retrieval(start, end, desc, frequency)

        # 1. 异步读取数据
        data_dict = {}
        if len(codes) == 1:
            single_code = codes[0]
            # await 获取的是原生 Python 列表（包含 dict 元素）
            res = await self.rd.vals(table, single_code, time_query)
            data_dict[single_code] = res
        else:
            # 批量多股票使用单路 pipeline 异步批量查询
            pp = self.rd.pipe()
            for c in codes:
                pp.mget(table, c, time_query)
            raw = await pp
            if not isinstance(raw, list):
                raw = [raw]
            
            for c, items in zip(codes, raw):
                data_dict[c] = [items] if isinstance(items, dict) else ([item[1] for item in items if isinstance(item, (list, tuple)) and len(item) > 1] if isinstance(items, list) else [])

        # 2. 转换与合并
        for c in codes:
            records = data_dict[c]
            
            # 剔除无效值（None、空列表等非dict记录）
            records = [r for r in records if isinstance(r, dict)]
            
            # 在内存中执行动态前/后复权折算
            if fq in ('qfq', 'hfq'):
                records = self._apply_fq_in_memory(c, records, fq)
            
            if frequency in ('1w', '1M'):
                records = self._merge_to_period(records, frequency)
            elif frequency in ('5m', '15m', '30m', '60m'):
                records = self._merge_minutes_to_period(records, frequency)
                
            if desc:
                records = records[::-1]
            
            if limit is not None:
                records = records[:limit]
                
            if fields:
                records = self._filter_fields(records, fields)
                
            data_dict[c] = records

        # 3. 封装返回
        if is_batch:
            if as_df:
                return self._to_dataframe(data_dict, is_batch=True, fields=fields)
            return data_dict
        else:
            single_res = data_dict[codes[0]]
            if as_df:
                return self._to_dataframe(single_res, is_batch=False, fields=fields)
            return single_res

    def build_time_query_for_retrieval(self, start: Optional[str], end: Optional[str], desc: bool, frequency: str) -> str:
        """
        辅助方法：根据周期性质构建日期查询条件
        若是分钟级查询且提供了8位日期，则自动将其补全为14位时间戳（包含当天的完整交易时段）
        """
        if frequency in ('1m', '5m', '15m', '30m', '60m'):
            if start and len(start) == 8:
                start = start + "000000"
            if end and len(end) == 8:
                end = end + "235959"
        return self._build_time_query(start, end, desc)
