# ！声明 ！
本项目为开源软件，遵循MIT许可证。任何个人或组织均可自由使用、修改和分发本项目的源代码。然而，我们明确声明，本项目及其任何衍生作品不得用于任何商业或付费项目。任何违反此声明的行为都将被视为对本项目许可证的侵犯。我们鼓励大家在遵守开源精神和许可证的前提下，积极贡献和分享代码。

# 网易云无损解析使用方法
先安装 文件所需要的依赖模块 
pip install -r requirements.txt
再运行main.py文件即可

# 环境要求
Python >= 3

# 请求示例

如图箭头显示

![url链接](https://raw.githubusercontent.com/Suxiaoqinx/Netease_url/main/620598f6-a651-4698-bfbc-7a5a904a8609.png)

## 参数列表

请求链接选择 http://ip:port/Song_V1 

请求方式 GET & POST

|  参数列表  | 参数说明 |
|  ----  | ---- |
| url & ids | 解析获取到的网易云音乐地址  *任选其一|
| level | 音质参数(请看下方音质说明) |
| type | 解析类型 json down text *任选其一 |

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
