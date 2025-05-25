from music_api import qr_login
print("开始网易云音乐二维码登录流程...")
cookies = qr_login()
    
if cookies:
    #print("\nCookie信息：")
    #print(json.dumps(cookies, indent=2, ensure_ascii=False))
        
    # 可以保存cookie到文件中供后续使用
    with open('cookie.txt', 'w') as f:
        f.write(cookies)
else:
    print("登录失败，请重试。")