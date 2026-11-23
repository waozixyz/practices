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
    foot_name = 'PracticeAuthoredFeet' if person == 'woman' else 'PracticeArticulatedFeet'
    feet = next(mesh for mesh in new.doc['meshes'] if mesh['name'] == foot_name)
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
        leveled = position[indices]
        if person == 'man':
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
        assert len(before) > 100
        assert np.ptp(before[:, 2]) > .12
        u, _, vh = np.linalg.svd((before - before.mean(0)).T @ (after - after.mean(0)))
        rotation = u @ vh
        assert np.linalg.det(rotation) > 0
        assert np.allclose((before - before.mean(0)) @ rotation, after - after.mean(0), atol=1e-7)
        assert np.allclose(source['NORMAL'][expected][lower] @ rotation,
                           attrs['NORMAL'][indices][lower], atol=1e-6)
        if person == 'woman':
            skin = old.doc['skins'][body['skin']]
            foot = next(i for i, node in enumerate(skeleton)
                        if old.doc['nodes'][node]['name'] == f"J_Bip_{receipt['side']}_Foot")
            bind = old.read(skin['inverseBindMatrices'])[foot].reshape(4, 4, order='F')
            ankle = np.linalg.inv(bind)[:3, 3]
            assert np.allclose((ankle - before.mean(0)) @ rotation + after.mean(0), ankle, atol=1e-7)
        assert np.array_equal(attrs['TEXCOORD_0'][indices], source['TEXCOORD_0'][expected])
        assert np.isfinite(position).all() and np.isfinite(attrs['NORMAL']).all()
        assert np.allclose(np.linalg.norm(attrs['NORMAL'], axis=1), 1, atol=1e-5)
        assert np.allclose(attrs['WEIGHTS_0'].sum(1), 1, atol=1e-5)
        used = np.unique(indices)
        plane = float(position[used, 1].min())
        if person == 'man':
            assert plane == 0
        contact = used[position[used, 1] <= plane + ARTICULATED_SOLE_BAND]
        assert len(contact) == receipt['support_vertices'] >= 3
        assert .09 < np.ptp(position[contact, 2]) == receipt['heel_to_ball']
        for zone in (position[contact, 2] > .016, position[contact, 2] < -.035):
            assert zone.any() and position[contact[zone], 1].min() - plane < 1e-6
        material = new.doc['materials'][primitive['material']]['pbrMetallicRoughness']
        texture = new.doc['textures'][material['baseColorTexture']['index']]
        image = new.doc['images'][texture['source']]
        view = new.doc['bufferViews'][image['bufferView']]
        offset = view.get('byteOffset', 0)
        atlas = np.asarray(Image.open(BytesIO(new.binary[offset:offset + view['byteLength']])).convert('RGB'))
        x, y = np.rint(attrs['TEXCOORD_0'][used] * [atlas.shape[1] - 1, atlas.shape[0] - 1]).astype(int).T
        toes = position[used, 1] < plane + .04
        assert toes.any()
        assert np.quantile(atlas[y[toes], x[toes], 0], .05) > 215, 'The atlas still paints dark socks on the foot'


def triangle_area(asset, primitive):
    triangles = asset.read(primitive['indices']).reshape(-1, 3)
    points = asset.read(primitive['attributes']['POSITION'])[triangles].astype(np.float64)
    return np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1)


def verify_training_outfit(old, asset, primary, training):
    names = ('skin', 'Leggings', 'Waistband', 'Cuffs', 'Top', 'Top_Hem')
    parts = training['primitives'][:len(names)]
    assert len(parts) == len(names) and parts[0]['material'] == primary['material']
    profiles = {}
    for name, part in zip(names, parts):
        material = asset.doc['materials'][part['material']]
        if name != 'skin':
            assert material['name'] == 'Practice_Training_' + name
            assert material.get('alphaMode', 'OPAQUE') == 'OPAQUE'
            assert material['pbrMetallicRoughness']['baseColorFactor'][3] == 1
        attrs = {key: asset.read(part['attributes'][key]) for key in primary['attributes']
                 if key in part['attributes']}
        assert np.allclose(np.linalg.norm(attrs['NORMAL'], axis=1), 1, atol=1e-5)
        profiles[name] = attrs
    areas = [triangle_area(asset, part) for part in parts]
    assert all(np.all(area > 0) for area in areas)
    assert np.isclose(sum(area.sum() for area in areas), triangle_area(old, primary).sum(), rtol=1e-6)

    for name, minimum, maximum in (('Cuffs', .173, .188), ('Leggings', .188, 1.000),
                                   ('Waistband', 1.000, 1.024), ('Top_Hem', 1.125, 1.142)):
        y = profiles[name]['POSITION'][:, 1]
        assert np.allclose((y.min(), y.max()), (minimum, maximum), atol=2e-7), name
    skin_faces = asset.read(parts[0]['indices']).reshape(-1, 3)
    skin_y = profiles['skin']['POSITION'][skin_faces, 1]
    assert np.all((skin_y.max(axis=1) < .1730001) | (skin_y.min(axis=1) > 1.0239999))
    top = profiles['Top']['POSITION']
    assert np.isclose(top[:, 1].min(), 1.142, atol=2e-7, rtol=0)
    shoulders = top[top[:, 1] > 1.33, 0]
    assert (shoulders < -.08).sum() > 10 and (shoulders > .08).sum() > 10
    front_neck = top[(np.abs(top[:, 0]) < .03) & (top[:, 2] < -.07), 1]
    assert len(front_neck) > 20 and front_neck.max() < 1.32

    def seam(name, height):
        attrs = profiles[name]
        on_cut = np.isclose(attrs['POSITION'][:, 1], height, atol=2e-7, rtol=0)
        return set(map(tuple, np.column_stack([attrs[key][on_cut] for key in attrs])))

    for first, second, height in (('skin', 'Cuffs', .173), ('Cuffs', 'Leggings', .188),
                                  ('Leggings', 'Waistband', 1.000), ('Waistband', 'skin', 1.024),
                                  ('skin', 'Top_Hem', 1.125), ('Top_Hem', 'Top', 1.142)):
        edges = seam(first, height)
        assert len(edges) > 20 and edges == seam(second, height), (first, second)


def verify_training_tshirt(asset):
    training = next(mesh for mesh in asset.doc['meshes'] if mesh['name'] == 'PracticeTrainingBody')
    skin, shirt, binding, *other = training['primitives']
    clothing = next(mesh for mesh in asset.doc['meshes'] if mesh['name'] == 'PracticeClothing')
    trousers = next(p for p in clothing['primitives']
                    if asset.doc['materials'][p['material']]['name'] == 'Practice_Relaxed_Trousers')
    assert trousers not in other
    for name, part in (('Tshirt', shirt), ('Tshirt_Binding', binding)):
        material = asset.doc['materials'][part['material']]
        assert material['name'] == 'Practice_Training_' + name
        assert material.get('alphaMode', 'OPAQUE') == 'OPAQUE'
        assert material['pbrMetallicRoughness']['baseColorFactor'][3] == 1
        assert np.all(triangle_area(asset, part) > 0)

    edges = []
    for part in (skin, binding):
        attrs = [asset.read(i) for i in part['attributes'].values()]
        edges.append(set(map(tuple, np.column_stack(attrs))))
    joined = np.array(sorted(edges[0] & edges[1]))[:, :3]
    assert (np.abs(joined[:, 1] - .994) < 2e-7).sum() > 20, 'Open waist seam'
    for side in (-1, 1):
        assert (np.abs(side * (joined[:, 0] - .00051) - .286) < 2e-7).sum() > 10, 'Open sleeve seam'
    neck = joined[(joined[:, 1] > 1.40) & (np.abs(joined[:, 0]) < .10)]
    assert len(neck) > 20 and neck[:, 2].min() < -.04 < neck[:, 2].max(), 'Open crew neck seam'
    exposed = asset.read(skin['attributes']['POSITION'])
    assert not np.any((np.abs(exposed[:, 0]) < .15) & (exposed[:, 1] > 1.00) & (exposed[:, 1] < 1.40))
    assert not np.any((exposed[:, 1] > .185001) & (exposed[:, 1] < .959999)), 'Skin inside opaque trousers'
    assert exposed[:, 1].min() < .146, 'Skin no longer meets the original foot mesh under the cuff'


def verify_training_trousers(asset):
    meshes = {mesh['name']: mesh for mesh in asset.doc['meshes']}
    materials = asset.doc['materials']
    relaxed = next(p for p in meshes['PracticeClothing']['primitives']
                   if materials[p['material']]['name'] == 'Practice_Relaxed_Trousers')
    fitted, = meshes['PracticeTrainingTrousers']['primitives']
    assert materials[fitted['material']]['name'] == 'Practice_Workout_Trousers'
    assert materials[fitted['material']]['pbrMetallicRoughness'] == materials[relaxed['material']]['pbrMetallicRoughness']

    def read(part, key):
        return asset.read(part['attributes'][key])

    assert np.array_equal(asset.read(relaxed['indices']), asset.read(fitted['indices']))
    for key in ('JOINTS_0', 'WEIGHTS_0', 'TEXCOORD_0'):
        assert np.array_equal(read(relaxed, key), read(fitted, key)), key
    original, tailored = read(relaxed, 'POSITION'), read(fitted, 'POSITION')
    y = original[:, 1]
    assert np.array_equal(y, tailored[:, 1]), 'Trouser length changed'
    cuff = y <= .15
    assert np.array_equal(original[cuff], tailored[cuff]), 'Ankle opening changed'
    assert np.array_equal(read(relaxed, 'NORMAL')[cuff], read(fitted, 'NORMAL')[cuff])
    # Halve at the existing center seam to measure each leg independently.
    # The depth stays substantial enough for a real trouser, with clearer taper.
    for low, high, depth_ratio in ((.25, .43, .82), (.53, .74, .82), (.83, .94, .88), (1.06, 1.12, .87)):
        for side in (-1, 1):
            band = (y >= low) & (y <= high) & (side * (original[:, 0] - .00051) >= 0)
            before, after = original[band], tailored[band]
            assert len(before) > 12
            assert .65 < np.ptp(after[:, 2]) / np.ptp(before[:, 2]) < depth_ratio, (low, side)
            assert np.ptp(after[:, 0]) < .97 * np.ptp(before[:, 0]), (low, side)
    assert np.all(triangle_area(asset, fitted) > 0)
    assert np.allclose(np.linalg.norm(read(fitted, 'NORMAL'), axis=1), 1, atol=1e-5)


def verify_woman_hair(old, new, authored, styled):
    original, updated = authored['primitives'], styled['primitives']
    assert len(updated) == len(original) - 22 + 3
    assert new.doc['extensions']['VRM']['secondaryAnimation'] == old.doc['extensions']['VRM']['secondaryAnimation']
    assert updated[:8] == original[6:14]
    assert updated[16:44] == original[22:50]
    assert updated[44:55] == original[66:77]
    assert updated[64:76] == original[86:98]
    assert updated[-4] == original[-1]
    for old_part, new_part in [*zip(original[14:22], updated[8:16]),
                              *zip(original[77:86], updated[55:64]),
                              *zip(original[98:107], updated[76:85])]:
        before = old.read(old_part['indices']).ravel()
        after = new.read(new_part['indices']).ravel()
        for key in ('TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0'):
            assert np.array_equal(old.read(old_part['attributes'][key])[before],
                                  new.read(new_part['attributes'][key])[after])
        old_points = old.read(old_part['attributes']['POSITION'])[before]
        points = new.read(new_part['attributes']['POSITION'])[after]
        assert np.array_equal(points[:, [0, 2]], old_points[:, [0, 2]])
        assert np.all(points[:, 1] >= old_points[:, 1])
        assert points[:, 1].min() > old_points[:, 1].min() + .01

    for lock in updated[-3:]:
        attrs = {name: new.read(index) for name, index in lock['attributes'].items()}
        points = attrs['POSITION']
        normals, weights = attrs['NORMAL'], attrs['WEIGHTS_0']
        triangles = new.read(lock['indices']).reshape(-1, 3)
        a, b, c = points[triangles].transpose(1, 0, 2)
        assert np.linalg.norm(np.cross(b - a, c - a), axis=1).min() > 1e-8
        assert np.isfinite(points).all() and np.allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-6)
        assert np.allclose(weights.sum(1), 1, atol=1e-6) and weights.min() >= 0
        base = points[:, 2] < .123
        assert np.count_nonzero(base) > 15 and np.all(weights[base, 0] == 1)
        assert weights[points[:, 1].argmin(), 0] < .75
        assert np.abs(points[:, 0]).max() < .08 and 1.27 < points[:, 1].min() < 1.34
        assert 1.64 < points[:, 1].max() < 1.69 and .21 < points[:, 2].max() < .26
        assert lock['material'] == original[6]['material']


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
            if person == 'woman' and mesh['name'] == 'Hair001.baked':
                verify_woman_hair(old, new, mesh, d['meshes'][i])
                continue
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
            assert all(mesh['name'] != 'PracticeTrainingSkirt' for mesh in d['meshes'])
            verify_training_outfit(old, new, primary, training)
            skirt = next(mesh for mesh, _ in garments if mesh.get('name') == 'PracticeSkirt')
            points = new.read(skirt['primitives'][0]['attributes']['POSITION'])
            assert .60 < points[:, 1].min() < .70 and np.ptp(points[:, 0]) > .45
        else:
            body_node = next(n for n in d['nodes'] if n.get('name') == 'Body')
            skin = d['skins'][body_node['skin']]
            assert receipts[person]['training_top'] == 'Short-sleeved crew-neck T-shirt'
            assert receipts[person]['training_bottom'] == 'Tapered, ankle-length athletic trousers'
            verify_training_tshirt(new)
            verify_training_trousers(new)
            hood = [j for j, node in enumerate(skin['joints']) if 'Hood' in d['nodes'][node].get('name', '')]
            for _, primitive in garments:
                a = primitive['attributes']
                joints, weights = new.read(a['JOINTS_0']), new.read(a['WEIGHTS_0'])
                assert np.max(np.where(np.isin(joints, hood), weights, 0)) < .01
        print(f'{person}: real linen wrap geometry, original barefoot topology, textures and level soles; CC0 and skeleton preserved')


if __name__ == '__main__':
    main()
