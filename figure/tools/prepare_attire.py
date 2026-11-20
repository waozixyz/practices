#!/usr/bin/env python3
"""Build calm cross-collar meditation clothes on the owner's CC0 VRoid figures.

Starts with the checksummed CC0 originals. Keeps identity, original
texture bytes, skeleton, hair and the original skin beneath the shoes. Reuses the fitted garment
surface and bind weights, removes the man's hood/cords, relaxes his trousers,
and adds real crossed lapel/sash geometry. The woman's flared skirt remains
separate so the runtime can drape it under gravity during folds.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
ORIGINAL = {
    'woman': 'adfd242317aaabc773f31f7fff7b013979fbb5baa47e97427a78913d9cb4e979',
    'man': '7aeca142dabbc26ba0f5b9c998c8f3cb6df341287d67788427ac837223785a3f',
}
COMPONENT = {5121: '<u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}



def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Asset:
    def __init__(self, path):
        with path.open('rb') as stream:
            assert struct.unpack('<III', stream.read(12))[:2] == (0x46546C67, 2)
            size, kind = struct.unpack('<II', stream.read(8))
            assert kind == 0x4E4F534A
            self.doc = json.loads(stream.read(size))
            size, kind = struct.unpack('<II', stream.read(8))
            assert kind == 0x004E4942
            self.binary = bytearray(stream.read(size))

    def read(self, index):
        a = self.doc['accessors'][index]
        v = self.doc['bufferViews'][a['bufferView']]
        dtype = np.dtype(COMPONENT[a['componentType']])
        width = WIDTH[a['type']]
        return np.ndarray((a['count'], width), dtype=dtype, buffer=self.binary,
                          offset=v.get('byteOffset', 0) + a.get('byteOffset', 0),
                          strides=(v.get('byteStride', dtype.itemsize * width), dtype.itemsize)).copy()

    def append(self, values, component, kind):
        values = np.asarray(values, dtype=COMPONENT[component])
        self.binary.extend(b'\0' * (-len(self.binary) % 4))
        view = len(self.doc['bufferViews'])
        self.doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(self.binary), 'byteLength': values.nbytes})
        self.binary.extend(values.tobytes())
        a = {'bufferView': view, 'componentType': component, 'count': len(values), 'type': kind}
        if kind == 'VEC3':
            a.update(min=values.min(0).tolist(), max=values.max(0).tolist())
        self.doc['accessors'].append(a)
        return len(self.doc['accessors']) - 1

    def material(self, name, color):
        d = self.doc
        i = len(d['materials'])
        d['materials'].append({'name': name, 'doubleSided': True,
                              'pbrMetallicRoughness': {'baseColorFactor': color,
                                                      'roughnessFactor': 1, 'metallicFactor': 0}})
        d['extensions']['VRM']['materialProperties'].append({
            'name': name, 'shader': 'VRM/MToon', 'renderQueue': -1,
            'floatProperties': {'_Cutoff': .5, '_CullMode': 0, '_BlendMode': 0},
            'vectorProperties': {'_Color': color, '_ShadeColor': color},
            'textureProperties': {}, 'keywordMap': {}, 'tagMap': {}})
        return i

    def primitive(self, attrs, triangles, material):
        # Compact the garment so its skin has only actual cloth vertices.
        used, indices = np.unique(np.asarray(triangles).reshape(-1), return_inverse=True)
        kinds = {'POSITION': (5126, 'VEC3'), 'NORMAL': (5126, 'VEC3'),
                 'TEXCOORD_0': (5126, 'VEC2'), 'JOINTS_0': (5123, 'VEC4'), 'WEIGHTS_0': (5126, 'VEC4')}
        return {'attributes': {key: self.append(values[used], *kinds[key]) for key, values in attrs.items()},
                'indices': self.append(indices.reshape(-1, 1), 5123, 'SCALAR'), 'material': material, 'mode': 4}

    def mesh(self, parent_node, name, primitives):
        d = self.doc
        node = d['nodes'][parent_node]
        mesh = len(d['meshes'])
        d['meshes'].append({'name': name, 'primitives': primitives})
        new = len(d['nodes'])
        d['nodes'].append({**node, 'name': name, 'mesh': mesh})
        parent = next((n for n in d['nodes'][:new] if parent_node in n.get('children', [])), None)
        if parent is not None:
            parent['children'].append(new)
        else:
            for scene in d['scenes']:
                if parent_node in scene['nodes']:
                    scene['nodes'].append(new)

    def save(self, path):
        self.binary.extend(b'\0' * (-len(self.binary) % 4))
        self.doc['buffers'][0]['byteLength'] = len(self.binary)
        data = json.dumps(self.doc, separators=(',', ':'), ensure_ascii=False).encode()
        data += b' ' * (-len(data) % 4)
        with path.open('wb') as stream:
            stream.write(struct.pack('<III', 0x46546C67, 2, 28 + len(data) + len(self.binary)))
            stream.write(struct.pack('<II', len(data), 0x4E4F534A))
            stream.write(data)
            stream.write(struct.pack('<II', len(self.binary), 0x004E4942))
            stream.write(self.binary)


def ribbon(asset, attrs, points, width, material, candidates):
    """A narrow real cloth facing fitted to the source top, with its weights."""
    source = attrs['POSITION']
    front = candidates[(np.abs(source[candidates, 0]) < .24) & (source[candidates, 2] < -.02)]
    values = {key: [] for key in attrs}
    for i, (x, y) in enumerate(points):
        # Fit depth to the local front surface instead of a floating flat stripe.
        distance = (source[front, 0] - x) ** 2 + (source[front, 1] - y) ** 2
        nearest = front[np.argsort(distance)[:6]]
        z = float(np.min(source[nearest, 2])) - .006
        nearest = int(nearest[0])
        tangent = np.array(points[min(i + 1, len(points) - 1)]) - np.array(points[max(0, i - 1)])
        across = np.array([-tangent[1], tangent[0]])
        across /= max(float(np.linalg.norm(across)), 1e-8)
        for sign in (-1, 1):
            for key in attrs:
                value = attrs[key][nearest].copy()
                if key == 'POSITION':
                    value = [x + sign * width * across[0] / 2, y + sign * width * across[1] / 2, z]
                elif key == 'NORMAL':
                    value = [0, 0, -1]
                values[key].append(value)
    triangles = []
    for i in range(len(points) - 1):
        a = i * 2
        triangles.extend([[a, a + 2, a + 1], [a + 1, a + 2, a + 3]])
    return asset.primitive({key: np.array(value) for key, value in values.items()}, triangles, material)


def blend_sleeves(asset, attrs, skin):
    """Grade the sleeve weights so they follow the bent shoulder and elbow."""
    joint_indices = {asset.doc['nodes'][node].get('name'): index for index, node in enumerate(skin['joints'])}
    bind = asset.read(skin['inverseBindMatrices'])
    positions, joints, weights = (attrs[key] for key in ('POSITION', 'JOINTS_0', 'WEIGHTS_0'))
    for side in ('L', 'R'):
        upper, lower = (joint_indices[f'J_Bip_{side}_{part}Arm'] for part in ('Upper', 'Lower'))
        shoulder = np.linalg.inv(bind[upper].reshape((4, 4), order='F'))[:3, 3]
        elbow = np.linalg.inv(bind[lower].reshape((4, 4), order='F'))[:3, 3]
        along = elbow - shoulder
        distance = (positions - elbow) @ (along / np.linalg.norm(along))
        arm = (joints == upper) | (joints == lower)
        arm_weight = np.sum(np.where(arm, weights, 0), axis=1)
        sleeve = arm_weight >= .90
        forearm = np.clip((distance[sleeve] + .11) / .22, 0, 1)
        forearm *= forearm * (3 - 2 * forearm)
        # A secondary sleeve bone can share a vertex with the elbow. Keep
        # that spring weight and smooth the arm contribution across the seam.
        remaining = np.where(arm[sleeve], 0, weights[sleeve])
        order = np.argsort(-remaining, axis=1, kind='stable')[:, :2]
        others = np.take_along_axis(joints[sleeve], order, axis=1)
        values = np.column_stack(((1 - forearm) * arm_weight[sleeve], forearm * arm_weight[sleeve],
                                  np.take_along_axis(remaining, order, axis=1)))
        joints[sleeve] = np.column_stack((np.full(len(forearm), upper), np.full(len(forearm), lower), others))
        weights[sleeve] = values / values.sum(axis=1, keepdims=True)


def blend_trouser_seat(asset, attrs, skin):
    """Keep the waistband on the hips and let each trouser leg follow its thigh."""
    names = [asset.doc['nodes'][node].get('name') for node in skin['joints']]
    hips, left, right = (names.index(name) for name in ('J_Bip_C_Hips', 'J_Bip_L_UpperLeg', 'J_Bip_R_UpperLeg'))
    bind = asset.read(skin['inverseBindMatrices'])[hips].reshape((4, 4), order='F')
    waist = np.linalg.inv(bind)[:3, 3]
    positions, joints, weights = (attrs[key] for key in ('POSITION', 'JOINTS_0', 'WEIGHTS_0'))
    left_shin, right_shin = (names.index(f'J_Bip_{side}_LowerLeg') for side in ('L', 'R'))
    seat = np.sum(np.where(np.isin(joints, [hips, left, right]), weights, 0), axis=1) >= .90
    seat &= waist[1] - positions[:, 1] < .43
    x = waist[0] - positions[seat, 0]
    depth = waist[1] - positions[seat, 1]
    leg = np.clip((depth - .02) / .23, 0, 1)
    leg *= leg * (3 - 2 * leg)
    width = .095 * np.clip((.43 - depth) / .15, 0, 1)
    side = np.clip((x + width) / (2 * width), 0, 1)
    side *= side * (3 - 2 * side)
    shin = np.where(x >= 0, left_shin, right_shin)
    shin_weight = np.sum(np.where(joints[seat] == shin[:, None], weights[seat], 0), axis=1)
    joints[seat] = np.column_stack((np.full(len(leg), hips), np.full(len(leg), left), np.full(len(leg), right), shin))
    weights[seat] = np.column_stack((1 - leg, leg * side, leg * (1 - side), np.zeros(len(leg)))) * (1 - shin_weight[:, None])
    weights[seat, 3] = shin_weight


def diffuse_garment_weights(attrs, triangles, joint_count):
    """Smooth neighboring skin weights, including across UV seams."""
    used, indices = np.unique(triangles.reshape(-1), return_inverse=True)
    positions = attrs['POSITION'][used]
    _, welded = np.unique(np.round(positions, 5), axis=0, return_inverse=True)
    triangles = welded[indices].reshape(-1, 3)
    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges = np.unique(np.concatenate([edges, edges[:, ::-1]]), axis=0)
    source, neighbor = edges[edges[:, 0] != edges[:, 1]].T
    neighbors = np.bincount(source, minlength=int(welded.max()) + 1)[:, None]
    weights = np.zeros((len(neighbors), joint_count), dtype=np.float64)
    np.add.at(weights, (welded[:, None], attrs['JOINTS_0'][used]), attrs['WEIGHTS_0'][used])
    weights /= np.sum(weights, axis=1, keepdims=True)
    for _ in range(5):
        average = np.zeros_like(weights)
        np.add.at(average, source, weights[neighbor])
        weights = np.where(neighbors, .4 * weights + .6 * average / np.maximum(neighbors, 1), weights)
    strongest = np.argsort(-weights, axis=1, kind='stable')[:, :4][welded]
    values = np.take_along_axis(weights[welded], strongest, axis=1)
    attrs['JOINTS_0'][used] = strongest
    attrs['WEIGHTS_0'][used] = values / np.sum(values, axis=1, keepdims=True)


def fit_garment_weights(attrs, joint_count, body, vertices, blend, body_region):
    """Blend the nearby skin weights into an existing graded cloth pattern."""
    blend *= blend * (3 - 2 * blend)
    selected = vertices[blend > 0]
    blend = blend[blend > 0, None]
    body_pos, body_joints, body_weights = (body[key][body_region] for key in ('POSITION', 'JOINTS_0', 'WEIGHTS_0'))
    delta = attrs['POSITION'][selected, None] - body_pos[None]
    distance = np.sum(delta ** 2, axis=2)
    nearest = np.argsort(distance, axis=1, kind='stable')[:, :4]
    sample = 1 / np.maximum(np.take_along_axis(distance, nearest, axis=1), .0001)
    sample /= sample.sum(axis=1, keepdims=True)
    row = np.arange(len(selected))[:, None]
    weights = np.zeros((len(selected), joint_count), dtype=np.float64)
    np.add.at(weights, (row, attrs['JOINTS_0'][selected]), attrs['WEIGHTS_0'][selected] * (1 - blend))
    for lane in range(nearest.shape[1]):
        index = nearest[:, lane]
        np.add.at(weights, (row, body_joints[index]), body_weights[index] * sample[:, lane, None] * blend)
    strongest = np.argsort(-weights, axis=1, kind='stable')[:, :4]
    weights = np.take_along_axis(weights, strongest, axis=1)
    attrs['JOINTS_0'][selected] = strongest
    attrs['WEIGHTS_0'][selected] = weights / weights.sum(axis=1, keepdims=True)


def is_foot_skin(asset, primitive):
    material = asset.doc['materials'][primitive['material']]['name']
    if 'SKIN' not in material:
        return False
    ids = np.unique(asset.read(primitive['indices']))
    heights = asset.read(primitive['attributes']['POSITION'])[ids, 1]
    return heights.min() < .05 and heights.max() < .20


def barefoot(asset, body_node, primitive, person):
    """Level the original plantar skin while preserving toes, UVs and seams."""
    doc = asset.doc
    skin = doc['skins'][doc['nodes'][body_node]['skin']]
    src = {key: asset.read(i) for key, i in primitive['attributes'].items()}
    src_triangles = asset.read(primitive['indices']).reshape(-1, 3)
    feet = []
    measurements = []
    for side, sign in (('L', -1), ('R', 1)):
        attrs = {key: values.copy() for key, values in src.items()}
        xyz = attrs['POSITION']
        triangles = src_triangles[np.all(xyz[src_triangles, 0] * sign > 0, axis=1)]
        used = np.unique(triangles)
        # The source models stand inside slightly elevated shoes. Measure the
        # bare heel and forefoot on both sides and remove that ramp below the ankle.
        rear = used[(xyz[used, 2] > .016) & (xyz[used, 2] < .063)]
        fore = used[(xyz[used, 2] > -.112) & (xyz[used, 2] < -.078)]
        heel = rear[xyz[rear, 1].argmin()]
        ball = fore[xyz[fore, 1].argmin()]
        plane = np.interp(xyz[used, 2], [xyz[ball, 2], xyz[heel, 2]], [xyz[ball, 1], xyz[heel, 1]])
        blend = np.clip((xyz[used, 1] - .086) / .048, 0, 1)
        drop = (plane + .0013) * (1 - blend * blend * (3 - 2 * blend))
        xyz[used, 1] = np.maximum(0, xyz[used, 1] - drop)
        # Skin on the plantar surface follows the sole affine, while skin at
        # the ankle still blends through the original lower-leg weights.
        foot_node = next(i for i, node in enumerate(doc['nodes']) if node.get('name') == f'J_Bip_{side}_Foot')
        foot = skin['joints'].index(foot_node)
        sole = used[xyz[used, 1] < .002]
        attrs['JOINTS_0'][sole] = [foot, 0, 0, 0]
        attrs['WEIGHTS_0'][sole] = [1, 0, 0, 0]
        normals = np.zeros_like(attrs['NORMAL'])
        cross = np.cross(xyz[triangles[:, 1]] - xyz[triangles[:, 0]], xyz[triangles[:, 2]] - xyz[triangles[:, 0]])
        for corner in range(3):
            np.add.at(normals, triangles[:, corner], cross)
        length = np.linalg.norm(normals, axis=1)
        # Some UV seams have coincident vertices and zero-area bridge triangles.
        valid = used[length[used] > 1e-8]
        attrs['NORMAL'][valid] = normals[valid] / length[valid, None]
        feet.append(asset.primitive(attrs, triangles, primitive['material']))
        contact = xyz[used][xyz[used, 1] == 0]
        if len(contact) < 8 or np.ptp(contact[:, 2]) < .12:
            raise ValueError(f'{person} {side}: heel and forefoot do not share the contact plane')
        measurements.append({'side': side, 'vertices': len(used), 'triangles': len(triangles),
                             'support_vertices': len(contact), 'heel_to_ball': float(np.ptp(contact[:, 2]))})
    if sum(m['triangles'] for m in measurements) != len(src_triangles):
        raise ValueError(f'{person}: foot extraction dropped original triangles')
    asset.mesh(body_node, 'PracticeBareFeet', feet)
    return measurements


def dress(source, target, person):
    if sha(source) != ORIGINAL[person]:
        raise ValueError(f'{source}: expected the original CC0 sample')
    asset = Asset(source)
    d = asset.doc
    body_node = next(i for i, n in enumerate(d['nodes']) if n.get('name') == 'Body')
    body = d['meshes'][d['nodes'][body_node]['mesh']]
    skin = d['skins'][d['nodes'][body_node]['skin']]
    foot_skin = next(p for p in body['primitives'] if is_foot_skin(asset, p))
    measurements = barefoot(asset, body_node, foot_skin, person)
    skin_parts = [p for p in body['primitives'] if p is not foot_skin and
                  'SKIN' in d['materials'][p['material']]['name']]
    # The skin and clothes share accessors. Only vertices indexed by skin
    # primitives belong to the surface we want to fit against.
    skin_vertices = np.unique(np.concatenate([asset.read(p['indices']) for p in skin_parts]))
    body_surface = {key: asset.read(skin_parts[0]['attributes'][key])[skin_vertices]
                    for key in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')}
    body_y = body_surface['POSITION'][:, 1]
    body_x = np.abs(body_surface['POSITION'][:, 0])
    joint_count = len(skin['joints'])
    top = asset.material('Practice_Linen_Wrap', [.76, .79, .69, 1] if person == 'woman' else [.36, .46, .39, 1])
    bottom = asset.material('Practice_Linen_Skirt' if person == 'woman' else 'Practice_Relaxed_Trousers',
                            [.22, .36, .33, 1] if person == 'woman' else [.25, .29, .27, 1])
    trim = asset.material('Practice_Crossed_Cloth_Facing', [.16, .27, .24, 1])
    kept, changed, skirt, trims, cloth = [], [], [], [], []
    for primitive_index, primitive in enumerate(body['primitives']):
        name = d['materials'][primitive['material']]['name']
        if primitive is foot_skin or 'Shoes' in name:
            continue
        if 'CLOTH' not in name:
            kept.append(primitive)
            continue
        attrs = {key: asset.read(index) for key, index in primitive['attributes'].items()}
        triangles = asset.read(primitive['indices']).reshape(-1, 3)
        if 'Tops' in name:
            blend_sleeves(asset, attrs, skin)
            if person == 'man':
                # The hood and drawstrings have their own spring-bone weights.
                hood = [i for i, node in enumerate(skin['joints']) if 'Hood' in d['nodes'][node].get('name', '')]
                hood_weight = np.sum(np.where(np.isin(attrs['JOINTS_0'], hood), attrs['WEIGHTS_0'], 0), axis=1)
                triangles = triangles[np.max(hood_weight[triangles], axis=1) < .01]
            if person == 'woman':
                lower = np.mean(attrs['POSITION'][triangles, 1], axis=1) < .975
                skirt.append(asset.primitive(attrs, triangles[lower], bottom))
                triangles = triangles[~lower]
            if person == 'man':
                diffuse_garment_weights(attrs, triangles, joint_count)
                used = np.unique(triangles)
                positions = attrs['POSITION'][used]
                x = np.abs(positions[:, 0])
                y = positions[:, 1]
                # Grade the armhole into the tunic and leave the collar and
                # elbow pattern alone. Lift the upper seam over the skin.
                shoulder = np.clip((x - .065) / .07, 0, 1) * np.clip((.28 - x) / .08, 0, 1)
                shoulder *= np.clip((y - 1.32) / .08, 0, 1)
                fit_garment_weights(attrs, joint_count, body_surface, used, shoulder.copy(),
                                    (body_y > 1.26) & (body_y < 1.49) & (body_x < .32))
                attrs['POSITION'][used, 1] += .012 * shoulder
            top_attrs = copy.deepcopy(attrs)
            cloth.append(asset.primitive(attrs, triangles, top))
            # Two overlapping facings describe a left-over-right wrap closure.
            neck_y, waist_y = (1.375, 1.005) if person == 'woman' else (1.46, 1.06)
            points = [(float(-.043 + u * .15), float(neck_y + u * (waist_y - neck_y))) for u in np.linspace(0, 1, 18)]
            trims.append(ribbon(asset, top_attrs, points, .022, trim, np.unique(triangles)))
            points = [(float(.043 - u * .087), float(neck_y - u * .18)) for u in np.linspace(0, 1, 10)]
            trims.append(ribbon(asset, top_attrs, points, .018, trim, np.unique(triangles)))
            # Fitted sash follows the waist surface, not a rigid accessory.
            sash = np.abs(top_attrs['POSITION'][:, 1] - waist_y) < .035
            sash_triangles = asset.read(primitive['indices']).reshape(-1, 3)
            sash_triangles = sash_triangles[np.all(sash[sash_triangles], axis=1)]
            if len(sash_triangles):
                top_attrs['POSITION'][:, 0] *= 1.008
                top_attrs['POSITION'][:, 2] *= 1.012
                trims.append(asset.primitive(top_attrs, sash_triangles, trim))
        else:
            # Relax the trousers around each leg while leaving the ankle cuff.
            blend_trouser_seat(asset, attrs, skin)
            diffuse_garment_weights(attrs, triangles, joint_count)
            xyz = attrs['POSITION']
            used = np.unique(triangles)
            # A high knee folds the hip farther than the imported trouser
            # weights follow. Match the thigh through the fold, tapering to
            # the original seat and knee weights outside it.
            depth = .965 - xyz[used, 1]
            thigh = np.clip((depth + .045) / .07, 0, 1) * np.clip((.30 - depth) / .14, 0, 1)
            fit_garment_weights(attrs, joint_count, body_surface, used, thigh, (body_y > .65) & (body_y < 1.04))
            u = np.clip((xyz[used, 1] - .10) / .88, 0, 1)
            expansion = .022 * np.sin(np.pi * u)
            # Expand around each leg's centre, rather than translating both
            # walls outward and exposing skin at the inside of the trousers.
            center_x = np.sign(xyz[used, 0]) * (.061 + .018 * np.clip((xyz[used, 1] - .45) / .45, 0, 1))
            radial_x = xyz[used, 0] - center_x
            radial_z = xyz[used, 2] - .01
            length = np.maximum(np.sqrt(radial_x ** 2 + radial_z ** 2), 1e-6)
            xyz[used, 0] += radial_x / length * expansion
            xyz[used, 2] += radial_z / length * expansion
            normals = np.zeros_like(attrs['NORMAL'])
            cross = np.cross(xyz[triangles[:, 1]] - xyz[triangles[:, 0]], xyz[triangles[:, 2]] - xyz[triangles[:, 0]])
            for corner in range(3):
                np.add.at(normals, triangles[:, corner], cross)
            length = np.linalg.norm(normals, axis=1)
            normals[length > 1e-8] /= length[length > 1e-8, None]
            attrs['NORMAL'][used] = normals[used]
            cloth.append(asset.primitive(attrs, triangles, bottom))
        changed.append({'original_primitive': primitive_index, 'original_material': name})
    body['primitives'] = kept
    asset.mesh(body_node, 'PracticeClothing', cloth)
    if skirt:
        asset.mesh(body_node, 'PracticeSkirt', skirt)
    asset.mesh(body_node, 'PracticeWrapFacings', trims)
    # Removed hood springs have no visible geometry; keep skeleton compatibility.
    asset.save(target)
    return {'source_sha256': ORIGINAL[person], 'output_sha256': sha(target),
                       'bare_feet': measurements,
                       'changed_body_primitives': changed, 'skirt_preserved': person == 'woman',
                       'identity': 'Original face, hair, body, skeleton and bare feet retained',
                       'style': 'Matte linen cross-collar wrap, plain sash and flared skirt' if person == 'woman'
                       else 'Matte linen cross-collar tunic and relaxed trousers; hood/cord meshes removed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--output-dir', default=Path('shared/figure'), type=Path)
    args = parser.parse_args()
    attire = {}
    for person in ORIGINAL:
        attire[person] = dress(args.source_dir / f'{person}.vrm', args.output_dir / f'{person}.vrm', person)
    (args.output_dir / 'attire.json').write_text(json.dumps(attire, indent=2) + '\n')
    print('Prepared both traditional-inspired meditation outfits; original CC0 identities and bare feet retained')


if __name__ == '__main__':
    main()
