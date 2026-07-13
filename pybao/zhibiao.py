from __future__ import annotations

import sys
import zb_core
from math import nan
from typing import Any
from copy import copy
from collections import defaultdict

from stock_sdk import StockDBClient
from zb_core import BATCH, BATCH_CROSS, ZHISHU


DEFAULT_START = "20260302"
METHOD_NAMES = {1: "equal", 2: "float_mv", 3: "amount", 4: "volume", 5: "total_mv"}
DATA_FIELD_INDEX = {
    "open": 2,
    "high": 3,
    "low": 4,
    "close": 5,
    "volume": 6,
    "amount": 7,
    "float_mv": 8,
    "total_mv": 9,
}
BASIC_INDICATORS = {"ma", "ema", "sma", "wma", "dma", "std", "sum", "hhv", "llv", "ref"}
BASIC_DEFAULT_N = {
    "ma": 5,
    "ema": 5,
    "sma": 5,
    "wma": 5,
    "dma": 10,
    "std": 5,
    "sum": 5,
    "hhv": 5,
    "llv": 5,
    "ref": 1,
}


client = StockDBClient(host="127.0.0.1", port=7899)

rd = client.rd


BOARD_FIELDS = ("code", "name", "source", "type", "group", "category", "symbols")
FIELD_ALIASES = {
    "symbol": "symbols",
    "symbols": "symbols",
    "symbls": "symbols",
    "codelist": "symbols",
}
CATEGORY_MAP = {
    0: "概念",
    1: "申万一级",
    2: "申万二级",
    3: "申万三级",
}


class BoardIndex:
    def __init__(self, rows: list | None = None):
        self.rows = rows if rows is not None else rd.get("板块*").do()
        self.boards: list[dict[str, Any]] = []
        self.by_code: dict[str, dict[str, Any]] = {}
        self.by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._build()

    def get(
        self,
        x: Any = None,
        category: int | str | None = None,
        fields: str | None = None,
    ) -> Any:
        category = self._category(category)
        fields = self._fields(fields)

        if isinstance(x, (list, tuple, set)):
            return {str(item): self.get(item, category, fields) for item in x}

        if x is None:
            items = self.boards if category is None else self.by_category.get(category, [])
            return self._result(items, fields, single=False, with_symbols=True)

        query = str(x).strip()
        if not query:
            return []

        if query in self.by_code:
            return self._result([self.by_code[query]], fields, single=True, with_symbols=True)

        if self._is_stock_code(query):
            stock = self._stock_code(query)
            items = self.by_stock.get(stock, [])
            if category is not None:
                items = [item for item in items if item["category"] == category]
            return self._result(items, fields, single=False, with_symbols=False)

        if category is not None:
            exact = self.by_name.get(f"{category}_{query}", [])
            if exact:
                return self._result(exact, fields, single=True, with_symbols=True)
            matched = self._match_name(query, category)
            return self._result(matched, fields, single=False, with_symbols=True)

        matched: list[dict[str, Any]] = []
        for cat in CATEGORY_MAP.values():
            matched.extend(self.by_name.get(f"{cat}_{query}", []))
        if not matched:
            matched = self._match_name(query, category=None)
        return self._result(matched, fields, single=False, with_symbols=True)

    def _build(self) -> None:
        for key, board in self.rows:
            if not isinstance(board, dict):
                continue

            code = str(board.get("code", "")).strip()
            name = str(board.get("name", "")).strip()
            category = str(board.get("category", "")).strip()
            if not code or not name or not category:
                continue

            symbols = [
                self._stock_code(symbol)
                for symbol in board.get("symbols", []) or []
                if str(symbol).strip()
            ]

            item = {
                **board,
                "code": code,
                "name": name,
                "category": category,
                "symbols": symbols,
            }

            self.boards.append(item)
            self.by_code[code] = item
            self.by_name[f"{category}_{name}"].append(item)
            self.by_category[category].append(item)

            stock_item = self._board(item, with_symbols=False)
            for stock in symbols:
                self.by_stock[stock].append(stock_item)

    def _result(
        self,
        items: list[dict[str, Any]],
        fields: str | None,
        single: bool,
        with_symbols: bool,
    ) -> Any:
        boards = [self._board(item, with_symbols) for item in items]
        if fields:
            selected = fields.split(",")
            if len(selected) == 1:
                values = [item.get(selected[0]) for item in boards]
            else:
                values = [
                    [item.get(key) for key in selected]
                    for item in boards
                ]
            if single:
                if values:
                    return values[0]
                return [] if selected == ["symbols"] else None
            return values
        if single:
            return boards[0] if boards else {}
        return boards

    def _match_name(self, keyword: str, category: str | None) -> list[dict[str, Any]]:
        items = self.boards if category is None else self.by_category.get(category, [])
        return [item for item in items if keyword in item["name"]]

    def _board(self, item: dict[str, Any], with_symbols: bool) -> dict[str, Any]:
        value = {field: copy(item[field]) for field in BOARD_FIELDS if field in item}
        if not with_symbols:
            value.pop("symbols", None)
        return value

    def _category(self, category: int | str | None) -> str | None:
        if category is None:
            return None
        if isinstance(category, int):
            if category not in CATEGORY_MAP:
                raise ValueError(f"unknown category number: {category}")
            return CATEGORY_MAP[category]

        category_text = str(category).strip()
        if category_text.isdigit():
            return self._category(int(category_text))
        return category_text

    def _fields(self, fields: str | None) -> str | None:
        if fields is None:
            return None
        selected = []
        for item in str(fields).split(","):
            item = item.strip()
            if not item:
                continue
            item = FIELD_ALIASES.get(item, item)
            if item not in BOARD_FIELDS:
                raise ValueError(f"unknown fields item: {item}")
            selected.append(item)
        if not selected:
            return None
        return ",".join(selected)

    def _is_stock_code(self, value: str) -> bool:
        return len(self._stock_code(value)) == 6 and self._stock_code(value).isdigit()

    def _stock_code(self, value: Any) -> str:
        return str(value).strip().split(".")[0]


bk = BoardIndex()



def _freq(frequency: str) -> str:
    return {"day": "1d", "d": "1d", "min": "1m"}.get(str(frequency).lower(), frequency)


def _codes(codes: Any) -> tuple[list[str], bool]:
    if isinstance(codes, str):
        return [codes], True
    return [str(x) for x in codes], False


def _row_value(row: list, idx: int, default: float = 0.0) -> float:
    if idx >= len(row) or row[idx] is None:
        return default
    try:
        return float(row[idx])
    except Exception:
        return default


def _load_rows(codes: list[str], frequency: str, start: str | None, end: str | None, fq: str | None):
    fields = "date,open,high,low,close,volume,amount,float_mv,total_mv"
    data = client.get_data(codes, start=start or DEFAULT_START, end=end, frequency=_freq(frequency), fields=fields, fq=fq)

    code_i: list[int] = []
    date: list[int] = []
    open_: list[float] = []
    high: list[float] = []
    low: list[float] = []
    close: list[float] = []
    volume: list[float] = []
    amount: list[float] = []
    float_mv: list[float] = []
    total_mv: list[float] = []

    for i, code in enumerate(codes):
        rows = sorted((row for row in data.get(code, []) if row and row[0] is not None), key=lambda row: int(row[0]))
        for row in rows:
            if not row or row[0] is None:
                continue
            code_i.append(i)
            date.append(int(row[0]))
            open_.append(_row_value(row, 1, nan))
            high.append(_row_value(row, 2, nan))
            low.append(_row_value(row, 3, nan))
            close.append(_row_value(row, 4, nan))
            volume.append(_row_value(row, 5, 0.0))
            amount.append(_row_value(row, 6, 0.0))
            float_mv.append(_row_value(row, 7, 0.0))
            total_mv.append(_row_value(row, 8, 0.0))

    return code_i, date, open_, high, low, close, volume, amount, float_mv, total_mv


def _indicator_result(codes: list[str], raw, single: bool):
    code_i, dates, names, cols = raw
    out = {code: [] for code in codes}
    for row_i, ci in enumerate(code_i):
        item = {"date": dates[row_i]}
        for name, col in zip(names, cols):
            item[name] = col[row_i]
        out[codes[ci]].append(item)
    return out[codes[0]] if single else out


def _cross_indicator_result(codes: list[str], raw, single: bool):
    code_i, dates, names, cols = raw
    out = {code: [] for code in codes}
    has_named_signals = any(name.endswith("_cross") for name in names)
    for row_i, ci in enumerate(code_i):
        item = {"date": dates[row_i]}
        for name, col in zip(names, cols):
            if name.endswith("_cross"):
                item[name] = int(col[row_i])
            elif name == "cross":
                value = int(col[row_i])
                item[name] = bool(value == 1) if has_named_signals else value
            else:
                item[name] = col[row_i]
        out[codes[ci]].append(item)
    return out[codes[0]] if single else out


def _data_fields(fields: Any, key: str) -> list[str]:
    if fields is None:
        return ["close"]

    out = []
    if isinstance(fields, (list, tuple)):
        items = fields
    else:
        items = str(fields).replace("，", ",").split(",")
    for item in items:
        item = str(item).strip().lower()
        if not item:
            continue
        if item not in DATA_FIELD_INDEX:
            raise ValueError(f"unknown fields item: {item}")
        out.append(item)
    return out or ["close"]

def _with_input_as_close(arrays, values: list[float]):
    values = list(values)
    return (
        arrays[0],
        arrays[1],
        arrays[2],
        arrays[3],
        arrays[4],
        values,
        arrays[6],
        arrays[7],
        arrays[8],
        arrays[9],
    )


def _rename_indicator(raw, prefix: str):
    code_i, dates, names, cols = raw
    names = [f"{prefix}_{name}" for name in names]
    return code_i, dates, names, cols


def _merge_field_results(codes: list[str], raws: list[tuple], single: bool):
    out = {code: {} for code in codes}
    for raw in raws:
        code_i, dates, names, cols = raw
        for row_i, ci in enumerate(code_i):
            code = codes[ci]
            date = dates[row_i]
            item = out[code].setdefault(date, {"date": date})
            for name, col in zip(names, cols):
                item[name] = col[row_i]

    result = {
        code: [rows[date] for date in sorted(rows)]
        for code, rows in out.items()
    }
    return result[codes[0]] if single else result


def _indicator_names(name: Any) -> list[str]:
    names = []
    if isinstance(name, (list, tuple)):
        items = name
    else:
        items = str(name).replace("，", ",").split(",")
    for item in items:
        item = str(item).strip().lower()
        if item:
            names.append(item)
    if not names:
        raise ValueError("indicator name is empty")
    return names


def _int_list(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
        return [int(item.strip()) for item in items if item.strip()]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if item is None or item == "":
                continue
            out.append(int(item))
        return out
    return [int(value)]


def _format_param_mapping_error(title: str, names: list[str], n: Any) -> str:
    if isinstance(n, (list, tuple)):
        values = list(n)
    else:
        values = [n]

    lines = [title, ""]
    max_len = max(len(names), len(values))
    for i in range(max_len):
        name = names[i] if i < len(names) else "X EXTRA"
        if i < len(values):
            lines.append(f"'{name}': {values[i]!r},")
        else:
            lines.append(f"'{name}': X ERROR,")
    return "\n".join(lines).rstrip(",")


def _indicator_params(names: list[str], n: Any) -> list[list[int]]:
    if len(names) == 1:
        return [_int_list(n)]

    if n is None:
        return [[] for _ in names]

    if not isinstance(n, (list, tuple)):
        raise ValueError(_format_param_mapping_error(
            "multi indicator n must align with names:", names, n
        ))

    if len(n) != len(names):
        raise ValueError(_format_param_mapping_error(
            "multi indicator n length mismatch:", names, n
        ))

    return [_int_list(item) for item in n]

def _zhishu_result(raw):
    dates, opens, highs, lows, closes, pct, volumes, amounts, counts = raw
    return [
        {
            "date": dates[i],
            "open": opens[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "pct_chg": pct[i],
            "volume": volumes[i],
            "amount": amounts[i],
            "stock_count": counts[i],
        }
        for i in range(len(dates))
    ]


def jisuan(
    name: str,
    codes: Any,
    *,
    start: str | None = None,
    end: str | None = None,
    frequency: str = "day",
    method: int = 1,
    base: float = 1000.0,
    fq: str | None = "qfq",
    fields: Any = None,
    n: Any = None,
    cross: Any = False,
):
    code_list, single = _codes(codes)
    arrays = _load_rows(code_list, frequency, start, end, fq)
    names = _indicator_names(name)

    if names == ["zhishu"]:
        if _freq(frequency) != "1d" and method in (2, 5):
            raise ValueError("分钟K不含 float_mv/total_mv，只支持 method=1/3/4")
        result = _zhishu_result(ZHISHU(*arrays, method=method, base=base))
        if cross:
            raise ValueError("cross does not support zhishu")
        return result[1:]

    supported = {
        "macd", "kdj", "rsi", "wr", "bias", "boll", "psy", "cci", "atr", "bbi",
        "dmi", "taq", "ktn", "trix", "vr", "cr", "emv", "dpo", "brar", "dfma",
        "mtm", "mass", "roc", "expma", "obv", "mfi", "asi", "xsii",
        "ma", "ema", "sma", "wma", "dma", "std", "sum", "hhv", "llv", "ref",
    }
    for key in names:
        if key not in supported:
            raise ValueError(f"unsupported indicator: {key}")

    if cross is not False and cross is not True and cross != "with_value":
        raise ValueError('cross only supports False, True, or "with_value"')

    params = _indicator_params(names, n)
    basic_only = all(key in BASIC_INDICATORS for key in names)

    if cross is True or cross == "with_value":
        keep_values = cross == "with_value"
        if basic_only:
            data_fields = _data_fields(fields, names[0])
            if len(data_fields) != 1:
                raise ValueError('cross=True/cross="with_value" only supports one fields item')
            field_arrays = _with_input_as_close(arrays, arrays[DATA_FIELD_INDEX[data_fields[0]]])
            raw = BATCH_CROSS(names, params, field_arrays[0], field_arrays[1], field_arrays[2],
                              field_arrays[3], field_arrays[4], field_arrays[5], field_arrays[6], keep_values)
            return _cross_indicator_result(code_list, raw, single)
        if fields is not None:
            raise ValueError("fields only supports ma/ema/sma/wma/dma/std/sum/hhv/llv/ref")
        raw = BATCH_CROSS(names, params, arrays[0], arrays[1], arrays[2], arrays[3], arrays[4], arrays[5], arrays[6], keep_values)
        return _cross_indicator_result(code_list, raw, single)

    if basic_only:
        data_fields = _data_fields(fields, names[0])
        raws = []
        for data_field in data_fields:
            field_arrays = _with_input_as_close(arrays, arrays[DATA_FIELD_INDEX[data_field]])
            raw = BATCH(names, params, field_arrays[0], field_arrays[1], field_arrays[2],
                        field_arrays[3], field_arrays[4], field_arrays[5], field_arrays[6])
            if len(data_fields) > 1:
                raw = _rename_indicator(raw, data_field)
            raws.append(raw)
        if len(raws) == 1:
            result = _indicator_result(code_list, raws[0], single)
        else:
            result = _merge_field_results(code_list, raws, single)
        return result

    if fields is not None:
        raise ValueError("fields only supports ma/ema/sma/wma/dma/std/sum/hhv/llv/ref")
    raw = BATCH(names, params, arrays[0], arrays[1], arrays[2], arrays[3], arrays[4], arrays[5], arrays[6])
    result = _indicator_result(code_list, raw, single)
    return result


class ZhiBiao:
    def get(self, name: Any, codes: Any, **kwargs: Any) -> Any:
        return jisuan(name, codes, **kwargs)

    def __getattr__(self, name: str) -> Any:
        try:
            return getattr(zb_core, name)
        except AttributeError:
            raise AttributeError(f"'ZhiBiao' object has no attribute {name!r}") from None


zb = ZhiBiao()


if __name__ == "__main__":
    pass