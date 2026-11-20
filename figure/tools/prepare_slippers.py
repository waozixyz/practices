#!/usr/bin/env python3
"""Replace only the CC0 samples' shoe primitives with simple cloth slippers.

Inputs must be the unmodified, checksummed VRoid samples (see MODELS.md).
Textures, body/clothing/hair geometry, skeleton, expressions and springs
are retained byte for byte. New slippers have one flat sole plane, no heel,
and rigid foot weights so heel/ball pivots preserve that measured plane.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np

ORIGINAL = {
    'woman': 'adfd242317aaabc773f31f7fff7b013979fbb5baa47e97427a78913d9cb4e979',
    'man': '7aeca142dabbc26ba0f5b9c998c8f3cb6df341287d67788427ac837223785a3f',
}
COMPONENT = {5121: '<u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def prepare(source, target, person):
    if hashlib.file_digest(source.open('rb'), 'sha256').hexdigest() != ORIGINAL[person]:
        raise ValueError(f'{source}: expected the original CC0 sample')
    with source.open('rb') as stream:
        magic, version, _ = struct.unpack('<III', stream.read(12))
        size, kind = struct.unpack('<II', stream.read(8))
        assert magic == 0x46546C67 and version == 2 and kind == 0x4E4F534A
        doc = json.loads(stream.read(size))
        size, kind = struct.unpack('<II', stream.read(8))
        assert kind == 0x004E4942
        binary = bytearray(stream.read(size))

    def read(index):
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        dtype = np.dtype(COMPONENT[accessor['componentType']])
        count, width = accessor['count'], WIDTH[accessor['type']]
        return np.ndarray((count, width), dtype=dtype, buffer=binary,
                          offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                          strides=(view.get('byteStride', dtype.itemsize * width), dtype.itemsize)).copy()

    def append(values, component, kind):
        values = np.asarray(values, dtype=COMPONENT[component])
        binary.extend(b'\0' * (-len(binary) % 4))
        view = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': values.nbytes})
        binary.extend(values.tobytes())
        accessor = len(doc['accessors'])
        spec = {'bufferView': view, 'componentType': component, 'count': len(values), 'type': kind}
        if kind == 'VEC3':
            spec.update(min=values.min(axis=0).tolist(), max=values.max(axis=0).tolist())
        doc['accessors'].append(spec)
        return accessor

    shoe_material = next(i for i, material in enumerate(doc['materials']) if 'Shoes' in material['name'])
    body_node = next(i for i, node in enumerate(doc['nodes']) if 'mesh' in node and
                     any(p.get('material') == shoe_material for p in doc['meshes'][node['mesh']]['primitives']))
    node = doc['nodes'][body_node]
    old = doc['meshes'][node['mesh']]
    original_points = []
    for primitive in old['primitives']:
        if primitive.get('material') == shoe_material:
            original_points.extend(read(primitive['attributes']['POSITION'])[np.unique(read(primitive['indices']))])
    original_points = np.array(original_points)
    old['primitives'] = [p for p in old['primitives'] if p.get('material') != shoe_material]
    material = len(doc['materials'])
    color = [.44, .43, .39, 1] if person == 'woman' else [.25, .27, .26, 1]
    doc['materials'].append({'name': 'Practice_Matte_Cloth', 'doubleSided': False,
                             'pbrMetallicRoughness': {'baseColorFactor': color, 'metallicFactor': 0,
                                                     'roughnessFactor': 1}})
    doc['extensions']['VRM']['materialProperties'].append({
        'name': 'Practice_Matte_Cloth', 'shader': 'VRM/MToon', 'renderQueue': -1,
        'floatProperties': {'_Cutoff': .5, '_CullMode': 2, '_BlendMode': 0},
        'vectorProperties': {'_Color': color, '_ShadeColor': color},
        'textureProperties': {}, 'keywordMap': {}, 'tagMap': {}})
    slippers = {'name': 'PracticeClothSlippers', 'primitives': []}
    measurements = []
    segments = 32
    for side in ['L', 'R']:
        foot_node = next(i for i, n in enumerate(doc['nodes']) if n.get('name') == f'J_Bip_{side}_Foot')
        joint = doc['skins'][node['skin']]['joints'].index(foot_node)
        inverse_bind = read(doc['skins'][node['skin']]['inverseBindMatrices'])[joint].reshape(4, 4).T
        foot_bind = np.linalg.inv(inverse_bind)
        sign = 1 if foot_bind[0, 3] > 0 else -1
        points = original_points[original_points[:, 0] * sign > 0]
        lower, upper = points.min(axis=0), points.max(axis=0)
        center_x = float((lower[0] + upper[0]) / 2)
        center_z = float((lower[2] + upper[2]) / 2)
        half_width = float((upper[0] - lower[0]) / 2) * .94
        half_length = float((upper[2] - lower[2]) / 2) * .96
        positions, indices = [], []
        # Thin flat underside, rounded cloth upper. No platform or heel block.
        for ring in range(7):
            angle = (ring - 1) / 5 * math.pi / 2 if ring > 0 else 0
            radius = math.cos(angle) if ring > 0 else 1
            height = .003 + .054 * math.sin(angle) if ring > 0 else 0
            for segment in range(segments):
                theta = 2 * math.pi * segment / segments
                # Toe is slightly broader than the heel, without a pointed tip.
                width = half_width * (1 - .12 * math.cos(theta))
                positions.append([center_x + math.sin(theta) * width * radius,
                                  height, center_z + math.cos(theta) * half_length * radius])
        positions.append([center_x, 0, center_z])
        center = len(positions) - 1
        for segment in range(segments):
            after = (segment + 1) % segments
            indices.extend([center, after, segment])
            for ring in range(6):
                a, b = ring * segments + segment, ring * segments + after
                c, d = a + segments, b + segments
                indices.extend([a, b, c, b, d, c])
        positions = np.array(positions)
        # Derive smooth normals from the generated triangles.
        normals = np.zeros_like(positions)
        for a, b, c in np.array(indices).reshape(-1, 3):
            normal = np.cross(positions[b] - positions[a], positions[c] - positions[a])
            normals[[a, b, c]] += normal
        lengths = np.linalg.norm(normals, axis=1)
        normals[lengths > 0] /= lengths[lengths > 0, None]
        joints = [[joint, 0, 0, 0]] * len(positions)
        weights = [[1, 0, 0, 0]] * len(positions)
        slippers['primitives'].append({'attributes': {
            'POSITION': append(positions, 5126, 'VEC3'), 'NORMAL': append(normals, 5126, 'VEC3'),
            'JOINTS_0': append(joints, 5123, 'VEC4'), 'WEIGHTS_0': append(weights, 5126, 'VEC4')},
            'indices': append(np.array(indices).reshape(-1, 1), 5123, 'SCALAR'), 'material': material, 'mode': 4})
        measurements.append({'side': side, 'vertices': len(positions), 'sole_height': 0,
                             'sole_flatness': 0, 'heel': [center_x, 0, center_z + half_length],
                             'ball': [center_x, 0, center_z - half_length],
                             'original_shoe_height': float(upper[1] - lower[1]), 'upper_height': .057})
    mesh_index = len(doc['meshes'])
    doc['meshes'].append(slippers)
    new_node = len(doc['nodes'])
    # Preserve the source mesh-node transform and skin binding exactly.
    doc['nodes'].append({**node, 'name': 'PracticeClothSlippers', 'mesh': mesh_index})
    parent = next((n for n in doc['nodes'][:new_node] if body_node in n.get('children', [])), None)
    if parent is not None:
        parent['children'].append(new_node)
    else:
        for scene in doc['scenes']:
            if body_node in scene['nodes']:
                scene['nodes'].append(new_node)
    binary.extend(b'\0' * (-len(binary) % 4))
    doc['buffers'][0]['byteLength'] = len(binary)
    encoded = json.dumps(doc, separators=(',', ':'), ensure_ascii=False).encode()
    encoded += b' ' * (-len(encoded) % 4)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('wb') as stream:
        stream.write(struct.pack('<III', 0x46546C67, 2, 28 + len(encoded) + len(binary)))
        stream.write(struct.pack('<II', len(encoded), 0x4E4F534A))
        stream.write(encoded)
        stream.write(struct.pack('<II', len(binary), 0x004E4942))
        stream.write(binary)
    return {'source_sha256': ORIGINAL[person], 'output_sha256': hashlib.file_digest(target.open('rb'), 'sha256').hexdigest(),
            'slippers': measurements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--output-dir', default=Path('shared/figure'), type=Path)
    args = parser.parse_args()
    report = {person: prepare(args.source_dir / f'{person}.vrm', args.output_dir / f'{person}.vrm', person)
              for person in ORIGINAL}
    (args.output_dir / 'slippers.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Prepared both cloth-slipper models; measurements: shared/figure/slippers.json')


if __name__ == '__main__':
    main()
