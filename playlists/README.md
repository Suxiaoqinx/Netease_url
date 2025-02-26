## 介绍

该脚本能够批量下载歌单中的歌曲，并且将歌曲信息写入MP3文件的元数据中（仅支持MP3，标准音质和高音质）

目前使用演示站点的url，后期可以会进一步完善。现在需要可以自行改动

## 项目配置
项目根目录下运行该命令安装依赖
```bash
pip install -r requirements.txt
```


## 获取歌曲url
1. 浏览器打开[网易云官网](https://music.163.com/#/playlist)
2. 选择自己的歌单
3. 在对应的歌单列表的某一首歌上右击，点检查
4. 弹出开发者工具面板中切换到控制台页面（一般为第二个选项）
5. 将下面的脚本粘贴进控制台，回车
6. 复制整个输出内容到当前项目下的 `settings.json`文件（替换原来的内容）
7. 可以自行更改`settings.json`中的`level`和`savePath`两个参数，以调整歌曲下载的音质和保存位置
```js
const settings = {
    "level": "exhigh",
    "savePath": "./success",
    "packPath": "./pack"
}
let spans;
let url = [];

spans = document.querySelectorAll(".ttc>.txt");
spans.forEach((span) => {
  // 在每个 <span> 内选择 <a> 元素
  const link = span.querySelector("a");
  if (link) {
    url.push(link.href)
  } else {
    console.log("No <a> tag found in this <span> tag.");
  }
});

settings['songs'] = url
console.log(JSON.stringify(settings, null, 2));
```

## 下载歌曲
> 提示：前提条件，完成项目配置，以及settings.json的内容
>

执行parse.py
```bash
python parse.py
```

等待进度条走完后，检查新生成的`errorList.json`其中记录着失败的歌曲，`completedList.json`记录着全部成功的歌曲。

自行检查`errorList.json`、`completedList.json`中的数据，当前success下已经有了对应的歌曲文件

## 歌曲信息打包
> 该步骤将success中下载的歌曲数据（封面-作者）等相关数据打包到MP3文件中
>
> 如不需要相关信息可以跳过此步骤

```bash
python pack.py
```