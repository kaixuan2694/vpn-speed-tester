import json
import math
import socket
import ssl
import statistics
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from urllib import error, request

try:
    import winreg
except ImportError:
    winreg = None


APP_TITLE = "网络测速工具"
APP_VERSION = "1.0.0"
USER_AGENT = f"VPN-Speed-Tester/{APP_VERSION}"

DOWNLOAD_TESTS = [
    ("Cloudflare 下载 10 MB", "https://speed.cloudflare.com/__down?bytes=10000000", 10_000_000),
    ("Cloudflare 下载 25 MB", "https://speed.cloudflare.com/__down?bytes=25000000", 25_000_000),
    ("Cachefly 下载 50 MB", "https://cachefly.cachefly.net/50mb.test", 50_000_000),
]

UPLOAD_URL = "https://speed.cloudflare.com/__up"
UPLOAD_BYTES = 10 * 1024 * 1024

LATENCY_URLS = [
    ("Cloudflare", "https://www.cloudflare.com/cdn-cgi/trace"),
    ("Google", "https://www.gstatic.com/generate_204"),
]


def format_mbps(bytes_per_second):
    return bytes_per_second * 8 / 1_000_000


def format_size(num_bytes):
    units = ["B", "KB", "MB", "GB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024


def evaluate_speed(download_mbps, upload_mbps, latency_ms):
    download = download_mbps or 0
    upload = upload_mbps or 0
    latency = latency_ms if latency_ms is not None else 999

    if download < 3 or latency > 1500:
        return "没有🐎：网速超级差，网页都可能卡，建议换节点。"
    if download < 12 or latency > 800:
        return "下等🐎：能用但偏慢，刷网页还行，视频和下载会难受。"
    if download < 35 or latency > 350:
        return "中等🐎：正常的网速，ChatGPT、网页、1080p 视频基本够用。"
    if download < 80 or upload < 10:
        return "上等🐎：速度挺好，高清视频、下载和日常办公都比较舒服。"
    return "🐎丁：网速巨快，这个节点很能跑。"


def is_port_open(host, port, timeout=0.3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_windows_proxy():
    if not winreg:
        return None
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            if not enabled:
                return None
            proxy_server = winreg.QueryValueEx(key, "ProxyServer")[0]
    except OSError:
        return None

    if not proxy_server:
        return None

    parts = {}
    for item in str(proxy_server).split(";"):
        if "=" in item:
            name, value = item.split("=", 1)
            parts[name.lower()] = value
    if parts:
        chosen = parts.get("https") or parts.get("http") or next(iter(parts.values()))
    else:
        chosen = str(proxy_server)

    if not chosen.startswith(("http://", "https://")):
        chosen = "http://" + chosen
    return chosen


def build_proxy_url(mode, custom_proxy):
    mode = mode.strip()
    aliases = {
        "自动识别": "Auto",
        "系统代理": "System proxy",
        "直连/TUN": "Direct",
        "自定义": "Custom",
    }
    mode = aliases.get(mode, mode)
    if mode == "Direct":
        return None
    if mode == "System proxy":
        return get_windows_proxy()
    if mode == "Auto":
        system_proxy = get_windows_proxy()
        if system_proxy:
            return system_proxy
        for port in (7890, 7897, 10809, 1080):
            if is_port_open("127.0.0.1", port):
                return f"http://127.0.0.1:{port}"
        return None
    if mode.startswith("127.0.0.1:"):
        return "http://" + mode
    custom = custom_proxy.strip()
    if custom:
        if not custom.startswith(("http://", "https://")):
            custom = "http://" + custom
        return custom
    return None


def make_opener(proxy_url):
    handlers = []
    if proxy_url:
        handlers.append(request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    else:
        handlers.append(request.ProxyHandler({}))
    opener = request.build_opener(*handlers)
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def fetch_json(opener, url, timeout=12):
    with opener.open(url, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
    return json.loads(payload)


def get_node_info(opener):
    errors = []
    for url in ("https://ipwho.is/", "https://ipapi.co/json/"):
        try:
            data = fetch_json(opener, url)
            if data.get("success") is False:
                raise RuntimeError(data.get("message", "IP lookup failed"))
            ip = data.get("ip") or data.get("query")
            country = data.get("country") or data.get("country_name") or ""
            city = data.get("city") or ""
            region = data.get("region") or data.get("regionName") or ""
            connection = data.get("connection") or {}
            isp = data.get("isp") or data.get("org") or connection.get("isp") or connection.get("org") or ""
            asn = data.get("asn") or connection.get("asn") or ""
            timezone = data.get("timezone")
            if isinstance(timezone, dict):
                timezone = timezone.get("id", "")
            return {
                "ip": ip or "Unknown",
                "country": country,
                "region": region,
                "city": city,
                "isp": isp,
                "asn": asn,
                "timezone": timezone or "",
            }
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    try:
        data = fetch_json(opener, "http://ip-api.com/json/?fields=status,country,regionName,city,isp,org,as,query,timezone")
        if data.get("status") != "success":
            raise RuntimeError("IP lookup failed")
        return {
            "ip": data.get("query", "Unknown"),
            "country": data.get("country", ""),
            "region": data.get("regionName", ""),
            "city": data.get("city", ""),
            "isp": data.get("isp") or data.get("org") or "",
            "asn": data.get("as", ""),
            "timezone": data.get("timezone", ""),
        }
    except Exception as exc:
        errors.append(f"ip-api: {exc}")

    raise RuntimeError("; ".join(errors))


def measure_latency(opener, url, samples=4):
    values = []
    for _ in range(samples):
        started = time.perf_counter()
        req = request.Request(url, method="GET", headers={"Cache-Control": "no-cache"})
        with opener.open(req, timeout=12) as response:
            response.read(256)
        values.append((time.perf_counter() - started) * 1000)
        time.sleep(0.2)
    return values


def download_speed(opener, url, limit_bytes=None, timeout=90):
    req = request.Request(url, headers={"Cache-Control": "no-cache"})
    started = time.perf_counter()
    total = 0
    with opener.open(req, timeout=timeout) as response:
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if limit_bytes and total >= limit_bytes:
                break
    elapsed = max(time.perf_counter() - started, 0.001)
    return total, elapsed, total / elapsed


def upload_speed(opener, size_bytes=UPLOAD_BYTES, timeout=90):
    payload = b"0" * size_bytes
    req = request.Request(
        UPLOAD_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/octet-stream",
            "Cache-Control": "no-cache",
        },
    )
    started = time.perf_counter()
    with opener.open(req, timeout=timeout) as response:
        response.read(1024)
    elapsed = max(time.perf_counter() - started, 0.001)
    return size_bytes, elapsed, size_bytes / elapsed


class SpeedTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("760x620")
        self.root.minsize(720, 560)
        self.worker = None

        self.proxy_mode = tk.StringVar(value="自动识别")
        self.custom_proxy = tk.StringVar(value="")
        self.status = tk.StringVar(value="准备就绪")
        self.node_text = tk.StringVar(value="还未测试")
        self.latency_text = tk.StringVar(value="-")
        self.download_text = tk.StringVar(value="-")
        self.upload_text = tk.StringVar(value="-")
        self.proxy_text = tk.StringVar(value="-")
        self.evaluation_text = tk.StringVar(value="测速后显示")
        self.progress_text = tk.StringVar(value="0%")
        self.progress_value = tk.DoubleVar(value=0)

        self.build_ui()

    def build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        root = ttk.Frame(self.root, padding=18)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="梯子测速工具", font=("Segoe UI", 20, "bold")).pack(side="left")
        ttk.Button(header, text="开始测速", command=self.start_test).pack(side="right")

        controls = ttk.LabelFrame(root, text="连接设置")
        controls.pack(fill="x", pady=(18, 12))

        ttk.Label(controls, text="代理模式").grid(row=0, column=0, sticky="w", padx=12, pady=10)
        proxy_box = ttk.Combobox(
            controls,
            textvariable=self.proxy_mode,
            state="readonly",
            values=["自动识别", "系统代理", "直连/TUN", "127.0.0.1:7890", "127.0.0.1:7897", "127.0.0.1:10809", "自定义"],
            width=20,
        )
        proxy_box.grid(row=0, column=1, sticky="w", padx=8, pady=10)

        ttk.Label(controls, text="自定义代理").grid(row=0, column=2, sticky="w", padx=12, pady=10)
        ttk.Entry(controls, textvariable=self.custom_proxy, width=28).grid(row=0, column=3, sticky="we", padx=8, pady=10)
        controls.columnconfigure(3, weight=1)

        progress_frame = ttk.Frame(root)
        progress_frame.pack(fill="x", pady=(0, 8))
        self.progress = ttk.Progressbar(progress_frame, variable=self.progress_value, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Label(progress_frame, textvariable=self.progress_text, width=8, anchor="e", font=("Segoe UI", 10, "bold")).pack(side="right", padx=(10, 0))

        summary = ttk.Frame(root)
        summary.pack(fill="x")
        self.add_metric(summary, "当前节点", self.node_text, 0, 0, colspan=2)
        self.add_metric(summary, "当前代理", self.proxy_text, 1, 0, colspan=2)
        self.add_metric(summary, "网页延迟", self.latency_text, 2, 0)
        self.add_metric(summary, "下载速度", self.download_text, 2, 1)
        self.add_metric(summary, "上传速度", self.upload_text, 3, 0)
        self.add_metric(summary, "测试状态", self.status, 3, 1)
        self.add_metric(summary, "网速评估", self.evaluation_text, 4, 0, colspan=2)

        log_frame = ttk.LabelFrame(root, text="详细记录")
        log_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.log = tk.Text(log_frame, height=12, wrap="word", font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)
        self.log.configure(yscrollcommand=scrollbar.set)

    def add_metric(self, parent, title, variable, row, column, colspan=1):
        frame = ttk.Frame(parent, padding=10, relief="ridge")
        frame.grid(row=row, column=column, columnspan=colspan, sticky="nsew", padx=5, pady=5)
        ttk.Label(frame, text=title, font=("Segoe UI", 9)).pack(anchor="w")
        ttk.Label(frame, textvariable=variable, font=("Segoe UI", 12, "bold"), wraplength=640).pack(anchor="w", pady=(4, 0))
        parent.columnconfigure(column, weight=1)
        if colspan > 1:
            parent.columnconfigure(column + 1, weight=1)

    def append_log(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def ui(self, func, *args):
        self.root.after(0, lambda: func(*args))

    def set_status(self, text):
        self.ui(self.status.set, text)
        self.ui(self.append_log, text)

    def set_progress(self, value, text=None):
        value = max(0, min(100, value))
        self.ui(self.progress_value.set, value)
        self.ui(self.progress_text.set, text or f"{value:.0f}%")

    def start_test(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "正在测速中，请稍等。")
            return
        self.log.delete("1.0", "end")
        self.node_text.set("测试中...")
        self.latency_text.set("-")
        self.download_text.set("-")
        self.upload_text.set("-")
        self.evaluation_text.set("测速后显示")
        self.status.set("准备开始")
        self.progress_value.set(0)
        self.progress_text.set("0%")
        self.worker = threading.Thread(target=self.run_test, daemon=True)
        self.worker.start()

    def run_test(self):
        try:
            proxy_url = build_proxy_url(self.proxy_mode.get(), self.custom_proxy.get())
            opener = make_opener(proxy_url)
            self.ui(self.proxy_text.set, proxy_url or "直连 / TUN 模式")
            self.set_progress(5)
            self.set_status("正在识别当前节点...")

            node = get_node_info(opener)
            location = ", ".join(part for part in [node["country"], node["region"], node["city"]] if part)
            node_line = f'{node["ip"]} | {location or "Unknown location"} | {node["isp"] or "Unknown ISP"}'
            if node["asn"]:
                node_line += f" | {node['asn']}"
            self.ui(self.node_text.set, node_line)
            self.set_progress(15)
            self.ui(self.append_log, f"节点：{node_line}")
            if node["timezone"]:
                self.ui(self.append_log, f"时区：{node['timezone']}")

            self.set_status("正在测试网页延迟...")
            latency_results = []
            for index, (name, url) in enumerate(LATENCY_URLS, start=1):
                try:
                    values = measure_latency(opener, url)
                    avg = statistics.mean(values)
                    latency_results.append(avg)
                    self.ui(self.append_log, f"{name} 延迟：平均 {avg:.0f} ms，最低 {min(values):.0f} ms，最高 {max(values):.0f} ms")
                except Exception as exc:
                    self.ui(self.append_log, f"{name} 延迟测试失败：{exc}")
                self.set_progress(15 + index * 10)
            if latency_results:
                avg_latency = statistics.mean(latency_results)
                self.ui(self.latency_text.set, f"平均 {avg_latency:.0f} ms")
            else:
                avg_latency = None
                self.ui(self.latency_text.set, "失败")

            self.set_status("正在测试下载速度...")
            download_mbps = []
            for index, (name, url, expected_size) in enumerate(DOWNLOAD_TESTS, start=1):
                try:
                    total, elapsed, bps = download_speed(opener, url, expected_size)
                    mbps = format_mbps(bps)
                    download_mbps.append(mbps)
                    self.ui(self.append_log, f"{name}：{mbps:.1f} Mbps（{format_size(total)}，{elapsed:.1f} 秒）")
                except (error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                    self.ui(self.append_log, f"{name} 失败：{exc}")
                self.set_progress(35 + index * 10)
            if download_mbps:
                best = max(download_mbps)
                avg = statistics.mean(download_mbps)
                avg_download = avg
                self.ui(self.download_text.set, f"平均 {avg:.1f} Mbps / 最高 {best:.1f} Mbps")
            else:
                avg_download = None
                self.ui(self.download_text.set, "失败")

            self.set_status("正在测试上传速度...")
            upload_mbps = []
            for index in range(2):
                try:
                    total, elapsed, bps = upload_speed(opener)
                    mbps = format_mbps(bps)
                    upload_mbps.append(mbps)
                    self.ui(self.append_log, f"上传 {index + 1}：{mbps:.1f} Mbps（{format_size(total)}，{elapsed:.1f} 秒）")
                except (error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                    self.ui(self.append_log, f"上传 {index + 1} 失败：{exc}")
                self.set_progress(65 + (index + 1) * 15)
            if upload_mbps:
                best = max(upload_mbps)
                avg = statistics.mean(upload_mbps)
                avg_upload = avg
                self.ui(self.upload_text.set, f"平均 {avg:.1f} Mbps / 最高 {best:.1f} Mbps")
            else:
                avg_upload = None
                self.ui(self.upload_text.set, "失败")

            evaluation = evaluate_speed(avg_download, avg_upload, avg_latency)
            self.ui(self.evaluation_text.set, evaluation)
            self.ui(self.append_log, f"网速评估：{evaluation}")
            self.set_progress(100)
            self.set_status("测试完成")
        except Exception as exc:
            self.set_progress(100, "失败")
            self.ui(self.status.set, "测试失败")
            self.ui(self.append_log, f"错误：{exc}")
            self.ui(messagebox.showerror, APP_TITLE, str(exc))


def main():
    root = tk.Tk()
    SpeedTesterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
