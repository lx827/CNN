"""在现场电脑弹出系统目录选择器；仅在用户点选目录按钮后调用。"""
import json
import sys

try:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
    selected = filedialog.askdirectory(title='选择 DC24 原始数据保存目录', parent=root, mustexist=True)
    root.destroy()
    result = {'directory': selected or None}
except Exception as exc:
    result = {'error': '目录选择器不可用，请手动填写路径：'+str(exc)}
sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
