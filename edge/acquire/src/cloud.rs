use crate::config::Config;
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use std::{fs::File, io::Read, path::Path, time::Duration};

#[derive(Clone)]
pub struct Cloud {
    agent: ureq::Agent,
    upload: ureq::Agent,
    base: String,
    key: String,
    pub id: String,
}
impl Cloud {
    pub fn new(config: &Config, key: String) -> Result<Self> {
        ensure!(
            !key.is_empty() && !key.contains(['\r', '\n']),
            "密钥为空或含换行符"
        );
        let agent = |seconds| {
            ureq::Agent::config_builder()
                .timeout_global(Some(Duration::from_secs(seconds)))
                .timeout_connect(Some(Duration::from_secs(3)))
                .max_redirects(0)
                .build()
                .into()
        };
        Ok(Self {
            agent: agent(config.http_timeout_seconds),
            upload: agent(config.upload_timeout_seconds),
            base: format!("{}/api/acquisition", config.cloud_url.trim_end_matches('/')),
            key,
            id: config.agent_id.clone(),
        })
    }
    fn data(mut response: ureq::http::Response<ureq::Body>) -> Result<Value> {
        ensure!(
            response.status().is_success(),
            "云端拒绝请求: {}",
            response.status()
        );
        let value: Value =
            serde_json::from_reader(response.body_mut().as_reader().take(1024 * 1024))
                .context("云端 JSON 响应无效或超过 1MiB")?;
        ensure!(value["code"] == 200, "云端业务响应不是成功状态");
        Ok(value.get("data").cloned().unwrap_or(Value::Null))
    }
    pub fn get(&self, path: &str) -> Result<Value> {
        Self::data(
            self.agent
                .get(format!("{}{path}", self.base))
                .header("X-Edge-Key", &self.key)
                .call()?,
        )
    }
    pub fn post(&self, path: &str, value: &Value) -> Result<Value> {
        Self::data(
            self.agent
                .post(format!("{}{path}", self.base))
                .header("X-Edge-Key", &self.key)
                .send_json(value)?,
        )
    }
    pub fn control(&self) -> Result<Value> {
        self.get(&format!("/agents/{}/control", self.id))
    }
    pub fn heartbeat(&self, state: &Value) -> Result<()> {
        self.post(
            "/agents/heartbeat",
            &json!({"agent_id":self.id,"source":"dc24_tcp","state":state}),
        )?;
        Ok(())
    }
    pub fn frames(&self, session: &str, start: u64, sequence: u16, data: &[u8]) -> Result<()> {
        let url = format!(
            "{}/sessions/{session}/frames?agent_id={}&start={start}&sequence={sequence}",
            self.base, self.id
        );
        Self::data(
            self.agent
                .post(url)
                .header("X-Edge-Key", &self.key)
                .header("Content-Type", "application/octet-stream")
                .send(data)?,
        )?;
        Ok(())
    }
    pub fn state(&self, session: &str, value: &Value) -> Result<()> {
        self.post(
            &format!("/sessions/{session}/state?agent_id={}", self.id),
            value,
        )?;
        Ok(())
    }
    pub fn upload_file(&self, job: &str, name: &str, path: &Path) -> Result<()> {
        let file = File::open(path)?;
        let size = file.metadata()?.len();
        let url = format!(
            "{}/jobs/{job}/stream-files/{name}?agent_id={}",
            self.base, self.id
        );
        Self::data(
            self.upload
                .put(url)
                .header("X-Edge-Key", &self.key)
                .header("Content-Type", "application/octet-stream")
                .header("Content-Length", size.to_string())
                .send(file)?,
        )?;
        Ok(())
    }
}
