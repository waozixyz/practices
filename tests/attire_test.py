#!/usr/bin/env python3
"""Verify real garment edits preserve both selected identities and plain soles."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'figure/tools'))
from prepare_attire import ARTICULATED_SOLE_BAND, Asset, ORIGINAL, is_foot_skin, sha


def verify_feet(old, new, receipts, person):
    original = next(p for mesh in old.doc['meshes'] for p in mesh['primitives'] if is_foot_skin(old, p))
    source = {name: old.read(accessor) for name, accessor in original['attributes'].items()}
    triangles = old.read(original['indices']).reshape(-1, 3)
    name = 'PracticeArticulatedFeet' if person == 'woman' else 'PracticeBareFeet'
    feet = next(mesh for mesh in new.doc['meshes'] if mesh['name'] == name)
    assert len(feet['primitives']) == len(receipts) == 2
    for sign, primitive, receipt in zip((-1, 1), feet['primitives'], receipts):
        assert primitive['material'] == original['material']
        expected = triangles[np.all(source['POSITION'][triangles, 0] * sign > 0, axis=1)]
        indices = new.read(primitive['indices']).reshape(-1, 3)
        assert len(indices) == len(expected) == receipt['triangles']
        assert len(np.unique(indices)) == receipt['vertices']
        attrs = {name: new.read(accessor) for name, accessor in primitive['attributes'].items()}
        position = attrs['POSITION']
        original_positions = source['POSITION'][expected]
        assert np.array_equal(position[indices][..., 0], original_positions[..., 0])
        if person == 'woman':
            leveled = position[indices]
            assert np.abs(leveled[..., 2] - original_positions[..., 2]).max() < .01
            shin = original_positions[..., 1] >= .145
            assert np.array_equal(leveled[shin], original_positions[shin])
            assert np.array_equal(attrs['NORMAL'][indices][shin], source['NORMAL'][expected][shin])
            assert np.array_equal(attrs['JOINTS_0'][indices], source['JOINTS_0'][expected])
            assert np.array_equal(attrs['WEIGHTS_0'][indices][shin], source['WEIGHTS_0'][expected][shin])
            body = next(node for node in old.doc['nodes'] if node['name'] == 'Body')
            skeleton = old.doc['skins'][body['skin']]['joints']
            toe_name = f"J_Bip_{receipt['side']}_ToeBase"
            toe = next(i for i, node in enumerate(skeleton) if old.doc['nodes'][node]['name'] == toe_name)
            toe_slots = source['JOINTS_0'][expected] == toe
            assert np.array_equal(attrs['WEIGHTS_0'][indices][toe_slots], source['WEIGHTS_0'][expected][toe_slots])
            # Fit one rotation to the entire lower foot, including the low
            # heel and toe vertices previously omitted by the clamp test.
            lower = original_positions[..., 1] <= .072
            before = original_positions[lower].astype(np.float64)
            after = leveled[lower].astype(np.float64)
            assert len(before) > 300
            u, _, vh = np.linalg.svd((before - before.mean(0)).T @ (after - after.mean(0)))
            rotation = u @ vh
            assert np.linalg.det(rotation) > 0
            assert np.allclose((before - before.mean(0)) @ rotation, after - after.mean(0), atol=1e-7)
            assert np.allclose(source['NORMAL'][expected][lower] @ rotation,
                               attrs['NORMAL'][indices][lower], atol=1e-6)
        else:
            assert np.array_equal(position[indices][..., 2], original_positions[..., 2])
        assert np.array_equal(attrs['TEXCOORD_0'][indices], source['TEXCOORD_0'][expected])
        assert np.isfinite(position).all() and np.isfinite(attrs['NORMAL']).all()
        assert np.allclose(np.linalg.norm(attrs['NORMAL'], axis=1), 1, atol=1e-5)
        assert np.allclose(attrs['WEIGHTS_0'].sum(1), 1, atol=1e-5)
        used = np.unique(indices)
        assert position[used, 1].min() == 0
        band = ARTICULATED_SOLE_BAND if person == 'woman' else 0
        contact = used[position[used, 1] <= band]
        assert len(contact) == receipt['support_vertices']
        assert .12 < np.ptp(position[contact, 2]) == receipt['heel_to_ball']
        if person == 'woman':
            assert len(contact) >= 4
            for zone in (position[contact, 2] > 0, position[contact, 2] < 0):
                assert zone.any() and position[contact[zone], 1].min() < 1e-6
        else:
            assert len(contact) >= 8
            assert np.all(attrs['WEIGHTS_0'][contact] == [1, 0, 0, 0])
        material = new.doc['materials'][primitive['material']]['pbrMetallicRoughness']
        texture = new.doc['textures'][material['baseColorTexture']['index']]
        image = new.doc['images'][texture['source']]
        view = new.doc['bufferViews'][image['bufferView']]
        offset = view.get('byteOffset', 0)
        atlas = np.asarray(Image.open(BytesIO(new.binary[offset:offset + view['byteLength']])).convert('RGB'))
        x, y = np.rint(attrs['TEXCOORD_0'][used] * [atlas.shape[1] - 1, atlas.shape[0] - 1]).astype(int).T
        toes = position[used, 1] < .04
        assert np.quantile(atlas[y[toes], x[toes], 0], .05) > 215, 'The atlas still paints dark socks on the foot'


def verify_training_skirt(asset, mesh, original_body):
    """The shell has smooth circular rows and only waist and hem boundaries."""
    panel, = mesh['primitives']
    attrs = panel['attributes']
    points = asset.read(attrs['POSITION'])
    normals = asset.read(attrs['NORMAL'])
    triangles = asset.read(panel['indices']).reshape(-1, 3)
    skin = asset.doc['skins'][original_body['skin']]
    bind = asset.read(skin['inverseBindMatrices'])
    knee_joints = [index for index, node in enumerate(skin['joints'])
                   if asset.doc['nodes'][node]['name'] in ('J_Bip_L_LowerLeg', 'J_Bip_R_LowerLeg')]
    assert len(knee_joints) == 2
    for joint in knee_joints:
        knee = np.linalg.inv(bind[joint].reshape(4, 4, order='F'))[1, 3]
        assert abs(points[:, 1].min() - knee) < .001
    edges = np.sort(np.concatenate([triangles[:, [a, b]] for a, b in ((0, 1), (1, 2), (2, 0))]), axis=1)
    edges, uses = np.unique(edges, axis=0, return_counts=True)
    assert np.all((uses == 1) | (uses == 2))
    boundary = edges[uses == 1]
    heights = points[boundary, 1]
    assert np.all(heights[:, 0] == heights[:, 1])
    assert np.array_equal(np.unique(heights), np.array([points[:, 1].min(), points[:, 1].max()]))
    for height in np.unique(heights):
        _, degree = np.unique(boundary[heights[:, 0] == height], return_counts=True)
        assert len(degree) >= 32 and np.all(degree == 2)
    assert np.min(np.sum(normals[edges[:, 0]] * normals[edges[:, 1]], axis=1)) > .85
    assert .45 < np.ptp(points[:, 0]) < .50 and .35 < np.ptp(points[:, 2]) < .41
    material = asset.doc['materials'][panel['material']]
    assert material['name'] == 'Practice_Training_Skirt' and material['doubleSided']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', required=True, type=Path)
    args = parser.parse_args()
    root = Path('shared/figure')
    receipts = json.loads((root / 'attire.json').read_text())
    for person in ('woman', 'man'):
        original_path = args.source_dir / f'{person}.vrm'
        target = root / f'{person}.vrm'
        assert sha(original_path) == ORIGINAL[person]
        old, new = Asset(original_path), Asset(target)
        d, o = new.doc, old.doc
        assert sha(target) == receipts[person]['output_sha256']
        assert new.binary[:len(old.binary)] == old.binary
        assert d['extensions']['VRM']['meta'] == o['extensions']['VRM']['meta']
        assert d['extensions']['VRM']['meta']['licenseName'] == 'CC0'
        for key in ('samplers', 'skins'):
            assert d[key] == o[key], (person, key)
        for key in ('images', 'textures'):
            extra = int(person == 'man')
            assert len(d[key]) == len(o[key]) + extra and d[key][:len(o[key])] == o[key], (person, key)
        for i, node in enumerate(o['nodes']):
            # Appended garment nodes may be new children; original nodes stay.
            assert {k: v for k, v in node.items() if k != 'children'} == {k: v for k, v in d['nodes'][i].items() if k != 'children'}
            assert d['nodes'][i].get('children', [])[:len(node.get('children', []))] == node.get('children', [])
        for i, mesh in enumerate(o['meshes']):
            expected = [p for p in mesh['primitives']
                        if 'CLOTH' not in o['materials'][p['material']]['name'] and not is_foot_skin(old, p)]
            actual = [p for p in d['meshes'][i]['primitives'] if not d['materials'][p['material']]['name'].startswith('Practice_')]
            assert actual == expected, (person, mesh.get('name'))
        verify_feet(old, new, receipts[person]['bare_feet'], person)
        garments = []
        for mesh in d['meshes']:
            for primitive in mesh['primitives']:
                name = d['materials'][primitive['material']]['name']
                if not name.startswith('Practice_') or name == 'Practice_Matte_Cloth':
                    continue
                garments.append((mesh, primitive))
                a = primitive['attributes']
                p, n = new.read(a['POSITION']), new.read(a['NORMAL'])
                weights = new.read(a['WEIGHTS_0'])
                indices = new.read(primitive['indices'])
                assert np.isfinite(p).all() and np.isfinite(n).all()
                assert np.allclose(weights.sum(1), 1, atol=1e-5)
                assert indices.max() < len(p)
                mat = d['materials'][primitive['material']]['pbrMetallicRoughness']
                assert mat['roughnessFactor'] == 1 and mat['metallicFactor'] == 0
                assert 'baseColorTexture' not in mat
        assert garments and any(mesh['name'] == 'PracticeWrapFacings' for mesh, _ in garments)
        if person == 'woman':
            training = next(mesh for mesh in d['meshes'] if mesh['name'] == 'PracticeTrainingBody')
            original_body = next(n for n in o['nodes'] if n['name'] == 'Body')
            primary = o['meshes'][original_body['mesh']]['primitives'][0]
            assert sum(len(new.read(p['indices'])) for p in training['primitives'][:3]) == len(old.read(primary['indices']))
            for part, name in zip(training['primitives'][1:3], ('Shorts', 'Top')):
                assert d['materials'][part['material']]['name'] == 'Practice_Training_' + name
                assert len(new.read(part['indices'])) > 150
            shorts = training['primitives'][1]
            shorts_faces = new.read(shorts['indices']).reshape(-1, 3)
            shorts_y = new.read(shorts['attributes']['POSITION'])[shorts_faces, 1].mean(axis=1)
            assert .738 <= shorts_y.min() < .76
            sports_skirt = next(mesh for mesh, _ in garments if mesh['name'] == 'PracticeTrainingSkirt')
            verify_training_skirt(new, sports_skirt, original_body)
            skirt = next(mesh for mesh, _ in garments if mesh.get('name') == 'PracticeSkirt')
            points = new.read(skirt['primitives'][0]['attributes']['POSITION'])
            assert .60 < points[:, 1].min() < .70 and np.ptp(points[:, 0]) > .45
        else:
            body_node = next(n for n in d['nodes'] if n.get('name') == 'Body')
            skin = d['skins'][body_node['skin']]
            hood = [j for j, node in enumerate(skin['joints']) if 'Hood' in d['nodes'][node].get('name', '')]
            for _, primitive in garments:
                a = primitive['attributes']
                joints, weights = new.read(a['JOINTS_0']), new.read(a['WEIGHTS_0'])
                assert np.max(np.where(np.isin(joints, hood), weights, 0)) < .01
        print(f'{person}: real linen wrap geometry, original barefoot topology, textures and level soles; CC0 and skeleton preserved')


if __name__ == '__main__':
    main()
