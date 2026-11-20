#!/usr/bin/env python3
"""Validate the shipped slipper geometry, skin bindings and CC0 metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np


def load(path):
    with path.open('rb') as stream:
        assert struct.unpack('<III', stream.read(12))[0:2] == (0x46546c67, 2)
        size, _ = struct.unpack('<II', stream.read(8))
        doc = json.loads(stream.read(size))
        size, _ = struct.unpack('<II', stream.read(8))
        data = stream.read(size)
    return doc, data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path)
    args = parser.parse_args()
    root = Path('shared/figure')
    receipts = json.loads((root / 'slippers.json').read_text())
    for person in ['woman', 'man']:
        path = root / f'{person}.vrm'
        doc, data = load(path)
        assert hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() == receipts[person]['output_sha256']
        assert doc['extensions']['VRM']['meta']['licenseName'] == 'CC0'
        mesh = next(m for m in doc['meshes'] if m.get('name') == 'PracticeClothSlippers')
        assert len(mesh['primitives']) == 2
        node = next(n for n in doc['nodes'] if n.get('name') == 'PracticeClothSlippers')
        skin = doc['skins'][node['skin']]

        def read(index):
            a = doc['accessors'][index]
            v = doc['bufferViews'][a['bufferView']]
            dtype = np.dtype({5123: '<u2', 5126: '<f4'}[a['componentType']])
            width = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[a['type']]
            return np.ndarray((a['count'], width), dtype=dtype, buffer=data,
                              offset=v.get('byteOffset', 0) + a.get('byteOffset', 0))

        for side, primitive in zip(['L', 'R'], mesh['primitives']):
            attributes = primitive['attributes']
            positions, normals = read(attributes['POSITION']), read(attributes['NORMAL'])
            assert np.isfinite(positions).all() and np.isfinite(normals).all()
            assert positions[:, 1].min() == 0 and positions[:, 1].max() <= .058
            assert np.count_nonzero(positions[:, 1] == 0) == 33
            assert np.allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-5)
            assert read(primitive['indices']).max() < len(positions)
            joints, weights = read(attributes['JOINTS_0']), read(attributes['WEIGHTS_0'])
            foot = skin['joints'][int(joints[0, 0])]
            assert doc['nodes'][foot]['name'] == f'J_Bip_{side}_Foot'
            assert (joints[:, 0] == joints[0, 0]).all()
            assert np.allclose(weights, [1, 0, 0, 0])
            material = doc['materials'][primitive['material']]['pbrMetallicRoughness']
            assert 'baseColorTexture' not in material and material['metallicFactor'] == 0
            assert material['roughnessFactor'] == 1
        if args.source_dir:
            original, source = load(args.source_dir / path.name)
            assert data[:len(source)] == source  # Every original bitmap/accessor byte is preserved.
            for old, new in zip(original['meshes'], doc['meshes']):
                expected = [p for p in old['primitives'] if 'CLOTH' not in original['materials'][p['material']]['name']]
                actual = [p for p in new['primitives'] if not doc['materials'][p['material']]['name'].startswith('Practice_')]
                assert actual == expected
            assert doc['extensions']['VRM']['meta'] == original['extensions']['VRM']['meta']
        print(f'{person}: flat 0 mm sole plane, 57 mm cloth upper, rigid foot weights; CC0, non-clothing geometry and original texture bytes preserved')


if __name__ == '__main__':
    main()
