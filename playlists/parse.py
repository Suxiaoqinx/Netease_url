import os
import json
import time
import random
import requests
from pprint import pprint
from tqdm import tqdm

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "authorization": "Bearer def09b44baa4ea815d604f03a44993ce",
    "content-type": "application/json",
    "priority": "u=1, i",
    "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Google Chrome\";v=\"133\", \"Chromium\";v=\"133\"",
    "sec-ch-ua-full-version-list": "\"Not(A:Brand\";v=\"99.0.0.0\", \"Google Chrome\";v=\"133.0.6943.127\", \"Chromium\";v=\"133.0.6943.127\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": "\"\"",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-ch-ua-platform-version": "\"15.0.0\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "Referer": "https://api.toubiec.cn/wyapi.html",
    "Referrer-Policy": "strict-origin-when-cross-origin"
  }

url = "https://api.toubiec.cn/api/music_v1.php"


with open("settings.json", "r", encoding="utf-8") as f:
    settings = json.load(f)
    songs_to_download = settings["songs"]
    level = settings.get("level", "lossless")
    save_path = settings["savePath"]

def download_file(file_url, output_location_path):
    response = requests.get(file_url, stream=True)
    with open(output_location_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def main():
    completed_list = []
    error_list = []

    # 创建日志文件夹
    log_folder = "./log"
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    for i, song_url in enumerate(tqdm(songs_to_download, desc="Downloading songs Task", unit="song")):
        data = {
            "url": song_url,
            "level": level,
            "type": "song",
            "token":"e7519f587b3cf92583d7388639eae7ee"
        }

        try:
            result = requests.post(url, json=data, headers=headers)

            if result.status_code != 200:
                raise Exception(f"Status code: {result.status_code}")
            
            # 解析结果
            resultData = result.json()

            # 校验
            if resultData['status'] != 200:
                raise Exception(f"Status code: {resultData['status']}")

            # pprint(resultData)
            
            cover = resultData['song_info']['cover']
            name = resultData['song_info']['name']
            artist = resultData['song_info']['artist']
            alia = resultData['song_info']['alia']
            album = resultData['song_info']['album']
            song_original_url = resultData['url_info']['url']
            song_type = resultData['url_info']['type']
            lrc = resultData['lrc']['lyric']

            song_data = {
                "cover": cover,
                "name": name,
                "artist": artist,
                "alia": alia,
                "album": album,
                "song_original_url": song_original_url,
                "song_type": song_type,
                "lrc": lrc
            }

            output_folder_path = os.path.join(save_path, f"{name}-{artist}")
            if not os.path.exists(output_folder_path):
                os.makedirs(output_folder_path)
            
            mp3_path = os.path.join(output_folder_path, f"song.{song_type}")
            download_file(song_original_url, mp3_path)

            cover_path = os.path.join(output_folder_path, "cover.jpg")
            download_file(cover, cover_path)

            data_path = os.path.join(output_folder_path, "data.json")
            with open(data_path, "w", encoding="utf-8") as data_file:
                json.dump(song_data, data_file, ensure_ascii=False, indent=2)

            completed_list.append(song_url)
            with open("./log/completedList.json", "w", encoding="utf-8") as f:
                json.dump(completed_list, f, ensure_ascii=False, indent=2)

            # 随机等待 1 到 3 秒
            time.sleep(random.randint(1, 3))
            

        except Exception as error:
            error_list.append({"url": song_url, "error": str(error)})
            with open("./log/errorList.json", "w", encoding="utf-8") as f:
                json.dump(error_list, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()