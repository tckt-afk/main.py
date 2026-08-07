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

    canh_bao_list = []
    
    for page in range(1, MAX_PAGES + 1):
        url = f"{URL_KHO}&page={page}"
        try:
            print(f"[{TEN_KHO}] Đang quét trang {page}...")
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"Dừng quét: Trang {page} trả về mã {response.status_code}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select("table tbody tr")
            
            if not rows:
                print(f"[{TEN_KHO}] Đã quét hết dữ liệu tại trang {page - 1}.")
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
                    except ValueError:
                        continue

                    # CHECK TỪNG MÃ: Mã nào có tồn kho < 1300 thì lưu vào danh sách
                    if ton_kho < NGUONG_CANH_BAO:
                        canh_bao_list.append({
                            "ma": ma_sp,
                            "ten": ten_sp,
                            "ton": ton_kho
                        })
            
            if not has_valid_item:
                print(f"[{TEN_KHO}] Trang {page} không đọc được sản phẩm nào. Dừng quét.")
                break

        except Exception as e:
            print(f"Lỗi khi quét trang {page}: {e}")
            break

    return canh_bao_list

def send_lark_alert(items):
    if not items:
        print(f"[{TEN_KHO}] Tất cả sản phẩm đều đủ hàng (Tồn >= {NGUONG_CANH_BAO}). Báo cáo hoàn tất!")
        return

    content_lines = []
    for item in items:
        content_lines.append(f"• **[{item['ma']}]** {item['ten']} — Tồn: <font color='red'>**{item['ton']}**</font>")
    
    content_text = "\n".join(content_lines)

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"⚠️ BÁO CÁO {TEN_KHO}: SẢN PHẨM TỒN < {NGUONG_CANH_BAO}"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📍 **Địa điểm:** {TEN_KHO}\nPhát hiện **{len(items)}** sản phẩm gần hết hàng (< {NGUONG_CANH_BAO}):\n\n{content_text}"
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
    data = fetch_data()
    send_lark_alert(data)
