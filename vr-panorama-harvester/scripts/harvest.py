#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harvest —— 从一个 VR 全景网页抓出真实的切片 URL 并批量下载

原理：服务端配置（tour.xml / data_self.xml）常被加密，但浏览器运行时必然要
请求真实图片。用 chromium 的 --log-net-log 记录网络事件，从中提取图片 URL，
按目录分组后批量下载。

用法:
  python3 harvest.py discover <页面URL> [--budget 25000] [--keep /tmp/net.json]
  python3 harvest.py download <清单文件|--list-from-netlog> <输出目录> [--referer URL] [--par 8]

典型:
  python3 harvest.py discover "https://example.com/t/xxx?scene_id=1" --keep /tmp/net.json
  python3 harvest.py download /tmp/net.json /data/panos --referer https://example.com/
"""
import argparse, json, os, re, subprocess, sys, urllib.parse
from concurrent.futures import ThreadPoolExecutor

IMG_RE = re.compile(r'https?://[^\s"\']+\.(?:jpg|jpeg|png)(?:\?[^\s"\']*)?', re.I)
KEY_HINT = re.compile(r'(panos?|tiles?|imgs?|cube|equirect|pano|_f\.|_b\.|_l\.|_r\.|_u\.|_d\.)', re.I)


def discover(url, budget=25000, keep=None, chromium=None):
    chromium = chromium or _find_chromium()
    netlog = keep or '/tmp/pano_netlog.json'
    cmd = [chromium, '--headless=new', '--no-sandbox', '--disable-gpu',
           '--enable-unsafe-swiftshader', '--use-angle=swiftshader',
           '--window-size=1280,800', f'--virtual-time-budget={budget}',
           f'--log-net-log={netlog}', '--net-log-capture-mode=IncludeSensitive',
           '--screenshot=/tmp/_pano_probe.png', url]
    subprocess.run(cmd, timeout=max(90, budget // 200),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return netlog


def _find_chromium():
    for c in ('chromium', 'chromium-browser', 'google-chrome', 'chrome'):
        p = shutil_which(c)
        if p:
            return p
    raise SystemExit('未找到 chromium，可显式传入 --chromium')


def shutil_which(name):
    for d in os.environ.get('PATH', '').split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None


def urls_from_netlog(path):
    txt = open(path, encoding='utf-8', errors='ignore').read()
    urls = sorted(set(m.group(0) for m in IMG_RE.finditer(txt)))
    return [u for u in urls if KEY_HINT.search(u)]


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('discover')
    d.add_argument('url'); d.add_argument('--budget', type=int, default=25000)
    d.add_argument('--keep', default=None); d.add_argument('--chromium', default=None)
    dl = sub.add_parser('download')
    dl.add_argument('list'); dl.add_argument('outdir')
    dl.add_argument('--referer', default=None)
    dl.add_argument('--par', type=int, default=8)
    dl.add_argument('--ua', default='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36')
    a = ap.parse_args()

    if a.cmd == 'discover':
        netlog = discover(a.url, a.budget, a.keep, a.chromium)
        urls = urls_from_netlog(netlog)
        print(json.dumps(urls, ensure_ascii=False, indent=1))
        print(f'# {len(urls)} 个候选图片 URL，netlog: {netlog}', file=sys.stderr)
        return

    urls = urls_from_netlog(a.list) if os.path.exists(a.list) and a.list.endswith('.json') \
        else [l.strip() for l in open(a.list, encoding='utf-8') if l.strip()]
    os.makedirs(a.outdir, exist_ok=True)
    jobs = []
    for u in urls:
        path = urllib.parse.urlparse(u).path
        rel = path.strip('/').replace('/', '__')
        jobs.append((u, os.path.join(a.outdir, rel)))

    def one(job):
        u, dst = job
        cmd = ['curl', '-sL', '--max-time', '40', '-A', a.ua, '-H', 'Accept: image/*']
        if a.referer:
            cmd += ['-H', f'Referer: {a.referer}']
        cmd += [u, '-o', dst]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            from PIL import Image
            im = Image.open(dst); im.load()
            return (u, True, im.size)
        except Exception:
            return (u, False, None)

    with ThreadPoolExecutor(max_workers=a.par) as ex:
        for u, ok, sz in ex.map(one, jobs):
            print(('OK  ' if ok else 'BAD '), u, sz if ok else '')


if __name__ == '__main__':
    main()
