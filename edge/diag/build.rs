//! 动态链接 libcnn_compute：设置了 EDGE_DIAG_LIB 时注入链接指令
//! （dylib=cnn_compute + 该目录搜索路径；Docker 交叉构建时设）。
//! 未设置时（本机无 .so）不注入，`cargo check` / `cargo test --lib`
//! 可离线运行，完整链接留给 Docker 构建环境。

fn main() {
    if let Ok(dir) = std::env::var("EDGE_DIAG_LIB") {
        println!("cargo:rustc-link-lib=dylib=cnn_compute");
        println!("cargo:rustc-link-search=native={dir}");
    }
    println!("cargo:rerun-if-env-changed=EDGE_DIAG_LIB");
    println!("cargo:rerun-if-changed=build.rs");
}
