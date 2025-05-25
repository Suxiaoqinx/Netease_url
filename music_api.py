import json
import urllib.parse
from random import randrange
import requests
from hashlib import md5
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def HexDigest(data):
    return "".join([hex(d)[2:].zfill(2) for d in data])

def HashDigest(text):
    HASH = md5(text.encode("utf-8"))
    return HASH.digest()

def HashHexDigest(text):
    return HexDigest(HashDigest(text))

def post(url, params, cookie):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154',
        'Referer': '',
    }
    cookies = {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!"
    }
    cookies.update(cookie)
    response = requests.post(url, headers=headers, cookies=cookies, data={"params": params})
    return response.text

def posts(url, params, cookie):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154',
        'Referer': '',
    }
    cookies = {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!"
    }
    cookies.update(cookie)
    response = requests.post(url, headers=headers, cookies=cookies, data={"params": params})
    return response  # 修改为返回完整的 response 对象

def url_v1(id, level, cookies):
    url = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
    AES_KEY = b"e82ckenh8dichen8"
    config = {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!",
        "requestId": str(randrange(20000000, 30000000))
    }

    payload = {
        'ids': [id],
        'level': level,
        'encodeType': 'flac',
        'header': json.dumps(config),
    }

    if level == 'sky':
        payload['immerseType'] = 'c51'
    
    url2 = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
    digest = HashHexDigest(f"nobody{url2}use{json.dumps(payload)}md5forencrypt")
    params = f"{url2}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
    padder = padding.PKCS7(algorithms.AES(AES_KEY).block_size).padder()
    padded_data = padder.update(params.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB())
    encryptor = cipher.encryptor()
    enc = encryptor.update(padded_data) + encryptor.finalize()
    params = HexDigest(enc)
    response = post(url, params, cookies)
    return json.loads(response)

def name_v1(id):
    urls = "https://interface3.music.163.com/api/v3/song/detail"
    data = {'c': json.dumps([{"id":id,"v":0}])}
    response = requests.post(url=urls, data=data)
    return response.json()

def lyric_v1(id, cookies):
    url = "https://interface3.music.163.com/api/song/lyric"
    data = {'id': id, 'cp': 'false', 'tv': '0', 'lv': '0', 'rv': '0', 'kv': '0', 'yv': '0', 'ytv': '0', 'yrv': '0'}
    response = requests.post(url=url, data=data, cookies=cookies)
    return response.json()

def search_music(keywords, cookies, limit=10):
    """
    网易云音乐搜索接口，返回歌曲信息列表
    :param keywords: 搜索关键词
    :param cookies: 登录 cookies
    :param limit: 返回数量
    :return: 歌曲信息列表
    """
    url = 'https://music.163.com/api/cloudsearch/pc'
    data = {'s': keywords, 'type': 1, 'limit': limit}
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://music.163.com/'
    }
    response = requests.post(url, data=data, headers=headers, cookies=cookies)
    result = response.json()
    songs = []
    for item in result.get('result', {}).get('songs', []):
        song_info = {
            'id': item['id'],
            'name': item['name'],
            'artists': '/'.join(artist['name'] for artist in item['ar']),
            'album': item['al']['name'],
            'picUrl': item['al']['picUrl']
        }
        songs.append(song_info)
    return songs

def playlist_detail(playlist_id, cookies):
    """
    获取网易云歌单详情及全部歌曲列表
    :param playlist_id: 歌单ID
    :param cookies: 登录 cookies
    :return: 歌单基本信息和全部歌曲列表
    """
    url = f'https://music.163.com/api/v6/playlist/detail'
    data = {'id': playlist_id}
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://music.163.com/'
    }
    response = requests.post(url, data=data, headers=headers, cookies=cookies)
    result = response.json()
    playlist = result.get('playlist', {})
    info = {
        'id': playlist.get('id'),
        'name': playlist.get('name'),
        'coverImgUrl': playlist.get('coverImgUrl'),
        'creator': playlist.get('creator', {}).get('nickname', ''),
        'trackCount': playlist.get('trackCount'),
        'description': playlist.get('description', ''),
        'tracks': []
    }
    # 获取所有trackIds
    track_ids = [str(t['id']) for t in playlist.get('trackIds', [])]
    # 分批获取详细信息（每批最多100首）
    for i in range(0, len(track_ids), 100):
        batch_ids = track_ids[i:i+100]
        song_detail_url = 'https://interface3.music.163.com/api/v3/song/detail'
        song_data = {'c': json.dumps([{ 'id': int(sid), 'v': 0 } for sid in batch_ids])}
        song_resp = requests.post(url=song_detail_url, data=song_data, headers=headers, cookies=cookies)
        song_result = song_resp.json()
        for song in song_result.get('songs', []):
            info['tracks'].append({
                'id': song['id'],
                'name': song['name'],
                'artists': '/'.join(artist['name'] for artist in song['ar']),
                'album': song['al']['name'],
                'picUrl': song['al']['picUrl']
            })
    return info

def album_detail(album_id, cookies):
    """
    获取网易云专辑详情及全部歌曲列表
    :param album_id: 专辑ID
    :param cookies: 登录 cookies
    :return: 专辑基本信息和全部歌曲列表
    """
    url = f'https://music.163.com/api/v1/album/{album_id}'
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://music.163.com/'
    }
    response = requests.get(url, headers=headers, cookies=cookies)
    result = response.json()
    album = result.get('album', {})
    info = {
        'id': album.get('id'),
        'name': album.get('name'),
        'coverImgUrl': get_pic_url(album.get('pic')),
        #'coverImgEncryptId': netease_encryptId(str(album.get('pic'))),
        'artist': album.get('artist', {}).get('name', ''),
        'publishTime': album.get('publishTime'),
        'description': album.get('description', ''),
        'songs': []
    }
    for song in result.get('songs', []):
        info['songs'].append({
            'id': song['id'],
            'name': song['name'],
            'artists': '/'.join(artist['name'] for artist in song['ar']),
            'album': song['al']['name'],
            'picUrl': get_pic_url(song['al'].get('pic'))
        })
    return info

def netease_encryptId(id_str):
    """
    网易云加密图片ID算法（PHP移植版）
    :param id_str: 歌曲/专辑/图片ID（字符串）
    :return: 加密后的字符串
    """
    import base64
    magic = list('3go8&$8*3*3h0k(2)2')
    song_id = list(id_str)
    for i in range(len(song_id)):
        song_id[i] = chr(ord(song_id[i]) ^ ord(magic[i % len(magic)]))
    m = ''.join(song_id)
    import hashlib
    md5_bytes = hashlib.md5(m.encode('utf-8')).digest()
    result = base64.b64encode(md5_bytes).decode('utf-8')
    result = result.replace('/', '_').replace('+', '-')
    return result

def get_pic_url(pic_id, size=300):
    """
    获取网易云加密歌曲/专辑封面直链
    :param pic_id: 封面ID（数字或字符串）
    :param size: 图片尺寸，默认300
    :return: url
    """
    enc_id = netease_encryptId(str(pic_id))
    url = f'https://p3.music.126.net/{enc_id}/{pic_id}.jpg?param={size}y{size}'
    return url

def generate_qr_key():
    """
    生成二维码的key
    :return: key和unikey
    """
    url = 'https://interface3.music.163.com/eapi/login/qrcode/unikey'
    AES_KEY = b"e82ckenh8dichen8"
    config = {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!",
        "requestId": str(randrange(20000000, 30000000))
    }

    payload = {
        'type': 1,
        'header': json.dumps(config)
    }
    
    url2 = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
    digest = HashHexDigest(f"nobody{url2}use{json.dumps(payload)}md5forencrypt")
    params = f"{url2}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
    padder = padding.PKCS7(algorithms.AES(AES_KEY).block_size).padder()
    padded_data = padder.update(params.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB())
    encryptor = cipher.encryptor()
    enc = encryptor.update(padded_data) + encryptor.finalize()
    params = HexDigest(enc)
    
    response = posts(url, params, {})
    result = json.loads(response.text)  # 保持不变，因为 post 函数已修复
    if result['code'] == 200:
        return result['unikey']
    return None

def create_qr_login():
    """
    创建登录二维码并在控制台显示
    :return: unikey用于检查登录状态
    """
    import qrcode
    from qrcode.main import QRCode
    import os

    unikey = generate_qr_key()
    if not unikey:
        print("生成二维码key失败")
        return None

    # 创建二维码
    qr = QRCode()
    qr.add_data(f'https://music.163.com/login?codekey={unikey}')
    qr.make(fit=True)
    
    # 在控制台显示二维码
    qr.print_ascii(tty=True)
    print("\n请使用网易云音乐APP扫描上方二维码登录")
    return unikey

def check_qr_login(unikey):
    """
    检查二维码登录状态
    :param unikey: 二维码key
    :return: (登录状态, cookie字典)
    """
    url = 'https://interface3.music.163.com/eapi/login/qrcode/client/login'
    AES_KEY = b"e82ckenh8dichen8"
    config = {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!",
        "requestId": str(randrange(20000000, 30000000))
    }

    payload = {
        'key': unikey,
        'type': 1,
        'header': json.dumps(config)
    }
    
    url2 = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
    digest = HashHexDigest(f"nobody{url2}use{json.dumps(payload)}md5forencrypt")
    params = f"{url2}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
    padder = padding.PKCS7(algorithms.AES(AES_KEY).block_size).padder()
    padded_data = padder.update(params.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB())
    encryptor = cipher.encryptor()
    enc = encryptor.update(padded_data) + encryptor.finalize()
    params = HexDigest(enc)
    
    response = posts(url, params, {})
    result = json.loads(response.text)
    
    cookie_dict = {}
    #print("服务器返回结果：", result)
    #print("Set-Cookie头:", response.headers.get('Set-Cookie', ''))
    
    if result['code'] == 803:
        # 直接从响应的headers获取Set-Cookie
        all_cookies = response.headers.get('Set-Cookie', '').split(', ')
        for cookie_str in all_cookies:
            if 'MUSIC_U=' in cookie_str:
                cookie_dict['MUSIC_U'] = cookie_str.split('MUSIC_U=')[1].split(';')[0]
            
    return result['code'], cookie_dict

def qr_login():
    """
    完整的二维码登录流程
    :return: 成功返回cookie字典，失败返回None
    """
    unikey = create_qr_login()
    if not unikey:
        return None
        
    import time
    while True:
        code, cookies = check_qr_login(unikey)
        if code == 803:
            print("\n登录成功！")
            return 'MUSIC_U=' + cookies['MUSIC_U'] + ';os=pc;appver=8.9.70;'  # 修复字符串拼接
        elif code == 801:
            print("\r等待扫码...", end='')
        elif code == 802:
            print("\r扫码成功，请在手机上确认登录...", end='')
        else:
            print(f"\n登录失败，错误码：{code}")
            return None
        time.sleep(2)
