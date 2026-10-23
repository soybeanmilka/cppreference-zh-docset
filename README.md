# BUILD

# 中文 cppreference → Zeal / Dash docset 生成器

把 cppreference 中文离线书（`html-book-*.tar.xz`）转换成 **Zeal / Dash / Velocity** 能装的 `.docset`。

> 官方 Zeal 源里 981 个 docset **没有任何中文 C++**（中文只有 ECharts、eggjs、MyBatis、PHP、Python、Swoole、Salyut、Vim）。中文 cppreference 官方归档停在 2019-06-07，太旧。所以只能自己造。

## 为什么要转换，不能直接装

中文离线书（来自 [myfreeer/cppreference2mshelp](https://github.com/myfreeer/cppreference2mshelp) 的 release，内容源是 cppreference.cn）只是**给浏览器看的裸目录**，直接丢进 Zeal 的 docsets 文件夹是没用的：

| 问题 | 后果 |
|---|---|
| 没有 `docSet.dsidx` | Zeal 搜不到任何东西 |
| 自带的 devhelp2 索引里 14342 个 link 全是 `404` 占位 | 没法照着建索引，只能从 HTML 抽标题 |
| 相对链接层级冗余 `../../../../zh.cppreference.com/../../../../common/x.css` | 样式、图片、跳转全丢 |
| 运算符页 href 是 URL 编码的 `operator%3D.html`，盘上是 `operator=.html` | `==`、`+`、`""i` 这类页面的链接全断 |
| 还有一层二次编码 `operator%2522%2522i.html` | 同上，得更解一轮 |

这个脚本把这些全部处理掉。

## 用法

```bash
# 1. 下载中文离线书（约 8.6 MB）
#    https://github.com/myfreeer/cppreference2mshelp/releases/latest
#    资产名形如 html-book-20260502.tar.xz

# 2. 转换（只需要 Python 3.7+ 标准库，无第三方依赖）
python build_docset.py html-book-20260502.tar.xz ./out

# 3. 校验
python verify_docset.py ./out/中文C++参考手册.docset
```

输出：

```
[1/4] unpacked: 6734 html pages, 174 shared assets
[2/4] indexed 33032 entries [('Section', 26642), ('Guide', 6036), ('Operator', 698)]
[3/4] rewrote links in 6720 pages
[4/4] done: 370.1 MB -> ./out/中文C++参考手册.docset
```

校验：

```
索引条目 33032 条 [('Guide', 6036), ('Operator', 698), ('Section', 26298)]
页面 6734 个
站内 html 跳转 858375 条，落不到 0 条 (0.00%)
资源引用 20492 条，落不到 116 条 (0.57%)
```

那 116 条是页面里 `File:math-atan2.svg` 这类**维基文件占位**——中文站本来就没有这些图的本地副本，在线看也是裂的，不影响正文。

## 安装

把生成的 `中文C++参考手册.docset` 整个目录复制进：

| 平台 | 路径 |
|---|---|
| Windows (Zeal) | `%LOCALAPPDATA%\Zeal\Zeal\docsets\` |
| macOS (Dash) | `~/Library/Application Support/Dash/DocSets/` |
| Linux (Zeal) | `~/.local/share/Zeal/Zeal/docsets/` |

然后重启 Zeal。注意是 **LOCALAPPDATA**，不是 APPDATA。

## 参数

```
python build_docset.py <tarball> <outdir>
    --name         docset 目录名，默认 中文C++参考手册.docset
    --site         书树挂载用的目录名，默认 zh.cppreference.com
    --root         书根目录在压缩包内的路径，默认 reference/zh
    --index-page   默认打开的页面，默认 cpp.html
```

`--site` / `--root` 是为了让脚本能处理别的 devhelp 风格 HTML 书。换成非 cppreference 的包时，记得再改 `Info.plist` 里的 `CFBundleIdentifier`（在 `build_docset.py` 的 `finish()` 里）。

## 踩过的坑（别人照做时最容易翻车的地方）

1. **`common/` 必须平铺在 `Documents/` 根下**，不能塞进 `Documents/zh.cppreference.com/`。页面里写的是 `../../../common/x.css`，从 `zh.cppreference.com/cpp/container/` 往上三级正好落在 `Documents/`，多套一层就全丢样式。
2. **匹配链接前必须先 `urllib.parse.unquote`**，否则 `operator%3D.html` 找不到 `operator=.html`。第一版就是这么漏了 4469 条链接。
3. **替换图片路径时新路径不能含会被正则再次命中的模式**（比如新路径里还有 `File`/`Image` 字样），要一次性 `re.sub` 做完。
4. **别用 `python -c @"..."@` 传含 `\\` / `?mode=ro` / 引号的多行代码**，PowerShell 会报 `SyntaxError: unexpected character after line continuation character`。写成 `.py` 再跑。

## 中英对照着用

装完会和英文 `C++.docset`（`https://kapeli.com/feeds/C++.tgz`，约 580 MB）共存。同一个主题搜出来两条，**英文看函数签名和示例（最新），中文看文字描述**，最省力。

## 版权

本仓库**只包含转换脚本，不包含任何 cppreference 内容**。生成的 HTML 版权归 cppreference  contributors（CC-BY-SA 3.0 / GFDL），请自行从上游 release 下载原始包并自行生成。

## License

MIT
