import os
import requests
from bs4 import BeautifulSoup

# --- CẤU HÌNH ---
TEN_KHO = "KHO HÀ NỘI"
URL_KHO = "https://admin-0911801688-268.nhuahvt.com/Warehouse/Items?whid=4&includeTemp=1"

LARK_WEBHOOK = os.getenv("LARK_WEBHOOK", "https://open.larksuite.com/open-apis/bot/v2/hook/0905e11c-b533-4963-8f76-6d71c18b1f6c")
COOKIE_STR = os.getenv("KHO_COOKIE", "ab.storage.deviceId.f9c2b69f-2136-44e0-a55a-dff72d99aa19=g%3AzSPXf3JQpXfAMri0MPiIb6YQbnb2%7Ce%3Aundefined%7Cc%3A1753666412621%7Cl%3A1753666412621; ab.storage.sessionId.f9c2b69f-2136-44e0-a55a-dff72d99aa19=g%3A2d80f29d-4282-bbc8-6cc8-9e0795416b76%7Ce%3A1753668212652%7Cc%3A1753666412653%7Cl%3A1753666412653; .AspNetCore.Antiforgery.-_GDC7Lnplw=CfDJ8NPrk8sz-19ClSlHejQLM82bL-w0xnHjrhD0do37dz3EUqxjp2ksv8GKkbADPuWJSXkB5ZzmRaW4tQXY8dtJk1zhDfA-aU-jIygB-qDK0WbVBf8S1sIrwPmo6Idtn3kMRHjj-K0oph1JC0yGk4a-TKc; HVTNhuaAdmin=CfDJ8NPrk8sz-19ClSlHejQLM81CS8Wj_vfsKR9FgwG2VaOsRcq83F16obboAamJ93I_GBU9VThuml0IqwqOZI-mXTpnPIg1imsQXmuMSWVAjL4Cma0vm6odvlQrsCZcTMvxgfUY9e-VChjHfng80jpwkExRZ8W3187WFDQBj7dnfWWgaSaq4W4ckYnPuYroz53EFx-IyLUmvcRqYuXG7aNj0ES9-_AUshnu9MaF7CINqBltCPU6zdaT4d-4i1YoXjeu5ASQzzCmWndqQc9GEZjKSByVVt1CnoPZODORaIVz5KpDn03USPAfsyoMlGC-kxnAy5YZO-RYpibNQa1jZuqNElu1r3-HkuQYMIflcR6jgXLeMtKdN43d0m0CsCMdaV2Qk8vH5y5Y5t8JVtOve7Cuvfaftf7pjOTT5MreX3kM5vAoMu4ySSps9oLxECC72pBBRZNR0Ch-t0r1WeWVteqLDTQUkggsDNBdiEtJxJBjJQUps-bZA5DYAmqqg2WTbNvEhi5Hpuzni5A5CoRnJtcH5bYEorUyPupK-cuF79DX9KKiw7UVsQ4jYRPVCJbsrvoMiVmLa_HaGLZzLHx6l8a_zqqVmuef273ROsQ97kqcfcQujRRdz5OgGbKS21y8Wtlmu_gwrKSaUUQA1twu1wqLZ22CAeMzzSiuDKQGhFI6sdNbu9Neac_2QZU45nSxB6D26k_uM8Uxsr4d_YyFx646Px4")

NGUONG_CANH_BAO = 1300

def fetch_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://admin-0911801688-268.nhuahvt.com/",
        "Cookie": COOKIE_STR
    }

    canh_bao_list = []
    page = 1
    
    while True:
        url = f"{URL_KHO}&page={page}"
        try:
            print(f"[{TEN_KHO}] Đang quét trang {page}...")
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                print(f"Dừng quét: Trang {page} trả về mã {response.status_code}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select("table tbody tr")
            
            if not rows:
                print(f"[{TEN_KHO}] Đã quét xong toàn bộ kho! Trang cuối cùng là trang {page - 1}.")
                break
                
            has_valid_item = False
            for row in rows:
                cols = row.find_all("td")
                # Kiểm tra đủ ít nhất 5 cột
                if len(cols) >= 5:
                    ten_sp = cols[1].text.strip()   # Cột 2: Sản phẩm
                    ma_sp = cols[2].text.strip()    # Cột 3: Mã SP
                    raw_ton = cols[4].text.strip().replace(",", "").replace(".", "") # Cột 5: Số lượng
                    
                    try:
                        ton_kho = int(raw_ton)
                        has_valid_item = True
                    except ValueError:
                        continue

                    # Kiểm tra điều kiện tồn kho nhỏ hơn 1300
                    if ton_kho < NGUONG_CANH_BAO:
                        canh_bao_list.append({
                            "ma": ma_sp,
                            "ten": ten_sp,
                            "ton": ton_kho
                        })
            
            if not has_valid_item:
                print(f"[{TEN_KHO}] Trang {page} không có dữ liệu hợp lệ. Dừng quét.")
                break

            page += 1

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
                    "content": f"⚠️ BÁO CÁO {TEN_KHO}: TỒN < {NGUONG_CANH_BAO}"
                },
                "template": "red"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📍 **Địa điểm:** {TEN_KHO}\nPhát hiện **{len(items)}** sản phẩm gần hết hàng:\n\n{content_text}"
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
