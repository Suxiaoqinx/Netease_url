"""
网易云音乐API服务主程序

提供网易云音乐相关API服务，包括：
- 歌曲信息获取
- 音乐搜索
- 歌单和专辑详情
- 音乐下载
- 健康检查
"""

import logging
import sys
import time
import traceback
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from urllib.parse import quote

# 确保当前目录在Python路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from flask import Flask, request, send_file, Response
except ImportError as e:
    print(f"❌ 缺少Flask库，请安装: pip install flask")
    input("按回车键退出...")
    sys.exit(1)

try:
    from music_api import (
        NeteaseAPI, APIException, QualityLevel,
        url_v1, name_v1, lyric_v1, search_music, 
        playlist_detail, album_detail
    )
    from cookie_manager import CookieManager, CookieException
    from music_downloader import MusicDownloader, DownloadException, AudioFormat
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保以下文件存在:")
    print("  - music_api.py")
    print("  - cookie_manager.py") 
    print("  - music_downloader.py")
    input("按回车键退出...")
    sys.exit(1)


@dataclass
class APIConfig:
    """API配置类"""
    host: str = '0.0.0.0'
    port: int = 5000
    debug: bool = False
    downloads_dir: str = 'downloads'
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    request_timeout: int = 30
    log_level: str = 'DEBUG'
    cors_origins: str = '*'


class APIResponse:
    """API响应工具类"""
    
    @staticmethod
    def success(data: Any = None, message: str = 'success', status_code: int = 200) -> Tuple[Dict[str, Any], int]:
        """成功响应"""
        response = {
            'status': status_code,
            'success': True,
            'message': message
        }
        if data is not None:
            response['data'] = data
        return response, status_code
    
    @staticmethod
    def error(message: str, status_code: int = 400, error_code: str = None) -> Tuple[Dict[str, Any], int]:
        """错误响应"""
        response = {
            'status': status_code,
            'success': False,
            'message': message
        }
        if error_code:
            response['error_code'] = error_code
        return response, status_code


class MusicAPIService:
    def __init__(self, config: APIConfig):
        self.config = config
        self.logger = self._setup_logger()
        
        try:
            self.cookie_manager = CookieManager()
            self.netease_api = NeteaseAPI()
            
            # 确保下载目录是绝对路径
            downloads_dir = Path(config.downloads_dir).absolute()
            self.logger.info(f"设置下载目录: {downloads_dir}")
            
            # 创建下载器
            self.downloader = MusicDownloader(
                download_dir=str(downloads_dir),
                logger=self.logger
            )
            
            # 创建下载目录
            self.downloads_path = downloads_dir
            self.downloads_path.mkdir(exist_ok=True)
            
            self.logger.info(f"音乐API服务初始化完成，下载目录: {self.downloads_path.absolute()}")
            
        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}")
            raise
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('music_api')
        logger.setLevel(getattr(logging, self.config.log_level.upper()))
        
        # 防止重复添加处理器
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            
            # 文件处理器
            try:
                file_handler = logging.FileHandler('music_api.log', encoding='utf-8')
                file_formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
                )
                file_handler.setFormatter(file_formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                logger.warning(f"无法创建日志文件: {e}")
        
        return logger
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符"""
        import re
        # 移除或替换非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        filename = re.sub(illegal_chars, '_', filename)
        # 移除前后空格和点
        filename = filename.strip(' .')
        # 限制长度
        if len(filename) > 200:
            filename = filename[:200]
        return filename or "unknown"

    def check_download_path(self) -> Dict[str, Any]:
        """检查下载路径状态"""
        path_info = {
            'downloads_path': str(self.downloads_path.absolute()),
            'exists': self.downloads_path.exists(),
            'is_dir': self.downloads_path.is_dir() if self.downloads_path.exists() else False,
            'writable': False,
            'files': []
        }
        
        # 检查是否可写
        try:
            test_file = self.downloads_path / "test_write.tmp"
            test_file.touch()
            path_info['writable'] = True
            test_file.unlink()  # 删除测试文件
        except Exception as e:
            path_info['writable_error'] = str(e)
        
        # 列出文件
        if self.downloads_path.exists() and self.downloads_path.is_dir():
            try:
                path_info['files'] = [f.name for f in self.downloads_path.iterdir() if f.is_file()]
            except Exception as e:
                path_info['list_error'] = str(e)
        
        return path_info
    
    def _get_cookies(self) -> Dict[str, str]:
        """获取Cookie"""
        try:
            cookie_str = self.cookie_manager.read_cookie()
            return self.cookie_manager.parse_cookie_string(cookie_str)
        except CookieException as e:
            self.logger.warning(f"获取Cookie失败: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Cookie处理异常: {e}")
            return {}
    
    def _extract_music_id(self, id_or_url: str) -> str:
        """提取音乐ID"""
        try:
            # 处理短链接
            if '163cn.tv' in id_or_url:
                import requests
                response = requests.get(id_or_url, allow_redirects=False, timeout=10)
                id_or_url = response.headers.get('Location', id_or_url)
            
            # 处理网易云链接
            if 'music.163.com' in id_or_url:
                index = id_or_url.find('id=') + 3
                if index > 2:
                    return id_or_url[index:].split('&')[0]
            
            # 直接返回ID
            return str(id_or_url).strip()
            
        except Exception as e:
            self.logger.error(f"提取音乐ID失败: {e}")
            return str(id_or_url).strip()
    
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
    
    def _get_quality_display_name(self, quality: str) -> str:
        """获取音质显示名称"""
        quality_names = {
            'standard': "标准音质",
            'exhigh': "极高音质", 
            'lossless': "无损音质",
            'hires': "Hi-Res音质",
            'sky': "沉浸环绕声",
            'jyeffect': "高清环绕声",
            'jymaster': "超清母带"
        }
        return quality_names.get(quality, f"未知音质({quality})")
    
    def _validate_request_params(self, required_params: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], int]]:
        """验证请求参数"""
        for param_name, param_value in required_params.items():
            if not param_value:
                return APIResponse.error(f"参数 '{param_name}' 不能为空", 400)
        return None
    
    def _safe_get_request_data(self) -> Dict[str, Any]:
        """安全获取请求数据"""
        try:
            if request.method == 'GET':
                return dict(request.args)
            else:
                # 优先使用JSON数据，然后是表单数据
                json_data = request.get_json(silent=True) or {}
                form_data = dict(request.form)
                # 合并数据，JSON优先
                return {**form_data, **json_data}
        except Exception as e:
            self.logger.error(f"获取请求数据失败: {e}")
            return {}


# 创建Flask应用
app = Flask(__name__)

# 延迟初始化服务实例
api_service = None

def initialize_api_service():
    """初始化API服务"""
    global api_service
    try:
        config = APIConfig()
        api_service = MusicAPIService(config)
        return True
    except Exception as e:
        print(f"❌ 初始化API服务失败: {e}")
        print("详细错误信息:")
        traceback.print_exc()
        return False


@app.before_request
def before_request():
    """请求前处理"""
    if api_service:
        # 记录请求信息
        api_service.logger.info(
            f"{request.method} {request.path} - IP: {request.remote_addr} - "
            f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}"
        )


@app.after_request
def after_request(response: Response) -> Response:
    """请求后处理 - 设置CORS头"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    response.headers.add('Access-Control-Max-Age', '3600')
    
    # 记录响应信息
    if api_service:
        api_service.logger.info(f"响应状态: {response.status_code}")
    return response


@app.errorhandler(400)
def handle_bad_request(e):
    """处理400错误"""
    return APIResponse.error("请求参数错误", 400)


@app.errorhandler(404)
def handle_not_found(e):
    """处理404错误"""
    return APIResponse.error("请求的资源不存在", 404)


@app.errorhandler(500)
def handle_internal_error(e):
    """处理500错误"""
    if api_service:
        api_service.logger.error(f"服务器内部错误: {e}")
    return APIResponse.error("服务器内部错误", 500)


@app.route('/')
def index() -> str:
    """首页路由 - 直接返回嵌入的HTML内容"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>网易云音乐工具箱</title>
    <link href="https://mirrors.sustech.edu.cn/cdnjs/ajax/libs/twitter-bootstrap/5.1.3/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://mirrors.sustech.edu.cn/cdnjs/ajax/libs/aplayer/1.10.1/APlayer.min.css">
    <style>
        body {
            background-color: #f8f9fa;
            color: #333;
        }
        .container {
            max-width: 800px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .btn-primary {
            margin-top: 20px;
            background-color: #007bff;
            border-color: #007bff;
        }
        .btn-primary:hover {
            background-color: #0056b3;
            border-color: #004085;
        }
        .btn-success {
            margin-top: 20px;
            background-color: #28a745;
            border-color: #28a745;
        }
        .btn-success:hover {
            background-color: #218838;
            border-color: #1e7e34;
        }
        .btn-warning {
            margin-top: 20px;
            background-color: #ffc107;
            border-color: #ffc107;
        }
        .btn-warning:hover {
            background-color: #e0a800;
            border-color: #d39e00;
        }
        #song-info {
            margin-top: 20px;
        }
        #song-info img {
            max-width: 100%;
            border-radius: 8px;
        }
        .alert-info {
            background-color: #d1ecf1;
            color: #0c5460;
            border-color: #bee5eb;
        }
        /* 歌曲/歌单标题过长自动省略号 */
        .song-title, .playlist-title {
            display: inline-block;
            max-width: 180px;
            vertical-align: middle;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        /* 歌单列表按钮不换行 */
        .list-group-item .select-song {
            flex-shrink: 0;
            margin-left: 10px;
        }
        /* 歌词区域美化 */
        .lyric-box {
            max-height: 180px;
            overflow-y: auto;
            background: linear-gradient(90deg,#f7f7fa 60%,#f0f4fa 100%);
            border-radius: 8px;
            padding: 12px 16px;
            font-size: 15px;
            color: #222;
            box-shadow: 0 1px 4px rgba(0,0,0,0.04);
            line-height: 1.7;
            margin-bottom: 0;
        }
    </style>
</head>
<body>
    <div class="container mt-5">
        <h1 class="text-center mb-4">网易云音乐工具箱</h1>
        <div class="card shadow-sm">
            <div class="card-body">
                <form id="main-form">
                    <div class="mb-3">
                        <label class="form-label">功能选择</label>
                        <select id="mode-select" class="form-select">
                            <option value="search">歌曲搜索</option>
                            <option value="parse">单曲解析</option>
                            <option value="playlist">歌单解析</option>
                            <option value="album">专辑解析</option>
                            <option value="download">音乐下载</option>
                        </select>
                    </div>
                    <div id="search-area">
                        <div class="mb-3">
                            <label for="search_keywords" class="form-label">搜索关键词</label>
                            <input type="text" id="search_keywords" class="form-control" placeholder="输入关键词进行搜索">
                        </div>
                        <div class="mb-3">
                            <label for="search_limit" class="form-label">返回数量</label>
                            <input type="number" id="search_limit" class="form-control" value="10" min="1" max="50">
                        </div>
                        <div class="text-center">
                            <button type="button" id="search-btn" class="btn btn-success w-50">搜索</button>
                        </div>
                    </div>
                    <div id="parse-area" style="display:none;">
                        <div class="mb-3">
                            <label for="song_ids" class="form-label">歌曲ID或URL</label>
                            <input type="text" id="song_ids" class="form-control" placeholder="输入歌曲ID或URL">
                        </div>
                        <div class="mb-3">
                            <label for="level" class="form-label">音质选择</label>
                            <select id="level" class="form-select">
                                <option value="standard">标准音质</option>
                                <option value="exhigh">极高音质</option>
                                <option value="lossless">无损音质</option>
                                <option value="hires">Hires音质</option>
                                <option value="sky">沉浸环绕声</option>
                                <option value="jyeffect">高清环绕声</option>
                                <option value="jymaster">超清母带</option>
                            </select>
                        </div>
                        <div class="text-center">
                            <button type="button" id="parse-btn" class="btn btn-primary w-50">解析</button>
                        </div>
                    </div>
                    <div id="playlist-area" style="display:none;">
                        <div class="mb-3">
                            <label for="playlist_id" class="form-label">歌单ID或链接</label>
                            <input type="text" id="playlist_id" class="form-control" placeholder="输入歌单ID或网易云歌单链接">
                        </div>
                        <div class="text-center">
                            <button type="button" id="playlist-btn" class="btn btn-warning w-50">解析歌单</button>
                        </div>
                    </div>
                    <div id="album-area" style="display:none;">
                        <div class="mb-3">
                            <label for="album_id" class="form-label">专辑ID或链接</label>
                            <input type="text" id="album_id" class="form-control" placeholder="输入专辑ID或网易云专辑链接">
                        </div>
                        <div class="text-center">
                            <button type="button" id="album-btn" class="btn btn-info w-50">解析专辑</button>
                        </div>
                    </div>
                    <div id="download-area" style="display:none;">
                        <div class="mb-3">
                            <label for="download_id" class="form-label">音乐ID或URL</label>
                            <input type="text" id="download_id" class="form-control" placeholder="输入音乐ID或网易云音乐链接">
                        </div>
                        <div class="mb-3">
                            <label for="download_quality" class="form-label">下载音质</label>
                            <select id="download_quality" class="form-select">
                                <option value="standard">标准音质</option>
                                <option value="exhigh">极高音质</option>
                                <option value="lossless" selected>无损音质</option>
                                <option value="hires">Hires音质</option>
                                <option value="sky">沉浸环绕声</option>
                                <option value="jyeffect">高清环绕声</option>
                                <option value="jymaster">超清母带</option>
                            </select>
                        </div>
                        <div class="text-center">
                            <button type="button" id="download-btn" class="btn btn-success w-50">下载音乐</button>
                        </div>
                        <div id="download-progress" class="mt-3 d-none">
                            <div class="progress">
                                <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 100%"></div>
                            </div>
                            <div class="text-center mt-2">
                                <small class="text-muted">正在下载并写入元信息...</small>
                            </div>
                        </div>
                    </div>
                </form>
            </div>
        </div>
        <!-- 搜索结果列表 -->
        <div id="search-result" class="mt-4 d-none">
            <h5>搜索结果：</h5>
            <ul class="list-group" id="search-list"></ul>
        </div>
        <!-- 结果展示区域 -->
        <div id="song-info" class="alert alert-info d-none mt-4 p-0 border-0" style="box-shadow:0 2px 8px rgba(0,0,0,0.07);">
            <div class="row g-0 align-items-stretch">
                <div class="col-md-8 p-3 d-flex flex-column justify-content-between">
                    <h4 class="mb-2" id="song_name" style="font-weight:700;"></h4>
                    <div class="mb-2"><span class="badge bg-primary me-2">歌手</span><span id="artist_names"></span></div>
                    <div class="mb-2"><span class="badge bg-secondary me-2">专辑</span><span id="song_alname"></span></div>
                    <div class="mb-2"><span class="badge bg-success me-2">音质</span><span id="song_level"></span></div>
                    <div class="mb-2"><span class="badge bg-warning text-dark me-2">大小</span><span id="song_size"></span></div>
                    <div class="mb-2">
                        <button id="show-big-pic" type="button" class="btn btn-outline-info btn-sm me-2" style="vertical-align:middle;">显示大图</button>
                    </div>
                    <div class="mb-2"><span class="badge bg-info text-dark me-2">链接</span><a id="song_url" href="" target="_blank">点击下载</a></div>
                    <div class="mb-2"><span class="badge bg-dark me-2">歌词</span></div>
                    <div class="lyric-box" id="lyric"></div>
                </div>
            </div>
            <div class="row g-0">
                <div class="col-12 p-3 pt-0">
                    <div id="aplayer"></div>
                </div>
            </div>
        </div>
        <!-- 歌单解析结果 -->
        <div id="playlist-result" class="mt-4 d-none">
            <div class="card">
                <div class="card-body">
                    <div class="d-flex align-items-center mb-3">
                        <img id="playlist-cover" src="" alt="cover" style="width:60px;height:60px;object-fit:cover;border-radius:8px;margin-right:15px;">
                        <div>
                            <h5 id="playlist-name" class="mb-1"></h5>
                            <div class="text-muted" id="playlist-creator"></div>
                        </div>
                    </div>
                    <div id="playlist-desc" class="mb-2 text-secondary small"></div>
                    <div>共 <span id="playlist-count"></span> 首歌</div>
                </div>
            </div>
            <ul class="list-group mt-3" id="playlist-tracks"></ul>
        </div>
        <!-- 专辑解析结果 -->
        <div id="album-result" class="mt-4 d-none">
            <div class="card">
                <div class="card-body">
                    <div class="d-flex align-items-center mb-3">
                        <img id="album-cover" src="" alt="cover" style="width:60px;height:60px;object-fit:cover;border-radius:8px;margin-right:15px;">
                        <div>
                            <h5 id="album-name" class="mb-1"></h5>
                            <div class="text-muted" id="album-artist"></div>
                        </div>
                    </div>
                    <div id="album-desc" class="mb-2 text-secondary small"></div>
                    <div>共 <span id="album-count"></span> 首歌</div>
                </div>
            </div>
            <ul class="list-group mt-3" id="album-tracks"></ul>
        </div>
    </div>
    <!-- Modal for big picture -->
    <div class="modal fade" id="bigPicModal" tabindex="-1" aria-labelledby="bigPicModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="bigPicModalLabel">大图预览</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body text-center">
                    <img id="big-pic-img" src="" alt="大图" style="max-width:100%;max-height:60vh;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,0.12);">
                </div>
            </div>
        </div>
    </div>
    <footer class="footer mt-5 py-3 bg-light border-top">
        <div class="container text-center text-muted small">
            <span>网易云音乐工具箱 &copy; 2025 | Powered by Suxiaoqingx &amp; Bootstrap | <a href="https://github.com/Suxiaoqinx/Netease_url" target="_blank">GitHub</a></span>
        </div>
    </footer>
    <script src="https://mirrors.sustech.edu.cn/cdnjs/ajax/libs/jquery/3.7.1/jquery.min.js"></script>
    <script src="https://mirrors.sustech.edu.cn/cdnjs/ajax/libs/aplayer/1.10.1/APlayer.min.js"></script>
    <script src="https://mirrors.sustech.edu.cn/cdnjs/ajax/libs/twitter-bootstrap/5.1.3/js/bootstrap.bundle.min.js"></script>
    <script>
        $(document).ready(function() {
            function lrctrim(lyrics) {
                const lines = lyrics.split('\\n');
                const data = [];

                lines.forEach((line, index) => {
                    const matches = line.match(/\\[(\\d{2}):(\\d{2}[\\.:]?\\d*)]/);
                    if (matches) {
                        const minutes = parseInt(matches[1], 10);
                        const seconds = parseFloat(matches[2].replace('.', ':')) || 0;
                        const timestamp = minutes * 60000 + seconds * 1000;

                        let text = line.replace(/\\[\\d{2}:\\d{2}[\\.:]?\\d*\\]/g, '').trim();
                        text = text.replace(/\\s\\s+/g, ' '); // Replace multiple spaces with a single space

                        data.push([timestamp, index, text]);
                    }
                });

                data.sort((a, b) => a[0] - b[0]);

                return data;
            }

            function lrctran(lyric, tlyric) {
                lyric = lrctrim(lyric);
                tlyric = lrctrim(tlyric);

                let len1 = lyric.length;
                let len2 = tlyric.length;
                let result = "";

                for (let i = 0, j = 0; i < len1 && j < len2; i++) {
                    while (lyric[i][0] > tlyric[j][0] && j + 1 < len2) {
                        j++;
                    }

                    if (lyric[i][0] === tlyric[j][0]) {
                        tlyric[j][2] = tlyric[j][2].replace('/', '');
                        if (tlyric[j][2]) {
                            lyric[i][2] += ` (翻译：${tlyric[j][2]})`;
                        }
                        j++;
                    }
                }

                for (let i = 0; i < len1; i++) {
                    let t = lyric[i][0];
                    result += `[${String(Math.floor(t / 60000)).padStart(2, '0')}:${String(Math.floor((t % 60000) / 1000)).padStart(2, '0')}.${String(t % 1000).padStart(3, '0')}]${lyric[i][2]}\\n`;
                }

                return result;
            }

            function extractLinks(text) {
                var regex = /https?:\\/\\/\\S+/g;
                var matches = text.match(regex);
                if (matches) {
                    return matches[0];
                } else {
                    return '';
                }
            }
    
            function checkValidLink(link) {
                if (link.indexOf("http") === -1 || 
                    (link.indexOf("music.163.com") === -1 && link.indexOf("163cn.tv") === -1)) {
                    return false;
                }
                return true;
            }
    
            function extractAndCheckId(text) {
                var link = extractLinks(text);
                if (checkValidLink(link)) {
                    return link;
                } else {
                    var idRegex = /\\b\\d+\\b/g;
                    var ids = text.match(idRegex);
                    if (ids && ids.length > 0) {
                        return ids[0];
                    }
                    return '';
                }
            }

            // 切换功能区
            $('#mode-select').on('change', function() {
                if ($(this).val() === 'search') {
                    $('#search-area').show();
                    $('#parse-area').hide();
                    $('#playlist-area').hide();
                    $('#album-area').hide();
                    $('#download-area').hide();
                    $('#song-info').addClass('d-none');
                    $('#playlist-result').addClass('d-none');
                    $('#album-result').addClass('d-none');
                } else if ($(this).val() === 'parse') {
                    $('#search-area').hide();
                    $('#parse-area').show();
                    $('#playlist-area').hide();
                    $('#album-area').hide();
                    $('#download-area').hide();
                    $('#search-result').addClass('d-none');
                    $('#playlist-result').addClass('d-none');
                    $('#album-result').addClass('d-none');
                } else if ($(this).val() === 'playlist') {
                    $('#search-area').hide();
                    $('#parse-area').hide();
                    $('#playlist-area').show();
                    $('#album-area').hide();
                    $('#download-area').hide();
                    $('#search-result').addClass('d-none');
                    $('#song-info').addClass('d-none');
                    $('#album-result').addClass('d-none');
                } else if ($(this).val() === 'album') {
                    $('#search-area').hide();
                    $('#parse-area').hide();
                    $('#playlist-area').hide();
                    $('#album-area').show();
                    $('#download-area').hide();
                    $('#search-result').addClass('d-none');
                    $('#song-info').addClass('d-none');
                    $('#playlist-result').addClass('d-none');
                    $('#album-result').addClass('d-none');
                } else if ($(this).val() === 'download') {
                    $('#search-area').hide();
                    $('#parse-area').hide();
                    $('#playlist-area').hide();
                    $('#album-area').hide();
                    $('#download-area').show();
                    $('#search-result').addClass('d-none');
                    $('#song-info').addClass('d-none');
                    $('#playlist-result').addClass('d-none');
                    $('#album-result').addClass('d-none');
                } else {
                    $('#album-area').hide();
                    $('#download-area').hide();
                    $('#album-result').addClass('d-none');
                }
            });

            // 搜索功能
            $('#search-btn').on('click', function() {
                const keywords = $('#search_keywords').val();
                const limit = $('#search_limit').val();
                if (!keywords) {
                    alert('请输入搜索关键词');
                    return;
                }
                $.ajax({
                    url: '/Search',
                    method: 'POST',
                    data: { keyword: keywords, limit: limit },
                    dataType: 'json',
                    success: function(data) {
                        if (data.status === 200) {
                            $('#search-list').empty();
                            data.data.forEach(function(song) {
                                const item = `<li class="list-group-item d-flex justify-content-between align-items-center">
                                    <div>
                                        <img src="${song.picUrl}" alt="cover" style="width:40px;height:40px;object-fit:cover;border-radius:4px;margin-right:10px;">
                                        <strong class='song-title'>${song.name}</strong> - <span>${song.artists}</span> <span class="text-muted">[${song.album}]</span>
                                    </div>
                                    <div>
                                        <button class="btn btn-sm btn-outline-primary select-song me-2" data-id="${song.id}" data-name="${song.name}">解析</button>
                                        <button class="btn btn-sm btn-success download-song" data-id="${song.id}" data-name="${song.name}">下载</button>
                                    </div>
                                </li>`;
                                $('#search-list').append(item);
                            });
                            $('#search-result').removeClass('d-none');
                        } else {
                            $('#search-list').html('<li class="list-group-item">未找到相关歌曲</li>');
                            $('#search-result').removeClass('d-none');
                        }
                    },
                    error: function() {
                        $('#search-list').html('<li class="list-group-item">搜索失败，请重试</li>');
                        $('#search-result').removeClass('d-none');
                    }
                });
            });

            // 搜索结果点击解析
            $(document).on('click', '.select-song', function() {
                const songId = $(this).data('id');
                $('#song_ids').val(songId);
                $('#mode-select').val('parse').trigger('change');
                $('html,body').animate({scrollTop: $('#main-form').offset().top}, 300);
            });

            // 单曲解析
            $('#parse-btn').on('click', function() {
                const songIds = $('#song_ids').val();
                const level = $('#level').val();
                if (!songIds) {
                    alert('请输入歌曲ID或URL');
                    return;
                }
                $.post('/Song_V1', { url: songIds, level: level, type:'json' }, function(data) {
                    if (data.status === 200) {
                        $('#song_name').text(data.data.name);
                        $('#artist_names').text(data.data.ar_name);
                        $('#song_alname').text(data.data.al_name);
                        $('#song_level').text(data.data.level);
                        $('#song_size').text(data.data.size);
                        let processedLyrics = data.data.lyric;
                        if (data.data.tlyric) {
                            processedLyrics = lrctran(data.data.lyric, data.data.tlyric);
                        }
                        $('#lyric').html(processedLyrics.replace(/\\n/g, '<br>'));
                        $('#song_url').attr('href', data.data.url).text('点击下载');
                        $('#song-info').removeClass('d-none');
                        $('#show-big-pic').data('pic', data.data.pic);
                        new APlayer({
                            container: document.getElementById('aplayer'),
                            lrcType: 1,
                            audio: [{
                                name: data.data.name,
                                artist: data.data.ar_name,
                                url: data.data.url,
                                cover: data.data.pic,
                                lrc: processedLyrics
                            }]
                        });
                    } else {
                        alert(data.data.msg);
                    }
                }, 'json');
            });

            // 显示大图按钮事件
            $(document).on('click', '#show-big-pic', function() {
                var picUrl = $(this).data('pic');
                $('#big-pic-img').attr('src', picUrl);
                var modal = new bootstrap.Modal(document.getElementById('bigPicModal'));
                modal.show();
            });

            // 歌单解析
            $('#playlist-btn').on('click', function() {
                let pid = $('#playlist_id').val().trim();
                if (!pid) {
                    alert('请输入歌单ID或链接');
                    return;
                }
                // 支持直接粘贴歌单链接
                const idMatch = pid.match(/playlist\\?id=(\\d+)/);
                if (idMatch) pid = idMatch[1];
                $.get('/Playlist', { id: pid }, function(data) {
                    if (data.status === 200) {
                        const pl = data.data.playlist;
                        $('#playlist-cover').attr('src', pl.coverImgUrl);
                        $('#playlist-name').text(pl.name);
                        $('#playlist-creator').text('by ' + pl.creator);
                        $('#playlist-desc').text(pl.description || '');
                        $('#playlist-count').text(pl.trackCount);
                        $('#playlist-tracks').empty();
                        pl.tracks.forEach(function(song, idx) {
                            const item = `<li class="list-group-item d-flex justify-content-between align-items-center">
                                <div>
                                    <img src="${song.picUrl}" alt="cover" style="width:32px;height:32px;object-fit:cover;border-radius:4px;margin-right:8px;">
                                    <strong class="playlist-title">${idx+1}. ${song.name}</strong> - <span>${song.artists}</span> <span class="text-muted">[${song.album}]</span>
                                </div>
                                <div>
                                    <button class="btn btn-sm btn-outline-primary select-song me-2" data-id="${song.id}" data-name="${song.name}">解析</button>
                                    <button class="btn btn-sm btn-success download-song" data-id="${song.id}" data-name="${song.name}">下载</button>
                                </div>
                            </li>`;
                            $('#playlist-tracks').append(item);
                        });
                        $('#playlist-result').removeClass('d-none');
                    } else {
                        $('#playlist-result').removeClass('d-none');
                        $('#playlist-tracks').html('<li class="list-group-item">歌单解析失败：'+data.data.msg+'</li>');
                    }
                }, 'json');
            });

            // 专辑解析
            $(document).on('click', '#album-btn', function() {
                let aid = $('#album_id').val().trim();
                if (!aid) {
                    alert('请输入专辑ID或链接');
                    return;
                }
                // 支持直接粘贴专辑链接
                const idMatch = aid.match(/album\\?id=(\\d+)/);
                if (idMatch) aid = idMatch[1];
                $.get('/Album', { id: aid }, function(data) {
                    if (data.status === 200) {
                        const al = data.data.album;
                        $('#album-cover').attr('src', al.coverImgUrl);
                        $('#album-name').text(al.name);
                        $('#album-artist').text(al.artist);
                        $('#album-desc').text(al.description || '');
                        $('#album-count').text(al.songs.length);
                        $('#album-tracks').empty();
                        al.songs.forEach(function(song, idx) {
                            const item = `<li class="list-group-item d-flex justify-content-between align-items-center">
                                <div>
                                    <img src="${song.picUrl}" alt="cover" style="width:32px;height:32px;object-fit:cover;border-radius:4px;margin-right:8px;">
                                    <strong class="playlist-title">${idx+1}. ${song.name}</strong> - <span>${song.artists}</span> <span class="text-muted">[${song.album}]</span>
                                </div>
                                <div>
                                    <button class="btn btn-sm btn-outline-primary select-song me-2" data-id="${song.id}" data-name="${song.name}">解析</button>
                                    <button class="btn btn-sm btn-success download-song" data-id="${song.id}" data-name="${song.name}">下载</button>
                                </div>
                            </li>`;
                            $('#album-tracks').append(item);
                        });
                        $('#album-result').removeClass('d-none');
                    } else {
                        $('#album-result').removeClass('d-none');
                        $('#album-tracks').html('<li class="list-group-item">专辑解析失败：'+data.data.msg+'</li>');
                    }
                }, 'json');
            });

            // 音乐下载功能
            $('#download-btn').on('click', function() {
                const musicId = $('#download_id').val().trim();
                const quality = $('#download_quality').val();
                
                if (!musicId) {
                    alert('请输入音乐ID或URL');
                    return;
                }
                
                // 提取ID（支持URL格式）
                let processedId = musicId;
                const idMatch = musicId.match(/song\\?id=(\\d+)/);
                if (idMatch) {
                    processedId = idMatch[1];
                }
                
                // 显示进度条
                $('#download-progress').removeClass('d-none');
                $('#download-btn').prop('disabled', true).text('下载中...');
                
                // 使用XMLHttpRequest来处理下载并获取响应头
                const xhr = new XMLHttpRequest();
                xhr.open('POST', '/Download', true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.responseType = 'blob';
                
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        // 获取自定义响应头
                        const downloadMessage = xhr.getResponseHeader('X-Download-Message');
                        const encodedFilename = xhr.getResponseHeader('X-Download-Filename');
                        const filename = encodedFilename ? decodeURIComponent(encodedFilename) : 'music.flac';
                        
                        // 创建下载链接
                        const blob = xhr.response;
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = filename || 'music.flac';
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(url);
                        
                        // 显示完成提示
                        alert('✅ 音乐文件下载完成！');
                        console.log(`下载完成: ${filename}`);
                        if (downloadMessage) {
                            console.log(`服务器消息: ${downloadMessage}`);
                        }
                    } else {
                        alert('下载失败，请重试');
                    }
                    
                    // 重置按钮状态
                    $('#download-progress').addClass('d-none');
                    $('#download-btn').prop('disabled', false).text('下载音乐');
                };
                
                xhr.onerror = function() {
                    alert('下载出错，请重试');
                    $('#download-progress').addClass('d-none');
                    $('#download-btn').prop('disabled', false).text('下载音乐');
                };
                
                // 发送请求
                const formData = `id=${encodeURIComponent(processedId)}&quality=${encodeURIComponent(quality)}`;
                xhr.send(formData);
            });

            // 列表中的下载按钮点击事件
            // 下载按钮点击跳转到下载功能
            $(document).on('click', '.download-song', function() {
                const musicId = $(this).data('id');
                const songName = $(this).data('name');
                
                if (!musicId) {
                    alert('无法获取音乐ID');
                    return;
                }
                
                // 填充下载ID并跳转到下载功能区域
                $('#download_id').val(musicId);
                $('#mode-select').val('download').trigger('change');
                $('html,body').animate({scrollTop: $('#main-form').offset().top}, 300);
            });
        });
    </script>
</body>
</html>
"""


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查API"""
    try:
        if not api_service:
            return APIResponse.error("服务未初始化", 503)
        
        # 检查Cookie状态
        cookie_status = api_service.cookie_manager.is_cookie_valid()
        
        health_info = {
            'service': 'running',
            'timestamp': int(time.time()),
            'cookie_status': 'valid' if cookie_status else 'invalid',
            'downloads_dir': str(api_service.downloads_path.absolute()),
            'version': '2.0.0'
        }
        
        return APIResponse.success(health_info, "API服务运行正常")
        
    except Exception as e:
        error_msg = f"健康检查失败: {str(e)}"
        if api_service:
            api_service.logger.error(error_msg)
        return APIResponse.error(error_msg, 500)
    
@app.route('/song', methods=['GET', 'POST'])
@app.route('/Song_V1', methods=['GET', 'POST'])  # 向后兼容
def get_song_info():
    """获取歌曲信息API"""
    try:
        # 获取请求参数
        data = api_service._safe_get_request_data()
        song_ids = data.get('ids') or data.get('id')
        url = data.get('url')
        level = data.get('level', 'lossless')
        info_type = data.get('type', 'url')
        
        # 参数验证
        if not song_ids and not url:
            return APIResponse.error("必须提供 'ids'、'id' 或 'url' 参数")
        
        # 提取音乐ID
        music_id = api_service._extract_music_id(song_ids or url)
        
        # 验证音质参数
        valid_levels = ['standard', 'exhigh', 'lossless', 'hires', 'sky', 'jyeffect', 'jymaster']
        if level not in valid_levels:
            return APIResponse.error(f"无效的音质参数，支持: {', '.join(valid_levels)}")
        
        # 验证类型参数
        valid_types = ['url', 'name', 'lyric', 'json']
        if info_type not in valid_types:
            return APIResponse.error(f"无效的类型参数，支持: {', '.join(valid_types)}")
        
        cookies = api_service._get_cookies()
        
        # 根据类型获取不同信息
        if info_type == 'url':
            result = url_v1(music_id, level, cookies)
            if result and result.get('data') and len(result['data']) > 0:
                song_data = result['data'][0]
                response_data = {
                    'id': song_data.get('id'),
                    'url': song_data.get('url'),
                    'level': song_data.get('level'),
                    'quality_name': api_service._get_quality_display_name(song_data.get('level', level)),
                    'size': song_data.get('size'),
                    'size_formatted': api_service._format_file_size(song_data.get('size', 0)),
                    'type': song_data.get('type'),
                    'bitrate': song_data.get('br')
                }
                return APIResponse.success(response_data, "获取歌曲URL成功")
            else:
                return APIResponse.error("获取音乐URL失败，可能是版权限制或音质不支持", 404)
        
        elif info_type == 'name':
            result = name_v1(music_id)
            return APIResponse.success(result, "获取歌曲信息成功")
        
        elif info_type == 'lyric':
            result = lyric_v1(music_id, cookies)
            return APIResponse.success(result, "获取歌词成功")
        
        elif info_type == 'json':
            # 获取完整的歌曲信息（用于前端解析）
            song_info = name_v1(music_id)
            url_info = url_v1(music_id, level, cookies)
            lyric_info = lyric_v1(music_id, cookies)
            
            if not song_info or 'songs' not in song_info or not song_info['songs']:
                return APIResponse.error("未找到歌曲信息", 404)
            
            song_data = song_info['songs'][0]
            
            # 构建前端期望的响应格式
            response_data = {
                'id': music_id,
                'name': song_data.get('name', ''),
                'ar_name': ', '.join(artist['name'] for artist in song_data.get('ar', [])),
                'al_name': song_data.get('al', {}).get('name', ''),
                'pic': song_data.get('al', {}).get('picUrl', ''),
                'level': level,
                'lyric': lyric_info.get('lrc', {}).get('lyric', '') if lyric_info else '',
                'tlyric': lyric_info.get('tlyric', {}).get('lyric', '') if lyric_info else ''
            }
            
            # 添加URL和大小信息
            if url_info and url_info.get('data') and len(url_info['data']) > 0:
                url_data = url_info['data'][0]
                response_data.update({
                    'url': url_data.get('url', ''),
                    'size': api_service._format_file_size(url_data.get('size', 0)),
                    'level': url_data.get('level', level)
                })
            else:
                response_data.update({
                    'url': '',
                    'size': '获取失败'
                })
            
            return APIResponse.success(response_data, "获取歌曲信息成功")
            
    except APIException as e:
        api_service.logger.error(f"API调用失败: {e}")
        return APIResponse.error(f"API调用失败: {str(e)}", 500)
    except Exception as e:
        api_service.logger.error(f"获取歌曲信息异常: {e}\n{traceback.format_exc()}")
        return APIResponse.error(f"服务器错误: {str(e)}", 500)
    
@app.route('/debug/path', methods=['GET'])
def debug_path():
    """调试路径信息"""
    if not api_service:
        return APIResponse.error("服务未初始化", 503)
    
    try:
        path_info = api_service.check_download_path()
        return APIResponse.success(path_info, "路径信息获取成功")
    except Exception as e:
        return APIResponse.error(f"获取路径信息失败: {str(e)}", 500)
    
@app.route('/search', methods=['GET', 'POST'])
@app.route('/Search', methods=['GET', 'POST'])  # 向后兼容
def search_music_api():
    """搜索音乐API"""
    if not api_service:
        return APIResponse.error("服务未初始化", 503)
    
    try:
        # 获取请求参数
        data = api_service._safe_get_request_data()
        keyword = data.get('keyword') or data.get('keywords') or data.get('q')
        limit = int(data.get('limit', 30))
        offset = int(data.get('offset', 0))
        search_type = data.get('type', '1')  # 1-歌曲, 10-专辑, 100-歌手, 1000-歌单
        
        # 参数验证
        if not keyword:
            return APIResponse.error("搜索关键词不能为空", 400)
        
        # 限制搜索数量
        if limit > 100:
            limit = 100
        
        cookies = api_service._get_cookies()
        result = search_music(keyword, cookies, limit)
        
        return APIResponse.success(result, "搜索完成")
        
    except ValueError as e:
        return APIResponse.error(f"参数格式错误: {str(e)}")
    except Exception as e:
        api_service.logger.error(f"搜索音乐异常: {e}\n{traceback.format_exc()}")
        return APIResponse.error(f"搜索失败: {str(e)}", 500)


@app.route('/playlist', methods=['GET', 'POST'])
@app.route('/Playlist', methods=['GET', 'POST'])  # 向后兼容
def get_playlist():
    """获取歌单详情API"""
    if not api_service:
        return APIResponse.error("服务未初始化", 503)
    
    try:
        # 获取请求参数
        data = api_service._safe_get_request_data()
        playlist_id = data.get('id')
        
        # 参数验证
        if not playlist_id:
            return APIResponse.error("歌单ID不能为空", 400)
        
        cookies = api_service._get_cookies()
        result = playlist_detail(playlist_id, cookies)
        
        # 适配前端期望的响应格式
        response_data = {
            'status': 'success',
            'playlist': result
        }
        
        return APIResponse.success(response_data, "获取歌单详情成功")
        
    except Exception as e:
        api_service.logger.error(f"获取歌单异常: {e}\n{traceback.format_exc()}")
        return APIResponse.error(f"获取歌单失败: {str(e)}", 500)


@app.route('/album', methods=['GET', 'POST'])
@app.route('/Album', methods=['GET', 'POST'])  # 向后兼容
def get_album():
    """获取专辑详情API"""
    if not api_service:
        return APIResponse.error("服务未初始化", 503)
    
    try:
        # 获取请求参数
        data = api_service._safe_get_request_data()
        album_id = data.get('id')
        
        # 参数验证
        if not album_id:
            return APIResponse.error("专辑ID不能为空", 400)
        
        cookies = api_service._get_cookies()
        result = album_detail(album_id, cookies)
        
        # 适配前端期望的响应格式
        response_data = {
            'status': 200,
            'album': result
        }
        
        return APIResponse.success(response_data, "获取专辑详情成功")
        
    except Exception as e:
        api_service.logger.error(f"获取专辑异常: {e}\n{traceback.format_exc()}")
        return APIResponse.error(f"获取专辑失败: {str(e)}", 500)


@app.route('/download', methods=['GET', 'POST'])
@app.route('/Download', methods=['GET', 'POST'])  # 向后兼容
def download_music_api():
    """下载音乐API"""
    if not api_service:
        return APIResponse.error("服务未初始化", 503)
    
    try:
        # 获取请求参数
        data = api_service._safe_get_request_data()
        music_id = data.get('id')
        quality = data.get('quality', 'lossless')
        return_format = data.get('format', 'file')  # file 或 json
        
        # 参数验证
        if not music_id:
            return APIResponse.error("音乐ID不能为空", 400)
        
        # 验证音质参数
        valid_qualities = ['standard', 'exhigh', 'lossless', 'hires', 'sky', 'jyeffect', 'jymaster']
        if quality not in valid_qualities:
            return APIResponse.error(f"无效的音质参数，支持: {', '.join(valid_qualities)}")
        
        # 验证返回格式
        if return_format not in ['file', 'json']:
            return APIResponse.error("返回格式只支持 'file' 或 'json'")
        
        music_id = api_service._extract_music_id(music_id)
        
        # 使用下载器下载文件
        download_result = api_service.downloader.download_music_file(music_id, quality)
        
        if not download_result.success:
            return APIResponse.error(f"下载失败: {download_result.error_message}", 500)
        
        file_path = Path(download_result.file_path)
        
        # 确保文件存在
        if not file_path.exists():
            return APIResponse.error("下载的文件不存在", 404)
        
        api_service.logger.info(f"下载完成，文件路径: {file_path}")
        
        # 根据返回格式返回结果
        if return_format == 'json':
            response_data = {
                'music_id': music_id,
                'name': download_result.music_info.name,
                'artist': download_result.music_info.artists,
                'album': download_result.music_info.album,
                'quality': quality,
                'quality_name': api_service._get_quality_display_name(quality),
                'file_type': download_result.music_info.file_type,
                'file_size': download_result.file_size,
                'file_size_formatted': api_service._format_file_size(download_result.file_size),
                'file_path': str(file_path.absolute()),
                'filename': file_path.name,
                'duration': download_result.music_info.duration
            }
            return APIResponse.success(response_data, "下载完成")
        else:
            # 返回文件下载
            try:
                # 确保文件名安全
                safe_filename = api_service._sanitize_filename(f"{download_result.music_info.artists} - {download_result.music_info.name}")
                download_filename = f"{safe_filename}.{download_result.music_info.file_type}"
                
                api_service.logger.info(f"发送文件: {file_path} -> {download_filename}")
                
                response = send_file(
                    str(file_path.absolute()),  # 使用绝对路径
                    as_attachment=True,
                    download_name=download_filename,
                    mimetype=f"audio/{download_result.music_info.file_type}"
                )
                response.headers['X-Download-Message'] = 'Download completed successfully'
                response.headers['X-Download-Filename'] = quote(download_filename, safe='')
                return response
            except Exception as e:
                api_service.logger.error(f"发送文件失败: {e}")
                api_service.logger.error(f"文件路径: {file_path.absolute()}")
                api_service.logger.error(f"文件存在: {file_path.exists()}")
                return APIResponse.error(f"文件发送失败: {str(e)}", 500)
            
    except Exception as e:
        api_service.logger.error(f"下载音乐异常: {e}\n{traceback.format_exc()}")
        return APIResponse.error(f"下载异常: {str(e)}", 500)

@app.route('/api/info', methods=['GET'])
def api_info():
    """API信息接口"""
    try:
        info = {
            'name': '网易云音乐API服务',
            'version': '2.0.0',
            'description': '提供网易云音乐相关API服务',
            'endpoints': {
                '/health': 'GET - 健康检查',
                '/song': 'GET/POST - 获取歌曲信息',
                '/search': 'GET/POST - 搜索音乐',
                '/playlist': 'GET/POST - 获取歌单详情',
                '/album': 'GET/POST - 获取专辑详情',
                '/download': 'GET/POST - 下载音乐',
                '/api/info': 'GET - API信息'
            },
            'supported_qualities': [
                'standard', 'exhigh', 'lossless', 
                'hires', 'sky', 'jyeffect', 'jymaster'
            ],
            'config': {
                'downloads_dir': str(api_service.downloads_path.absolute()) if api_service else 'unknown',
                'max_file_size': f"{config.max_file_size // (1024*1024)}MB",
                'request_timeout': f"{config.request_timeout}s"
            }
        }
        
        return APIResponse.success(info, "API信息获取成功")
        
    except Exception as e:
        if api_service:
            api_service.logger.error(f"获取API信息异常: {e}")
        return APIResponse.error(f"获取API信息失败: {str(e)}", 500)

def start_api_server():
    """启动API服务器"""
    try:
        print("\n" + "="*60)
        print("🚀 网易云音乐API服务启动中...")
        print("="*60)
        
        # 初始化服务
        if not initialize_api_service():
            print("❌ 服务初始化失败，请检查错误信息")
            input("按回车键退出...")
            return
        
        config = APIConfig()
        
        print(f"📡 服务地址: http://{config.host}:{config.port}")
        print(f"📁 下载目录: {api_service.downloads_path.absolute()}")
        print(f"📋 日志级别: {config.log_level}")
        print("\n📚 API端点:")
        print(f"  ├─ GET  /health        - 健康检查")
        print(f"  ├─ POST /song          - 获取歌曲信息")
        print(f"  ├─ POST /search        - 搜索音乐")
        print(f"  ├─ POST /playlist      - 获取歌单详情")
        print(f"  ├─ POST /album         - 获取专辑详情")
        print(f"  ├─ POST /download      - 下载音乐")
        print(f"  └─ GET  /              - 服务状态")
        print("\n🎵 支持的音质:")
        print(f"  standard, exhigh, lossless, hires, sky, jyeffect, jymaster")
        print("="*60)
        print(f"⏰ 启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🌟 服务已就绪，等待请求...\n")
        
        # 启动Flask应用
        app.run(
            host=config.host,
            port=config.port,
            debug=config.debug,
            threaded=True
        )
        
    except KeyboardInterrupt:
        print("\n\n👋 服务已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("详细错误信息:")
        traceback.print_exc()
        input("按回车键退出...")


if __name__ == '__main__':
    start_api_server()