from music_api import qr_login
print("开始网易云音乐二维码登录流程...")
cookies = qr_login()
    
if cookies:
    print("\nCookie信息：")
    print(cookies)
else:
    print("登录失败，请重试。")
