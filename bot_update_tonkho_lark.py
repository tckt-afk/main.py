import os
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# 1. CẤU HÌNH ĐẦY ĐỦ THÔNG TIN 2 KHO
# ==========================================
DANH_SACH_KHO = [
    {
        "ten": "KHO HÀ NỘI",
        "mau_sac": "red",
        "url_inventory": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?whid=4&includeTemp=1",
        "url_history_hientai": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=4",
        "url_history_cho": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=9",
        "cookie": os.getenv("KHO_COOKIE", "")
    },
    {
        "ten": "KHO HỒ CHÍ MINH",
        "mau_sac": "blue",
        "url_inventory": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?includeTemp=1&whid=6",
        "url_history_hientai": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=6",
        "url_history_cho": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=11",
        "cookie": os.getenv("COOKIE_HCM", "")
    }
]

# ==========================================
# 2. CÁC HẰNG SỐ CẤU HÌNH HỆ THỐNG
# ==========================================
LARK_WEBHOOK = os.getenv("LARK_WEBHOOK", "")
NGUONG_BAO_CAO = 300      # Ngưỡng báo cáo tổng hợp chốt ca
MAX_PAGES_HISTORY = 30    
MAX_PAGES_INVENTORY = 30  

# ==========================================
# 3. HÀM QUÉT LỊCH SỬ BÁN HÀNG
# ==========================================
def get_product_sales_stats(url_history_hientai, url_history_cho, cookie, ten_kho):
    sales_data = {}
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": cookie
    }

    for base_url in [url_history_hientai, url_history_cho]:
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
                    if len(cols) >= 5:
                        loai_sp = cols[2].text.strip()
                        ma_sp = cols[3].text.strip()
                        raw_qty = cols[4].text.strip()
                        if not ma_sp: continue
                        if ma_sp not in sales_data: sales_data[ma_sp] = 0
                        qty_digits = re.sub(r'[^\d]', '', raw_qty)
                        qty = int(qty_digits) if qty_digits.isdigit() else 0
                        
                        if "-" in raw_qty or "Xuất" in loai_sp or "Đơn hàng" in loai_sp:
                            sales_data[ma_sp] += qty
                        else:
                            sales_data[ma_sp] += max(1, qty // 2)
            except Exception as e:
                print(f"[{ten_kho}] Lỗi lịch sử trang {page}: {e}")
                break
    return sales_data

# ==========================================
# 4. HÀM QUÉT TỒN KHO THỰC TẾ
# ==========================================
def fetch_data_by_kho(kho, nguong_ton):
    sales_stats = get_product_sales_stats(kho["url_history_hientai"], kho["url_history_cho"], kho["cookie"], kho["ten"])
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": kho["cookie"]}
    canh_bao_list = []
    
    for page in range(1, MAX_PAGES_INVENTORY + 1):
        url = f"{kho['url_inventory']}&pageindex={page}&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200: break
            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select("table tbody tr")
            if not rows: break
                
            has_valid_item = False
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 5:
                    ten_sp = cols[1].text.strip()
                    ma_sp = cols[2].text.strip()
                    raw_ton = cols[4].text.strip().replace(",", "").replace(".", "")
                    try:
                        ton_kho = int(raw_ton)
                        has_valid_item = True
                        if ton_kho <= nguong_ton and ma_sp in sales_stats:
                            canh_bao_list.append({
                                "ma": ma_sp,
                                "ten": ten_sp,
                                "ton": ton_kho,
                                "da_ban": sales_stats[ma_sp]
                            })
                    except ValueError: continue
            
            if not has_valid_item: break
        except Exception as e:
            print(f"[{kho['ten']}] Lỗi tồn kho trang {page}: {e}")
            break
    return canh_bao_list

# ==========================================
# 5. TẠO GIAO DIỆN & GỬI THÔNG BÁO LARK
# ==========================================
def send_lark_alert(kho, items):
    if not items:
        return

    ten_kho = kho["ten"]
    items_sorted = sorted(items, key=lambda x: x['da_ban'], reverse=True)
    
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    now_str = now.strftime("%H:%M - %d/%m/%Y")

    # Chỉ còn bản tin tổng hợp vào 11:00 và 16:00
    formatted_items = []
    for idx, item in enumerate(items_sorted, 1):
        formatted_items.append(f"**{idx}. {item['ma']}**\n└ Tồn kho: **{item['ton']}** sp | Đã bán: **{item['da_ban']}** sp")

    content_text = "\n\n".join(formatted_items)

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🚨 BÁO CÁO CẦN NHẬP KHO: {ten_kho}"
                },
                "template": kho["mau_sac"]
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📍 **Địa điểm:** `{ten_kho}`\n"
                                   f"⏰ **Thời gian:** {now_str}\n"
                                   f"⚠️ **Cảnh báo:** Có **{len(items)}** sản phẩm **đang bán** cần nhập (Tồn kho ≤ **{NGUONG_BAO_CAO}**)\n"
                                   f"🔥 *Danh sách đã được ưu tiên xếp theo MÃ BÁN CHẠY NHẤT lên đầu.*"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content_text
                    }
                }
            ]
        }
    }

    res = requests.post(LARK_WEBHOOK, json=payload)
    print(f"[{ten_kho}] Gửi tin nhắn Lark thành công:", res.text)

# ==========================================
# 6. KHỞI CHẠY CHƯƠNG TRÌNH CHÍNH (MAIN)
# ==========================================
if __name__ == "__main__":
    # Cố định giờ Việt Nam để chạy đúng cả khi máy chủ dùng múi giờ UTC.
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    hour = now.hour
    minute = now.minute

    # Chỉ gửi đúng 2 thời điểm: 11:00 và 16:00.
    is_scheduled_report = hour in (11, 16) and minute == 0

    if is_scheduled_report:
        for kho in DANH_SACH_KHO:
            if not kho["cookie"]:
                continue

            ten_kho = kho["ten"]
            print(f"--- BẮT ĐẦU BÁO CÁO CHỐT CA: {ten_kho} ---")
            data = fetch_data_by_kho(kho, NGUONG_BAO_CAO)
            send_lark_alert(kho, data)
    else:
        print("Ngoài khung giờ 11:00 hoặc 16:00, không gửi thông báo tồn kho.")
