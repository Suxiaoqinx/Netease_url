# ！声明 ！
本项目为开源软件，遵循MIT许可证。任何个人或组织均可自由使用、修改和分发本项目的源代码。然而，我们明确声明，本项目及其任何衍生作品不得用于任何商业或付费项目。任何违反此声明的行为都将被视为对本项目许可证的侵犯。我们鼓励大家在遵守开源精神和许可证的前提下，积极贡献和分享代码。

# 网易云无损解析使用方法
先安装 文件所需要的依赖模块 
pip install -r requirements.txt
再运行main.py文件即可

# 环境要求
Python >= 3

## GUI模式参数
python main.py 
|  参数列表  | 参数说明 |
|  ----  | ---- |
| --mode | api 或 gui|
| --level | 音质参数(请看下方音质说明) |
| --url |  解析获取到的网易云音乐地址 |

完整请求 python main.py --mode gui --url 音乐地址 --level 音质

## API模式参数列表

请求链接选择 http://ip:port/Song_V1 

请求方式 GET & POST

|  参数列表  | 参数说明 |
|  ----  | ---- |
| url & ids | 解析获取到的网易云音乐地址  *任选其一|
| level | 音质参数(请看下方音质说明) |
| type | 解析类型 json down text *任选其一 |

# docker-compose一键部署

## 修改参数

部署前，可以根据需要修改`.env`文件中的环境变量

默认端口为`5000`，如果需要修改，请在`docker-compose.yml`文件中修改`ports`变量

例如，如果需要将端口修改为`8080`，请将以下代码：

```yaml
ports:
  - "8080:5000"
```

## docker-compose一键启动

```bash
docker-compose up -d
```

# 音质说明
standard(标准音质), exhigh(极高音质), lossless(无损音质), hires(Hi-Res音质), jyeffect(高清环绕声), sky(沉浸环绕声), jymaster(超清母带)

黑胶VIP音质选择 standard, exhigh, lossless, hires, jyeffect <br> <br>
黑胶SVIP音质选择 sky, jymaster

# 演示站点
[在线解析](https://api.toubiec.cn/wyapi.html)

# 注意事项
请先在cookie.txt文件内填入黑胶会员账号的cookie 才可以解析！
Cookie格式为↓
MUSIC_U=你获取到的MUSIC_U值;os=pc;appver=8.9.70; 完整填入cookie.txt即可！
具体值在cookie.txt里面就有 替换一下就行了

# 感谢
[Ravizhan](https://github.com/ravizhan)

# 反馈方法
请在Github的lssues反馈 或者到我[博客](https://www.toubiec.cn)反馈
