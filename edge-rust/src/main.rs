use anyhow::{Context, Result};
use dc24_edge::{config::Config, runtime};
use std::{
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};

fn main() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let first = args.next().unwrap_or_else(|| "--help".into());
    if first == "--help" || first == "-h" {
        println!(
            "dc24-edge --config <config.json> [--check]\n\
            --check: validate configuration only; does not connect, sample or upload.\n\
            Acquisition settings are controlled by cloud sessions or configuration.\n\
            Secret is read from EDGE_API_KEY (or api_key_env); never from command arguments."
        );
        return Ok(());
    }
    anyhow::ensure!(
        first == "--config",
        "使用 --config 指定配置文件，或 --help 查看帮助"
    );
    let path = PathBuf::from(args.next().context("缺少配置文件路径")?);
    let tail: Vec<_> = args.collect();
    anyhow::ensure!(tail.is_empty() || tail == ["--check"], "未知命令参数");
    Config::load(&path)?;
    if !tail.is_empty() {
        println!("PASS: configuration valid; no hardware or cloud operations performed.");
        return Ok(());
    }
    let quit = Arc::new(AtomicBool::new(false));
    let signal = quit.clone();
    ctrlc::set_handler(move || signal.store(true, Ordering::Relaxed))?;
    runtime::run(&path, None, quit)
}
