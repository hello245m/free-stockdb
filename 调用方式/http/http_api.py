import requests

#极简http_api 

#请求地址 "http://127.0.0.1:7899"

#双击启动stockdb.exe 数据库后即可调用

z=requests.get("http://127.0.0.1:7899/?cmd=get&t=日k:600702:20260623")
print(z.text,z.json())



#查看更多生成的url格式 （比如/?cmd=get&t=日k:600702:20260623）
#前提: 先运行一次文件 ./pybao/安装.py

from stockdb import rd

print(rd.get("复权","600702","2026*").url())
print(rd.get("日k","600702*").url())
print(rd.get("分钟k","600702","2026062310000").url())


print(rd.vals("复权","600702","2026*").url())
print(rd.vals("日k","600702*").url())
print(rd.vals("分钟k","600702","2026062310000").get("close,open").url())


#更多使用参考 ./http/rd_test.py 

