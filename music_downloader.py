"""网易云音乐下载器（适配 ffmpeg 写入元数据）

提供功能：
- 同步 / 异步下载（本地落盘 / 内存返回）
- 批量并发下载
- 进度查询
- 基于 ffmpeg 的元数据 + 封面写入（MP3/FLAC/M4A/MP4/OGG/Opus）

设计要点：
1. ffmpeg 路径懒加载：每次写入前重新检测，支持服务启动后中途安装
2. 显式 -f 指定输出格式 + 临时文件保留原扩展名在最后，双保险
3. MP4（杜比全景声 EAC3）单独分支，启用 +faststart
4. 扩展名优先使用 API 返回的 type 字段，URL/Content-Type 兜底
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import aiohttp
import requests

from music_api import APIException, NeteaseAPI, load_cookies


# ============ 类型定义 ============

class AudioFormat(Enum):
    """音频格式枚举"""
    MP3 = "mp3"
    FLAC = "flac"
    M4A = "m4a"
    MP4 = "mp4"
    UNKNOWN = "unknown"


class QualityLevel(Enum):
    """音质等级枚举"""
    STANDARD = "standard"
    EXHIGH = "exhigh"
    LOSSLESS = "lossless"
    HIRES = "hires"
    SKY = "sky"
    JYEFFECT = "jyeffect"
    JYMASTER = "jymaster"
    DOLBY = "dolby"


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


# ============ 工具映射表 ============

# API 返回的 type -> 文件扩展名
API_TYPE_TO_EXT = {
    "mp3": ".mp3",
    "flac": ".flac",
    "m4a": ".m4a",
    "mp4": ".mp4",
    "ogg": ".ogg",
    "opus": ".opus",
}

# 文件扩展名 -> ffmpeg 输出 muxer 名称
EXT_TO_FFMPEG_FORMAT = {
    ".mp3": "mp3",
    ".flac": "flac",
    ".m4a": "mp4",
    ".mp4": "mp4",
    ".ogg": "ogg",
    ".opus": "opus",
}

# 支持元数据写入的扩展名
METADATA_FORMATS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus"}


# ============ 核心实现 ============

class MusicDownloader:
    """网易云音乐下载器

    用法:
        downloader = MusicDownloader(download_dir="downloads")
        result = downloader.download_music_file(music_id, quality="lossless")
    """

    def __init__(
        self,
        download_dir: str = "downloads",
        max_concurrent: int = 3,
        ffmpeg_path: Optional[str] = None,
    ):
        """
        Args:
            download_dir: 下载目录
            max_concurrent: 最大并发下载数
            ffmpeg_path: ffmpeg 可执行文件路径，为 None 时启动时检测一次
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.max_concurrent = max_concurrent

        self.api = NeteaseAPI()

        # ffmpeg 路径缓存：启动时检测一次，写入时还会再懒加载一次
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")
        if not self.ffmpeg_path:
            print("警告: 未检测到 ffmpeg，写入元数据功能将不可用")

    # ----------- 工具方法 -----------

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名非法字符"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip(' .')
        if len(filename) > 200:
            filename = filename[:200]
        return filename or "unknown"

    def _determine_file_extension(
        self,
        url: str,
        content_type: str = "",
        api_type: str = "",
    ) -> str:
        """确定文件扩展名

        优先级: API 返回的 type > URL 后缀 > HTTP Content-Type > 默认 mp3
        """
        api_type = (api_type or "").lower()
        if api_type in API_TYPE_TO_EXT:
            return API_TYPE_TO_EXT[api_type]

        url_lower = url.lower()
        if ".flac" in url_lower:
            return ".flac"
        if ".mp3" in url_lower:
            return ".mp3"
        if ".m4a" in url_lower or ".mp4" in url_lower:
            return ".m4a"

        content_type = (content_type or "").lower()
        if "flac" in content_type:
            return ".flac"
        if "mpeg" in content_type or "mp3" in content_type:
            return ".mp3"
        if "mp4" in content_type or "m4a" in content_type:
            return ".m4a"

        return ".mp3"

    def _resolve_ffmpeg(self) -> Optional[str]:
        """懒加载解析 ffmpeg 路径

        每次写入前调用一次：若启动时未检测到，但中途已安装，下一次就能用。
        """
        if self.ffmpeg_path:
            return self.ffmpeg_path
        path = shutil.which("ffmpeg")
        if path:
            self.ffmpeg_path = path  # 回写缓存
        return path

    # ----------- 信息获取 -----------

    def get_music_info(self, music_id: int, quality: str = "standard") -> MusicInfo:
        """获取音乐详细信息（同步）"""
        try:
            cookies = load_cookies()

            url_result = self.api.get_song_url(music_id, quality, cookies)
            print(url_result)
            if not url_result.get("data") or not url_result["data"]:
                raise DownloadException(f"无法获取音乐ID {music_id} 的播放链接")

            song_data = url_result["data"][0]
            download_url = song_data.get("url", "")
            if not download_url:
                raise DownloadException(f"音乐ID {music_id} 无可用的下载链接")

            detail_result = self.api.get_song_detail(music_id)
            if not detail_result.get("songs") or not detail_result["songs"]:
                raise DownloadException(f"无法获取音乐ID {music_id} 的详细信息")

            song_detail = detail_result["songs"][0]

            lyric_result = self.api.get_lyric(music_id, cookies)
            lyric = lyric_result.get("lrc", {}).get("lyric", "") if lyric_result else ""
            tlyric = lyric_result.get("tlyric", {}).get("lyric", "") if lyric_result else ""

            artists = "/".join(a["name"] for a in song_detail.get("ar", []))

            return MusicInfo(
                id=music_id,
                name=song_detail.get("name", "未知歌曲"),
                artists=artists or "未知艺术家",
                album=song_detail.get("al", {}).get("name", "未知专辑"),
                pic_url=song_detail.get("al", {}).get("picUrl", ""),
                duration=song_detail.get("dt", 0) // 1000,
                track_number=song_detail.get("no", 0),
                download_url=download_url,
                file_type=song_data.get("type", "mp3").lower(),
                file_size=song_data.get("size", 0),
                quality=quality,
                lyric=lyric,
                tlyric=tlyric,
            )

        except APIException as e:
            raise DownloadException(f"API调用失败: {e}")
        except Exception as e:
            raise DownloadException(f"获取音乐信息时发生错误: {e}")

    # ----------- 文件路径 -----------

    def _build_file_path(self, music_info: MusicInfo) -> Path:
        """根据 MusicInfo 生成下载文件路径"""
        filename = f"{music_info.artists} - {music_info.name}"
        safe = self._sanitize_filename(filename)
        ext = self._determine_file_extension(
            music_info.download_url,
            api_type=music_info.file_type,
        )
        return self.download_dir / f"{safe}{ext}"

    # ----------- 下载（同步） -----------

    def download_music_file(
        self,
        music_id: int,
        quality: str = "standard",
    ) -> DownloadResult:
        """同步下载音乐到本地"""
        try:
            music_info = self.get_music_info(music_id, quality)
            file_path = self._build_file_path(music_info)

            # 已存在则直接返回
            if file_path.exists():
                return DownloadResult(
                    success=True,
                    file_path=str(file_path),
                    file_size=file_path.stat().st_size,
                    music_info=music_info,
                )

            # 流式下载
            response = requests.get(music_info.download_url, stream=True, timeout=30)
            response.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # 写入元数据（失败不影响主流程）
            self._write_metadata_with_ffmpeg(file_path, music_info)

            return DownloadResult(
                success=True,
                file_path=str(file_path),
                file_size=file_path.stat().st_size,
                music_info=music_info,
            )

        except DownloadException:
            raise
        except requests.RequestException as e:
            return DownloadResult(success=False, error_message=f"下载请求失败: {e}")
        except Exception as e:
            return DownloadResult(success=False, error_message=f"下载过程中发生错误: {e}")

    # ----------- 下载（异步） -----------

    async def download_music_file_async(
        self,
        music_id: int,
        quality: str = "standard",
    ) -> DownloadResult:
        """异步下载音乐到本地"""
        try:
            music_info = self.get_music_info(music_id, quality)
            file_path = self._build_file_path(music_info)

            if file_path.exists():
                return DownloadResult(
                    success=True,
                    file_path=str(file_path),
                    file_size=file_path.stat().st_size,
                    music_info=music_info,
                )

            async with aiohttp.ClientSession() as session:
                async with session.get(music_info.download_url) as resp:
                    resp.raise_for_status()
                    async with aiofiles.open(file_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            await f.write(chunk)

            self._write_metadata_with_ffmpeg(file_path, music_info)

            return DownloadResult(
                success=True,
                file_path=str(file_path),
                file_size=file_path.stat().st_size,
                music_info=music_info,
            )

        except DownloadException:
            raise
        except aiohttp.ClientError as e:
            return DownloadResult(success=False, error_message=f"异步下载请求失败: {e}")
        except Exception as e:
            return DownloadResult(success=False, error_message=f"异步下载过程中发生错误: {e}")

    # ----------- 下载到内存 -----------

    def download_music_to_memory(
        self,
        music_id: int,
        quality: str = "standard",
    ) -> Tuple[bool, BytesIO, MusicInfo]:
        """下载音乐到内存"""
        try:
            music_info = self.get_music_info(music_id, quality)
            resp = requests.get(music_info.download_url, timeout=30)
            resp.raise_for_status()
            return True, BytesIO(resp.content), music_info

        except DownloadException:
            raise
        except requests.RequestException as e:
            raise DownloadException(f"下载到内存失败: {e}")
        except Exception as e:
            raise DownloadException(f"内存下载过程中发生错误: {e}")

    # ----------- 批量下载 -----------

    async def download_batch_async(
        self,
        music_ids: List[int],
        quality: str = "standard",
    ) -> List[DownloadResult]:
        """批量并发下载"""
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def _one(music_id: int) -> DownloadResult:
            async with semaphore:
                return await self.download_music_file_async(music_id, quality)

        tasks = [_one(mid) for mid in music_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: List[DownloadResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                processed.append(DownloadResult(
                    success=False,
                    error_message=f"下载音乐ID {music_ids[i]} 时发生异常: {r}",
                ))
            else:
                processed.append(r)
        return processed

    # ----------- 进度查询 -----------

    def get_download_progress(
        self,
        music_id: int,
        quality: str = "standard",
    ) -> Dict[str, Any]:
        """查询下载进度"""
        try:
            music_info = self.get_music_info(music_id, quality)
            file_path = self._build_file_path(music_info)

            if file_path.exists():
                current_size = file_path.stat().st_size
                progress = (
                    current_size / music_info.file_size * 100
                    if music_info.file_size > 0
                    else 0
                )
                return {
                    "music_id": music_id,
                    "filename": file_path.name,
                    "total_size": music_info.file_size,
                    "current_size": current_size,
                    "progress": min(progress, 100),
                    "completed": current_size >= music_info.file_size,
                }

            return {
                "music_id": music_id,
                "filename": file_path.name,
                "total_size": music_info.file_size,
                "current_size": 0,
                "progress": 0,
                "completed": False,
            }

        except Exception as e:
            return {
                "music_id": music_id,
                "error": str(e),
                "progress": 0,
                "completed": False,
            }

    # ============ ffmpeg 元数据写入（核心） ============

    def _write_metadata_with_ffmpeg(
        self,
        file_path: Path,
        music_info: MusicInfo,
    ) -> bool:
        """使用 ffmpeg 写入音频元数据

        处理: title/artist/album/track + 封面（如果是 mp3/flac/m4a/mp4）

        Returns:
            是否写入成功（失败不影响主流程）
        """
        ffmpeg_path = self._resolve_ffmpeg()
        if not ffmpeg_path:
            print("跳过元数据写入: ffmpeg 不可用")
            return False

        file_ext = file_path.suffix.lower()
        if file_ext not in METADATA_FORMATS:
            print(f"跳过元数据写入: 不支持的格式 {file_ext}")
            return False

        if not file_path.exists():
            print(f"跳过元数据写入: 文件不存在 {file_path}")
            return False

        # 临时输出文件：保留原扩展名在最后，便于 ffmpeg 识别 muxer
        # 例: 艾辰 - 错位时空.tagging.flac
        tmp_output = file_path.with_name(
            file_path.stem + ".tagging" + file_path.suffix
        )
        # 临时封面文件
        cover_tmp: Optional[str] = None

        try:
            # 下载封面到临时文件
            if music_info.pic_url:
                try:
                    pic_resp = requests.get(music_info.pic_url, timeout=10)
                    pic_resp.raise_for_status()
                    fd, cover_tmp = tempfile.mkstemp(suffix=".jpg", dir=str(self.download_dir))
                    os.close(fd)
                    with open(cover_tmp, "wb") as cf:
                        cf.write(pic_resp.content)
                except Exception as e:
                    print(f"封面下载失败，跳过封面写入: {e}")
                    cover_tmp = None

            # 构造 ffmpeg 命令
            # 顺序: global opts -> -i input1 -> -i input2 -> metadata -> mapping -> -f format -> output
            output_format = EXT_TO_FFMPEG_FORMAT.get(file_ext, "")
            cmd: List[str] = [
                ffmpeg_path, "-y", "-loglevel", "error",
                "-i", str(file_path),
            ]
            if cover_tmp:
                cmd += ["-i", cover_tmp]

            # 通用元数据
            meta = {
                "title": music_info.name,
                "artist": music_info.artists,
                "album": music_info.album,
                "album_artist": music_info.artists,
                "comment": "Downloaded from Netease Cloud Music",
            }
            if music_info.track_number > 0:
                meta["track"] = str(music_info.track_number)
                meta["tracktotal"] = str(music_info.track_number)
            for k, v in meta.items():
                if v:
                    cmd += ["-metadata", f"{k}={v}"]

            # 各格式的 mapping / 编码选项
            cmd += self._build_format_args(file_ext, has_cover=bool(cover_tmp))

            # -f 必须放在所有 -i 之后（作为 output option）才生效
            if output_format:
                cmd += ["-f", output_format]
            cmd.append(str(tmp_output))

            # 执行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                encoding="utf-8",
                errors="ignore",
            )

            if result.returncode == 0 and tmp_output.exists():
                # 原子替换原文件
                shutil.move(str(tmp_output), str(file_path))
                return True

            print(
                f"ffmpeg 写入元数据失败: "
                f"{(result.stderr or result.stdout or '').strip()}"
            )
            return False

        except subprocess.TimeoutExpired:
            print("ffmpeg 执行超时")
            return False
        except FileNotFoundError:
            print(f"ffmpeg 可执行文件未找到: {ffmpeg_path}")
            return False
        except Exception as e:
            print(f"ffmpeg 写入元数据异常: {e}")
            return False
        finally:
            # 清理封面临时文件
            if cover_tmp and os.path.exists(cover_tmp):
                try:
                    os.unlink(cover_tmp)
                except OSError:
                    pass
            # 清理可能残留的临时输出
            if tmp_output.exists():
                try:
                    tmp_output.unlink()
                except OSError:
                    pass

    def _build_format_args(self, file_ext: str, has_cover: bool) -> List[str]:
        """根据文件格式构造 mapping / 编码参数"""
        if file_ext == ".mp3":
            # MP3: 封面通过 ID3v2 APIC 帧写入
            if has_cover:
                return [
                    "-map", "0:a", "-map", "1:v",
                    "-c:a", "copy", "-c:v", "copy",
                    "-id3v2_version", "3",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)",
                ]
            return ["-map", "0:a", "-c:a", "copy", "-id3v2_version", "3"]

        if file_ext == ".flac":
            # FLAC: 原生支持封面
            if has_cover:
                return [
                    "-map", "0", "-map", "1",
                    "-c", "copy",
                    "-disposition:v:0", "attached_pic",
                ]
            return ["-map", "0", "-c", "copy"]

        if file_ext == ".m4a":
            # M4A: AAC 音频 + mp4 容器
            if has_cover:
                return [
                    "-map", "0:a", "-map", "1:v",
                    "-c", "copy",
                    "-disposition:v:0", "attached_pic",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)",
                ]
            return ["-map", "0:a", "-c:a", "copy"]

        if file_ext == ".mp4":
            # MP4 (杜比全景声 EAC3 / 其它 mp4 容器音频)
            # 杜比文件通常无视频流，封面作为 video stream 注入；+faststart 让 moov 在文件头
            if has_cover:
                return [
                    "-map", "0", "-map", "1:v",
                    "-c", "copy",
                    "-disposition:v:0", "attached_pic",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)",
                    "-movflags", "+faststart",
                ]
            return ["-map", "0", "-c", "copy", "-movflags", "+faststart"]

        if file_ext in (".ogg", ".opus"):
            if has_cover:
                return [
                    "-map", "0:a", "-map", "1:v",
                    "-c:a", "copy", "-c:v", "copy",
                ]
            return ["-map", "0:a", "-c:a", "copy"]

        # 默认
        if has_cover:
            return ["-map", "0:a", "-map", "1:v", "-c", "copy"]
        return ["-map", "0:a", "-c:a", "copy"]


# ============ CLI 入口 ============

if __name__ == "__main__":
    import sys
    from dataclasses import asdict

    downloader = MusicDownloader()

    # 无参数：打印模块信息
    if len(sys.argv) < 2:
        print("网易云音乐下载器")
        print(f"ffmpeg 路径: {downloader.ffmpeg_path or '未找到'}")
        print("支持的音质: standard / exhigh / lossless / hires / sky / jyeffect / jymaster / dolby")
        print("支持的功能: 同步/异步/批量下载、内存下载、进度查询、ffmpeg 元数据写入")
        print()
        print("用法:")
        print("  python music_downloader.py <music_id> [quality]            # 仅打印信息")
        print("  python music_downloader.py <music_id> [quality] --download # 打印并下载")
        print()
        print("示例:")
        print("  python music_downloader.py 123456")
        print("  python music_downloader.py 123456 lossless")
        print("  python music_downloader.py 123456 hires --download")
        sys.exit(0)

    # 解析参数
    try:
        music_id = int(sys.argv[1])
    except ValueError:
        print(f"错误: music_id 必须是整数，收到: {sys.argv[1]!r}")
        sys.exit(1)

    quality = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "lossless"
    do_download = "--download" in sys.argv

    # 打印音乐信息
    try:
        info = downloader.get_music_info(music_id, quality)
    except DownloadException as e:
        print(f"获取音乐信息失败: {e}")
        sys.exit(1)

    print()
    print("=" * 70)
    print(f"音乐信息  (ID={info.id}, quality={info.quality})")
    print("=" * 70)

    info_dict = asdict(info)
    for key, value in info_dict.items():
        # 歌词太长，只显示行数
        if key in ("lyric", "tlyric"):
            lines = [ln for ln in (value or "").splitlines() if ln.strip()]
            preview = " | ".join(lines[:2])[:80] if lines else "(空)"
            print(f"  {key:<14}: {len(lines)} 行  预览: {preview}{'...' if len(lines) > 2 else ''}")
            continue
        # URL 类字段：完整展示（如果终端窄可换行）
        if key in ("download_url", "pic_url"):
            print(f"  {key:<14}: {value}")
            continue
        print(f"  {key:<14}: {value}")

    print("=" * 70)

    # 可选：触发下载
    if do_download:
        print()
        print("开始下载...")
        result = downloader.download_music_file(music_id, quality)
        if result.success:
            print(f"下载完成: {result.file_path}  ({result.file_size} 字节)")
        else:
            print(f"下载失败: {result.error_message}")
            sys.exit(1)
