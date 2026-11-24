"""Bounded USB SSH/PNG acceptance probe; run in the user's normal terminal.

No firmware, USB mode, Wi-Fi, global SSH config, or autostart changes.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
HOST = "192.168.15.244"
HOST_IP = "192.168.15.201"
REMOTE = "/mnt/us/kdd-probe"
SSH_DIR = ROOT / "data" / "ssh"
KEY = SSH_DIR / "kindle_ed25519"
KNOWN_HOSTS = SSH_DIR / "known_hosts"
NATIVE = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "OpenSSH"


def run(args, *, data=None, timeout=30, interactive=False):
    result = subprocess.run(
        [str(x) for x in args], input=data, text=True, encoding="utf-8",
        errors="replace", stdout=subprocess.PIPE,
        stderr=None if interactive else subprocess.PIPE, timeout=timeout,
        creationflags=0 if interactive else getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode:
        # Commands are fixed project operations; no authentication material in logs.
        detail = (result.stderr or "See terminal output.").strip()[:1400]
        raise RuntimeError(f"{Path(str(args[0])).name} failed ({result.returncode}): {detail}")
    return result.stdout


def ssh_options(*, batch=True):
    return [
        "-F", "none", "-p", "22", "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS.as_posix()}",
        "-o", "GlobalKnownHostsFile=none", "-o", "IdentitiesOnly=yes",
        "-o", f"BindAddress={HOST_IP}",
        "-o", "IdentityAgent=none", "-i", str(KEY),
        "-o", f"BatchMode={'yes' if batch else 'no'}",
    ]


def ssh(command, *, batch=True, timeout=30):
    return run([NATIVE / "ssh.exe", *ssh_options(batch=batch), f"root@{HOST}", command],
               timeout=timeout, interactive=not batch)


def validate_usb_snapshot(snapshot):
    """Refuse routes through Wi-Fi or a different device, including /32 overrides."""
    if not snapshot.get("hardware_match"):
        raise RuntimeError("Expected Kindle USB hardware ID not confirmed.")
    index = int(snapshot["interface_index"])
    if not snapshot.get("up") or not snapshot.get("host_ip_ok"):
        raise RuntimeError("USB adapter is not Up at 192.168.15.201/24. Run Configure-USBNetwork.ps1 first.")
    target = ipaddress.ip_address(HOST)
    routes = [r for r in snapshot.get("routes", [])
              if target in ipaddress.ip_network(r["prefix"], strict=False)]
    if not routes:
        raise RuntimeError("No IPv4 route to Kindle.")
    longest = max(ipaddress.ip_network(r["prefix"]).prefixlen for r in routes)
    best = [r for r in routes if ipaddress.ip_network(r["prefix"]).prefixlen == longest]
    if longest < 24 or any(int(r["index"]) != index or r["next_hop"] != "0.0.0.0" for r in best):
        raise RuntimeError("Kindle route is not exclusively direct through the verified USB adapter.")
    return {"interface_index": index, "host_ip": HOST_IP, "kindle_ip": HOST,
            "direct_usb_route": True}


def check_usb():
    script = r'''
$ErrorActionPreference='Stop'
$a=@(Get-NetAdapter | Where-Object {$_.InterfaceDescription -match '^USB Ethernet/RNDIS Gadget(?: #[0-9]+)?$' -and $_.Status -eq 'Up'})
if ($a.Count -ne 1) { throw 'Expected exactly one Kindle RNDIS adapter.' }
$a=$a[0]
$c=Get-CimInstance Win32_NetworkAdapter | Where-Object {$_.InterfaceIndex -eq $a.ifIndex}
$ip=@(Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue)
$routes=@(Get-NetRoute -AddressFamily IPv4 | ForEach-Object {
  @{prefix=$_.DestinationPrefix;index=[int]$_.InterfaceIndex;next_hop=$_.NextHop}
})
@{hardware_match=([string]$c.PNPDeviceID -like 'USB\VID_0525&PID_A4A2\*');
  interface_index=[int]$a.ifIndex;up=([string]$a.Status -eq 'Up');
  host_ip_ok=(@($ip | Where-Object {$_.IPAddress -eq '192.168.15.201' -and $_.PrefixLength -eq 24 -and $_.AddressState -eq 'Preferred'}).Count -eq 1);
  routes=$routes} | ConvertTo-Json -Depth 5 -Compress
'''
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    output = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded])
    return validate_usb_snapshot(json.loads(output.lstrip("\ufeff")))


def make_test_image(path):
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if not font_path.is_file():
        raise RuntimeError("Microsoft YaHei font not found; Chinese glyphs cannot be verified.")
    def font(size):
        return ImageFont.truetype(str(font_path), size)
    image = Image.new("L", (1072, 1448), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 1063, 1439), outline=0, width=6)
    draw.rectangle((28, 28, 1043, 1419), outline=0, width=2)
    draw.text((55, 55), "左上 TOP LEFT", font=font(32), fill=0)
    draw.text((55, 160), "Kindle Desk", font=font(83), fill=0)
    draw.text((55, 270), "USB 有线显示测试", font=font(64), fill=0)
    draw.line((55, 380, 1015, 380), fill=0, width=5)
    lines = ["1072 × 1448 / 8-bit 灰度 PNG", "中文：时间、待办、电脑状态",
             "独立测试页，不代表完整系统已验收", "USB 传输 → SHA256 校验 → eips"]
    for y, line in zip((420, 500, 580, 660), lines):
        draw.text((55, y), line, font=font(36), fill=0)
    for i in range(16):
        x = 56 + i * 60
        draw.rectangle((x, 790, x + 59, 950), fill=i * 17)
        draw.text((x + 12, 970), str(i), font=font(24), fill=0)
    draw.text((55, 1060), "灰阶应连续，边框应完整，文字无变形", font=font(35), fill=0)
    draw.text((55, 1150), datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"), font=font(34), fill=0)
    draw.text((55, 1325), "底部 BOTTOM                         右下 ↘", font=font(32), fill=0)
    image.save(path, format="PNG")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_public_key(path):
    value = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]+={0,2}(?: [A-Za-z0-9_.@-]+)?", value):
        raise RuntimeError("Unexpected project public key format.")
    return value


def bootstrap_key():
    SSH_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY.exists():
        if KEY.with_suffix(".pub").exists():
            raise RuntimeError("Public key exists without private key; preserve and review it before retrying.")
        run([NATIVE / "ssh-keygen.exe", "-t", "ed25519", "-N", "", "-C", "kdd-usb", "-f", KEY])
    public_path = KEY.with_suffix(".pub")
    if not public_path.exists():
        raise RuntimeError("Project public key missing; private key has not been changed.")
    public_key = read_public_key(public_path)
    try:
        if "KDD_KEY_OK" in ssh("printf KDD_KEY_OK"):
            return
    except RuntimeError:
        pass
    print("First USB SSH login: at the password prompt press Enter once.", flush=True)
    # Only public material enters the remote command. Existing keys are preserved.
    command = (
        "set -e; test \"$(id -u)\" = 0; "
        "test -d /mnt/us/usbnet/etc; "
        "grep -Fq '5.16.2.1.1' /etc/prettyversion.txt; "
        "umask 077; touch /mnt/us/usbnet/etc/authorized_keys; "
        f"grep -qxF '{public_key}' /mnt/us/usbnet/etc/authorized_keys || "
        f"printf '\\n%s\\n' '{public_key}' >> /mnt/us/usbnet/etc/authorized_keys; "
        "printf KDD_PUBLIC_KEY_ADDED"
    )
    if "KDD_PUBLIC_KEY_ADDED" not in ssh(command, batch=False, timeout=180):
        raise RuntimeError("Public-key bootstrap marker missing.")
    if "KDD_KEY_OK" not in ssh("printf KDD_KEY_OK"):
        raise RuntimeError("Unattended key authentication did not pass.")


def validate_framebuffer(output):
    if not re.search(r"\bxres:\s*1072\b", output) or not re.search(r"\byres:\s*1448\b", output):
        raise RuntimeError("Live eips framebuffer differs from expected 1072 x 1448; no image sent.")
    if not re.search(r"bits_per_pixel:\s*8\b", output):
        raise RuntimeError("Live eips framebuffer is not confirmed 8-bit; no image sent.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true", help="Generate local PNG only; no network or keys.")
    parser.add_argument("--stability-minutes", type=int, choices=range(0, 1441), default=0, metavar="0..1440")
    parser.add_argument("--skip-display", action="store_true", help="SSH/optional soak only; do not redraw.")
    args = parser.parse_args()
    evidence = ROOT / "docs" / "evidence" / ("ssh-display-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    evidence.mkdir(parents=True)
    report = {"time": datetime.now().astimezone().isoformat(), "ssh_authenticated": False,
              "png_hash_verified": False, "eips_command_succeeded": False,
              "visual_display_verified": False, "reconnect_verified": False,
              "stability": {"requested_minutes": args.stability_minutes, "passed": False}}
    def save():
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        if args.prepare_only or not args.skip_display:
            png = evidence / "usb-test.png"
            digest = make_test_image(png)
            report["png_sha256"] = digest
            print(f"Test PNG: {png}", flush=True)
        if args.prepare_only:
            report["local_preparation_only"] = True
            return 0
        report["usb"] = check_usb()
        print("Verified direct USB route and Kindle hardware ID.", flush=True)
        bootstrap_key()
        report["ssh_authenticated"] = True
        save()
        print("SSH PUBLIC-KEY AUTHENTICATION PASSED.", flush=True)
        if not args.skip_display:
            info = ssh("set -e; test \"$(id -u)\" = 0; test \"$(uname -m)\" = armv7l; grep -Fq '5.16.2.1.1' /etc/prettyversion.txt; /usr/sbin/eips -i 2>&1")
            validate_framebuffer(info)
            (evidence / "eips-info.txt").write_text(info, encoding="utf-8")
            ssh(f"mkdir -p {REMOTE}")
            # -O selects legacy SCP, supported by the installed Dropbear package.
            options = ssh_options()
            options[options.index("-p")] = "-P"
            run([NATIVE / "scp.exe", "-O", *options, png, f"root@{HOST}:{REMOTE}/usb-test.png"])
            remote_hash = ssh(f"sha256sum {REMOTE}/usb-test.png").split()[0]
            if remote_hash.lower() != digest:
                raise RuntimeError("Transferred PNG hash mismatch; no display command executed.")
            report["png_hash_verified"] = True
            save()
            result = ssh(f"set -e; /usr/sbin/eips -c; /usr/sbin/eips -g {REMOTE}/usb-test.png; printf KDD_EIPS_OK")
            if "KDD_EIPS_OK" not in result:
                raise RuntimeError("eips completion marker missing.")
            report["eips_command_succeeded"] = True
            save()
            print("PNG HASH VERIFIED; EIPS COMMAND SUCCEEDED. Check Kindle screen visually.", flush=True)
        if args.stability_minutes:
            start = time.monotonic()
            end = start + args.stability_minutes * 60
            samples = []
            report["stability"]["samples"] = samples
            next_tick = start
            while True:
                now = time.monotonic()
                if now < next_tick:
                    time.sleep(min(next_tick - now, 1))
                    continue
                sample = {"elapsed_seconds": round(now - start, 2), "ok": False}
                try:
                    check_usb()
                    sample["ok"] = "KDD_HEARTBEAT" in ssh("printf KDD_HEARTBEAT", timeout=25)
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    sample["error"] = str(error)[:500]
                samples.append(sample)
                report["stability"]["elapsed_seconds"] = round(time.monotonic() - start, 2)
                save()
                print(f"USB SSH sample {len(samples)}: {'PASS' if sample['ok'] else 'FAIL'} ({sample['elapsed_seconds']} s)", flush=True)
                if now >= end:
                    break
                next_tick = min(next_tick + 60, end)
            report["stability"]["passed"] = all(s["ok"] for s in samples)
            if not report["stability"]["passed"]:
                raise RuntimeError("Stability test recorded failed samples; inspect report.json.")
        print("PROBE COMPLETE. Visual display and physical reconnect need separate confirmation.", flush=True)
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error)[:1800]
        print(f"STOPPED: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        save()
        print(f"REPORT SAVED: {evidence / 'report.json'}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
