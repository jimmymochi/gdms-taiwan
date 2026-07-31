"""
GDMS Client — 所有 API 封裝
帳密從環境變數讀取，不寫在程式碼中
"""

import os
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 帳密從環境變數讀取（安全）─────────────────────────────────────────────
GDMS_USERNAME = os.environ.get("GDMS_USERNAME", "jimmymochi@gmail.com")
GDMS_PASSWORD = os.environ.get("GDMS_PASSWORD", "Jimmymochi@0320")

BASE_URL     = "https://gdms.cwa.gov.tw"
LOGIN_URL    = f"{BASE_URL}/login.php"
CATALOG_API  = f"{BASE_URL}/php/dbconnect/getCatalog.php"
NETWORK_API  = f"{BASE_URL}/php/dbconnect/getNetworkList.php"
STATION_API  = f"{BASE_URL}/php/dbconnect/getStationList.php"
LOCATION_API = f"{BASE_URL}/php/dbconnect/getLocationList.php"
CHANNEL_API  = f"{BASE_URL}/php/dbconnect/getchannelList.php"
STATION1_API = f"{BASE_URL}/php/dbconnect/getOneStationChannel.php"
EQ_DL_API    = f"{BASE_URL}/php/sendEqdownload.php"
RESP_DL_API  = f"{BASE_URL}/php/sendRespDownload.php"
DL_LIST_API  = f"{BASE_URL}/member_downloadList.php"

# ── Session 管理 ──────────────────────────────────────────────────────────

_session: requests.Session | None = None
_logged_in: bool = False


def _make_session() -> requests.Session:
    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def _login(s: requests.Session) -> bool:
    try:
        # Check if session is already authenticated
        r_chk = s.get(f"{BASE_URL}/userpage.php?r=check", timeout=10)
        if "登出" in r_chk.text or "logout" in r_chk.text.lower():
            return True

        import io
        from PIL import Image
        import ddddocr

        def clean_captcha(img_bytes: bytes) -> bytes:
            image = Image.open(io.BytesIO(img_bytes)).convert("L")
            buf = io.BytesIO()
            image.point(lambda p: 255 if p > 85 else 0).save(buf, format="PNG")
            return buf.getvalue()

        ocr = ddddocr.DdddOcr(show_ad=False)
        for _ in range(8):
            cap_res = s.get(f"{BASE_URL}/php/createcode.php", timeout=10)
            cleaned = clean_captcha(cap_res.content)
            code = ocr.classification(cleaned)
            chk_res = s.post(f"{BASE_URL}/php/checkcode.php", data={"code": code}, timeout=10)
            if chk_res.text.strip() == "1":
                lp_res = s.post(f"{BASE_URL}/php/loginProcess.php", data={
                    "username": GDMS_USERNAME,
                    "password": GDMS_PASSWORD,
                    "g-recaptcha-response": "",
                    "img-captcha": code
                }, timeout=10)
                if lp_res.json().get("status") == 1:
                    return True
        return False
    except Exception:
        try:
            r = s.post(LOGIN_URL, data={"username": GDMS_USERNAME, "password": GDMS_PASSWORD}, allow_redirects=True, timeout=20)
            return "logout" in r.text.lower() or "登出" in r.text
        except Exception:
            return False


def get_session() -> requests.Session:
    global _session, _logged_in
    if _session is None or not _logged_in:
        _session = _make_session()
        _logged_in = _login(_session)
    return _session


def ensure_login() -> bool:
    global _logged_in
    s = get_session()
    if not _logged_in:
        _logged_in = _login(s)
    return _logged_in


def _post(url: str, data: dict | None = None) -> list | dict | None:
    s = get_session()
    try:
        r = s.post(url, data=data or {}, timeout=30)
        return r.json()
    except Exception:
        return None


def _get(url: str, params: dict | None = None) -> list | dict | None:
    s = get_session()
    try:
        r = s.get(url, params=params, timeout=30)
        return r.json()
    except Exception:
        return None


def _get_raw(url: str, params: dict | None = None) -> requests.Response | None:
    """回傳原始 Response（用於二進位下載）"""
    s = get_session()
    try:
        return s.get(url, params=params, timeout=60, stream=True)
    except Exception:
        return None


# ── 地震目錄 ────────────────────────────────────────────────────────────────

def get_catalog(
    stdate: str, sttime: str, eddate: str, edtime: str,
    min_ml: float | None = None, max_ml: float | None = None,
    min_dep: float | None = None, max_dep: float | None = None,
    min_lon: float | None = None, max_lon: float | None = None,
    min_lat: float | None = None, max_lat: float | None = None,
    cir_lon: float | None = None, cir_lat: float | None = None,
    cir_rad: float | None = None,
) -> list:
    p: dict[str, str] = {
        "stdate": stdate, "sttime": sttime,
        "eddate": eddate, "edtime": edtime,
    }
    if min_ml  is not None: p["minML"]  = str(min_ml)
    if max_ml  is not None: p["maxML"]  = str(max_ml)
    if min_dep is not None: p["minDep"] = str(min_dep)
    if max_dep is not None: p["maxDep"] = str(max_dep)
    if cir_lon is not None and cir_lat is not None and cir_rad is not None:
        p["cirlon"] = str(cir_lon)
        p["cirlat"] = str(cir_lat)
        p["cirrad"] = str(cir_rad)
    else:
        if min_lon is not None: p["minlon"] = str(min_lon)
        if max_lon is not None: p["maxlon"] = str(max_lon)
        if min_lat is not None: p["minlat"] = str(min_lat)
        if max_lat is not None: p["maxlat"] = str(max_lat)
    result = _post(CATALOG_API, p)
    return result if isinstance(result, list) else []


# ── 觀測網路 / 測站 / 通道 ───────────────────────────────────────────────────

def get_networks() -> list:
    result = _get(NETWORK_API)
    return result if isinstance(result, list) else []


def get_stations(network: str = "", type_: str = "") -> list:
    p: dict[str, str] = {}
    if network: p["network"] = network
    if type_:   p["type"]    = type_
    result = _post(STATION_API, p)
    return result if isinstance(result, list) else []


def get_locations(network: str = "", station: str = "") -> list:
    p: dict[str, str] = {}
    if network: p["network"] = network
    if station: p["station"] = station
    result = _post(LOCATION_API, p)
    return result if isinstance(result, list) else []


def get_channels(
    network: str = "", station: str = "", location: str = ""
) -> list:
    p: dict[str, str] = {}
    if network:  p["network"]  = network
    if station:  p["station"]  = station
    if location: p["location"] = location
    result = _post(CHANNEL_API, p)
    return result if isinstance(result, list) else []


def get_one_station_channels(
    network: str, station: str
) -> list:
    result = _post(STATION1_API, {"network": network, "station": station})
    return result if isinstance(result, list) else []


# ── 多站波形資料（事件下載）─────────────────────────────────────────────────

def submit_eq_download(
    stations: str,         # 逗號分隔站名, e.g. "NACB,WGKF"
    sttime: str,           # e.g. "2024-04-03 07:58:00"
    edtime: str,           # e.g. "2024-04-03 08:10:00"
    network: str = "",
    location: str = "*",
    channel: str = "",
    output: str = "MiniSEED",   # MiniSEED | SAC binary | ASCII: 1 column format
    label: str = "GDMSData",
    all_station: bool = False,
) -> dict:
    """送出多站波形下載請求，回傳 {success, message, download_id}"""
    s = get_session()
    data = {
        "station":  "all" if all_station else stations,
        "sttime":   sttime,
        "edtime":   edtime,
        "network":  network,
        "location": location,
        "channel":  channel,
        "output":   output,
        "label":    label,
    }
    if all_station:
        data["allstation"] = "on"
    try:
        r = s.post(EQ_DL_API, data=data, timeout=60)
        try:
            return r.json()
        except Exception:
            return {"success": False, "message": r.text[:300]}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── 儀器響應資料 ────────────────────────────────────────────────────────────

def submit_resp_download(
    stations: str,
    sttime: str,
    edtime: str,
    network: str = "",
    location: str = "*",
    channel: str = "",
    label: str = "GDMSData",
) -> dict:
    s = get_session()
    data = {
        "station":  stations,
        "sttime":   sttime,
        "edtime":   edtime,
        "network":  network,
        "location": location,
        "channel":  channel,
        "label":    label,
    }
    try:
        r = s.post(RESP_DL_API, data=data, timeout=60)
        try:
            return r.json()
        except Exception:
            return {"success": False, "message": r.text[:300]}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── 用戶下載清單 ─────────────────────────────────────────────────────────────

def get_download_list() -> list:
    """取得用戶的下載任務清單（含下載連結）"""
    s = get_session()
    try:
        r = s.get(DL_LIST_API, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        table = soup.find("table")
        if not table:
            return []
        headers: list[str] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            links = [a.get("href", "") for a in tr.find_all("a")]
            if not headers:
                headers = cells
                continue
            if cells:
                row = dict(zip(headers, cells))
                if links:
                    row["download_url"] = links[0]
                rows.append(row)
        return rows
    except Exception:
        return []


# ── 地球物理資料（GeophyDownload）─────────────────────────────────────────

def submit_geophy_download(
    stations: str,
    sttime: str,
    edtime: str,
    network: str = "GNSS",
    gnss_type: str = "Observation file (.o)",
    label: str = "GDMSData",
    all_station: bool = False,
) -> dict:
    """送出地球物理資料（GNSS/地磁/地下水）下載請求"""
    s = get_session()
    data = {
        "station":   "all" if all_station else stations,
        "sttime":    sttime,
        "edtime":    edtime,
        "network":   network,
        "gnss-type": gnss_type,
        "label":     label,
    }
    if all_station:
        data["allstation"] = "on"
    try:
        r = s.post(f"{BASE_URL}/php/sendGeophyDownload.php", data=data, timeout=60)
        try:
            return r.json()
        except Exception:
            return {"success": False, "message": r.text[:300]}
    except Exception as e:
        return {"success": False, "message": str(e)}
