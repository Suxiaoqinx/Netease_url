"""音乐下载器模块

提供网易云音乐下载功能，包括：
- 音乐信息获取
- 文件下载到本地
- 内存下载
- 音乐标签写入
- 异步下载支持
"""

import os
import re
import asyncio
import aiohttp
import aiofiles
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any, Union
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

import requests
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK, APIC
from mutagen.mp4 import MP4

from music_api import NeteaseAPI, APIException
from cookie_manager import CookieManager


class AudioFormat(Enum):
    """音频格式枚举"""
    MP3 = "mp3"
    FLAC = "flac"
    M4A = "m4a"
    UNKNOWN = "unknown"


class QualityLevel(Enum):
    """音质等级枚举"""
    STANDARD = "standard"  # 标准
    EXHIGH = "exhigh"      # 极高
    LOSSLESS = "lossless"  # 无损
    HIRES = "hires"        # Hi-Res
    SKY = "sky"            # 沉浸环绕声
    JYEFFECT = "jyeffect"  # 高清环绕声
    JYMASTER = "jymaster"  # 超清母带


@dataclass
class MusicInfo:
    """音乐信息数据类"""
    id: int
    name: str
    artists: str
    album: str
    pic_url: str
    duration: int
    track_number: int
    download_url: str
    file_type: str
    file_size: int
    quality: str
    lyric: str = ""
    tlyric: str = ""


@dataclass
class DownloadResult:
    """下载结果数据类"""
    success: bool
    file_path: Optional[str] = None
    file_size: int = 0
    error_message: str = ""
    music_info: Optional[MusicInfo] = None


class DownloadException(Exception):
    """下载异常类"""
    pass


class MusicDownloader:
    """音乐下载器主类"""
    
    def __init__(self, download_dir: str = "downloads", max_concurrent: int = 3, logger=None):
        """
        初始化音乐下载器
        
        Args:
            download_dir: 下载目录
            max_concurrent: 最大并发下载数
            logger: 日志记录器
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.max_concurrent = max_concurrent
        
        # 设置logger
        self.logger = logger or self._create_default_logger()
        
        # 初始化依赖
        self.cookie_manager = CookieManager()
        self.api = NeteaseAPI()
        
        # 支持的文件格式
        self.supported_formats = {
            'mp3': AudioFormat.MP3,
            'flac': AudioFormat.FLAC,
            'm4a': AudioFormat.M4A
        }
        
        self.logger.info(f"音乐下载器初始化完成 - 下载目录: {self.download_dir.absolute()}")
    
    def _create_default_logger(self):
        """创建默认的日志记录器"""
        logger = logging.getLogger('music_downloader')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符
        
        Args:
            filename: 原始文件名
            
        Returns:
            清理后的安全文件名
        """
        # 移除或替换非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        filename = re.sub(illegal_chars, '_', filename)
        
        # 移除前后空格和点
        filename = filename.strip(' .')
        
        # 限制长度
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename or "unknown"
    
    def _determine_file_extension(self, url: str, content_type: str = "") -> str:
        """根据URL和Content-Type确定文件扩展名
        
        Args:
            url: 下载URL
            content_type: HTTP Content-Type头
            
        Returns:
            文件扩展名
        """
        # 首先尝试从URL获取
        if '.flac' in url.lower():
            return '.flac'
        elif '.mp3' in url.lower():
            return '.mp3'
        elif '.m4a' in url.lower():
            return '.m4a'
        
        # 从Content-Type获取
        content_type = content_type.lower()
        if 'flac' in content_type:
            return '.flac'
        elif 'mpeg' in content_type or 'mp3' in content_type:
            return '.mp3'
        elif 'mp4' in content_type or 'm4a' in content_type:
            return '.m4a'
        
        return '.mp3'  # 默认
    
    def get_music_info(self, music_id: int, quality: str = "standard") -> MusicInfo:
        """获取音乐详细信息
        
        Args:
            music_id: 音乐ID
            quality: 音质等级
            
        Returns:
            音乐信息对象
            
        Raises:
            DownloadException: 获取信息失败时抛出
        """
        try:
            self.logger.info(f"开始获取音乐信息 - ID: {music_id}, 音质: {quality}")
            
            # 获取cookies
            cookies = self.cookie_manager.parse_cookies()
            self.logger.debug(f"使用Cookies: {bool(cookies)}")
            
            # 获取音乐URL信息
            self.logger.debug("正在获取音乐播放链接...")
            url_result = self.api.get_song_url(music_id, quality, cookies)
            if not url_result.get('data') or not url_result['data']:
                raise DownloadException(f"无法获取音乐ID {music_id} 的播放链接")
            
            song_data = url_result['data'][0]
            download_url = song_data.get('url', '')
            if not download_url:
                raise DownloadException(f"音乐ID {music_id} 无可用的下载链接")
            
            self.logger.debug(f"获取到下载链接: {bool(download_url)}, 文件类型: {song_data.get('type')}")
            
            # 获取音乐详情
            self.logger.debug("正在获取音乐详细信息...")
            detail_result = self.api.get_song_detail(music_id)
            if not detail_result.get('songs') or not detail_result['songs']:
                raise DownloadException(f"无法获取音乐ID {music_id} 的详细信息")
            
            song_detail = detail_result['songs'][0]
            self.logger.debug(f"获取到音乐详情: {song_detail.get('name', '未知')}")
            
            # 获取歌词
            self.logger.debug("正在获取歌词信息...")
            lyric_result = self.api.get_lyric(music_id, cookies)
            lyric = lyric_result.get('lrc', {}).get('lyric', '') if lyric_result else ''
            tlyric = lyric_result.get('tlyric', {}).get('lyric', '') if lyric_result else ''
            
            # 记录歌词获取情况
            lyric_status = f"原文歌词: {'有' if lyric else '无'}, 翻译歌词: {'有' if tlyric else '无'}"
            self.logger.debug(f"歌词获取结果 - {lyric_status}")
            
            if lyric:
                lyric_lines = lyric.split('\n')[:3]  # 只显示前3行作为示例
                self.logger.debug(f"原文歌词示例: {lyric_lines}")
            
            # 构建艺术家字符串
            artists = '/'.join(artist['name'] for artist in song_detail.get('ar', []))
            
            # 创建MusicInfo对象
            music_info = MusicInfo(
                id=music_id,
                name=song_detail.get('name', '未知歌曲'),
                artists=artists or '未知艺术家',
                album=song_detail.get('al', {}).get('name', '未知专辑'),
                pic_url=song_detail.get('al', {}).get('picUrl', ''),
                duration=song_detail.get('dt', 0) // 1000,  # 转换为秒
                track_number=song_detail.get('no', 0),
                download_url=download_url,
                file_type=song_data.get('type', 'mp3').lower(),
                file_size=song_data.get('size', 0),
                quality=quality,
                lyric=lyric,
                tlyric=tlyric
            )
            
            self.logger.info(f"音乐信息获取成功 - {music_info.artists} - {music_info.name}")
            return music_info
            
        except APIException as e:
            self.logger.error(f"API调用失败: {e}")
            raise DownloadException(f"API调用失败: {e}")
        except Exception as e:
            self.logger.error(f"获取音乐信息时发生错误: {e}")
            raise DownloadException(f"获取音乐信息时发生错误: {e}")
    
    def download_music_file(self, music_id: int, quality: str = "standard") -> DownloadResult:
        """下载音乐文件到本地"""
        try:
            self.logger.info(f"开始下载音乐 - ID: {music_id}, 音质: {quality}")
            
            # 获取音乐信息
            music_info = self.get_music_info(music_id, quality)
            
            # 生成文件名
            filename = f"{music_info.artists} - {music_info.name}"
            safe_filename = self._sanitize_filename(filename)
            
            # 确定文件扩展名
            file_ext = self._determine_file_extension(music_info.download_url)
            file_path = self.download_dir / f"{safe_filename}{file_ext}"
            
            # 确保下载目录存在且是正确路径
            self.download_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"目标文件路径: {file_path.absolute()}")
            
            # 检查文件是否已存在
            if file_path.exists():
                file_size = file_path.stat().st_size
                self.logger.info(f"文件已存在，跳过下载 - 大小: {self._format_file_size(file_size)}")
                return DownloadResult(
                    success=True,
                    file_path=str(file_path.absolute()),  # 使用绝对路径
                    file_size=file_size,
                    music_info=music_info
                )
            
            self.logger.info(f"开始下载文件 - 预计大小: {self._format_file_size(music_info.file_size)}")
            
            # 下载文件
            response = requests.get(music_info.download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # 写入文件
            downloaded_size = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if downloaded_size % (1024 * 1024) == 0:  # 每MB记录一次
                            self.logger.debug(f"下载进度: {self._format_file_size(downloaded_size)} / {self._format_file_size(music_info.file_size)}")
            
            final_size = file_path.stat().st_size
            self.logger.info(f"文件下载完成 - 实际大小: {self._format_file_size(final_size)}")
            
            # 写入音乐标签
            self.logger.info("开始写入音乐标签...")
            self._write_music_tags(file_path, music_info)
            self.logger.info("音乐标签写入完成")
            
            return DownloadResult(
                success=True,
                file_path=str(file_path.absolute()),  # 返回绝对路径
                file_size=final_size,
                music_info=music_info
            )
            
        except Exception as e:
            self.logger.error(f"下载过程中发生错误: {e}")
            return DownloadResult(
                success=False,
                error_message=f"下载过程中发生错误: {e}"
            )
    def _write_music_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入音乐标签信息，包括歌词
        
        Args:
            file_path: 音乐文件路径
            music_info: 音乐信息
        """
        try:
            file_ext = file_path.suffix.lower()
            self.logger.debug(f"开始写入标签 - 文件格式: {file_ext}")
            
            # 检查歌词数据
            has_lyrics = bool(music_info.lyric or music_info.tlyric)
            lyric_status = f"原文歌词: {'有' if music_info.lyric else '无'}, 翻译歌词: {'有' if music_info.tlyric else '无'}"
            self.logger.debug(f"歌词状态 - {lyric_status}")
            
            if has_lyrics:
                self.logger.info("检测到歌词数据，开始嵌入歌词...")
            else:
                self.logger.warning("未检测到歌词数据，跳过歌词嵌入")
            
            if file_ext == '.mp3':
                self._write_mp3_tags(file_path, music_info)
            elif file_ext == '.flac':
                self._write_flac_tags(file_path, music_info)
            elif file_ext == '.m4a':
                self._write_m4a_tags(file_path, music_info)
            else:
                self.logger.warning(f"不支持的文件格式: {file_ext}")
                
        except Exception as e:
            self.logger.error(f"写入音乐标签失败: {e}")
    
    def _write_mp3_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入MP3标签和歌词"""
        try:
            from mutagen.id3 import ID3, USLT, Encoding
            
            self.logger.debug("处理MP3文件标签...")
            
            # 创建或加载ID3标签
            try:
                audio = ID3(str(file_path))
                self.logger.debug("加载现有ID3标签")
            except:
                audio = ID3()
                self.logger.debug("创建新的ID3标签")
            
            # 添加基本标签
            audio.add(TIT2(encoding=3, text=music_info.name))
            audio.add(TPE1(encoding=3, text=music_info.artists))
            audio.add(TALB(encoding=3, text=music_info.album))
            
            if music_info.track_number > 0:
                audio.add(TRCK(encoding=3, text=str(music_info.track_number)))
            
            self.logger.debug("基本标签写入完成")
            
            # 处理歌词
            if music_info.lyric or music_info.tlyric:
                # 合并原文和翻译歌词
                combined_lyrics = ""
                if music_info.lyric:
                    combined_lyrics = self._clean_lrc_lyrics(music_info.lyric)
                if music_info.tlyric:
                    if combined_lyrics:
                        combined_lyrics += "\n\n[翻译歌词]\n" + self._clean_lrc_lyrics(music_info.tlyric)
                    else:
                        combined_lyrics = self._clean_lrc_lyrics(music_info.tlyric)
                
                # 移除可能已存在的歌词标签
                lyrics_removed = 0
                for tag in list(audio.keys()):
                    if tag.startswith('USLT') or tag.startswith('SYLT'):
                        del audio[tag]
                        lyrics_removed += 1
                
                if lyrics_removed > 0:
                    self.logger.debug(f"移除 {lyrics_removed} 个现有歌词标签")
                
                # 添加USLT歌词标签
                if combined_lyrics:
                    uslt = USLT(
                        encoding=Encoding.UTF8,
                        lang='eng',
                        desc='Lyrics',
                        text=combined_lyrics
                    )
                    audio.add(uslt)
                    self.logger.info(f"MP3歌词嵌入成功 - 字符数: {len(combined_lyrics)}")
            
            # 下载并添加封面
            if music_info.pic_url:
                try:
                    self.logger.debug("开始下载封面图片...")
                    pic_response = requests.get(music_info.pic_url, timeout=10)
                    pic_response.raise_for_status()
                    audio.add(APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=pic_response.content
                    ))
                    self.logger.debug("封面图片添加成功")
                except Exception as e:
                    self.logger.warning(f"添加封面失败: {e}")
            
            # 保存文件
            audio.save(str(file_path), v2_version=3)
            self.logger.info("MP3标签写入完成")
            
        except Exception as e:
            self.logger.error(f"写入MP3标签失败: {e}")
            raise
    
    def _write_flac_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入FLAC标签和歌词"""
        try:
            self.logger.debug("处理FLAC文件标签...")
            
            audio = FLAC(str(file_path))
            
            # 基本标签
            audio['TITLE'] = music_info.name
            audio['ARTIST'] = music_info.artists
            audio['ALBUM'] = music_info.album
            
            if music_info.track_number > 0:
                audio['TRACKNUMBER'] = str(music_info.track_number)
            
            self.logger.debug("基本标签写入完成")
            
            # 处理歌词
            if music_info.lyric or music_info.tlyric:
                # 合并原文和翻译歌词
                combined_lyrics = ""
                if music_info.lyric:
                    combined_lyrics = self._clean_lrc_lyrics(music_info.lyric)
                if music_info.tlyric:
                    if combined_lyrics:
                        combined_lyrics += "\n\n[翻译歌词]\n" + self._clean_lrc_lyrics(music_info.tlyric)
                    else:
                        combined_lyrics = self._clean_lrc_lyrics(music_info.tlyric)
                
                # 添加歌词到FLAC文件
                if combined_lyrics:
                    audio['LYRICS'] = combined_lyrics
                    self.logger.info(f"FLAC歌词嵌入成功 - 字符数: {len(combined_lyrics)}")
            
            # 下载并添加封面
            if music_info.pic_url:
                try:
                    self.logger.debug("开始下载封面图片...")
                    pic_response = requests.get(music_info.pic_url, timeout=10)
                    pic_response.raise_for_status()
                    
                    from mutagen.flac import Picture
                    picture = Picture()
                    picture.type = 3  # Cover (front)
                    picture.mime = 'image/jpeg'
                    picture.desc = 'Cover'
                    picture.data = pic_response.content
                    audio.add_picture(picture)
                    self.logger.debug("封面图片添加成功")
                except Exception as e:
                    self.logger.warning(f"添加封面失败: {e}")
            
            audio.save()
            self.logger.info("FLAC标签写入完成")
            
        except Exception as e:
            self.logger.error(f"写入FLAC标签失败: {e}")
            raise
    
    def _write_m4a_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入M4A标签和歌词"""
        try:
            self.logger.debug("处理M4A文件标签...")
            
            audio = MP4(str(file_path))
            
            # 基本标签
            audio['\xa9nam'] = music_info.name
            audio['\xa9ART'] = music_info.artists
            audio['\xa9alb'] = music_info.album
            
            if music_info.track_number > 0:
                audio['trkn'] = [(music_info.track_number, 0)]
            
            self.logger.debug("基本标签写入完成")
            
            # 处理歌词
            if music_info.lyric or music_info.tlyric:
                # 合并原文和翻译歌词
                combined_lyrics = ""
                if music_info.lyric:
                    combined_lyrics = self._clean_lrc_lyrics(music_info.lyric)
                if music_info.tlyric:
                    if combined_lyrics:
                        combined_lyrics += "\n\n[翻译歌词]\n" + self._clean_lrc_lyrics(music_info.tlyric)
                    else:
                        combined_lyrics = self._clean_lrc_lyrics(music_info.tlyric)
                
                # 添加歌词到M4A文件
                if combined_lyrics:
                    audio['\xa9lyr'] = combined_lyrics
                    self.logger.info(f"M4A歌词嵌入成功 - 字符数: {len(combined_lyrics)}")
            
            # 下载并添加封面
            if music_info.pic_url:
                try:
                    self.logger.debug("开始下载封面图片...")
                    pic_response = requests.get(music_info.pic_url, timeout=10)
                    pic_response.raise_for_status()
                    audio['covr'] = [pic_response.content]
                    self.logger.debug("封面图片添加成功")
                except Exception as e:
                    self.logger.warning(f"添加封面失败: {e}")
            
            audio.save()
            self.logger.info("M4A标签写入完成")
            
        except Exception as e:
            self.logger.error(f"写入M4A标签失败: {e}")
            raise
    
    def _clean_lrc_lyrics(self, lrc_text: str) -> str:
        """清理LRC格式歌词，移除多余的空行和标签"""
        if not lrc_text:
            return ""
        
        lines = lrc_text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 移除空行
            if not line.strip():
                continue
            
            # 移除ID标签（如：[ar:艺术家]、[ti:歌曲名]等）
            if line.startswith('[') and ':' in line and not line.startswith('[0'):
                continue
            
            cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines)
        self.logger.debug(f"歌词清理完成 - 原始行数: {len(lines)}, 清理后行数: {len(cleaned_lines)}")
        return result
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0B"
        
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        unit_index = 0
        
        while size >= 1024.0 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1
        
        return f"{size:.2f}{units[unit_index]}"
    

if __name__ == "__main__":
    # 测试代码
    downloader = MusicDownloader()
    print("音乐下载器模块")
    print("支持的功能:")
    print("- 同步下载")
    print("- 异步下载")
    print("- 批量下载")
    print("- 内存下载")
    print("- 音乐标签写入")
    print("- 下载进度跟踪")