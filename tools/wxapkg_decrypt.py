#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PC 微信小程序包（__APP__.wxapkg）解密 + 解包 + 搜 RSA 公钥。

算法（PC 微信 3.x/4.x，文件以 V1MMWX 开头）：
  1. key = PBKDF2-HMAC-SHA1(appid, b"saltiest", iterations=1000, dklen=32)
  2. 前 1024 字节：AES-256-CBC(key, iv=b"the iv: 16 bytes") 解密（跳过 6 字节 magic）
  3. 其余字节：逐字节异或 ord(appid[-2])
  4. 明文 = 解密头[0:1023] + 异或尾部（首字节应为 0xBE）

用法：
    python wxapkg_decrypt.py --appid wx56af9763578b9a93 \
        --file "%APPDATA%\\Tencent\\xwechat\\radium\\users\\<user>\\applet\\packages\\wx56af9763578b9a93\\494\\__APP__.wxapkg" \
        --out ./out
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import struct
import sys

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:  # 兜底：pycryptodome
    Cipher = None
    try:
        from Crypto.Cipher import AES
    except ImportError:
        sys.exit("需要 cryptography 或 pycryptodome：pip install cryptography")


def decrypt(appid: str, blob: bytes) -> bytes:
    """去掉 V1MMWX 加密，返回明文 wxapkg 内容。"""
    if blob[:6] == b"V1MMWX":
        body = blob[6:]
        key = hashlib.pbkdf2_hmac("sha1", appid.encode(), b"saltiest", 1000, 32)
        head = body[:1024]
        if Cipher is not None:
            dec = Cipher(algorithms.AES(key), modes.CBC(b"the iv: 16 bytes")).decryptor()
            head_plain = dec.update(head) + dec.finalize()
        else:
            head_plain = AES.new(key, AES.MODE_CBC, b"the iv: 16 bytes").decrypt(head)
        xor_key = ord(appid[-2]) if len(appid) >= 2 else 0x66
        tail = bytes(b ^ xor_key for b in body[1024:])
        return head_plain[:1023] + tail
    return blob  # 未加密


def unpack(plain: bytes, out_dir: str) -> list[tuple[str, int]]:
    """解析 wxapkg 结构并落盘，返回 (文件名, 大小) 列表。"""
    if plain[0] != 0xBE:
        raise SystemExit("解密结果首字节不是 0xBE，说明 appid 或算法不对")
    off = 1
    _info1, _index_len, _body_len = struct.unpack(">III", plain[off:off + 12])
    off += 12
    if plain[off] != 0xED:
        raise SystemExit("wxapkg 结构异常（0xED 标记缺失）")
    off += 1
    count = struct.unpack(">I", plain[off:off + 4])[0]
    off += 4

    files = []
    for _ in range(count):
        name_len = struct.unpack(">I", plain[off:off + 4])[0]
        off += 4
        name = plain[off:off + name_len].decode("utf-8", "replace")
        off += name_len
        foff, fsize = struct.unpack(">II", plain[off:off + 8])
        off += 8
        files.append((name, foff, fsize))

    for name, foff, fsize in files:
        dest = os.path.join(out_dir, name.lstrip("/"))
        os.makedirs(os.path.dirname(dest) or out_dir, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(plain[foff:foff + fsize])
    return [(n, s) for n, _o, s in files]


def find_rsa_keys(out_dir: str) -> None:
    """在解包出的 JS 里找 RSA 公钥（DER/SPKI base64，通常 392 字符）。"""
    pat = re.compile(r"MII[A-Za-z0-9+/]{200,}={0,2}")
    for root, _dirs, names in os.walk(out_dir):
        for n in names:
            if not n.endswith((".js", ".wxs")):
                continue
            p = os.path.join(root, n)
            text = open(p, encoding="utf-8", errors="replace").read()
            for m in set(pat.findall(text)):
                print("\n[公钥] %s" % os.path.relpath(p, out_dir))
                print("  %s" % m)
            for kw in ("setPublicKey", "JSEncrypt", "getRsa"):
                if kw in text:
                    print("[关键词] %-22s %s" % (kw, os.path.relpath(p, out_dir)))


def main() -> None:
    ap = argparse.ArgumentParser(description="PC 微信小程序包解密/解包/搜 RSA 公钥")
    ap.add_argument("--appid", required=True, help="小程序 AppID，例如 wx56af9763578b9a93")
    ap.add_argument("--file", required=True, help="__APP__.wxapkg 路径")
    ap.add_argument("--out", default="./out", help="输出目录（默认 ./out）")
    args = ap.parse_args()

    with open(args.file, "rb") as f:
        blob = f.read()
    print("输入: %s（%d 字节）" % (args.file, len(blob)))

    plain = decrypt(args.appid, blob)
    os.makedirs(args.out, exist_ok=True)
    pkg = os.path.join(args.out, "decrypted.wxapkg")
    with open(pkg, "wb") as f:
        f.write(plain)
    print("解密: %d 字节，首字节 %#x（0xbe 为标准 wxapkg）→ %s" % (len(plain), plain[0], pkg))

    files = unpack(plain, args.out)
    print("解包: %d 个文件 → %s" % (len(files), args.out))
    for name, size in sorted(files, key=lambda x: -x[1])[:10]:
        print("   %-56s %8d" % (name, size))

    print("\n=== 搜 RSA 公钥 / 加密关键字 ===")
    find_rsa_keys(args.out)
    print("\n提示：把公钥填进集成 const.py 的 PUBKEY_B64 即可（去掉换行）。")


if __name__ == "__main__":
    main()
