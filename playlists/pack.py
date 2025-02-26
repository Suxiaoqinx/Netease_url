import os
import json
import shutil
import requests
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, USLT
from tqdm import tqdm

def update_mp3_metadata(mp3_path, data, folder_path):
    audio = EasyID3(mp3_path)
    audio['title'] = data['name']
    audio['artist'] = data['artist']
    audio['album'] = data['album']
    audio['albumartist'] = data['artist']
    audio.save()

    audio = ID3(mp3_path)
    audio.update_to_v23()  # 把可能存在的旧版本升级为2.3版本
    # 添加封面
    cover_path = os.path.join(folder_path, 'cover.jpg')
    if os.path.exists(cover_path):
        with open(cover_path, 'rb') as f:
            cover_data = f.read()
        audio['APIC'] = APIC(
            encoding=0,  # 3 is for utf-8
            mime='image/jpeg',  # image/jpeg or image/png
            type=3,  # 3 is for the cover(front) image
            desc='Cover',
            data=cover_data
        )
    # 添加歌词
    if 'lrc' in data:
        audio['USLT'] = USLT(
            encoding=3,
            lang='eng',
            desc='Lyrics',
            text=data['lrc']
        )
    audio.save()

def process_folder(folder_path, new_folder_path):
    data_path = os.path.join(folder_path, 'data.json')
    mp3_path = os.path.join(folder_path, 'song.mp3')

    if os.path.exists(data_path) and os.path.exists(mp3_path):
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            new_mp3_path = os.path.join(new_folder_path, f"{data['name']}-{data['artist']}.mp3")
            shutil.copy(mp3_path, new_mp3_path)
            update_mp3_metadata(new_mp3_path, data, folder_path)

def main():
    with open("settings.json", "r", encoding="utf-8") as f:
        settings = json.load(f)
        success_folder = settings.get("./success", "./success")
        pack_folder = settings.get("packPath", "./pack")
    if not os.path.exists(pack_folder):
        os.makedirs(pack_folder)

    dirs = [d for d in os.listdir(success_folder) if os.path.isdir(os.path.join(success_folder, d))]
    for dir_name in tqdm(dirs, desc="Processing folders"):
        folder_path = os.path.join(success_folder, dir_name)
        process_folder(folder_path, pack_folder)

if __name__ == "__main__":
    main()