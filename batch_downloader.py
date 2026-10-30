"""批量下载任务管理器

为歌单、专辑或任意歌曲集合提供后台并发下载能力：

- 后台线程池并发下载，不阻塞 Flask 请求
- 每首歌曲实时进度（回调自 ``MusicDownloader``）
- 高音质失败时自动降级重试（jymaster -> hires -> lossless -> ...）
- 任务快照（总数 / 成功 / 跳过 / 失败 / 进度）供前端轮询
- 已下载完成的文件可流式打包为 ZIP（不生成临时大文件）

设计说明：
1. 任务保存在内存中，服务重启后丢失（音频文件仍保留在 downloads 目录）
2. 同一首歌重复下载时由 ``MusicDownloader`` 判定文件已存在并标记为 skipped
3. 下载器使用 ``.part`` 临时文件，取消 / 失败不会留下损坏文件
4. ZIP 边读音频边发送，避免在磁盘上再复制一份整个歌单
"""

from __future__ import annotations

import re
import threading
import time
import uuid
import zipfile
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from music_downloader import DownloadException, MusicDownloader


# ============ 状态常量 ============

TRACK_PENDING = "pending"
TRACK_DOWNLOADING = "downloading"
TRACK_SUCCESS = "success"
TRACK_SKIPPED = "skipped"
TRACK_FAILED = "failed"
TRACK_CANCELLED = "cancelled"

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_CANCELLING = "cancelling"
JOB_COMPLETED = "completed"
JOB_CANCELLED = "cancelled"
JOB_FAILED = "failed"

FINAL_JOB_STATUSES = {JOB_COMPLETED, JOB_CANCELLED, JOB_FAILED}

# 单个任务允许的最大歌曲数，避免误操作把整个账号的歌单塞满磁盘
MAX_BATCH_TRACKS = 1000

# 高音质不可用时的降级顺序
QUALITY_FALLBACKS: Dict[str, List[str]] = {
    "jymaster": ["hires", "lossless", "exhigh", "standard"],
    "sky": ["jyeffect", "hires", "lossless", "exhigh", "standard"],
    "dolby": ["hires", "lossless", "exhigh", "standard"],
    "hires": ["lossless", "exhigh", "standard"],
    "jyeffect": ["lossless", "exhigh", "standard"],
    "lossless": ["exhigh", "standard"],
    "exhigh": ["standard"],
    "standard": [],
}


class BatchDownloadError(Exception):
    """批量下载参数 / 任务错误"""
    pass


class _Cancelled(Exception):
    """内部使用：进度回调中检测到取消"""
    pass


class _ZipStreamWriter:
    """供 ``zipfile`` 使用的不可 seek 流式写入器

    ``zipfile`` 检测到输出流不可 seek 后会使用 data descriptor 直接顺序写出，
    因此不需要生成完整的临时 ZIP 文件，可以边读音频边发送给浏览器，
    不会额外占用一份与歌单等大的磁盘空间。
    """

    def __init__(self) -> None:
        self._chunks: List[bytes] = []

    def write(self, data: bytes) -> int:
        data = bytes(data)
        if data:
            self._chunks.append(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def drain(self) -> List[bytes]:
        chunks, self._chunks = self._chunks, []
        return chunks


# ============ 数据模型 ============

@dataclass
class TrackTask:
    """单首歌曲的下载任务"""

    index: int
    music_id: str
    name: str = ""
    artists: str = ""
    album: str = ""
    pic_url: str = ""
    status: str = TRACK_PENDING
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    quality: str = ""
    file_path: str = ""
    filename: str = ""
    file_size: int = 0
    error: str = ""
    skipped: bool = False

    def to_dict(self, job_id: str) -> Dict[str, Any]:
        data = {
            "index": self.index,
            "id": self.music_id,
            "name": self.name or f"歌曲 {self.music_id}",
            "artists": self.artists,
            "album": self.album,
            "picUrl": self.pic_url,
            "status": self.status,
            "progress": round(self.progress, 1),
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "quality": self.quality,
            "filename": self.filename,
            "file_size": self.file_size,
            "error": self.error,
            "skipped": self.skipped,
        }
        if self.status in (TRACK_SUCCESS, TRACK_SKIPPED):
            data["file_url"] = f"/batch/file/{job_id}/{self.index}"
        return data


# ============ 批量任务 ============

class BatchJob:
    """一个批量下载任务，内部使用线程池并发执行"""

    def __init__(
        self,
        job_id: str,
        tasks: List[TrackTask],
        quality: str,
        downloader: MusicDownloader,
        name: str = "",
        fallback: bool = True,
        max_workers: int = 3,
    ):
        self.job_id = job_id
        self.tasks = tasks
        self.quality = quality
        self.downloader = downloader
        self.name = name or "批量下载"
        self.fallback = fallback
        self.max_workers = max(1, min(int(max_workers), 8))

        self.status = JOB_PENDING
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"batch-{job_id[:8]}",
            daemon=True,
        )

    # ---------- 对外接口 ----------

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> bool:
        """请求取消任务，返回是否成功发出取消请求"""
        with self._lock:
            if self.status in FINAL_JOB_STATUSES:
                return False
            self._cancel_event.set()
            self.status = JOB_CANCELLING
            # 尚未开始的任务直接标记为已取消
            for task in self.tasks:
                if task.status == TRACK_PENDING:
                    task.status = TRACK_CANCELLED
                    task.error = "已取消"
            return True

    def snapshot(self) -> Dict[str, Any]:
        """获取任务当前状态（线程安全）"""
        with self._lock:
            total = len(self.tasks)
            success = sum(1 for t in self.tasks if t.status == TRACK_SUCCESS)
            skipped = sum(1 for t in self.tasks if t.status == TRACK_SKIPPED)
            failed = sum(1 for t in self.tasks if t.status == TRACK_FAILED)
            cancelled = sum(1 for t in self.tasks if t.status == TRACK_CANCELLED)
            downloading = sum(1 for t in self.tasks if t.status == TRACK_DOWNLOADING)
            finished = success + skipped + failed + cancelled

            return {
                "job_id": self.job_id,
                "name": self.name,
                "quality": self.quality,
                "fallback": self.fallback,
                "status": self.status,
                "created_at": int(self.created_at),
                "started_at": int(self.started_at) if self.started_at else None,
                "finished_at": int(self.finished_at) if self.finished_at else None,
                "total": total,
                "success": success,
                "skipped": skipped,
                "failed": failed,
                "cancelled": cancelled,
                "downloading": downloading,
                "finished": finished,
                "progress": round(finished / total * 100, 1) if total else 100.0,
                "zip_available": (success + skipped) > 0,
                "tracks": [t.to_dict(self.job_id) for t in self.tasks],
            }

    def completed_files(self) -> List[TrackTask]:
        """返回已成功下载（含已存在）且文件仍存在的任务"""
        with self._lock:
            tasks = [
                t
                for t in self.tasks
                if t.status in (TRACK_SUCCESS, TRACK_SKIPPED) and t.file_path
            ]
        return [t for t in tasks if Path(t.file_path).is_file()]

    def get_task(self, index: int) -> Optional[TrackTask]:
        """按序号获取任务"""
        with self._lock:
            return next((t for t in self.tasks if t.index == index), None)

    # ---------- 内部执行 ----------

    def _set_task(self, task: TrackTask, **fields: Any) -> None:
        with self._lock:
            for key, value in fields.items():
                setattr(task, key, value)

    def _report_progress(self, task: TrackTask, downloaded: int, total: int) -> None:
        """下载器进度回调：更新单曲进度；取消时中断下载"""
        if self._cancel_event.is_set():
            raise _Cancelled("任务已取消")

        with self._lock:
            task.downloaded_bytes = downloaded
            if total:
                task.total_bytes = total
            if task.total_bytes:
                task.progress = min(99.0, downloaded / task.total_bytes * 100)

    def _run(self) -> None:
        with self._lock:
            if self._cancel_event.is_set():
                self.status = JOB_CANCELLED
                self.finished_at = time.time()
                return
            self.status = JOB_RUNNING
            self.started_at = time.time()

        executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix=f"batch-{self.job_id[:6]}",
        )
        futures = []
        try:
            for task in self.tasks:
                if self._cancel_event.is_set():
                    break
                futures.append(executor.submit(self._download_task, task))

            # 轮询等待：取消时尽快取消排队中的任务
            while not all(f.done() for f in futures):
                if self._cancel_event.is_set():
                    for future in futures:
                        future.cancel()
                time.sleep(0.2)
        finally:
            executor.shutdown(wait=True)

        with self._lock:
            # 排队中被取消 / 未执行的任务统一收尾
            for task in self.tasks:
                if task.status in (TRACK_PENDING, TRACK_DOWNLOADING):
                    task.status = TRACK_CANCELLED
                    task.error = task.error or "已取消"

            success = sum(
                1 for t in self.tasks if t.status in (TRACK_SUCCESS, TRACK_SKIPPED)
            )
            failed = sum(1 for t in self.tasks if t.status == TRACK_FAILED)

            self.finished_at = time.time()
            if self._cancel_event.is_set():
                self.status = JOB_CANCELLED
            elif success == 0 and failed > 0:
                self.status = JOB_FAILED
            else:
                self.status = JOB_COMPLETED

    def _download_task(self, task: TrackTask) -> None:
        if self._cancel_event.is_set():
            self._set_task(task, status=TRACK_CANCELLED, error="已取消")
            return

        self._set_task(
            task,
            status=TRACK_DOWNLOADING,
            progress=0.0,
            downloaded_bytes=0,
            error="",
        )

        # 音质降级列表：请求音质优先，失败后依次尝试更低音质
        qualities = [self.quality]
        if self.fallback:
            qualities += [
                q for q in QUALITY_FALLBACKS.get(self.quality, []) if q != self.quality
            ]

        last_error = "未知错误"
        for quality in qualities:
            if self._cancel_event.is_set():
                self._set_task(task, status=TRACK_CANCELLED, error="已取消")
                return

            self._set_task(task, quality=quality, progress=0.0, downloaded_bytes=0)

            try:
                result = self.downloader.download_music_file(
                    int(task.music_id),
                    quality,
                    progress_callback=lambda done, total: self._report_progress(
                        task, done, total
                    ),
                )
            except DownloadException as e:
                last_error = str(e)
                continue
            except (TypeError, ValueError):
                last_error = f"歌曲ID无效: {task.music_id}"
                break
            except Exception as e:  # 网络等偶发异常，尝试下一个音质
                last_error = f"{type(e).__name__}: {e}"
                continue

            if self._cancel_event.is_set():
                self._set_task(task, status=TRACK_CANCELLED, error="已取消")
                return

            if result.success:
                info = result.music_info
                filename = Path(result.file_path).name if result.file_path else ""
                fields: Dict[str, Any] = {
                    "status": TRACK_SKIPPED if result.skipped else TRACK_SUCCESS,
                    "progress": 100.0,
                    "downloaded_bytes": result.file_size,
                    "total_bytes": result.file_size,
                    "quality": info.quality if info else quality,
                    "file_path": result.file_path or "",
                    "filename": filename,
                    "file_size": result.file_size,
                    "skipped": result.skipped,
                    "error": "",
                }
                # 下载器返回的歌曲信息比列表接口更完整，用它补全展示字段
                if info:
                    fields.update(
                        name=info.name or task.name,
                        artists=info.artists or task.artists,
                        album=info.album or task.album,
                        pic_url=info.pic_url or task.pic_url,
                    )
                self._set_task(task, **fields)
                return

            last_error = result.error_message or "下载失败"

        if self._cancel_event.is_set():
            self._set_task(task, status=TRACK_CANCELLED, error="已取消")
            return

        self._set_task(task, status=TRACK_FAILED, error=last_error, progress=0.0)


# ============ 任务管理器 ============

class BatchDownloadManager:
    """批量下载任务管理器（内存任务表）"""

    def __init__(
        self,
        downloader: MusicDownloader,
        download_dir: str = "downloads",
        max_workers: int = 3,
        max_jobs: int = 50,
        job_ttl: int = 6 * 3600,
    ):
        self.downloader = downloader
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        self.max_workers = max(1, min(int(max_workers), 8))
        self.max_jobs = max(1, max_jobs)
        self.job_ttl = max(60, job_ttl)

        self._jobs: "OrderedDict[str, BatchJob]" = OrderedDict()
        self._lock = threading.RLock()
        self._zip_dir = self.download_dir / ".batch_zips"
        # 旧版本会把完整 ZIP 落在 .batch_zips；新版改为流式发送，启动时清理历史残留
        self._cleanup_legacy_zip_files()
        self._cleanup_stale_parts()

    # ---------- 任务管理 ----------

    def create_job(
        self,
        tracks: Iterable[Dict[str, Any]],
        quality: str = "lossless",
        name: str = "",
        fallback: bool = True,
    ) -> BatchJob:
        """创建并启动批量下载任务"""
        if not quality:
            quality = "lossless"

        tasks = [
            self._normalize_track(track, index)
            for index, track in enumerate(tracks)
        ]
        if not tasks:
            raise BatchDownloadError("没有可下载的歌曲")
        if len(tasks) > MAX_BATCH_TRACKS:
            raise BatchDownloadError(
                f"单次最多下载 {MAX_BATCH_TRACKS} 首歌曲，当前 {len(tasks)} 首"
            )

        job = BatchJob(
            job_id=uuid.uuid4().hex,
            tasks=tasks,
            quality=quality,
            downloader=self.downloader,
            name=name,
            fallback=fallback,
            max_workers=self.max_workers,
        )

        with self._lock:
            self._prune_locked()
            self._jobs[job.job_id] = job

        job.start()
        return job

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        with self._lock:
            self._prune_locked()
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())[-max(1, limit):]
        return [job.snapshot() for job in reversed(jobs)]

    def get_completed_task(self, job_id: str, index: int) -> Optional[TrackTask]:
        """获取已完成且文件可访问的单曲任务（用于单文件下载）"""
        job = self.get_job(job_id)
        if job is None:
            return None

        task = job.get_task(index)
        if (
            task is None
            or task.status not in (TRACK_SUCCESS, TRACK_SKIPPED)
            or not task.file_path
        ):
            return None

        path = Path(task.file_path)
        if not path.is_file() or not self._is_inside_download_dir(path):
            return None
        return task

    @staticmethod
    def _normalize_track(track: Any, index: int) -> TrackTask:
        """把前端 / 列表接口传入的字典统一为 TrackTask"""
        if not isinstance(track, dict):
            track = {"id": track}

        raw_id = (
            track.get("id")
            or track.get("song_id")
            or track.get("songId")
            or track.get("music_id")
            or track.get("musicId")
        )
        if raw_id is None:
            raise BatchDownloadError(f"第 {index + 1} 首歌曲缺少 id")

        music_id = str(raw_id).strip()
        if not music_id.isdigit():
            match = re.search(r"(\d{3,})", music_id)
            if not match:
                raise BatchDownloadError(f"第 {index + 1} 首歌曲 id 无效: {raw_id!r}")
            music_id = match.group(1)

        artists = track.get("artists") or track.get("artist") or track.get("ar_name") or ""
        if isinstance(artists, (list, tuple)):
            artists = "/".join(
                a.get("name", "") if isinstance(a, dict) else str(a) for a in artists
            )

        return TrackTask(
            index=index,
            music_id=music_id,
            name=str(track.get("name") or track.get("song_name") or track.get("title") or ""),
            artists=str(artists),
            album=str(track.get("album") or track.get("al_name") or ""),
            pic_url=str(track.get("picUrl") or track.get("pic") or track.get("cover") or ""),
        )

    # ---------- ZIP 打包 ----------

    def prepare_zip(self, job_id: str) -> Optional[List[Tuple[Path, str]]]:
        """收集待打包文件，返回 ``[(源文件路径, ZIP 内文件名), ...]``

        只收集已完成且仍存在于下载目录中的文件。真正发送时由
        :meth:`stream_zip` 边读边写，不再生成临时 ZIP 文件。
        """
        job = self.get_job(job_id)
        if job is None:
            return None

        files = job.completed_files()
        if not files:
            return None

        entries: List[Tuple[Path, str]] = []
        used_names = set()
        for task in sorted(files, key=lambda t: t.index):
            source = Path(task.file_path)
            # 安全校验：只打包下载目录内的文件
            if not source.is_file() or not self._is_inside_download_dir(source):
                continue

            base = f"{task.index + 1:03d}. {task.artists} - {task.name}"
            base = self._sanitize_filename(base) or f"{task.index + 1:03d}"
            arcname = f"{base[:80]}{source.suffix.lower()}"
            arcname = self._unique_name(arcname, used_names)
            entries.append((source, arcname))

        return entries or None

    def stream_zip(self, entries: List[Tuple[Path, str]]) -> Iterator[bytes]:
        """把文件流式打包为 ZIP 数据块，不占用额外磁盘空间"""
        writer = _ZipStreamWriter()
        with zipfile.ZipFile(
            writer, "w", compression=zipfile.ZIP_STORED, allowZip64=True
        ) as zf:
            for source, arcname in entries:
                zf.write(source, arcname)
                for chunk in writer.drain():
                    yield chunk

        for chunk in writer.drain():
            yield chunk

    def zip_download_name(self, job: BatchJob) -> str:
        """生成 ZIP 下载文件名"""
        quality_names = {
            "standard": "标准音质",
            "exhigh": "极高音质",
            "lossless": "无损音质",
            "hires": "Hi-Res",
            "sky": "沉浸环绕声",
            "jyeffect": "高清环绕声",
            "jymaster": "超清母带",
            "dolby": "杜比全景声",
        }
        quality = quality_names.get(job.quality, job.quality)
        name = self._sanitize_filename(f"{job.name} - {quality}") or "网易云音乐"
        return f"{name[:80]}.zip"

    @staticmethod
    def cleanup_zip(path: Path) -> None:
        try:
            Path(path).unlink()
        except OSError:
            pass

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            Path(path).unlink()
        except OSError:
            pass

    def _cleanup_legacy_zip_files(self) -> None:
        """删除旧版本残留的临时 ZIP，避免其占满磁盘"""
        if not self._zip_dir.is_dir():
            return
        for stale in self._zip_dir.glob("*.zip"):
            self.cleanup_zip(stale)

    def _cleanup_stale_parts(self) -> None:
        """清理超过 1 小时的下载临时文件（崩溃 / 磁盘满时可能残留）"""
        cutoff = time.time() - 3600
        for part in self.download_dir.glob(".download-*.part"):
            try:
                if part.stat().st_mtime < cutoff:
                    self._remove_file(part)
            except OSError:
                continue

    # ---------- 工具方法 ----------

    def _is_inside_download_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.download_dir.resolve())
            return True
        except (ValueError, OSError):
            return False

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
        filename = filename.strip(" .")
        return filename[:200]

    @staticmethod
    def _unique_name(arcname: str, used: set) -> str:
        if arcname not in used:
            used.add(arcname)
            return arcname

        path = Path(arcname)
        stem, suffix = path.stem, path.suffix
        counter = 2
        while True:
            candidate = f"{stem} ({counter}){suffix}"
            if candidate not in used:
                used.add(candidate)
                return candidate
            counter += 1

    def _prune_locked(self) -> None:
        """清理过期 / 超量的任务与 ZIP 临时文件（调用方需持锁）"""
        now = time.time()

        for job_id, job in list(self._jobs.items()):
            if (
                job.finished_at
                and now - job.finished_at > self.job_ttl
            ):
                self._jobs.pop(job_id, None)
                for stale in self._zip_dir.glob(f"{job_id[:8]}-*.zip"):
                    self.cleanup_zip(stale)

        while len(self._jobs) > self.max_jobs:
            oldest_id = next(
                (
                    job_id
                    for job_id, job in self._jobs.items()
                    if job.status in FINAL_JOB_STATUSES
                ),
                None,
            )
            if oldest_id is None:
                break
            self._jobs.pop(oldest_id, None)

        # 清理超过 12 小时、未被取走的 ZIP
        for stale in self._zip_dir.glob("*.zip"):
            try:
                if now - stale.stat().st_mtime > 12 * 3600:
                    self.cleanup_zip(stale)
            except OSError:
                continue
