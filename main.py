import os
import requests
from bs4 import BeautifulSoup

# --- CẤU HÌNH ---
TEN_KHO = "KHO HÀ NỘI"
URL_KHO = "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?whid=4&includeTemp=1"

LARK_WEBHOOK = os.getenv("LARK_WEBHOOK", "https://open.larksuite.com/open-apis/bot/v2/hook/0905e11c-b533-4963-8f76-6d71c18b1f6c")
COOKIE_STR = os.getenv("KHO_COOKIE", "")

NGUONG_CANH_BAO = 1300
MAX_PAGES = 30  # Quét tối đa 30 trang

def fetch_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://admin-0911801688-268.nhuahvt.com/",
        "Cookie": COOKIE_STR
    }

    all_items = []
    
    for page in range(1, MAX_PAGES + 1):
        url = f"{URL_KHO}&page={page}"
        try:
            print(f"[{TEN_KHO}] Đang quét trang {page}...")
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code != 200:
                print(f"Dừng quét: Trang {page} trả về mã {response.status_code}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select("table tbody tr")
            
            if not rows:
                print(f"[{TEN_KHO}] Đã hết dữ liệu tại trang {page - 1}.")
                break
                
            has_valid_item = False
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 5:
                    ten_sp = cols[1].text.strip()   # Cột 2: Sản phẩm
                    ma_sp = cols[2].text.strip()    # Cột 3: Mã SP
                    raw_ton = cols[4].text.strip().replace(",", "").replace(".", "") # Cột 5: Số lượng
                    
                    try:
                        ton_kho = int(raw_ton)
                        has_valid_item = True
                        all_items.append({
                            "ma": ma_sp,
                            "ten": ten_sp,
                            "ton": ton_kho
                        })
                    except ValueError:
                        continue
            
            if not has_valid_item:
                print(f"[{TEN_KHO}] Trang {page} không chứa sản phẩm hợp lệ. Dừng quét.")
                break

        except Exception as e:
            print(f"Lỗi/Timeout khi quét trang {page}: {e}")
            break

    # KIỂM TRA LOGIC: Tất cả sản phẩm có đều < NGUONG_CANH_BAO hay không?
    if not all_items:
        print(f"[{TEN_KHO}] Không quét được sản phẩm nào.")
        return False, []

    # Tìm xem có sản phẩm nào còn >= NGUONG_CANH_BAO không
    san_pham_con_nhieu = [item for item in all_items if item['ton'] >= NGUONG_CANH_BAO]

    if len(san_pham_con_nhieu) == 0:
        # TẤT CẢ SẢN PHẨM ĐỀU < 1300
        print(f"[{TEN_KHO}] CẢNH BÁO: TOÀN BỘ kho đều có tồn kho dưới {NGUONG_CANH_BAO}!")
        return True, all_items
    else:
        print(f"[{TEN_KHO}] Vẫn còn {len(san_pham_con_nhieu)} sản phẩm có tồn >= {NGUONG_CANH_BAO}. Chưa phát cảnh báo.")
        return False, []

def send_lark_alert(should_alert, items):
    if not should_alert:
        return

    content_lines = []
    for item in items[:15]:  # Hiển thị tối đa 15 sản phẩm tiêu biểu
        content_lines.append(f"• **[{item['ma']}]** {item['ten']} — Tồn: <font color='red'>**{item['ton']}**</font>")
    
    if len(items) > 15:
        content_lines.append(f"\n...và **{len(items) - 15}** sản phẩm khác.")

    content_text = "\n".join(content_lines)

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🚨 BÁO CÁO TOÀN BỘ KHO HÀ NỘI < {NGUONG_CANH_BAO}"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📍 **Địa điểm:** {TEN_KHO}\n⚠️ **CẢNH BÁO NGUY CẤP:** Tất cả **{len(items)}** sản phẩm trong kho đều đã giảm xuống dưới {NGUONG_CANH_BAO}!\n\n{content_text}"
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
                            "content": f"Hệ thống quét tự động Nhựa HVT - {TEN_KHO}"
                        }
                    ]
                }
            ]
        }
    }

    res = requests.post(LARK_WEBHOOK, json=payload)
    print("Kết quả gửi tin nhắn sang Lark:", res.text)

if __name__ == "__main__":
    should_alert, data = fetch_data()
    send_lark_alert(should_alert, data)
