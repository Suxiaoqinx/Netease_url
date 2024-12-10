from flask import Flask, request, jsonify ,redirect ,Response
import json
import os
import urllib.parse
from hashlib import md5
from random import randrange
import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

def HexDigest(data):
    return "".join([hex(d)[2:].zfill(2) for d in data])

def HashDigest(text):
    HASH = md5(text.encode("utf-8"))
    return HASH.digest()

def HashHexDigest(text):
    return HexDigest(HashDigest(text))

def parse_cookie(text: str):
    cookie_ = [item.strip().split('=', 1) for item in text.strip().split(';') if item]
    cookie_ = {k.strip(): v.strip() for k, v in cookie_}
    return cookie_

def read_cookie():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cookie_file = os.path.join(script_dir, 'cookie.txt')
    with open(cookie_file, 'r') as f:
        cookie_contents = f.read()
    return cookie_contents

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

# 输入id选项
def ids(ids):
    if '163cn.tv' in ids:
        response = requests.get(ids, allow_redirects=False)
        ids = response.headers.get('Location')
    if 'music.163.com' in ids:
        index = ids.find('id=') + 3
        ids = ids[index:].split('&')[0]
    return ids

#转换文件大小
def size(value):
     units = ["B", "KB", "MB", "GB", "TB", "PB"]
     size = 1024.0
     for i in range(len(units)):
         if (value / size) < 1:
             return "%.2f%s" % (value, units[i])
         value = value / size
     return value

#转换音质
def music_level1(value):
    if value == 'standard':
        return "标准音质"
    elif value == 'exhigh':
        return "极高音质"
    elif value == 'lossless':
        return "无损音质"
    elif value == 'hires':
        return "Hires音质"
    elif value == 'sky':
        return "沉浸环绕声"
    elif value == 'jyeffect':
        return "高清环绕声"
    elif value == 'jymaster':
        return "超清母带"
    else:
        return "未知音质"

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
    #歌曲信息接口
    urls = "https://interface3.music.163.com/api/v3/song/detail"
    data = {'c': json.dumps([{"id":id,"v":0}])}
    response = requests.post(url=urls, data=data)
    return response.json()

def lyric_v1(id,cookies):
    #歌词接口
    url = "https://interface3.music.163.com/api/song/lyric"
    data = {'id' : id,'cp' : 'false','tv' : '0','lv' : '0','rv' : '0','kv' : '0','yv' : '0','ytv' : '0','yrv' : '0'}
    response = requests.post(url=url, data=data, cookies=cookies)
    return response.json()

app = Flask(__name__)

@app.route('/')
def hello_world():
    return '你好，世界！'

@app.route('/Song_V1', methods=['GET', 'POST'])
def Song_v1():
    if request.method == 'GET':
        song_ids = request.args.get('ids')
        url = request.args.get('url')
        level = request.args.get('level')
        type_ = request.args.get('type')
    else:
        song_ids = request.form.get('ids')
        url = request.form.get('url')
        level = request.form.get('level')
        type_ = request.form.get('type')

    if not song_ids and not url:
        return jsonify({'error': '必须提供 ids 或 url 参数'}), 400
    if level is None:
        return jsonify({'error': 'level参数为空'}), 400
    if type_ is None:
        return jsonify({'error': 'type参数为空'}), 400

    jsondata = song_ids if song_ids else url
    cookies = parse_cookie(read_cookie())
    urlv1 = url_v1(ids(jsondata),level,cookies)
    namev1 = name_v1(urlv1['data'][0]['id'])
    lyricv1 = lyric_v1(urlv1['data'][0]['id'],cookies)
    if urlv1['data'][0]['url'] is not None:
        if namev1['songs']:
           song_url = urlv1['data'][0]['url']
           song_name = namev1['songs'][0]['name']
           song_picUrl = namev1['songs'][0]['al']['picUrl']
           song_alname = namev1['songs'][0]['al']['name']
           artist_names = []
           for song in namev1['songs']:
               ar_list = song['ar']
               if len(ar_list) > 0:
                   artist_names.append('/'.join(ar['name'] for ar in ar_list))
               song_arname = ', '.join(artist_names)
    else:
       data = jsonify({"status": 400,'msg': '信息获取不完整！'}), 400
    if type_ == 'text':
       data = '歌曲名称：' + song_name + '<br>歌曲图片：' + song_picUrl  + '<br>歌手：' + song_arname + '<br>歌曲专辑：' + song_alname + '<br>歌曲音质：' + music_level1(urlv1['data'][0]['level']) + '<br>歌曲大小：' + size(urlv1['data'][0]['size']) + '<br>音乐地址：' + song_url
    elif  type_ == 'down':
       data = redirect(song_url)
    elif  type_ == 'json':
       data = {
           "status": 200,
           "name": song_name,
           "pic": song_picUrl,
           "ar_name": song_arname,
           "al_name": song_alname,
           "level":music_level1(urlv1['data'][0]['level']),
           "size": size(urlv1['data'][0]['size']),
           "url": song_url.replace("http://", "https://", 1),
           "lyric": lyricv1.get('lrc', {}).get('lyric', '无歌词'),
           "tlyric": lyricv1.get('tlyric', {}).get('lyric', '无翻译歌词')
        }
       data = Response(json.dumps(data), content_type='application/json')
    else:
        data = jsonify({"status": 400,'msg': '解析失败！请检查参数是否完整！'}), 400
    return data

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
