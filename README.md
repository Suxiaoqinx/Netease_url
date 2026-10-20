# 网易云音乐无损解析

<div align="center">

![GitHub stars](https://img.shields.io/github/stars/Suxiaoqinx/Netease_url?style=flat-square)
![GitHub forks](https://img.shields.io/github/forks/Suxiaoqinx/Netease_url?style=flat-square)
![GitHub issues](https://img.shields.io/github/issues/Suxiaoqinx/Netease_url?style=flat-square)
![GitHub license](https://img.shields.io/github/license/Suxiaoqinx/Netease_url?style=flat-square)

**功能强大的网易云音乐解析工具**

支持歌曲搜索 | 单曲解析 | 歌单解析 | 专辑解析 | 音乐下载 | 批量下载

[在线体验](https://wyapi.toubiec.cn) • [使用文档](./使用文档.md) • [问题反馈](https://github.com/Suxiaoqinx/Netease_url/issues)

</div>

---

## 授权说明 / License

本仓库中的源代码基于 **MIT License** 开源，任何人可按 MIT 条款使用、修改和分发本仓库代码。

⚠️ 注意：
线上体验版本（Online Demo / 官网体验页）是作者另行独立开发的闭源产品，
不属于本仓库 MIT 代码的一部分。
线上版本的权利声明以对应产品页面为准（可能标注 All rights reserved）。

简单说：
- 本仓库代码 → MIT
- 线上体验站 → 闭源，独立作品

## ✨ 功能特性

### 🎵 核心功能
- **🔍 歌曲搜索**：支持关键词搜索网易云音乐库中的歌曲
- **🎧 单曲解析**：解析单首歌曲的详细信息和下载链接
- **📋 歌单解析**：批量解析歌单中的所有歌曲信息
- **💿 专辑解析**：批量解析专辑中的所有歌曲信息
- **⬇️ 音乐下载**：支持多种音质的音乐文件下载
- **📦 批量下载**：歌单 / 专辑一键批量下载，后台并发、实时进度、失败自动降级音质，支持打包 ZIP

### 🎼 音质支持
- `standard`：标准音质 (128kbps)
- `exhigh`：极高音质 (320kbps)
- `lossless`：无损音质 (FLAC)
- `hires`：Hi-Res音质 (24bit/96kHz)
- `jyeffect`：高清环绕声
- `sky`：沉浸环绕声
- `jymaster`：超清母带

### 🌐 使用方式
- **Web界面**：直观友好的网页操作界面
- **RESTful API**：完整的API接口支持
- **批量处理**：支持歌单和专辑的批量解析与批量下载
- **多格式支持**：支持ID和链接多种输入格式

---

## 🚀 快速开始

### 环境要求
- Python 3.7+
- 网易云音乐黑胶会员账号

### 安装步骤

#### 1. 克隆项目
```bash
git clone https://github.com/Suxiaoqinx/Netease_url.git
cd Netease_url
```

#### 2. 安装依赖
```bash
pip install -r requirements.txt
```

#### 3. 配置Cookie
在 `cookie.txt` 文件中填入黑胶会员账号的Cookie：

> 💡 **获取Cookie方法**：登录网易云音乐网页版 → F12开发者工具 → Network标签页 → 复制任意请求的Cookie值


> 杜比全景声音质需要设备支持，不同的设备可能会返回不同码率的 url cookie 需要传入os=pc保证返回正常码率的 url

#### 4. 启动服务
```bash
python main.py
```

#### 5. 访问界面
打开浏览器访问：`http://localhost:5000`

### 🐳 Docker部署

```bash
# 使用Docker Compose
docker-compose up -d

# 或使用Docker
docker build -t netease-music-api .
docker run -d -p 5000:5000 netease-music-api
```

---

## 📖 使用指南

### Web界面使用

#### 🔍 歌曲搜索
1. 选择功能：**歌曲搜索**
2. 输入关键词（歌曲名、歌手名等）
3. 点击**搜索**按钮
4. 在搜索结果中点击**解析**或**下载**按钮

#### 🎧 单曲解析
1. 选择功能：**单曲解析**
2. 输入歌曲ID或网易云音乐链接
   - 支持格式：`1234567890` 或 `https://music.163.com/song?id=1234567890`
3. 点击**解析**按钮查看歌曲信息

#### 📋 歌单解析
1. 选择功能：**歌单解析**
2. 输入歌单ID或网易云音乐歌单链接
   - 支持格式：`1234567890` 或 `https://music.163.com/playlist?id=1234567890`
3. 点击**解析**按钮查看歌单中所有歌曲
4. 点击单首歌曲的**解析**或**下载**按钮
5. 勾选需要下载的歌曲（默认全选）并选择音质，点击**批量下载全部**或**下载选中**
6. 在批量下载面板查看实时进度；完成后可**打包下载 ZIP**，也可逐首下载

#### 💿 专辑解析
1. 选择功能：**专辑解析**
2. 输入专辑ID或网易云音乐专辑链接
   - 支持格式：`1234567890` 或 `https://music.163.com/album?id=1234567890`
3. 点击**解析**按钮查看专辑中所有歌曲
4. 点击单首歌曲的**解析**或**下载**按钮
5. 勾选需要下载的歌曲（默认全选）并选择音质，点击**批量下载全部**或**下载选中**
6. 在批量下载面板查看实时进度；完成后可**打包下载 ZIP**，也可逐首下载

#### ⬇️ 音乐下载
1. 选择功能：**音乐下载**
2. 输入歌曲ID或链接
3. 选择音质（标准/极高/无损/Hi-Res等）
4. 点击**下载**按钮

### 支持的链接格式

```
# 歌曲链接
https://music.163.com/song?id=1234567890
https://music.163.com/#/song?id=1234567890

# 歌单链接
https://music.163.com/playlist?id=1234567890
https://music.163.com/#/playlist?id=1234567890

# 专辑链接
https://music.163.com/album?id=1234567890
https://music.163.com/#/album?id=1234567890

# 直接使用ID
1234567890
```

## 🔌 API接口文档

### 基础信息
- **Base URL**: `http://localhost:5000`
- **请求方式**: GET / POST
- **响应格式**: JSON

### 接口列表

#### 1. 健康检查
```http
GET /health
```
**响应示例**:
```json
{
  "status": "ok",
  "message": "Service is running"
}
```

#### 2. 歌曲搜索
```http
POST /search
Content-Type: application/json

{
  "keywords": "周杰伦 稻香",
  "limit": 10
}
```
**响应示例**:
```json
{
  "code": 200,
  "result": {
    "songs": [
      {
        "id": 185668,
        "name": "稻香",
        "artists": ["周杰伦"],
        "album": "魔杰座",
        "duration": 223000
      }
    ]
  }
}
```

#### 3. 单曲解析
```http
POST /song
Content-Type: application/json

{
  "id": "185668"
}
```

#### 4. 歌单解析
```http
POST /playlist
Content-Type: application/json

{
  "id": "123456789"
}
```

#### 5. 专辑解析
```http
POST /album
Content-Type: application/json

{
  "id": "123456789"
}
```

#### 6. 音乐下载
```http
POST /download
Content-Type: application/json

{
  "id": "185668",
  "quality": "lossless"
}
```
**响应**: 直接返回音频文件流

#### 7. 批量下载

批量下载采用「创建任务 + 轮询进度」的方式，下载在后台线程池中进行，不会阻塞请求。

**创建任务**
```http
POST /batch/download
Content-Type: application/json

{
  "type": "playlist",
  "id": "123456789",
  "quality": "lossless",
  "fallback": true
}
```

`type` 支持以下取值：

| type | 说明 | 必填参数 |
| --- | --- | --- |
| `playlist` | 下载整个歌单 | `id`（歌单 ID 或链接） |
| `album` | 下载整个专辑 | `id`（专辑 ID 或链接） |
| `tracks` | 下载指定的歌曲数组 | `tracks` |
| `ids` | 下载指定的歌曲 ID 列表 | `ids`（逗号分隔） |

其他参数：
- `quality`：音质，默认 `lossless`
- `fallback`：高音质不可用时是否自动降级重试，默认 `true`
- `name`：任务名称，默认使用歌单 / 专辑名

`tracks` 示例：
```json
{
  "type": "tracks",
  "quality": "lossless",
  "tracks": [
    {"id": 185668, "name": "稻香", "artists": "周杰伦", "album": "魔杰座"}
  ]
}
```

**响应示例**（节选）：
```json
{
  "status": 200,
  "success": true,
  "message": "批量下载任务已创建",
  "data": {
    "job_id": "4f1c...",
    "name": "我喜欢的音乐",
    "quality": "lossless",
    "status": "running",
    "total": 30,
    "success": 0,
    "skipped": 0,
    "failed": 0,
    "progress": 0,
    "tracks": [
      {
        "index": 0,
        "id": "185668",
        "name": "稻香",
        "status": "pending",
        "progress": 0,
        "file_url": null
      }
    ]
  }
}
```

**查询进度**
```http
GET /batch/status/<job_id>
```

**取消任务**
```http
POST /batch/cancel/<job_id>
```

**打包下载已完成文件**
```http
GET /batch/zip/<job_id>
```
返回 ZIP 文件流，只包含已下载完成（含此前已存在）的歌曲。ZIP 采用边读边发的方式生成，不会在磁盘上再生成一份和歌单等大的临时文件。

> ZIP 为流式响应，不支持断点续传 / 多线程分段下载，请使用浏览器自带的下载功能。若下载中断，文件会不完整，需要重新下载。

**下载任务中的单曲**
```http
GET /batch/file/<job_id>/<index>
```
`index` 为任务歌曲序号（从 0 开始）。

> 说明：单个任务最多 1000 首歌曲，默认 3 个并发下载。高音质失败时会按 `jymaster → hires → lossless → exhigh → standard` 的顺序自动降级（可通过 `fallback: false` 关闭）。任务状态保存在内存中，服务重启后任务列表清空，但已下载的音频文件仍保留在 `downloads` 目录。

---

## 音质参数说明

- `standard`：标准音质
- `exhigh`：极高音质
- `lossless`：无损音质
- `hires`：Hi-Res音质
- `jyeffect`：高清环绕声
- `sky`：沉浸环绕声
- `jymaster`：超清母带
- `dolby`：杜比全景声

> 黑胶VIP音质：standard, exhigh, lossless, hires, jyeffect  
> 黑胶SVIP音质：sky, jymaster, dolby

---

## Docker 一键部署

1. **修改参数**

   - 如需修改端口，请编辑 `.env` 或 `docker-compose.yml` 文件中的 `ports` 配置，例如：

     ```yaml
     ports:
       - "8080:5000"
     ```

2. **启动服务**

   ```bash
   docker-compose up -d
   ```

---

## 在线演示

[在线解析](https://wyapi.toubiec.cn/)

---

## 注意事项

- 必须使用黑胶会员账号的 Cookie 才能解析高音质资源。
- Cookie 格式请严格按照 `cookie.txt` 示例填写。

---

## 致谢

- [Ravizhan](https://github.com/ravizhan)

---

## 反馈与交流

- 在 Github [Issues](https://github.com/Suxiaoqinx/Netease_url/issues) 提交反馈
- 或访问 [我的博客](https://www.toubiec.cn)

---

欢迎 Star、Fork 和 PR！



