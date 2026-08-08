import os
import requests
import re
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

def get_product_sales_stats(url_history_hientai, url_history_cho, cookie, ten_kho):
    """
    Quét 30 trang lịch sử giao dịch (Kho hiện tại + Kho chờ)
    Tính tổng số lượng bán / xuất kho của từng Mã SP để xếp hạng độ BÁN CHẠY.
    """
    sales_data = {} # { "MÃ_SP": total_sold_qty }
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
                    # Cột Loại/Sản phẩm (Col 3), Mã SP (Col 4), Số lượng (Col 5)
                    if len(cols) >= 5:
                        loai_sp = cols[2].text.strip()
                        ma_sp = cols[3].text.strip()
                        raw_qty = cols[4].text.strip()

                        if not ma_sp:
                            continue

                        # Nếu chưa có mã này trong dict thì khởi tạo = 0
                        if ma_sp not in sales_data:
                            sales_data[ma_sp] = 0

                        # Lấy số lượng (Xử lý chuỗi ví dụ '- 10', '+ 5', '10')
                        qty_digits = re.sub(r'[^\d]', '', raw_qty)
                        qty = int(qty_digits) if qty_digits.isdigit() else 0

                        # Nếu là giao dịch xuất/bán hoặc có dấu trừ -> cộng dồn vào lượng bán
                        if "-" in raw_qty or "Xuất" in loai_sp or "Đơn hàng" in loai_sp:
                            sales_data[ma_sp] += qty
                        else:
                            # Nếu có bất kỳ giao dịch nhập/xuất nào cũng tính mã này đang hoạt động (tối thiểu 1)
                            sales_data[ma_sp] += max(1, qty // 2)

            except Exception as e:
                print(f"[{ten_kho}] Lỗi khi quét lịch sử trang {page}: {e}")
                break

    print(f"[{ten_kho}] Tìm thấy {len(sales_data)} mã sản phẩm ĐANG BÁN trong {MAX_PAGES_HISTORY} trang lịch sử.")
    return sales_data

def fetch_data_by_kho(kho):
    # 1. Lấy thống kê bán chạy từ lịch sử 30 trang
    sales_stats = get_product_sales_stats(
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

                        # ĐIỀU KIỆN LỌC:
                        # 1. Tồn kho <= 300
                        # 2. Mã SP phải nằm trong danh sách ĐANG BÁN (sales_stats)
                        if ton_kho <= NGUONG_CANH_BAO and ma_sp in sales_stats:
                            canh_bao_list.append({
                                "ma": ma_sp,
                                "ten": ten_sp,
                                "ton": ton_kho,
                                "da_ban": sales_stats[ma_sp] # Lượng bán ra để làm căn cứ sắp xếp
                            })
                    except ValueError:
                        continue
            
            if not has_valid_item:
                break

        except Exception as e:
            print(f"[{ten_kho}] Lỗi quét tồn kho trang {page}: {e}")
            break

    return canh_bao_list

def send_lark_alert(ten_kho, items):
    if not items:
        print(f"[{ten_kho}] Không có sản phẩm đang bán nào bị thiếu hàng (Tồn > {NGUONG_CANH_BAO}).")
        return

    # SẮP XẾP ƯU TIÊN: MÃ BÁN CHẠY NHẤT (da_ban giảm dần) LÊN ĐẦU
    items_sorted = sorted(items, key=lambda x: x['da_ban'], reverse=True)

    formatted_items = []
    for idx, item in enumerate(items_sorted, 1):
        # Đánh dấu icon cho các sản phẩm siêu bán chạy
        hot_badge = " 🔥" if idx <= 3 else ""
        formatted_items.append(
            f"**{idx}. `{item['ma']}`**{hot_badge} — {item['ten']}\n"
            f"└ 📦 Tồn kho: <font color='red'>**{item['ton']}**</font> | ⚡ Lượng bán gần đây: **{item['da_ban']}** sp"
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
                                   f"⚠️ **Cảnh báo:** Có **{len(items)}** sản phẩm **đang bán** cần nhập (Tồn kho **≤ {NGUONG_CANH_BAO}**)\n"
                                   f"🔥 *Danh sách đã được ưu tiên xếp theo MÃ BÁN CHẠY NHẤT lên đầu.*"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"### 📋 MÃ HÀNG BÁN CHẠY CẦN BỔ SUNG GẤP\n\n{content_text}"
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
                            "content": "🤖 Hệ thống kiểm soát kho tự động Nhựa HVT • Tự động xếp hạng theo độ bán chạy"
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
