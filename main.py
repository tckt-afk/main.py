import os
import requests
from bs4 import BeautifulSoup

# --- CẤU HÌNH ---
URL_KHO = "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?whid=4&includeTemp=1"

# Tự động lấy từ Secrets hoặc dùng giá trị mặc định bạn đã cung cấp
LARK_WEBHOOK = os.getenv("LARK_WEBHOOK", "https://open.larksuite.com/open-apis/bot/v2/hook/0905e11c-b533-4963-8f76-6d71c18b1f6c")
COOKIE_STR = os.getenv("KHO_COOKIE", "CfDJ8NPrk8sz-19ClSlHejQLM82bL-w0xnHjrhD0do37dz3EUqxjp2ksv8GKkbADPuWJSXkB5ZzmRaW4tQXY8dtJk1zhDfA-aU-jIygB-qDK0WbVBf8S1sIrwPmo6Idtn3kMRHjj-K0oph1JC0yGk4a-TKc")

NGUONG_CANH_BAO = 300

def fetch_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://admin-0911801688-268.nhuahvt.com/",
        "Cookie": COOKIE_STR
    }

    canh_bao_list = []
    
    # Quét qua 5 trang kho
    for page in range(1, 6):
        url = f"{URL_KHO}&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"Trang {page} bị lỗi response: {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Đọc các dòng dữ liệu trong bảng
            rows = soup.select("table tbody tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    ma_sp = cols[0].text.strip()
                    ten_sp = cols[1].text.strip()
                    
                    # Xử lý chuỗi số tồn kho (loại bỏ phẩy/chấm)
                    raw_ton = cols[2].text.strip().replace(",", "").replace(".", "")
                    try:
                        ton_kho = int(raw_ton)
                    except ValueError:
                        continue

                    # Kiểm tra ngưỡng < 300
                    if ton_kho < NGUONG_CANH_BAO:
                        canh_bao_list.append({
                            "ma": ma_sp,
                            "ten": ten_sp,
                            "ton": ton_kho
                        })
        except Exception as e:
            print(f"Lỗi truy cập trang {page}: {e}")

    return canh_bao_list

def send_lark_alert(items):
    if not items:
        print("Tất cả sản phẩm đều đủ hàng (Tồn >= 300). Báo cáo hoàn tất!")
        return

    # Chuẩn bị danh sách gửi tin nhắn
    content_lines = []
    for item in items:
        content_lines.append(f"• **[{item['ma']}]** {item['ten']} — Tồn: <font color='red'>**{item['ton']}**</font>")
    
    content_text = "\n".join(content_lines)

    # Khung tin nhắn Interactive Card trên Lark
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "⚠️ BÁO CÁO KHO: SẢN PHẨM TỒN < 300"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"Phát hiện **{len(items)}** sản phẩm gần hết hàng:\n\n{content_text}"
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
                            "content": "Hệ thống quét tự động Nhuạ HVT"
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
