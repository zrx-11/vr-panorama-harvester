#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pano_toolkit —— 全景立方体贴图 / 等距柱状全景 互转与切图工具

用法:
  python3 pano_toolkit.py equirect  <面片目录> <输出jpg> [--width 4000]
  python3 pano_toolkit.py timeslice <等距柱状jpg> <输出目录> [--dirs 0,90,180,270] [--fov 90] [--w 1600]
  python3 pano_toolkit.py cube      <等距柱状jpg> <输出目录> [--size 2048]

面片目录约定: 内含 f.jpg b.jpg l.jpg r.jpg u.jpg d.jpg（大小必须一致）
"""
import os, sys, argparse
import numpy as np
from PIL import Image

FACES = ['f', 'b', 'r', 'l', 'u', 'd']
Image.MAX_IMAGE_PIXELS = None


def _dirs(ow, oh, width, height, y0, y1):
    """生成第 y0..y1 行对应的方向向量"""
    yaw = np.linspace(0, 2 * np.pi, ow, endpoint=False, dtype=np.float32)
    pitch = np.linspace(np.pi / 2, -np.pi / 2, oh, dtype=np.float32)[y0:y1]
    Y, P = np.meshgrid(yaw, pitch)
    dx = np.cos(P) * np.sin(Y)
    dy = np.sin(P)
    dz = np.cos(P) * np.cos(Y)
    return dx, dy, dz


def faces_to_equirect(face_dir, out_path, out_w=4000, quality=88, chunk=256, progress=True):
    """六面立方体贴图 -> 等距柱状全景（按行分块，避免大图爆内存）"""
    imgs = {}
    for k in FACES:
        p = os.path.join(face_dir, f'{k}.jpg')
        if not os.path.exists(p):
            raise FileNotFoundError(f'缺少面片: {p}')
        imgs[k] = np.asarray(Image.open(p).convert('RGB'))
    H, W = imgs['f'].shape[:2]
    for k in FACES:
        if imgs[k].shape[:2] != (H, W):
            raise ValueError(f'面片尺寸不一致: {k} {imgs[k].shape[:2]} vs {(H, W)}')

    ow = int(out_w)
    oh = ow // 2
    canvas = Image.new('RGB', (ow, oh))
    for y0 in range(0, oh, chunk):
        y1 = min(y0 + chunk, oh)
        dx, dy, dz = _dirs(ow, oh, W, H, y0, y1)
        ax, ay, az = np.abs(dx), np.abs(dy), np.abs(dz)
        mask = np.zeros((y1 - y0, ow), dtype=np.uint8)
        hdom = az >= np.maximum(ax, ay)
        mask[hdom & (dz > 0)] = 0
        mask[hdom & (dz <= 0)] = 1
        xdom = ax > np.maximum(az, ay)
        mask[xdom & (dx > 0)] = 2
        mask[xdom & (dx <= 0)] = 3
        ydom = ay > np.maximum(ax, az)
        mask[ydom & (dy > 0)] = 4
        mask[ydom & (dy <= 0)] = 5

        block = np.zeros((y1 - y0, ow, 3), dtype=np.uint8)
        for ki, name in enumerate(FACES):
            m = mask == ki
            if not m.any():
                continue
            if name in 'fb':
                ma = az[m]
            elif name in 'rl':
                ma = ax[m]
            else:
                ma = ay[m]
            ma = np.where(ma < 1e-6, 1e-6, ma)
            if name == 'f':
                u, v = dx[m] / ma, -dy[m] / ma
            elif name == 'b':
                u, v = -dx[m] / ma, -dy[m] / ma
            elif name == 'r':
                u, v = -dz[m] / ma, -dy[m] / ma
            elif name == 'l':
                u, v = dz[m] / ma, -dy[m] / ma
            elif name == 'u':
                u, v = dx[m] / ma, dz[m] / ma
            else:
                u, v = dx[m] / ma, -dz[m] / ma
            px = ((u + 1) * 0.5 * (W - 1)).astype(np.int32).clip(0, W - 1)
            py = ((v + 1) * 0.5 * (H - 1)).astype(np.int32).clip(0, H - 1)
            block[m] = imgs[name][py, px]
        canvas.paste(Image.fromarray(block), (0, y0))
        if progress:
            print(f'  row {y1}/{oh}', flush=True)
    canvas.save(out_path, quality=quality, optimize=True)
    return out_path


def persp_from_equirect(eq_arr, yaw_deg, pitch_deg=0, fov_deg=90, w=1600, h=None):
    """从等距柱状全景裁一张透视平面图"""
    H, W = eq_arr.shape[:2]
    h = h or int(w * 0.75)
    f = (w / 2) / np.tan(np.radians(fov_deg) / 2)
    cx, cy = w / 2, h / 2
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    tx = np.arctan((xs - cx) / f)
    ty = np.arctan((ys - cy) / f)
    ya = np.radians(yaw_deg) + tx
    pa = np.radians(pitch_deg) - ty
    px = ((ya / (2 * np.pi)) % 1.0 * (W - 1)).astype(np.int32)
    py = ((0.5 - pa / np.pi) * (H - 1)).astype(np.int32).clip(0, H - 1)
    return Image.fromarray(eq_arr[py, px].astype(np.uint8))


def timeslice(eq_path, outdir, dirs=(0, 90, 180, 270), fov=90, w=1600, quality=88, tag=''):
    os.makedirs(outdir, exist_ok=True)
    arr = np.asarray(Image.open(eq_path).convert('RGB'))
    outs = []
    for d in dirs:
        p = os.path.join(outdir, f'view_{int(d):03d}{tag}.jpg')
        persp_from_equirect(arr, d, 0, fov, w).save(p, quality=quality, optimize=True)
        outs.append(p)
    return outs


def equirect_to_cube(eq_path, outdir, size=2048, quality=88):
    """等距柱状全景 -> 六面立方体贴图（供 three.js CubeTexture/skybox 使用）"""
    os.makedirs(outdir, exist_ok=True)
    arr = np.asarray(Image.open(eq_path).convert('RGB'))
    H, W = arr.shape[:2]
    n = int(size)
    xs, ys = np.meshgrid(np.arange(n, dtype=np.float32), np.arange(n, dtype=np.float32))
    uu = (xs / (n - 1)) * 2 - 1
    vv = (ys / (n - 1)) * 2 - 1
    for name in FACES:
        if name == 'f':
            d = (uu, -vv, np.ones_like(uu))
        elif name == 'b':
            d = (-uu, -vv, -np.ones_like(uu))
        elif name == 'r':
            d = (np.ones_like(uu), -vv, -uu)
        elif name == 'l':
            d = (-np.ones_like(uu), -vv, uu)
        elif name == 'u':
            d = (uu, np.ones_like(uu), vv)
        else:
            d = (uu, -np.ones_like(uu), -vv)
        vx, vy, vz = [np.asarray(t, dtype=np.float32) for t in d]
        norm = np.sqrt(vx ** 2 + vy ** 2 + vz ** 2)
        vx, vy, vz = vx / norm, vy / norm, vz / norm
        lon = np.arctan2(-vx, -vz)
        lat = np.arcsin(np.clip(vy, -1, 1))
        px = ((lon / (2 * np.pi)) % 1.0 * (W - 1)).astype(np.int32)
        py = ((0.5 - lat / np.pi) * (H - 1)).astype(np.int32).clip(0, H - 1)
        Image.fromarray(arr[py, px].astype(np.uint8)).save(
            os.path.join(outdir, f'{name}.jpg'), quality=quality)
    return outdir


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('equirect')
    a.add_argument('face_dir'); a.add_argument('out'); a.add_argument('--width', type=int, default=4000)
    a.add_argument('--quality', type=int, default=88)
    b = sub.add_parser('timeslice')
    b.add_argument('eq'); b.add_argument('outdir'); b.add_argument('--dirs', default='0,90,180,270')
    b.add_argument('--fov', type=float, default=90); b.add_argument('--w', type=int, default=1600)
    b.add_argument('--quality', type=int, default=88); b.add_argument('--tag', default='')
    c = sub.add_parser('cube')
    c.add_argument('eq'); c.add_argument('outdir'); c.add_argument('--size', type=int, default=2048)
    args = ap.parse_args()

    if args.cmd == 'equirect':
        faces_to_equirect(args.face_dir, args.out, args.width, args.quality)
        print('OK', args.out)
    elif args.cmd == 'timeslice':
        dirs = [float(x) for x in args.dirs.split(',') if x.strip()]
        for p in timeslice(args.eq, args.outdir, dirs, args.fov, args.w, args.quality, args.tag):
            print('OK', p)
    else:
        equirect_to_cube(args.eq, args.outdir, args.size)
        print('OK', args.outdir)


if __name__ == '__main__':
    main()
