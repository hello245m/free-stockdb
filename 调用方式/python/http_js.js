/**
 * 全局函数 GP(code, [start], [end], [frequency], [fields])
 * 
 * 说明：
 * js版本演示通过http_api访问stockdb （http://127.0.0.1:7899）
 * 测试，浏览器f12粘贴此代码，(注意跨域，需先打开本地任意html)。
 * console.table(GP("600633", "20260620", "20260626", "1d", "date,close,pct_chg","qfq"))
 */

// 全局函数GP()
// @customfunction
function GP(code, start_date, end_date, frequency, fields, fq) {
    // 默认参数处理
    frequency = frequency || "1d";
    start_date = start_date ? String(start_date) : "";
    end_date = end_date ? String(end_date) : "";
    fields = fields || "date,code,name,open,high,low,close,volume,amount";
    fq = fq || "qfq";

    let host = "127.0.0.1";
    let port = 7899;

    // 1. 自动补全分钟级时间戳
    let isMinFreq = ["1m", "5m", "15m", "30m", "60m"].indexOf(frequency) !== -1;
    if (isMinFreq) {
        if (start_date && start_date.length === 8) {
            if (!end_date) {
                end_date = start_date + "235959";
            }
            start_date += "000000";
        }
        if (end_date && end_date.length === 8) {
            end_date += "235959";
        }
    }

    // 2. 构造查询条件
    let k2 = "all:";
    if (start_date && end_date) {
        k2 = "fwd:" + start_date + "," + end_date;
    } else if (start_date) {
        k2 = "key:" + start_date;
    }

    let table = ["1m", "5m", "15m", "30m", "60m"].indexOf(frequency) !== -1 ? "分钟k" : "日k";

    // 3. 构造请求 URL 并进行 URL 编码
    let url = "http://" + host + ":" + port + "/?cmd=vals" +
              "&t=" + encodeURIComponent(table) +
              "&k1=" + encodeURIComponent("key:" + code) +
              "&k2=" + encodeURIComponent(k2);

    // 4. 同步请求本地数据库 (设置 async = false 以供 WPS 自定义函数阻塞等待返回)
    let rawData = [];
    try {
        let xhr = new ActiveXObject("MSXML2.ServerXMLHTTP"); // WPS 环境中高兼容的同步 HTTP 对象
        xhr.open("GET", url, false);
        xhr.send();
        if (xhr.status === 200) {
            rawData = JSON.parse(xhr.responseText);
        } else {
            return [["连接错误", "状态码: " + xhr.status]];
        }
    } catch (e) {
        // 如果 ServerXMLHTTP 失败，尝试原生的 XMLHttpRequest
        try {
            let xhr2 = new XMLHttpRequest();
            xhr2.open("GET", url, false);
            xhr2.send();
            if (xhr2.status === 200) {
                rawData = JSON.parse(xhr2.responseText);
            } else {
                return [["连接错误", "状态码: " + xhr2.status]];
            }
        } catch (e2) {
            return [["无法连接数据库", "请确保 stockdb.exe 已在后台运行"]];
        }
    }

    // 5. 剔除无效的空记录 (None 值过滤)
    if (!rawData || rawData.length === 0) {
        return [["无数据", "请检查股票代码或时间范围"]];
    }
    rawData = rawData.filter(item => item !== null && typeof item === 'object');

    if (rawData.length === 0) {
        return [["无有效数据"]];
    }

    // 6. 核心复权算法：同步拉取复权因子并进行内存折算
    if (fq !== "none") {
        let fqUrl = "http://" + host + ":" + port + "/?cmd=get&t=" + encodeURIComponent("复权") +
                    "&k1=" + encodeURIComponent("key:" + code) +
                    "&k2=all:";
        let rawFactors = [];
        try {
            let xhrFq = new ActiveXObject("MSXML2.ServerXMLHTTP");
            xhrFq.open("GET", fqUrl, false);
            xhrFq.send();
            if (xhrFq.status === 200) {
                rawFactors = JSON.parse(xhrFq.responseText);
            }
        } catch (e) {
            try {
                let xhrFq2 = new XMLHttpRequest();
                xhrFq2.open("GET", fqUrl, false);
                xhrFq2.send();
                if (xhrFq2.status === 200) {
                    rawFactors = JSON.parse(xhrFq2.responseText);
                }
            } catch (e2) {}
        }
        rawData = _applyFqInWps(rawData, rawFactors, fq);
    } else {
        rawData = _applyFqInWps(rawData, null, "none");
    }

    // 7. 执行周期合并逻辑 (如果不是 1d 或 1m，在内存中进行聚合)
    let processedData = [];
    if (frequency === "1w" || frequency === "1M") {
        processedData = _mergeToPeriod(rawData, frequency);
    } else if (["5m", "15m", "30m", "60m"].indexOf(frequency) !== -1) {
        processedData = _mergeMinutesToPeriod(rawData, frequency);
    } else {
        processedData = rawData.sort((a, b) => (a.date || 0) - (b.date || 0));
    }

    // 统一按日期从大到小（降序）排序，方便用户查看最新数据
    processedData.sort((a, b) => (b.date || 0) - (a.date || 0));

    // 8. 进行字段投影并生成带表头的二维数组
    let fieldsList = fields.split(",").map(f => f.trim());
    let result = [];
    
    // 第一行放入表头
    result.push(fieldsList);

    // 后续行填充数据
    for (let item of processedData) {
        let row = [];
        for (let field of fieldsList) {
            row.push(item[field] !== undefined ? item[field] : "");
        }
        result.push(row);
    }

    return result;
}

/**
 * 内部辅助函数：在 WPS 宏内折算复权价格及规整前收盘价
 */
function _applyFqInWps(data, rawFactors, fqMode) {
    if (!data || data.length === 0) return data;
    
    // 克隆数据，防止直接污染缓存
    let processedData = data.map(item => {
        let copy = {};
        for (let k in item) {
            copy[k] = item[k];
        }
        return copy;
    });
    
    if (fqMode !== "none") {
        let factors = [];
        if (rawFactors && Array.isArray(rawFactors)) {
            factors = rawFactors.map(item => {
                let key = item[0];
                let val = item[1];
                if (val && typeof val === "object") {
                    let parts = String(key).split(":");
                    val.date = parseInt(parts[parts.length - 1]);
                    return val;
                }
                return null;
            }).filter(f => f !== null).sort((a, b) => (a.date || 0) - (b.date || 0));
        }
        
        let fLatest = 1.0;
        if (factors.length > 0) {
            fLatest = parseFloat(factors[factors.length - 1].cum || 1.0);
        }
        
        const codeStr = String(processedData[0].code || "");
        const isEtf = codeStr.indexOf("1") === 0 || codeStr.indexOf("5") === 0;
        const decimals = isEtf ? 3 : 2;
        
        processedData = processedData.map(item => {
            let dateVal = item.date;
            if (!dateVal) return item;
            
            let dateStr = String(dateVal);
            let dateCompare = parseInt(dateStr.substring(0, 8));
            
            let fCurrent = 1.0;
            for (let i = factors.length - 1; i >= 0; i--) {
                if ((factors[i].date || 0) <= dateCompare) {
                    fCurrent = parseFloat(factors[i].cum || 1.0);
                    break;
                }
            }
            
            let ratio = 1.0;
            if (fqMode === "qfq") {
                ratio = fLatest / fCurrent;
            } else if (fqMode === "hfq") {
                ratio = 1.0 / fCurrent;
            }
            
            const priceFields = ["open", "high", "low", "close", "pre_close"];
            for (let field of priceFields) {
                if (item[field] !== undefined && item[field] !== null) {
                    let rawPrice = parseFloat(item[field]);
                    let adjusted = rawPrice / ratio;
                    item[field] = Math.round(adjusted * Math.pow(10, decimals)) / Math.pow(10, decimals);
                }
            }
            
            return item;
        });
    }
    
    // 强制使用前一天的收盘价覆盖今天的前收盘价
    processedData.sort((a, b) => (b.date || 0) - (a.date || 0));
    for (let i = 0; i < processedData.length - 1; i++) {
        processedData[i].pre_close = processedData[i + 1].close;
    }
    
    return processedData;
}


/**
 * 内部辅助函数：合并日K为周K/月K
 */
function _mergeToPeriod(dailyData, frequency) {
    // 升序排列
    let sorted = dailyData.sort((a, b) => (a.date || 0) - (b.date || 0));
    let groups = {};
    let groupKeys = [];

    for (let item of sorted) {
        let dateVal = item.date;
        if (!dateVal) continue;
        let dateStr = String(dateVal);
        
        let year = parseInt(dateStr.substring(0, 4));
        let month = parseInt(dateStr.substring(4, 6));
        let day = parseInt(dateStr.substring(6, 8));
        let dt = new Date(year, month - 1, day);

        let key = "";
        if (frequency === "1w") {
            // 计算 ISO 周分组键：(Year_Week)
            let iso = _getISOWeek(dt);
            key = iso[0] + "_W" + String(iso[1]).padStart(2, '0');
        } else {
            // 月K分组键：(Year_Month)
            key = String(year) + "_M" + String(month).padStart(2, '0');
        }

        if (!groups[key]) {
            groups[key] = [];
            groupKeys.push(key);
        }
        groups[key].push(item);
    }

    let mergedList = [];
    for (let i = 0; i < groupKeys.length; i++) {
        let key = groupKeys[i];
        let items = groups[key];
        let first = items[0];
        let last = items[items.length - 1];

        let high = Math.max(...items.map(x => x.high || 0));
        let low = Math.min(...items.map(x => x.low || 999999));
        let volume = items.map(x => x.volume || 0).reduce((a, b) => a + b, 0);
        let amount = items.map(x => x.amount || 0).reduce((a, b) => a + b, 0);

        let mergedItem = {
            date: last.date,
            code: last.code,
            name: last.name || "",
            open: first.open,
            high: high,
            low: low,
            close: last.close,
            volume: volume,
            amount: amount
        };

        // 计算前收盘价
        let pre_close = 0;
        if (i > 0) {
            pre_close = mergedList[i - 1].close;
        } else {
            pre_close = first.pre_close || first.open;
        }
        mergedItem.pre_close = pre_close;

        if (pre_close) {
            mergedItem.pct_chg = Math.round(((mergedItem.close - pre_close) / pre_close) * 100000) / 1000;
            mergedItem.amplitude = Math.round(((high - low) / pre_close) * 100000) / 1000;
        } else {
            mergedItem.pct_chg = 0;
            mergedItem.amplitude = 0;
        }

        // 换手率求和
        if (last.turnover !== undefined) {
            mergedItem.turnover = Math.round(items.map(x => x.turnover || 0).reduce((a, b) => a + b, 0) * 1000) / 1000;
        }
        // 量比求平均
        if (last.vol_ratio !== undefined) {
            mergedItem.vol_ratio = Math.round((items.map(x => x.vol_ratio || 0).reduce((a, b) => a + b, 0) / items.length) * 1000) / 1000;
        }

        // 复制截面属性
        let fieldsToCopy = ['pe_ttm', 'pb', 'total_mv', 'float_mv', 'float_share', 'total_share', 'is_st'];
        for (let f of fieldsToCopy) {
            if (last[f] !== undefined) mergedItem[f] = last[f];
        }

        mergedList.push(mergedItem);
    }

    return mergedList;
}

/**
 * 内部辅助函数：合并分钟K为更长周期
 */
function _mergeMinutesToPeriod(minuteData, frequency) {
    let sorted = minuteData.sort((a, b) => (a.date || 0) - (b.date || 0));
    let interval = parseInt(frequency.replace("m", ""));
    let groups = {};
    let groupKeys = [];

    for (let item of sorted) {
        let dateVal = item.date;
        if (!dateVal) continue;
        let dateStr = String(dateVal);
        if (dateStr.length < 14) continue;

        let year = dateStr.substring(0, 4);
        let month = dateStr.substring(4, 6);
        let day = dateStr.substring(6, 8);
        let hour = parseInt(dateStr.substring(8, 10));
        let minute = parseInt(dateStr.substring(10, 12));

        // 经典时间偏移区间对齐算法
        let totalMinutes = hour * 60 + minute;
        let groupIdx = Math.floor((totalMinutes - 1) / interval);
        let groupEndMins = (groupIdx + 1) * interval;

        let key = year + month + day + "_" + groupEndMins;
        if (!groups[key]) {
            groups[key] = [];
            groupKeys.push(key);
        }
        groups[key].push(item);
    }

    let mergedList = [];
    for (let i = 0; i < groupKeys.length; i++) {
        let key = groupKeys[i];
        let items = groups[key];
        let first = items[0];
        let last = items[items.length - 1];

        let high = Math.max(...items.map(x => x.high || 0));
        let low = Math.min(...items.map(x => x.low || 999999));
        let volume = items.map(x => x.volume || 0).reduce((a, b) => a + b, 0);
        let amount = items.map(x => x.amount || 0).reduce((a, b) => a + b, 0);

        let parts = key.split("_");
        let datePart = parts[0];
        let endMins = parseInt(parts[1]);
        
        let endHour = Math.floor(endMins / 60);
        let endMin = endMins % 60;
        if (endHour >= 24) {
            endHour = 23;
            endMin = 59;
        }

        let alignedDate = parseInt(datePart + 
            String(endHour).padStart(2, '0') + 
            String(endMin).padStart(2, '0') + "00");

        let mergedItem = {
            date: alignedDate,
            code: last.code,
            name: last.name || "",
            open: first.open,
            high: high,
            low: low,
            close: last.close,
            volume: volume,
            amount: amount
        };

        // 计算前收盘价
        let pre_close = 0;
        if (i > 0) {
            pre_close = mergedList[i - 1].close;
        } else {
            pre_close = first.pre_close || first.open;
        }
        mergedItem.pre_close = pre_close;

        if (pre_close) {
            mergedItem.pct_chg = Math.round(((mergedItem.close - pre_close) / pre_close) * 100000) / 1000;
            mergedItem.amplitude = Math.round(((high - low) / pre_close) * 100000) / 1000;
        } else {
            mergedItem.pct_chg = 0;
            mergedItem.amplitude = 0;
        }

        let fieldsToCopy = ['vol_ratio', 'pe_ttm', 'pb', 'total_mv', 'float_mv', 'float_share', 'total_share', 'is_st'];
        for (let f of fieldsToCopy) {
            if (last[f] !== undefined) mergedItem[f] = last[f];
        }

        mergedList.push(mergedItem);
    }

    return mergedList;
}

/**
 * 辅助算法：计算 ISO 周数
 */
function _getISOWeek(date) {
    let d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    let dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    let yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    let weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    return [d.getUTCFullYear(), weekNo];
}
