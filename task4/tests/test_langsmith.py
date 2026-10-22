import time, urllib.request, requests

import requests
print(requests.get("https://www.google.com", timeout=10).status_code)

print("Python 看到的代理:", urllib.request.getproxies())  # 空的 = Python 没走代理

body = b"x" * (15 * 1024 * 1024)  # 模拟 15MB 上传
for label, proxies in [("直连", None), ("走代理", {"https": "http://127.0.0.1:7890"})]:
    t0 = time.time()
    try:
        r = requests.post("https://api.smith.langchain.com/runs/multipart",
                          data=body, timeout=(10, 60), proxies=proxies)
        print(label, "->", r.status_code, f"{time.time()-t0:.1f}s")
    except Exception as e:
        print(label, "-> 失败:", type(e).__name__, f"{time.time()-t0:.1f}s")
