# 网易云无损解析使用方法
先安装 文件所需要的依赖模块 
pip install -r requirements.txt
再运行main.py文件即可

# 环境要求
Python >= 3

# 参数列表
http://127.0.0.1:5000/Song_V1?ids=(填写歌曲链接或者ID)&level=(填写需要解析的音质)&type=(down json text)

黑胶VIP音质选择 standard, exhigh, lossless, hires, jyeffect
黑胶SVIP音质选择 sky, jymaster

# 音质说明
standard(标准音质), exhigh(极高音质), lossless(无损音质), hires(Hi-Res音质), jyeffect(高清环绕声), sky(沉浸环绕声), jymaster(超清母带)

# 演示列表
[在线解析](https://api.toubiec.cn/wyapi.html)

# 注意事项
请先在cookie.txt文件内填入黑胶会员账号的cookie 才可以解析！
Cookie格式为↓
MUSIC_U=你获取到的MUSIC_U值;appver=8.9.70; 完整填入cookie.txt即可！
具体值在cookie.txt里面就有 替换一下就行了

# 感谢
[Ravizhan](https://github.com/ravizhan)

# 反馈方法
请在Github的lssues反馈 或者到我[博客](https://www.toubiec.cn)反馈
