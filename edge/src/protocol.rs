//! 来源：CNN DC24_PROTOCOL 第11节，交接基线 c18cd21。
//! 只实现四路 IEPE/AC0.2Hz/PASS 模式，不推测未知字段。
use anyhow::{bail, ensure, Result};
use serde_json::{json, Value};

pub const RATES: [u32; 12] = [
    50, 100, 200, 500, 1000, 2000, 4000, 5000, 10000, 20000, 50000, 100000,
];
pub const B2: [u8; 13] = [0, 1, 0, 1, 0, 1, 0, 1, 3, 1, 0, 0, 0];
pub fn input_configuration() -> Value {
    json!({"measurement":"IEPE", "coupling":"AC0.2Hz", "upper_frequency":"PASS",
           "profile_id":"iepe-ac02-pass-20261106"})
}
pub fn profile(rate: u32) -> Result<Vec<u8>> {
    ensure!(RATES.contains(&rate), "不是已验证的原厂采样率档位: {rate}");
    let mut data = vec![0, 0, 0x1c, 0];
    data.extend(rate.to_le_bytes());
    data.extend([15, 0, 0, 0]);
    Ok(data)
}
pub fn command(code: u8, payload: &[u8]) -> Vec<u8> {
    let mut out = vec![0x7e];
    out.extend(((payload.len() + 1) as u16).to_be_bytes());
    out.push(code);
    out.extend(payload);
    let sum = out[3..].iter().fold(0u8, |sum, v| sum.wrapping_add(*v));
    out.push(!sum);
    out
}
pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|v| format!("{v:02x}")).collect()
}

#[derive(Default)]
pub struct Frames {
    buffer: Vec<u8>,
}
impl Frames {
    pub fn feed(&mut self, chunk: &[u8]) -> Result<Vec<Vec<u8>>> {
        ensure!(
            self.buffer.len() + chunk.len() <= 131075,
            "接收缓冲超过协议上限"
        );
        self.buffer.extend_from_slice(chunk);
        let mut offset = 0;
        let mut result = Vec::new();
        while offset < self.buffer.len() {
            let data = &self.buffer[offset..];
            if data[0] == 0 {
                offset += 1;
                continue;
            }
            ensure!(data[0] == 0x7e, "设备流出现无效帧头");
            if data.len() < 4 {
                break;
            }
            let size = u16::from_be_bytes([data[1], data[2]]) as usize + 4;
            ensure!(size >= 5, "零长度设备帧");
            if data.len() < size {
                break;
            }
            let frame = &data[..size];
            if frame[3] == 0x80 {
                ensure!(frame[size - 1] == 0xff, "采样帧固定尾错误（此项不是 CRC）");
            } else {
                ensure!(
                    frame[3..].iter().fold(0u8, |s, v| s.wrapping_add(*v)) == 255,
                    "控制帧校验失败"
                );
            }
            result.push(frame.to_vec());
            offset += size;
        }
        self.buffer.drain(..offset);
        Ok(result)
    }
    pub fn pending(&self) -> usize {
        self.buffer.len()
    }
}
pub fn samples(frame: &[u8]) -> Result<(u16, Vec<[i32; 4]>)> {
    ensure!(
        frame.len() >= 23 && frame[3] == 0x80 && (frame.len() - 7) % 16 == 0,
        "四通道数据帧尺寸无效"
    );
    let sequence = u16::from_le_bytes([frame[4], frame[5]]);
    let mut result = Vec::with_capacity((frame.len() - 7) / 16);
    for group in frame[6..frame.len() - 1].chunks_exact(16) {
        let mut row = [0; 4];
        for (channel, word) in group.chunks_exact(4).enumerate() {
            ensure!(word[0] as usize == channel, "通道标记无效");
            row[channel] = i32::from_le_bytes(word.try_into().unwrap()) >> 8;
        }
        result.push(row);
    }
    Ok((sequence, result))
}
pub fn check_sequence(previous: Option<u16>, next: u16) -> Result<()> {
    if previous.is_some_and(|v| v.wrapping_add(1) != next) {
        bail!("设备帧不连续: {previous:?} -> {next}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn frame(sequence: u16, n: usize) -> Vec<u8> {
        let mut body = vec![0x80];
        body.extend(sequence.to_le_bytes());
        for _ in 0..n {
            for (tag, value) in [-8388608i32, 8388607, -1, 12345].iter().enumerate() {
                body.extend(((value << 8) | tag as i32).to_le_bytes());
            }
        }
        let mut out = vec![0x7e];
        out.extend((body.len() as u16).to_be_bytes());
        out.extend(body);
        out.push(255);
        out
    }
    #[test]
    fn captured_input_commands_match() {
        assert_eq!(
            hex(&command(0xb2, &B2)),
            "7e000eb20001000100010001030100000045"
        );
        assert_eq!(
            hex(&command(0xb5, &profile(10000).unwrap())),
            "7e000db500001c00102700000f000000e8"
        );
        assert!(profile(6000).is_err());
    }
    #[test]
    fn fragmentation_signed_counts_variable_frames_and_wrap() {
        for n in [1, 254, 508, 4095] {
            let expected = frame(65535, n);
            for size in [1, 2, 3, 7, 23, 1460, 8192] {
                let mut parser = Frames::default();
                let mut got = Vec::new();
                for part in expected.chunks(size) {
                    got.extend(parser.feed(part).unwrap());
                }
                assert_eq!(got, vec![expected.clone()]);
                assert_eq!(parser.pending(), 0);
                assert_eq!(
                    samples(&got[0]).unwrap().1,
                    vec![[-8388608, 8388607, -1, 12345]; n]
                );
            }
        }
        check_sequence(Some(65535), 0).unwrap();
        assert!(check_sequence(Some(2), 4).is_err());
    }
    #[test]
    fn corrupt_data_and_control_are_rejected() {
        let mut f = frame(1, 1);
        *f.last_mut().unwrap() = 0;
        assert!(Frames::default().feed(&f).is_err());
        let mut c = command(0xb8, &[0]);
        *c.last_mut().unwrap() ^= 1;
        assert!(Frames::default().feed(&c).is_err());
        let mut f = frame(1, 1);
        f[6] = 3;
        assert!(samples(&f).is_err());
    }
}
