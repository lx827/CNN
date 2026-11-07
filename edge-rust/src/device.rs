use crate::{
    config::Config,
    protocol::{self, Frames},
};
use anyhow::{bail, ensure, Result};
use serde_json::{json, Value};
use std::{
    collections::VecDeque,
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub type Consume<'a> = dyn FnMut(&[u8], &VecDeque<Value>) -> Result<()> + 'a;

pub struct Link {
    stream: TcpStream,
    parser: Frames,
    last_heartbeat: Instant,
    pub events: VecDeque<Value>,
}
impl Link {
    pub fn accept(config: &Config, stop: &Arc<AtomicBool>) -> Result<Option<Self>> {
        let listener = TcpListener::bind(SocketAddr::new(config.listen_ip, config.port))?;
        listener.set_nonblocking(true)?;
        eprintln!(
            "监听 {}:{}，等待设备 {}",
            config.listen_ip, config.port, config.device_ip
        );
        let deadline = Instant::now() + Duration::from_secs(config.device_wait_seconds);
        while !stop.load(Ordering::Relaxed) {
            match listener.accept() {
                Ok((stream, addr)) if addr.ip() == config.device_ip => {
                    stream.set_read_timeout(Some(Duration::from_millis(100)))?;
                    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
                    stream.set_nodelay(true)?;
                    return Ok(Some(Self {
                        stream,
                        parser: Frames::default(),
                        events: VecDeque::new(),
                        last_heartbeat: Instant::now() - Duration::from_secs(2),
                    }));
                }
                Ok(_) => (),
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => (),
                Err(e) => return Err(e.into()),
            }
            ensure!(Instant::now() < deadline, "等待 DC24 连接超时");
            thread::sleep(Duration::from_millis(50));
        }
        Ok(None)
    }
    fn event(&mut self, direction: &str, code: u8, frame: &[u8]) {
        if self.events.len() == 100 {
            self.events.pop_front();
        }
        self.events.push_back(json!({"host_time_unix_ms":SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis(),
            "direction":direction,"command":format!("{code:02X}"),"hex":protocol::hex(frame)}));
    }
    pub fn send(&mut self, code: u8, payload: &[u8]) -> Result<()> {
        let frame = protocol::command(code, payload);
        self.stream.write_all(&frame)?;
        self.event("host_to_device", code, &frame);
        Ok(())
    }
    pub fn pump(&mut self, consume: &mut Consume<'_>) -> Result<Vec<Vec<u8>>> {
        if self.last_heartbeat.elapsed() >= Duration::from_secs(1) {
            self.stream.write_all(&[0])?;
            self.last_heartbeat = Instant::now();
        }
        let mut data = [0; 65536];
        let n = match self.stream.read(&mut data) {
            Ok(0) => bail!("设备断开 TCP 连接"),
            Ok(n) => n,
            Err(e)
                if matches!(
                    e.kind(),
                    std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut
                ) =>
            {
                return Ok(Vec::new())
            }
            Err(e) => return Err(e.into()),
        };
        let frames = self.parser.feed(&data[..n])?;
        for frame in &frames {
            if frame[3] == 0x80 {
                consume(frame, &self.events)?;
            } else {
                self.event("device_to_host", frame[3], frame);
            }
        }
        Ok(frames)
    }
    pub fn exchange(
        &mut self,
        code: u8,
        payload: &[u8],
        status: bool,
        consume: &mut Consume<'_>,
    ) -> Result<()> {
        self.send(code, payload)?;
        let deadline = Instant::now() + Duration::from_secs(5);
        while Instant::now() < deadline {
            for frame in self.pump(consume)? {
                if frame[3] == code {
                    ensure!(
                        !status || frame[4..frame.len() - 1] == [0],
                        "设备命令 {code:02x} 返回未知状态"
                    );
                    return Ok(());
                }
            }
        }
        bail!("设备命令 {code:02x} 应答超时")
    }
    pub fn pending(&self) -> usize {
        self.parser.pending()
    }
}
