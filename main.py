import os
import requests
import re
import json
from bs4 import BeautifulSoup
from datetime import datetime

# --- CẤU HÌNH KHO & URL ---
DANH_SACH_KHO = [
    {
        "ten": "KHO HÀ NỘI",
        "tag_nhan_biet": "🏙️ [KHO HÀ NỘI - MIỀN BẮC]",
        "mau_sac_chot_ca": "purple",      # Màu Tím đặc trưng cho Hà Nội
        "url_inventory": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?whid=4&includeTemp=1",
        "url_history_hientai": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=4",
        "url_history_cho": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=9",
        "cookie": os.getenv("KHO_COOKIE", "")
    },
    {
        "ten": "KHO HỒ CHÍ MINH",
        "tag_nhan_biet": "🌆 [KHO HỒ CHÍ MINH - MIỀN NAM]",
        "mau_sac_chot_ca": "wathet",      # Màu Xanh Dương rực rỡ đặc trưng cho HCM
        "url_inventory": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?includeTemp=1&whid=6",
        "url_history_hientai": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=6",
        "url_history_cho": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Transaction?whid=11",
        "cookie": os.getenv("COOKIE_HCM", "")
    }
]

LARK_WEBHOOK = os.getenv("LARK_WEBHOOK", "")
NGUONG_BAO_CAO = 300      # Ngưỡng báo cáo tổng hợp ca (<= 300)
NGUONG_KHAN_CAP = 100     # Ngưỡng cảnh báo khẩn cấp (<= 100)
MAX_PAGES_HISTORY = 30 
MAX_PAGES_INVENTORY = 30 

STATE_FILE = "alerted_items.json"

def load_alerted_items():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_alerted_items(data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi lưu bộ nhớ đệm: {e}")

def get_product_sales_stats(url_history_hientai, url_history_cho, cookie, ten_kho):
    sales_data = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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

                        if not ma_sp:
                            continue

                        if ma_sp not in sales_data:
                            sales_data[ma_sp] = 0

                        qty_digits = re.sub(r'[^\d]', '', raw_qty)
                        qty = int(qty_digits) if qty_digits.isdigit() else 0

                        if "-" in raw_qty or "Xuất" in loai_sp or "Đơn hàng" in loai_sp:
                            sales_data[ma_sp] += qty
                        else:
                            sales_data[ma_sp] += max(1, qty // 2)

            except Exception as e:
                print(f"[{ten_kho}] Lỗi quét lịch sử trang {page}: {e}")
                break

    return sales_data

def fetch_data_by_kho(kho, nguong_ton):
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
                    except ValueError:
                        continue
            
            if not has_valid_item:
                break

        except Exception as e:
            print(f"[{kho['ten']}] Lỗi quét tồn kho trang {page}: {e}")
            break

    return canh_bao_list

def send_lark_alert(kho, items, is_urgent=False):
    if not items:
        return

    ten_kho = kho["ten"]
    tag_nhan_biet = kho["tag_nhan_biet"]
    items_sorted = sorted(items, key=lambda x: x['da_ban'], reverse=True)
    now_str = datetime.now().strftime("%H:%M - %d/%m/%Y")

    if is_urgent:
        # GIAO DIỆN CẢNH BÁO KHẨN CẤP (TỒN <= 100) - MÀU ĐỎ NỔI BẬT KHÁC BIỆT
        formatted_items = []
        for idx, item in enumerate(items_sorted, 1):
            formatted_items.append(
                f"🔥 **`{item['ma']}`** — {item['ten']}\n"
                f"└ 🚨 Tồn kho khẩn cấp: <font color='red'>**{item['ton']}**</font> sp | Đã bán: **{item['da_ban']}** sp"
            )
        
        content_text = "\n\n".join(formatted_items)
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🚨 [KHẨN CẤP SẮP CHÁY HÀNG] {ten_kho}"
                    },
                    "template": "red"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"📍 **Địa điểm:** {tag_nhan_biet}\n"
                                       f"⏰ **Thời gian phát hiện:** {now_str}\n"
                                       f"⚠️ Phát hiện **{len(items)}** mã MỚI bị tụt dưới **{NGUONG_KHAN_CAP} sp**!\n"
                                       f"⚡ **Đề nghị Xưởng ưu tiên dồn máy sản xuất ngay.**"
                        }
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"### 💥 DANH SÁCH MÃ CẦN DỒN MÁY GẤP\n\n{content_text}"
                        }
                    },
                    {"tag": "hr"},
                    {
                        "tag": "note",
                        "elements": [{"tag": "plain_text", "content": f"🤖 Cảnh báo khẩn cấp tự động - {ten_kho}"}]
                    }
                ]
            }
        }
    else:
        # GIAO DIỆN BÁO CÁO CHỐT CA (HN MÀU TÍM, HCM MÀU XANH DƯƠNG)
        formatted_items = []
        for idx, item in enumerate(items_sorted, 1):
            hot_badge = " 🔥 (TOP BÁN CHẠY)" if idx <= 5 else ""
            formatted_items.append(
                f"**{idx}. `{item['ma']}`**{hot_badge}\n"
                f"├ 📦 Tồn kho: <font color='red'>**{item['ton']}**</font> sp\n"
                f"└ ⚡ Đã bán gần đây: **{item['da_ban']}** sp"
            )
        
        content_text = "\n\n".join(formatted_items)
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"📋 BÁO CÁO CHỐT CA: {ten_kho}"
                    },
                    "template": kho["mau_sac_chot_ca"]
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"📍 **Địa điểm:** {tag_nhan_biet}\n"
                                       f"⏰ **Thời gian chốt ca:** {now_str}\n"
                                       f"⚠️ Tổng số mã cần sản xuất: **{len(items)}** mã đang bán (Tồn **≤ {NGUONG_BAO_CAO}**)\n"
                                       f"💡 *Đã tự động sắp xếp mã BÁN CHẠY NHẤT lên đầu.*"
                        }
                    },
                    {"tag": "hr"},
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"### 🏭 DANH SÁCH MÃ ƯU TIÊN SẢN XUẤT\n\n{content_text}"
                        }
                    },
                    {"tag": "hr"},
                    {
                        "tag": "note",
                        "elements": [{"tag": "plain_text", "content": f"🤖 Báo cáo định kỳ chốt ca - {ten_kho}"}]
                    }
                ]
            }
        }

    res = requests.post(LARK_WEBHOOK, json=payload)
    print(f"[{ten_kho}] Gửi tin nhắn Lark thành công:", res.text)

if __name__ == "__main__":
    now = datetime.now()
    hour = now.hour
    minute = now.minute

    # KIỂM TRA 2 KHUNG GIỜ CHỐT CA: 08:15 SÁNG VÀ 12:00 TRƯA
    is_ca_sang = (hour == 8 and 10 <= minute <= 25)
    is_ca_chieu = (hour == 12 and 0 <= minute <= 15)
    is_scheduled_report = is_ca_sang or is_ca_chieu

    alerted_state = load_alerted_items()

    for kho in DANH_SACH_KHO:
        if not kho["cookie"]:
            continue
            
        ten_kho = kho["ten"]
        if ten_kho not in alerted_state:
            alerted_state[ten_kho] = []

        if is_scheduled_report:
            # 1. BÁO CÁO CHỐT CA TỔNG HỢP (08:15 & 12:00)
            print(f"--- BẮT ĐẦU BÁO CÁO CHỐT CA: {ten_kho} ---")
            data = fetch_data_by_kho(kho, NGUONG_BAO_CAO)
            send_lark_alert(kho, data, is_urgent=False)
            
            # Reset lại danh sách khẩn cấp để chuẩn bị theo dõi cho ca mới
            alerted_state[ten_kho] = [item['ma'] for item in data if item['ton'] <= NGUONG_KHAN_CAP]
        else:
            # 2. CẢNH BÁO KHẨN CẤP TỰ ĐỘNG NẾU CÓ MÃ MỚI SỤT <= 100
            print(f"--- QUÉT CẢNH BÁO KHẨN CẤP: {ten_kho} ---")
            data_urgent = fetch_data_by_kho(kho, NGUONG_KHAN_CAP)
            
            # Lọc danh sách mã MỚI phát sinh (chưa có trong bộ nhớ đã báo gần nhất)
            new_urgent_items = [
                item for item in data_urgent 
                if item['ma'] not in alerted_state[ten_kho]
            ]

            if new_urgent_items:
                print(f"[{ten_kho}] Phát hiện {len(new_urgent_items)} mã MỚI sắp cháy hàng (<= {NGUONG_KHAN_CAP})!")
                send_lark_alert(kho, new_urgent_items, is_urgent=True)
                
                # Lưu mã vừa báo vào bộ nhớ để KHÔNG BẮN LẠI ở các lần quét sau
                for item in new_urgent_items:
                    alerted_state[ten_kho].append(item['ma'])
            else:
                print(f"[{ten_kho}] Không có mã mới nào bị tụt khẩn cấp.")

    save_alerted_items(alerted_state)
