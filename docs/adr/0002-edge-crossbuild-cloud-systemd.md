# 部署架构:边端交叉编译容器,云端 systemd 不上 Docker

边端(Rust,目标树莓派)在 WSL Docker 内用树莓派同款环境交叉编译,产物(二进制)直接拷贝到树莓派运行,绝不在树莓派上编译;构建封装放在仓库级部署目录,Rust 项目自 `edge-rust/` 平移至 `edge/`(git mv,源码/Cargo 清单/锁文件内容零改动)。云端继续跑在阿里云 ECS,systemd + `uv sync` 管理,明确不引入 Docker——ECS 上只有这一套服务,容器化收益不抵额外复杂度。
