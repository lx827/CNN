param([string]$VendorRoot, [string]$HostIp, [int]$Port, [string]$PeerIp)
$ErrorActionPreference = 'Stop'
if ([IntPtr]::Size -ne 4) { throw 'JMServer.dll requires a 32-bit process.' }
Add-Type -TypeDefinition @"
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

public static class VendorBridge
{
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr LoadLibrary(string path);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi, ExactSpelling=true, SetLastError=true)] static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("ws2_32.dll")] static extern int getpeername(IntPtr socket, byte[] address, ref int addressLength);
    [DllImport("ws2_32.dll")] static extern int send(IntPtr socket, byte[] data, int length, int flags);
    [DllImport("ws2_32.dll")] static extern int WSAGetLastError();

    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void Init(int option);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void Finish();
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void EventHandler(IntPtr context, IntPtr server, IntPtr address, IntPtr socket, int code, IntPtr data, int length);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet=CharSet.Ansi)] delegate byte Start(IntPtr context, string address, ushort port, int workerCount, int bufferBytes, EventHandler callback);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int LinkCount();
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate uint DeviceIP(int index);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void SetCollect(int index, int active);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate byte GetCollect(int index);
    static LinkCount linkCount;
    static DeviceIP deviceIP;
    static SetCollect setCollect;
    static GetCollect getCollect;
    static readonly object Gate = new object();
    static readonly byte[] StopFrame = {0x7e, 0, 1, 0xb8, 0x47};
    static IntPtr device = IntPtr.Zero;
    static bool accepted, mayBeSampling, stopping;
    static string expectedPeer;

    static T Export<T>(IntPtr library, string name) where T : class
    {
        var address = GetProcAddress(library, name);
        if (address == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        return Marshal.GetDelegateForFunctionPointer(address, typeof(T)) as T;
    }

    static string Peer(IntPtr socket, out int port)
    {
        var bytes = new byte[16];
        int length = bytes.Length;
        port = 0;
        if (getpeername(socket, bytes, ref length) != 0 || length != 16 || bytes[0] != 2) return "";
        port = (bytes[2] << 8) | bytes[3];
        return String.Join(".", bytes[4], bytes[5], bytes[6], bytes[7]);
    }

    static void OnEvent(IntPtr context, IntPtr server, IntPtr address, IntPtr socket, int code, IntPtr data, int length)
    {
        if (code != 1 && code != 5 && code != 6) return;
        lock (Gate)
        {
            if (code == 1)
            {
                int port;
                string ip = Peer(socket, out port);
                if (!accepted && ip == expectedPeer)
                {
                    accepted = true;
                    device = socket;
                    Console.WriteLine("CONNECTED {0}:{1}", ip, port);
                }
                else Console.WriteLine("IGNORED {0}:{1}", ip, port);
                return;
            }
            if (device == IntPtr.Zero || socket != device) return;
            if (code == 5)
            {
                if (length == 0)
                {
                    device = IntPtr.Zero;
                    Console.WriteLine("DISCONNECTED");
                }
                return;
            }
            if (data == IntPtr.Zero || length < 5 || length > 65536)
            {
                Console.WriteLine("ERROR invalid callback frame length " + length);
                return;
            }
            var frame = new byte[length];
            Marshal.Copy(data, frame, 0, length);
            if (stopping && length == 6 && frame[3] == 0xb8 && frame[4] == 0 && frame[5] == 0x47)
            {
                mayBeSampling = false;
                stopping = false;
            }
            Console.WriteLine("FRAME " + Convert.ToBase64String(frame));
        }
    }

    static void SendAll(IntPtr socket, byte[] bytes)
    {
        if (socket == IntPtr.Zero) throw new IOException("No matching DC24 socket");
        int offset = 0;
        while (offset < bytes.Length)
        {
            byte[] rest = bytes;
            if (offset != 0)
            {
                rest = new byte[bytes.Length - offset];
                Buffer.BlockCopy(bytes, offset, rest, 0, rest.Length);
            }
            int length = send(socket, rest, rest.Length, 0);
            if (length <= 0) throw new IOException("WinSock send failed: " + WSAGetLastError());
            offset += length;
        }
    }

    static int FindDeviceIndex()
    {
        uint expected = BitConverter.ToUInt32(System.Net.IPAddress.Parse(expectedPeer).GetAddressBytes(), 0);
        int count = linkCount();
        for (int index = 0; index < count; ++index)
            if (deviceIP(index) == expected) return index;
        return -1;
    }

    static void Forward(byte[] bytes)
    {
        IntPtr socket;
        lock (Gate)
        {
            socket = device;
            if (bytes.Length >= 5 && bytes[0] == 0x7e)
            {
                if (bytes[3] == 0xb7)
                {
                    int index = FindDeviceIndex();
                    if (index < 0)
                        throw new IOException("The connected DC24 was not registered in JMServer; start withheld");
                    // Otherwise JMServer stops the DC24 when the first sample frame arrives.
                    setCollect(index, 1);
                    if (getCollect(index) != 1) throw new IOException("JMServer collection state was not enabled");
                    mayBeSampling = true;
                    stopping = false;
                }
                if (bytes[3] == 0xb8) stopping = true;
            }
        }
        SendAll(socket, bytes);
    }

    public static void Run(string root, string host, int port, string peer)
    {
        expectedPeer = peer;
        if (!SetDllDirectory(root)) throw new Win32Exception(Marshal.GetLastWin32Error());
        var library = LoadLibrary(Path.Combine(root, "dll", "JMServer.dll"));
        if (library == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        var initialize = Export<Init>(library, "InitialDevice");
        var start = Export<Start>(library, "StartServer");
        var stop = Export<Finish>(library, "StopServer");
        var release = Export<Finish>(library, "ReleaseDevice");
        linkCount = Export<LinkCount>(library, "GetLinkCount");
        deviceIP = Export<DeviceIP>(library, "GetDeviceIP");
        setCollect = Export<SetCollect>(library, "SetCollectState");
        getCollect = Export<GetCollect>(library, "GetCollectState");
        EventHandler callback = OnEvent;
        initialize(1);
        bool started = false;
        try
        {
            started = start(IntPtr.Zero, host, (ushort)port, 1, 65536, callback) != 0;
            if (!started) throw new IOException("JMServer.StartServer returned false");
            Console.WriteLine("READY {0}:{1}", host, port);
            string request;
            while ((request = Console.ReadLine()) != null && request != "QUIT")
            {
                if (!request.StartsWith("TX ")) throw new IOException("Unexpected bridge request");
                Forward(Convert.FromBase64String(request.Substring(3)));
            }
        }
        finally
        {
            IntPtr fallback = IntPtr.Zero;
            lock (Gate) { if (mayBeSampling) { stopping = true; fallback = device; } }
            if (fallback != IntPtr.Zero)
            {
                try { SendAll(fallback, StopFrame); Console.WriteLine("FALLBACK_STOP_SENT"); Thread.Sleep(250); }
                catch (IOException error) { Console.WriteLine("ERROR " + error.Message); }
            }
            if (started)
            {
                int index = FindDeviceIndex();
                if (index >= 0) setCollect(index, 0);
                stop();
            }
            release();
            GC.KeepAlive(callback);
        }
        Console.WriteLine("DONE");
    }
}
"@
[VendorBridge]::Run($VendorRoot, $HostIp, $Port, $PeerIp)
