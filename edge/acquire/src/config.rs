use anyhow::{bail, Context, Result};
use serde::Deserialize;
use std::{net::IpAddr, path::PathBuf};

#[derive(Clone, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub cloud_url: String,
    pub agent_id: String,
    pub api_key_env: String,
    pub listen_ip: IpAddr,
    pub device_ip: IpAddr,
    pub port: u16,
    pub storage: PathBuf,
    pub mode: Mode,
    pub sample_rate: Option<u32>,
    pub duration_seconds: Option<u64>,
    pub interval_seconds: Option<u64>,
    pub min_free_bytes: u64,
    pub http_timeout_seconds: u64,
    pub upload_timeout_seconds: u64,
    pub device_wait_seconds: u64,
    pub data_timeout_seconds: u64,
}

#[derive(Clone, Copy, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    Cloud,
    Periodic,
    Continuous,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            cloud_url: String::new(),
            agent_id: "dc24-pi".into(),
            api_key_env: "EDGE_API_KEY".into(),
            listen_ip: "192.168.2.100".parse().unwrap(),
            device_ip: "192.168.2.101".parse().unwrap(),
            port: 6800,
            storage: "/var/lib/dc24-edge".into(),
            mode: Mode::Cloud,
            sample_rate: None,
            duration_seconds: None,
            interval_seconds: None,
            min_free_bytes: 256 * 1024 * 1024,
            http_timeout_seconds: 4,
            upload_timeout_seconds: 180,
            device_wait_seconds: 45,
            data_timeout_seconds: 10,
        }
    }
}

impl Config {
    pub fn load(path: &std::path::Path) -> Result<Self> {
        Self::from_json(&std::fs::read_to_string(path).context("读取配置失败")?)
    }
    /// FFI 入口共用同一份配置文本（config.json 全 schema；网络核心只使用其中设备链路字段）。
    pub fn from_json(text: &str) -> Result<Self> {
        let value: Self = serde_json::from_str(text).context("配置格式错误")?;
        value.validate()?;
        Ok(value)
    }
    pub fn validate(&self) -> Result<()> {
        let url: ureq::http::Uri = self.cloud_url.parse().context("cloud_url 无效")?;
        if !matches!(url.scheme_str(), Some("http" | "https"))
            || url.authority().is_none()
            || url.path() != "/"
            || url.query().is_some()
            || url.authority().unwrap().as_str().contains('@')
        {
            bail!("cloud_url 必须是无账号、路径或查询参数的 HTTP(S) 服务根地址");
        }
        if !valid_agent(&self.agent_id)
            || self.api_key_env.is_empty()
            || !self.storage.is_absolute()
        {
            bail!("agent_id 无效、密钥环境变量为空或 storage 不是绝对路径");
        }
        if self.listen_ip.is_ipv4() != self.device_ip.is_ipv4() || self.port == 0 {
            bail!("设备和监听 IP 地址族必须一致，端口不能为零");
        }
        if self.http_timeout_seconds == 0
            || self.upload_timeout_seconds == 0
            || self.device_wait_seconds == 0
            || self.data_timeout_seconds == 0
        {
            bail!("超时必须大于零");
        }
        if self.mode != Mode::Cloud {
            crate::protocol::profile(self.sample_rate.context("本地调度模式需要 sample_rate")?)?;
        }
        if self.mode == Mode::Periodic
            && (self.duration_seconds.unwrap_or(0) == 0 || self.interval_seconds.unwrap_or(0) == 0)
        {
            bail!("periodic 模式需要正数 duration_seconds 和 interval_seconds");
        }
        Ok(())
    }
}

pub fn valid_agent(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 64
        && id
            .bytes()
            .all(|v| v.is_ascii_alphanumeric() || b"_.-".contains(&v))
}
pub fn valid_id(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}
