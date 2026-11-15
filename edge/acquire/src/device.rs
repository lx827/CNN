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

/// 进程生命周期内只绑定一次的常驻监听（对齐原厂软件行为）。
/// Unix 设置 SO_REUSEADDR：上一会话主机主动关闭产生的 TIME_WAIT 不会再阻塞下一次 bind；
/// Windows 保持默认独占绑定（冲突即报错），与 Python 版 SO_EXCLUSIVEADDRUSE 行为一致。
pub fn bind_listener(config: &Config) -> Result<TcpListener> {
    let addr = SocketAddr::new(config.listen_ip, config.port);
    #[cfg(unix)]
    let listener = {
        use socket2::{Domain, Protocol, Socket, Type};
        let socket = Socket::new(Domain::for_address(addr), Type::STREAM, Some(Protocol::TCP))?;
        socket.set_reuse_address(true)?;
        socket.bind(&addr.into())?;
        socket.listen(128)?;
        TcpListener::from(socket)
    };
    #[cfg(windows)]
    let listener = TcpListener::bind(addr)?;
    eprintln!(
        "监听 {}:{}，等待设备 {}",
        config.listen_ip, config.port, config.device_ip
    );
    Ok(listener)
}

pub struct Link {
    stream: TcpStream,
    parser: Frames,
    last_heartbeat: Instant,
    pub events: VecDeque<Value>,
}
impl Link {
    /// 在 deadline 前等待设备连入；只接受来自 device_ip 的连接，其余立即关闭。
    pub fn accept_before(
        listener: &TcpListener,
        config: &Config,
        stop: &Arc<AtomicBool>,
        deadline: Instant,
    ) -> Result<Option<Self>> {
        listener.set_nonblocking(true)?;
        while !stop.load(Ordering::Relaxed) {
            match listener.accept() {
                Ok((stream, addr)) if addr.ip() == config.device_ip => {
                    stream.set_read_timeout(Some(Duration::from_millis(100)))?;
                    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
                    stream.set_nodelay(true)?;
                    let now = Instant::now();
                    return Ok(Some(Self {
                        stream,
                        parser: Frames::default(),
                        events: VecDeque::new(),
                        // 单调时钟启动初期不足 2 秒时不能下溢 panic。
                        last_heartbeat: now.checked_sub(Duration::from_secs(2)).unwrap_or(now),
                    }));
                }
                Ok((other, _)) => drop(other),
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => (),
                Err(e) => return Err(e.into()),
            }
            ensure!(Instant::now() < deadline, "等待 DC24 连接超时");
            thread::sleep(Duration::from_millis(50));
        }
        Ok(None)
    }
    /// 常驻监听会积累设备在空闲期拨入、随后又超时断开的陈旧连接；
    /// accept 后用 BA 探活，无应答即丢弃换下一个，直到 device_wait_seconds 用尽。
    pub fn connect(
        listener: &TcpListener,
        config: &Config,
        stop: &Arc<AtomicBool>,
    ) -> Result<Option<Self>> {
        let deadline = Instant::now() + Duration::from_secs(config.device_wait_seconds);
        let mut discard = |_: &[u8], _: &VecDeque<Value>| Ok(());
        loop {
            let Some(mut link) = Self::accept_before(listener, config, stop, deadline)? else {
                return Ok(None);
            };
            match link.exchange(0xba, &[], false, &mut discard) {
                Ok(()) => return Ok(Some(link)),
                Err(e) => eprintln!("丢弃无应答的陈旧连接，继续等待设备: {e:#}"),
            }
        }
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
