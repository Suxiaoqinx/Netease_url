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
    DOLBY = "dolby"      # 杜比全景声


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
    
    def __init__(self, download_dir: str = "downloads", max_concurrent: int = 3):
        """
        初始化音乐下载器
        
        Args:
            download_dir: 下载目录
            max_concurrent: 最大并发下载数
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.max_concurrent = max_concurrent
        
        # 初始化依赖
        self.cookie_manager = CookieManager()
        self.api = NeteaseAPI()
        
        # 支持的文件格式
        self.supported_formats = {
            'mp3': AudioFormat.MP3,
            'flac': AudioFormat.FLAC,
            'm4a': AudioFormat.M4A
        }
    
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
            # 获取cookies
            cookies = self.cookie_manager.parse_cookies()
            
            # 获取音乐URL信息
            url_result = self.api.get_song_url(music_id, quality, cookies)
            if not url_result.get('data') or not url_result['data']:
                raise DownloadException(f"无法获取音乐ID {music_id} 的播放链接")
            
            song_data = url_result['data'][0]
            download_url = song_data.get('url', '')
            if not download_url:
                raise DownloadException(f"音乐ID {music_id} 无可用的下载链接")
            
            # 获取音乐详情
            detail_result = self.api.get_song_detail(music_id)
            if not detail_result.get('songs') or not detail_result['songs']:
                raise DownloadException(f"无法获取音乐ID {music_id} 的详细信息")
            
            song_detail = detail_result['songs'][0]
            
            # 获取歌词
            lyric_result = self.api.get_lyric(music_id, cookies)
            lyric = lyric_result.get('lrc', {}).get('lyric', '') if lyric_result else ''
            tlyric = lyric_result.get('tlyric', {}).get('lyric', '') if lyric_result else ''
            
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
            
            return music_info
            
        except APIException as e:
            raise DownloadException(f"API调用失败: {e}")
        except Exception as e:
            raise DownloadException(f"获取音乐信息时发生错误: {e}")
    
    def download_music_file(self, music_id: int, quality: str = "standard") -> DownloadResult:
        """下载音乐文件到本地
        
        Args:
            music_id: 音乐ID
            quality: 音质等级
            
        Returns:
            下载结果对象
        """
        try:
            # 获取音乐信息
            music_info = self.get_music_info(music_id, quality)
            
            # 生成文件名
            filename = f"{music_info.artists} - {music_info.name}"
            safe_filename = self._sanitize_filename(filename)
            
            # 确定文件扩展名
            file_ext = self._determine_file_extension(music_info.download_url)
            file_path = self.download_dir / f"{safe_filename}{file_ext}"
            
            # 检查文件是否已存在
            if file_path.exists():
                return DownloadResult(
                    success=True,
                    file_path=str(file_path),
                    file_size=file_path.stat().st_size,
                    music_info=music_info
                )
            
            # 下载文件
            response = requests.get(music_info.download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # 写入文件
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # 写入音乐标签
            self._write_music_tags(file_path, music_info)
            
            return DownloadResult(
                success=True,
                file_path=str(file_path),
                file_size=file_path.stat().st_size,
                music_info=music_info
            )
            
        except DownloadException:
            raise
        except requests.RequestException as e:
            return DownloadResult(
                success=False,
                error_message=f"下载请求失败: {e}"
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=f"下载过程中发生错误: {e}"
            )
    
    async def download_music_file_async(self, music_id: int, quality: str = "standard") -> DownloadResult:
        """异步下载音乐文件到本地
        
        Args:
            music_id: 音乐ID
            quality: 音质等级
            
        Returns:
            下载结果对象
        """
        try:
            # 获取音乐信息（同步操作）
            music_info = self.get_music_info(music_id, quality)
            
            # 生成文件名
            filename = f"{music_info.artists} - {music_info.name}"
            safe_filename = self._sanitize_filename(filename)
            
            # 确定文件扩展名
            file_ext = self._determine_file_extension(music_info.download_url)
            file_path = self.download_dir / f"{safe_filename}{file_ext}"
            
            # 检查文件是否已存在
            if file_path.exists():
                return DownloadResult(
                    success=True,
                    file_path=str(file_path),
                    file_size=file_path.stat().st_size,
                    music_info=music_info
                )
            
            # 异步下载文件
            async with aiohttp.ClientSession() as session:
                async with session.get(music_info.download_url) as response:
                    response.raise_for_status()
                    
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
            
            # 写入音乐标签
            self._write_music_tags(file_path, music_info)
            
            return DownloadResult(
                success=True,
                file_path=str(file_path),
                file_size=file_path.stat().st_size,
                music_info=music_info
            )
            
        except DownloadException:
            raise
        except aiohttp.ClientError as e:
            return DownloadResult(
                success=False,
                error_message=f"异步下载请求失败: {e}"
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=f"异步下载过程中发生错误: {e}"
            )
    
    def download_music_to_memory(self, music_id: int, quality: str = "standard") -> Tuple[bool, BytesIO, MusicInfo]:
        """下载音乐到内存
        
        Args:
            music_id: 音乐ID
            quality: 音质等级
            
        Returns:
            (是否成功, 音乐数据流, 音乐信息)
            
        Raises:
            DownloadException: 下载失败时抛出
        """
        try:
            # 获取音乐信息
            music_info = self.get_music_info(music_id, quality)
            
            # 下载到内存
            response = requests.get(music_info.download_url, timeout=30)
            response.raise_for_status()
            
            # 创建BytesIO对象
            audio_data = BytesIO(response.content)
            
            return True, audio_data, music_info
            
        except DownloadException:
            raise
        except requests.RequestException as e:
            raise DownloadException(f"下载到内存失败: {e}")
        except Exception as e:
            raise DownloadException(f"内存下载过程中发生错误: {e}")
    
    async def download_batch_async(self, music_ids: List[int], quality: str = "standard") -> List[DownloadResult]:
        """批量异步下载音乐
        
        Args:
            music_ids: 音乐ID列表
            quality: 音质等级
            
        Returns:
            下载结果列表
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def download_with_semaphore(music_id: int) -> DownloadResult:
            async with semaphore:
                return await self.download_music_file_async(music_id, quality)
        
        tasks = [download_with_semaphore(music_id) for music_id in music_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(DownloadResult(
                    success=False,
                    error_message=f"下载音乐ID {music_ids[i]} 时发生异常: {result}"
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def _write_music_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入音乐标签信息
        
        Args:
            file_path: 音乐文件路径
            music_info: 音乐信息
        """
        try:
            file_ext = file_path.suffix.lower()
            
            if file_ext == '.mp3':
                self._write_mp3_tags(file_path, music_info)
            elif file_ext == '.flac':
                self._write_flac_tags(file_path, music_info)
            elif file_ext == '.m4a':
                self._write_m4a_tags(file_path, music_info)
                
        except Exception as e:
            print(f"写入音乐标签失败: {e}")
    
    def _write_mp3_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入MP3标签"""
        try:
            audio = MP3(str(file_path), ID3=ID3)
            
            # 添加ID3标签
            audio.tags.add(TIT2(encoding=3, text=music_info.name))
            audio.tags.add(TPE1(encoding=3, text=music_info.artists))
            audio.tags.add(TALB(encoding=3, text=music_info.album))
            
            if music_info.track_number > 0:
                audio.tags.add(TRCK(encoding=3, text=str(music_info.track_number)))
            
            # 下载并添加封面
            if music_info.pic_url:
                try:
                    pic_response = requests.get(music_info.pic_url, timeout=10)
                    pic_response.raise_for_status()
                    audio.tags.add(APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=pic_response.content
                    ))
                except:
                    pass  # 封面下载失败不影响主流程
            
            audio.save()
        except Exception as e:
            print(f"写入MP3标签失败: {e}")
    
    def _write_flac_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入FLAC标签"""
        try:
            audio = FLAC(str(file_path))
            
            audio['TITLE'] = music_info.name
            audio['ARTIST'] = music_info.artists
            audio['ALBUM'] = music_info.album
            
            if music_info.track_number > 0:
                audio['TRACKNUMBER'] = str(music_info.track_number)
            
            # 下载并添加封面
            if music_info.pic_url:
                try:
                    pic_response = requests.get(music_info.pic_url, timeout=10)
                    pic_response.raise_for_status()
                    
                    from mutagen.flac import Picture
                    picture = Picture()
                    picture.type = 3  # Cover (front)
                    picture.mime = 'image/jpeg'
                    picture.desc = 'Cover'
                    picture.data = pic_response.content
                    audio.add_picture(picture)
                except:
                    pass  # 封面下载失败不影响主流程
            
            audio.save()
        except Exception as e:
            print(f"写入FLAC标签失败: {e}")
    
    def _write_m4a_tags(self, file_path: Path, music_info: MusicInfo) -> None:
        """写入M4A标签"""
        try:
            audio = MP4(str(file_path))
            
            audio['\xa9nam'] = music_info.name
            audio['\xa9ART'] = music_info.artists
            audio['\xa9alb'] = music_info.album
            
            if music_info.track_number > 0:
                audio['trkn'] = [(music_info.track_number, 0)]
            
            # 下载并添加封面
            if music_info.pic_url:
                try:
                    pic_response = requests.get(music_info.pic_url, timeout=10)
                    pic_response.raise_for_status()
                    audio['covr'] = [pic_response.content]
                except:
                    pass  # 封面下载失败不影响主流程
            
            audio.save()
        except Exception as e:
            print(f"写入M4A标签失败: {e}")
    
    def get_download_progress(self, music_id: int, quality: str = "standard") -> Dict[str, Any]:
        """获取下载进度信息
        
        Args:
            music_id: 音乐ID
            quality: 音质等级
            
        Returns:
            包含进度信息的字典
        """
        try:
            music_info = self.get_music_info(music_id, quality)
            
            filename = f"{music_info.artists} - {music_info.name}"
            safe_filename = self._sanitize_filename(filename)
            file_ext = self._determine_file_extension(music_info.download_url)
            file_path = self.download_dir / f"{safe_filename}{file_ext}"
            
            if file_path.exists():
                current_size = file_path.stat().st_size
                progress = (current_size / music_info.file_size * 100) if music_info.file_size > 0 else 0
                
                return {
                    'music_id': music_id,
                    'filename': safe_filename + file_ext,
                    'total_size': music_info.file_size,
                    'current_size': current_size,
                    'progress': min(progress, 100),
                    'completed': current_size >= music_info.file_size
                }
            else:
                return {
                    'music_id': music_id,
                    'filename': safe_filename + file_ext,
                    'total_size': music_info.file_size,
                    'current_size': 0,
                    'progress': 0,
                    'completed': False
                }
                
        except Exception as e:
            return {
                'music_id': music_id,
                'error': str(e),
                'progress': 0,
                'completed': False
            }


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
