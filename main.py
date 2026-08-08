import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- CẤU HÌNH DANH SÁCH KHO ---
DANH_SACH_KHO = [
    {
        "ten": "KHO HÀ NỘI",
        "url": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?whid=4&includeTemp=1",
        "cookie": os.getenv("KHO_COOKIE", "")
    },
    {
        "ten": "KHO HỒ CHÍ MINH",
        "url": "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?includeTemp=1&whid=6",
        "cookie": os.getenv("COOKIE_HCM", "")
    }
]

LARK_WEBHOOK = os.getenv("LARK_WEBHOOK", "")
NGUONG_CANH_BAO = 300  # Cảnh báo khi Tồn <= 300
MAX_PAGES = 30 

def fetch_data_by_kho(kho):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://admin-0911801688-268.nhuahvt.com/",
        "Cookie": kho["cookie"]
    }

    canh_bao_list = []
    
    for page in range(1, MAX_PAGES + 1):
        url = f"{kho['url']}&pageindex={page}&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"[{kho['ten']}] Lỗi HTTP {response.status_code} ở trang {page}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select("table tbody tr")
            
            if not rows:
                break
                
            has_valid_item = False
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 5:
                    ten_sp = cols[1].text.strip()   # Cột 2
                    ma_sp = cols[2].text.strip()    # Cột 3
                    raw_ton = cols[4].text.strip().replace(",", "").replace(".", "") # Cột 5
                    
                    try:
                        ton_kho = int(raw_ton)
                        has_valid_item = True

                        if ton_kho <= NGUONG_CANH_BAO:
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
            print(f"[{kho['ten']}] Lỗi trang {page}: {e}")
            break

    return canh_bao_list

def send_lark_alert(ten_kho, items):
    if not items:
        print(f"[{ten_kho}] Tất cả sản phẩm đều đủ hàng (Tồn > {NGUONG_CANH_BAO}). Báo cáo hoàn tất!")
        return

    # Sắp xếp danh sách sản phẩm theo Tồn kho giảm dần
    items_sorted = sorted(items, key=lambda x: x['ton'])

    # Format danh sách thành bảng/dòng đẹp mắt hơn
    formatted_items = []
    for idx, item in enumerate(items_sorted, 1):
        formatted_items.append(
            f"**{idx}. `{item['ma']}`** — {item['ten']}\n"
            f"└ 📦 Tồn kho hiện tại: <font color='red'>**{item['ton']}**</font> sản phẩm"
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
                                   f"⏰ **Thời gian quét:** {now_str}\n"
                                   f"⚠️ **Trạng thái:** Phát hiện **{len(items)}** sản phẩm chạm mức báo động (Tồn kho **≤ {NGUONG_CANH_BAO}**)"
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
                            "content": "🤖 Hệ thống kiểm soát kho tự động Nhựa HVT • Cập nhật 15 phút/lần"
                        }
                    ]
                }
            ]
        }
    }

    res = requests.post(LARK_WEBHOOK, json=payload)
    print(f"[{ten_kho}] Kết quả gửi Lark:", res.text)

if __name__ == "__main__":
    for kho in DANH_SACH_KHO:
        if kho["cookie"]:
            print(f"--- BẮT ĐẦU QUÉT {kho['ten']} ---")
            data = fetch_data_by_kho(kho)
            send_lark_alert(kho['ten'], data)
