#!/usr/bin/env python3
"""
BLF to TXT Converter
自动处理同目录下的 can_flashing_log 文件（支持 .blf 扩展名）
"""

import os
import sys

try:
    import can
except ImportError:
    print("错误：缺少 python-can 库，请运行：pip install python-can")
    sys.exit(1)


def main():
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 可能的输入文件名（无扩展名 或 .blf）
    base_name = "can_flashing_log"
    input_candidates = [
        os.path.join(script_dir, base_name),  # 无扩展名
        os.path.join(script_dir, base_name + ".blf")  # 带 .blf
    ]

    blf_path = None
    for candidate in input_candidates:
        if os.path.isfile(candidate):
            blf_path = candidate
            break

    if not blf_path:
        print(f"错误：在当前目录找不到 can_flashing_log 或 can_flashing_log.blf 文件")
        print(f"当前目录: {script_dir}")
        sys.exit(1)

    # 输出文件：同目录下的 can_flashing_log.txt
    txt_path = os.path.join(script_dir, base_name + ".txt")

    try:
        with can.BLFReader(blf_path) as reader, open(txt_path, "w", encoding="utf-8") as f:
            count = 0
            for msg in reader:
                # 跳过错误帧
                if msg.is_error_frame:
                    continue
                can_id = msg.arbitration_id
                dlc = msg.dlc
                data_hex = "".join(f"{b:02x}" for b in msg.data)
                f.write(f"ID: {can_id} (0x{can_id:x}), Length: {dlc}\n    Data: {data_hex}\n")
                count += 1

        print(f"转换完成！共导出 {count} 条 CAN 消息")
        print(f"输出文件: {txt_path}")

    except FileNotFoundError:
        print(f"错误：文件 '{blf_path}' 不存在")
        sys.exit(1)
    except Exception as e:
        print(f"转换失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()