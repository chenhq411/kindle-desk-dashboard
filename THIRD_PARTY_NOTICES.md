# 第三方依赖与工具说明

项目自主代码采用根目录 MIT 许可。本仓库没有打包第三方 Python 库二进制；安装时从 Python 包源取得依赖，其原始许可证和版权声明仍适用。下表依据发布准备时本机安装包元数据记录，不能代替其发行包内完整声明。Pillow 自身及其依赖组件的具体声明以 Pillow 发行物为准。

| Python 包（含开发测试与当前环境传递依赖） | 本机版本 | 元数据许可 |
|---|---|---|
| [annotated-doc](https://pypi.org/project/annotated-doc/0.0.4/) | 0.0.4 | MIT |
| [annotated-types](https://pypi.org/project/annotated-types/0.7.0/) | 0.7.0 | License :: OSI Approved :: MIT License |
| [anyio](https://pypi.org/project/anyio/4.13.0/) | 4.13.0 | MIT |
| [certifi](https://pypi.org/project/certifi/2026.5.20/) | 2026.5.20 | MPL-2.0 |
| [click](https://pypi.org/project/click/8.4.1/) | 8.4.1 | BSD-3-Clause |
| [colorama](https://pypi.org/project/colorama/0.4.6/) | 0.4.6 | License :: OSI Approved :: BSD License |
| [fastapi](https://pypi.org/project/fastapi/0.136.3/) | 0.136.3 | MIT |
| [h11](https://pypi.org/project/h11/0.16.0/) | 0.16.0 | MIT |
| [httpcore](https://pypi.org/project/httpcore/1.0.9/) | 1.0.9 | BSD-3-Clause |
| [httpx](https://pypi.org/project/httpx/0.28.1/) | 0.28.1 | BSD-3-Clause |
| [idna](https://pypi.org/project/idna/3.17/) | 3.17 | BSD-3-Clause |
| [pillow](https://pypi.org/project/pillow/12.2.0/) | 12.2.0 | MIT-CMU |
| [psutil](https://pypi.org/project/psutil/7.2.2/) | 7.2.2 | BSD-3-Clause |
| [pydantic](https://pypi.org/project/pydantic/2.13.4/) | 2.13.4 | MIT |
| [pydantic_core](https://pypi.org/project/pydantic_core/2.46.4/) | 2.46.4 | MIT |
| [starlette](https://pypi.org/project/starlette/1.2.1/) | 1.2.1 | BSD-3-Clause |
| [typing-inspection](https://pypi.org/project/typing-inspection/0.4.2/) | 0.4.2 | MIT |
| [typing_extensions](https://pypi.org/project/typing_extensions/4.15.0/) | 4.15.0 | PSF-2.0 |
| [uvicorn](https://pypi.org/project/uvicorn/0.48.0/) | 0.48.0 | BSD-3-Clause |

requirements.txt 与 requirements-dev.txt 锁定直接依赖；传递依赖由安装器解析，上表是本次环境记录，不表示完整环境锁定。若将来提供 exe/安装器，应重新审查实际包含的库和二进制，并随包保留它们的 LICENSE/NOTICE。

外部工具不包含在本项目中，也不因本项目 MIT 许可而改变其许可：

- Windows、OpenSSH 客户端及 NVIDIA SMI 由操作系统/驱动提供。
- Kindle 固件及系统 eips 由设备提供，未复制到仓库。
- USBNetwork、Dropbear、MRPI、越狱工具由其维护者独立分发。
- 微软雅黑从本机 Windows 字体目录读取，仓库不附带字体。
- Codex App Server 从官方本地安装取得，其认证和使用受官方条款约束。

研究参考见 docs/OPEN_SOURCE_AUDIT.md。没有明确许可证的候选仓库不复制代码；本仓库也不包含 research 目录下的下载内容。
