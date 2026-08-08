import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- CẤU HÌNH KHO & URL ---
DANH_SACH_KHO = [
    {
        "ten": "KHO HÀ NỘI",
        "url_inventory": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?whid=4&includeTemp=1",
        "url_history_hientai": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=4",
        "url_history_cho": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=9",
        "cookie": os.getenv("KHO_COOKIE", "")
    },
    {
        "ten": "KHO HỒ CHÍ MINH",
        "url_inventory": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?includeTemp=1&whid=6",
        "url_history_hientai": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=6",
        "url_history_cho": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=11",
        "cookie": os.getenv("COOKIE_HCM", "")
    }
]

LARK_WEBHOOK = os.getenv("LARK_WEBHOOK", "")
NGUONG_CANH_BAO = 300  # Cảnh báo khi Tồn <= 300
MAX_PAGES_HISTORY = 30 # Quét 30 trang lịch sử giao dịch gần nhất
MAX_PAGES_INVENTORY = 30 

def get_active_product_codes(url_history_hientai, url_history_cho, cookie, ten_kho):
    """
    Quét 30 trang lịch sử giao dịch (Kho hiện tại + Kho chờ)
    để lấy danh sách tất cả các Mã SP đang có hoạt động bán/xuất nhập.
    """
    active_codes = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie
    }

    urls_to_scan = [url_history_hientai, url_history_cho]

    for base_url in urls_to_scan:
        for page in range(1, MAX_PAGES_HISTORY + 1):
            url = f"{base_url}&pageindex={page}&page={page}"
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code != 200:
                    break

                soup = BeautifulSoup(res.text, 'html.parser')
                rows = soup.select("table tbody tr")
                if not rows:
                    break

                for row in rows:
                    cols = row.find_all("td")
                    # Cột Mã SP nằm ở cột thứ 4 (index 3)
                    if len(cols) >= 4:
                        ma_sp = cols[3].text.strip()
                        if ma_sp:
                            active_codes.add(ma_sp)

            except Exception as e:
                print(f"[{ten_kho}] Lỗi khi quét lịch sử trang {page}: {e}")
                break

    print(f"[{ten_kho}] Tìm thấy {len(active_codes)} mã sản phẩm ĐANG BÁN/HOẠT ĐỘNG trong {MAX_PAGES_HISTORY} trang lịch sử.")
    return active_codes

def fetch_data_by_kho(kho):
    # 1. Lấy danh sách Mã SP đang active từ lịch sử
    active_codes = get_active_product_codes(
        kho["url_history_hientai"], 
        kho["url_history_cho"], 
        kho["cookie"], 
        kho["ten"]
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": kho["cookie"]
    }

    canh_bao_list = []
    
    # 2. Quét tồn kho
    for page in range(1, MAX_PAGES_INVENTORY + 1):
        url = f"{kho['url_inventory']}&pageindex={page}&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select("table tbody tr")
            if not rows:
                break
                
            has_valid_item = False
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 5:
                    ten_sp = cols[1].text.strip()   # Cột 2: Tên sản phẩm
                    ma_sp = cols[2].text.strip()    # Cột 3: Mã SP
                    raw_ton = cols[4].text.strip().replace(",", "").replace(".", "") # Cột 5: Tồn kho
                    
                    try:
                        ton_kho = int(raw_ton)
                        has_valid_item = True

                        # ĐIỀU KIỆN LỌC KÉP: 
                        # 1. Tồn kho <= 300
                        # 2. Mã SP phải nằm trong danh sách ĐANG BÁN (active_codes)
                        if ton_kho <= NGUONG_CANH_BAO and ma_sp in active_codes:
                            canh_bao_list.append({
                                "ma": ma_sp,
                                "ten": ten_sp,
                                "ton": ton_kho
                            })
                    except ValueError:
                        continue
            
            if not has_valid_item:
                break

        except Exception as e:
            print(f"[{kho['ten']}] Lỗi quét tồn kho trang {page}: {e}")
            break

    return canh_bao_list

def send_lark_alert(ten_kho, items):
    if not items:
        print(f"[{ten_kho}] Không có sản phẩm đang bán nào bị thiếu hàng (Tồn > {NGUONG_CANH_BAO}).")
        return

    # Sắp xếp theo lượng tồn tăng dần (ít nhất lên đầu)
    items_sorted = sorted(items, key=lambda x: x['ton'])

    formatted_items = []
    for idx, item in enumerate(items_sorted, 1):
        formatted_items.append(
            f"**{idx}. `{item['ma']}`** — {item['ten']}\n"
            f"└ 📦 Tồn kho: <font color='red'>**{item['ton']}**</font> sản phẩm"
        )
    
    content_text = "\n\n".join(formatted_items)
    now_str = datetime.now().strftime("%H:%M - %d/%m/%Y")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🚨 BÁO CÁO CẦN NHẬP KHO: {ten_kho}"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📍 **Địa điểm:** `{ten_kho}`\n"
                                   f"⏰ **Thời gian:** {now_str}\n"
                                   f"⚠️ **Cảnh báo:** Có **{len(items)}** sản phẩm **đang bán** bị tồn thấp (Tồn kho **≤ {NGUONG_CANH_BAO}**)"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"### 📋 DANH SÁCH SẢN PHẨM CẦN BỔ SUNG\n\n{content_text}"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "🤖 Hệ thống kiểm soát kho tự động Nhựa HVT • Tự lọc bỏ sản phẩm ngừng bán"
                        }
                    ]
                }
            ]
        }
    }

    res = requests.post(LARK_WEBHOOK, json=payload)
    print(f"[{ten_kho}] Gửi báo cáo Lark thành công:", res.text)

if __name__ == "__main__":
    for kho in DANH_SACH_KHO:
        if kho["cookie"]:
            print(f"--- BẮT ĐẦU QUÉT {kho['ten']} ---")
            data = fetch_data_by_kho(kho)
            send_lark_alert(kho['ten'], data)
