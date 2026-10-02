# checksum-tree

为目录树创建或校验 SHA-256 清单。只读取普通文件，不跟随符号链接，也不会修改被扫描目录。

## 使用

需要 Python 3.8+，不安装依赖。

~~~sh
python checksum_tree.py create ./release-folder --output ./release-folder.sha256.jsonl
python checksum_tree.py verify ./release-folder ./release-folder.sha256.jsonl
~~~

省略 `--output` 时，清单写到标准输出。指定文件时，目标必须尚不存在，且必须位于扫描目录之外。清单按相对路径排序，以 JSON Lines 保存路径、大小和摘要；校验时也会报告新增、缺失或内容变化的文件。符号链接会跳过。读取失败会让清单创建中止并以非零状态退出。

退出状态：0 表示成功，1 表示扫描不完整或清单有差异，2 表示参数、清单或 I/O 错误，130 表示中断。

## 许可

MIT，见 [LICENSE](LICENSE)。

## Linux x86_64 下载

- [单文件版](https://github.com/506058115-cmd/checksum-tree/releases/download/v1.0.0/checksum-tree-linux-x86_64-onefile.tar.gz)
- [目录版](https://github.com/506058115-cmd/checksum-tree/releases/download/v1.0.0/checksum-tree-linux-x86_64-onedir.tar.gz)
- [v1.0.0 Release 页面](https://github.com/506058115-cmd/checksum-tree/releases/tag/v1.0.0)

压缩包附带构建信息和依赖许可证；Release 另附 SHA-256 校验文件。构建目标为 GNU/Linux x86_64。较旧发行版可能需要兼容的 glibc。
