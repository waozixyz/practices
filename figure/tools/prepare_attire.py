#!/usr/bin/env python3
"""Build calm cross-collar meditation clothes on the owner's CC0 VRoid figures.

Starts with the checksummed CC0 originals. Keeps identity, original
texture bytes, skeleton and the original skin beneath the shoes. Reuses the fitted garment
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
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
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

    def compact(self):
        """Keep only indexed vertices, including every matching morph delta."""
        before = after = 0
        for mesh in self.doc['meshes']:
            for primitive in mesh['primitives']:
                if 'indices' not in primitive:
                    continue
                indices = self.read(primitive['indices'])
                used, remapped = np.unique(indices.reshape(-1), return_inverse=True)
                count = self.doc['accessors'][primitive['attributes']['POSITION']]['count']
                before += count
                after += len(used)
                if len(used) == count:
                    continue

                def compact_accessor(index):
                    source = self.doc['accessors'][index]
                    output = self.append(self.read(index)[used], source['componentType'], source['type'])
                    if 'normalized' in source:
                        self.doc['accessors'][output]['normalized'] = source['normalized']
                    return output

                primitive['attributes'] = {name: compact_accessor(index)
                                           for name, index in primitive['attributes'].items()}
                if 'targets' in primitive:
                    primitive['targets'] = [{name: compact_accessor(index) for name, index in target.items()}
                                            for target in primitive['targets']]
                component = self.doc['accessors'][primitive['indices']]['componentType']
                primitive['indices'] = self.append(remapped.reshape(-1, 1), component, 'SCALAR')
        return {'geometry_vertices_before': before, 'geometry_vertices': after}

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


def remove_sock_dye(asset, body, material_id):
    """Recover the skin colour below the sock line on the original atlas."""
    doc = asset.doc
    material = doc['materials'][material_id]['pbrMetallicRoughness']['baseColorTexture']
    texture_id = material['index']
    texture = doc['textures'][texture_id]
    image = doc['images'][texture['source']]
    data = doc['bufferViews'][image['bufferView']]
    start = data.get('byteOffset', 0)
    original = Image.open(BytesIO(asset.binary[start:start + data['byteLength']])).convert('RGBA')
    region = Image.new('L', original.size)
    draw = ImageDraw.Draw(region)
    dimensions = np.array(original.size) - 1
    for primitive in body['primitives']:
        if primitive['material'] != material_id:
            continue
        attrs = primitive['attributes']
        vertices = asset.read(attrs['POSITION'])
        triangles = asset.read(primitive['indices']).reshape(-1, 3)
        below_sock_line = np.any(vertices[triangles, 1] < .29, axis=1)
        pixels = asset.read(attrs['TEXCOORD_0']) * dimensions
        for triangle in pixels[triangles[below_sock_line]]:
            draw.polygon([tuple(point) for point in triangle], fill=255)
    # Include neighbouring texels so normal texture filtering cannot pull
    # the sock colour back in at a UV seam. Preserve the skin above the sock.
    mask = np.asarray(region.filter(ImageFilter.MaxFilter(5))) != 0
    rgba = np.array(original)
    rgb = rgba[mask, :3].astype(np.float32)
    weight = np.clip((180 - rgb[:, 0]) / 123, 0, 1)
    rgb += weight[:, None] * [187, 161, 134]
    rgba[mask, :3] = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    stream = BytesIO()
    Image.fromarray(rgba).save(stream, 'PNG')
    encoded = stream.getbuffer()
    asset.binary.extend(b'\0' * (-len(asset.binary) % 4))
    view = len(doc['bufferViews'])
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(asset.binary), 'byteLength': len(encoded)})
    asset.binary.extend(encoded)
    source = len(doc['images'])
    doc['images'].append({'name': 'PracticeBareSkin', 'mimeType': 'image/png', 'bufferView': view})
    corrected = len(doc['textures'])
    doc['textures'].append({**texture, 'source': source})
    material['index'] = corrected
    properties = doc['extensions']['VRM']['materialProperties'][material_id]['textureProperties']
    for key in ('_MainTex', '_ShadeTexture'):
        if properties.get(key) == texture_id:
            properties[key] = corrected


ARTICULATED_SOLE_BAND = .0005


def level_foot(attrs, used, ankle=None):
    """Rest the heel and ball on their common tangent, preserving the toe rig."""
    positions = attrs['POSITION'][used].astype(np.float64)
    y, z = positions[:, 1:].T
    heel = z > .016
    ball = z < -.035
    # The shoe pitched the whole sole. Find the pitch at which the lowest
    # points of the heel and ball touch, including the pads behind the toes.
    lower, upper = 0., .5
    for _ in range(32):
        pitch = (lower + upper) / 2
        height = np.cos(pitch) * y - np.sin(pitch) * z
        if height[heel].min() > height[ball].min():
            lower = pitch
        else:
            upper = pitch
    pitch = (lower + upper) / 2
    cosine, sine = np.cos(pitch), np.sin(pitch)
    rotation = np.array([[1, 0, 0], [0, cosine, -sine], [0, sine, cosine]])
    if ankle is None:
        # Keep the accepted Man asset's existing calibration.
        ball_index = np.argmin(np.where(ball, cosine * y - sine * z, np.inf))
        pivot = np.array([0, (y[ball_index] + y[heel].min()) / 2, z[ball_index]])
        leveled = (positions - pivot) @ rotation.T + pivot
        leveled[:, 1] -= leveled[:, 1].min()
    else:
        # The pose solver plants the measured sole. Keep the rest foot at
        # its authored ankle height so leveling cannot lengthen the heel.
        leveled = (positions - ankle) @ rotation.T + ankle
    delta = leveled - positions

    # The lower foot is rigid. Fade the pitch into the unmodified shin and
    # apply the inverse transpose of that blend to the authored normals.
    blend = np.clip((y - .072) / .073, 0, 1)
    move = 1 - blend * blend * (3 - 2 * blend)
    derivative = -6 * blend * (1 - blend) / .073
    attrs['POSITION'][used] = positions + delta * move[:, None]
    changed = move > 0
    jacobian = np.eye(3) + move[changed, None, None] * (rotation - np.eye(3))
    jacobian[:, :, 1] += delta[changed] * derivative[changed, None]
    normals = np.linalg.solve(jacobian.transpose(0, 2, 1), attrs['NORMAL'][used[changed], :, None])[..., 0]
    attrs['NORMAL'][used[changed]] = normals / np.linalg.norm(normals, axis=1, keepdims=True)


def barefoot(asset, body_node, primitive, person):
    """Level the original plantar skin while preserving toes, UVs and seams."""
    doc = asset.doc
    skin = doc['skins'][doc['nodes'][body_node]['skin']]
    src = {key: asset.read(i) for key, i in primitive['attributes'].items()}
    src_triangles = asset.read(primitive['indices']).reshape(-1, 3)
    inverse_bind = asset.read(skin['inverseBindMatrices']) if person == 'woman' else None
    feet = []
    measurements = []
    for side, sign in (('L', -1), ('R', 1)):
        attrs = {key: values.copy() for key, values in src.items()}
        xyz = attrs['POSITION']
        triangles = src_triangles[np.all(xyz[src_triangles, 0] * sign > 0, axis=1)]
        used = np.unique(triangles)
        original_height = xyz[used, 1].copy()
        foot_node = next(i for i, node in enumerate(doc['nodes']) if node.get('name') == f'J_Bip_{side}_Foot')
        foot = skin['joints'].index(foot_node)
        shin_node = next(i for i, node in enumerate(doc['nodes']) if node.get('name') == f'J_Bip_{side}_LowerLeg')
        shin = skin['joints'].index(shin_node)
        # Shoe-fitted heels partly followed the shin. Plant the heel with
        # the foot while retaining toe motion and the original ankle seam.
        mix = np.clip((original_height - .084) / .061, 0, 1)
        mix = mix * mix * (3 - 2 * mix)
        ankle = np.linalg.inv(inverse_bind[foot].reshape(4, 4, order='F'))[:3, 3] if inverse_bind is not None else None
        level_foot(attrs, used, ankle)
        release_heel_weights(attrs, used, foot, shin, mix)
        feet.append(asset.primitive(attrs, triangles, primitive['material']))
        plane = xyz[used, 1].min()
        contact = xyz[used][xyz[used, 1] <= float(plane) + ARTICULATED_SOLE_BAND]
        if not np.any(contact[:, 2] > .016) or not np.any(contact[:, 2] < -.035):
            raise ValueError(f'{side}: heel and forefoot do not share a support plane')
        measurements.append({'side': side, 'vertices': len(used), 'triangles': len(triangles),
                             'support_vertices': len(contact), 'heel_to_ball': float(np.ptp(contact[:, 2]))})
    if sum(m['triangles'] for m in measurements) != len(src_triangles):
        raise ValueError('Foot extraction dropped original triangles')
    asset.mesh(body_node, 'PracticeAuthoredFeet' if person == 'woman' else 'PracticeArticulatedFeet', feet)
    return measurements


def release_heel_weights(attrs, used, foot, shin, mix):
    joints = attrs['JOINTS_0'][used]
    weights = attrs['WEIGHTS_0'][used]
    release = np.where(joints == shin, weights * (1 - mix[:, None]), 0)
    weights -= release
    weights += (joints == foot) * release.sum(axis=1, keepdims=True)
    has_foot = np.any(joints == foot, axis=1)
    attrs['WEIGHTS_0'][used[has_foot]] = weights[has_foot]


def training_surface(attrs, triangles):
    """Partition the skin at garment seams, creating shared cut vertices."""
    x, y, z = attrs['POSITION'].T
    # The fitted armhole tapers from the ribs toward the shoulder. The
    # front neckline scoops lower, with broad straps over each shoulder.
    armhole = .133 + .049 * np.exp(-((y - 1.235) / .072) ** 2)
    scoop = np.clip((np.abs(x) - .025) / .074, 0, 1)
    scoop = scoop * scoop * (3 - 2 * scoop)
    neck_base = np.interp(z, [-.07, .03], [1.300, 1.346])
    fields = np.column_stack((y - .173, y - .188, 1.024 - y, 1.000 - y,
                              y - 1.125, y - 1.142, armhole - np.abs(x),
                              neck_base + (1.453 - neck_base) * scoop - y))
    attrs, polygons = cut_surface(attrs, triangles, fields)

    regions = {name: [] for name in ('skin', 'leggings', 'waist', 'cuffs', 'top', 'hem')}
    for poly, bits in polygons:
        above_ankle, above_cuff, below_waist, below_band, above_hem, above_trim, in_armhole, below_neck = (
            bool(bits & (1 << field)) for field in range(fields.shape[1]))
        name = 'skin'
        if above_ankle and below_waist:
            if not above_cuff:
                name = 'cuffs'
            else:
                name = 'leggings' if below_band else 'waist'
        elif above_hem and in_armhole and below_neck:
            name = 'top' if above_trim else 'hem'
        regions[name].extend((poly[0], a, b) for a, b in zip(poly[1:-1], poly[2:]))
    return attrs, regions


def cut_surface(attrs, triangles, fields):
    values = list(fields)
    vertices = {key: list(data) for key, data in attrs.items()}
    polygons = [(list(map(int, tri)), 0) for tri in triangles]
    for field in range(fields.shape[1]):
        # All garments share the same position, normal, UV and skin weights
        # at each cut, including the pieces on opposite sides of a seam.
        edges = {}
        clipped = []
        for polygon, flags in polygons:
            inside, outside = [], []
            for a, b in zip(polygon[-1:] + polygon[:-1], polygon):
                av, bv = values[a][field], values[b][field]
                if (av >= 0) != (bv >= 0):
                    edge = tuple(sorted((a, b)))
                    if edge not in edges:
                        lo, hi = edge
                        fraction = values[lo][field] / (values[lo][field] - values[hi][field])
                        if fraction <= 1e-7 or fraction >= 1 - 1e-7:
                            edges[edge] = lo if fraction <= 1e-7 else hi
                        else:
                            edges[edge] = len(values)
                            boundary = values[lo] + fraction * (values[hi] - values[lo])
                            boundary[field] = 0
                            values.append(boundary)
                            for key in ('POSITION', 'NORMAL', 'TEXCOORD_0'):
                                first, last = vertices[key][lo], vertices[key][hi]
                                value = first + fraction * (last - first)
                                if key == 'NORMAL':
                                    value /= max(float(np.linalg.norm(value)), 1e-8)
                                vertices[key].append(value)
                            joint = np.r_[vertices['JOINTS_0'][lo], vertices['JOINTS_0'][hi]]
                            weight = np.r_[(1 - fraction) * vertices['WEIGHTS_0'][lo],
                                           fraction * vertices['WEIGHTS_0'][hi]]
                            joint, inverse = np.unique(joint, return_inverse=True)
                            weight = np.bincount(inverse, weights=weight)
                            use = np.argsort(-weight, kind='stable')[:4]
                            pad = (0, 4 - len(use))
                            vertices['JOINTS_0'].append(np.pad(joint[use], pad))
                            vertices['WEIGHTS_0'].append(np.pad(weight[use] / weight[use].sum(), pad))
                    seam = edges[edge]
                    inside.append(seam)
                    outside.append(seam)
                (inside if bv >= 0 else outside).append(b)
            for side, mark in ((outside, flags), (inside, flags | (1 << field))):
                side = list(dict.fromkeys(side))
                if len(side) >= 3:
                    clipped.append((side, mark))
        polygons = clipped

    return {key: np.asarray(data) for key, data in vertices.items()}, polygons


def tai_chi_trousers(asset, body_node, skin_parts):
    """Cut relaxed ankle-length trousers on the woman's own rig."""
    primary = max(skin_parts, key=lambda part: len(asset.read(part['indices'])))
    attrs = {key: asset.read(index) for key, index in primary['attributes'].items()}
    faces = asset.read(primary['indices']).reshape(-1, 3)
    y = attrs['POSITION'][:, 1]
    attrs, polygons = cut_surface(attrs, faces, np.column_stack((y - .157, 1.015 - y)))
    faces = np.array([(poly[0], a, b) for poly, bits in polygons if bits == 3
                      for a, b in zip(poly[1:-1], poly[2:])])
    positions = attrs['POSITION']
    used = np.unique(faces)
    x, y, z = positions[used].T.copy()
    seat = np.clip((y - .76) / .15, 0, 1)
    seat *= seat * (3 - 2 * seat)
    skin = asset.doc['skins'][asset.doc['nodes'][body_node]['skin']]
    inverse_bind = asset.read(skin['inverseBindMatrices'])
    centers = np.zeros((len(used), 2))
    for side, sign in (('L', -1), ('R', 1)):
        leg = []
        for joint_name in ('Foot', 'LowerLeg', 'UpperLeg'):
            node = next(i for i, node in enumerate(asset.doc['nodes'])
                        if node.get('name') == f'J_Bip_{side}_{joint_name}')
            joint = skin['joints'].index(node)
            leg.append(np.linalg.inv(inverse_bind[joint].reshape(4, 4, order='F'))[:3, 3])
        leg = np.asarray(leg)
        selected = x * sign > 0
        centers[selected, 0] = np.interp(y[selected], leg[:, 1], leg[:, 0])
        centers[selected, 1] = np.interp(y[selected], leg[:, 1], leg[:, 2])
    # Expand around the rig's bent shin, not the world origin: its forward
    # wall otherwise moves into the calf instead of opening away from it.
    center_x = centers[:, 0] * (1 - seat)
    center_z = centers[:, 1] * (1 - seat) + .006 * seat
    dx, dz = x - center_x, z - center_z
    radius = np.maximum(np.hypot(dx, dz), 1e-6)
    # A narrow cuff opens into full legs, then tucks below the wrap's sash.
    fullness = .022 + .045 * np.sin(np.pi * np.clip((y - .157) / .858, 0, 1))
    positions[used, 0] += dx / radius * fullness
    positions[used, 2] += dz / radius * fullness
    _, welded = np.unique(np.round(positions, 5), axis=0, return_inverse=True)
    cross = np.cross(positions[faces[:, 1]] - positions[faces[:, 0]],
                     positions[faces[:, 2]] - positions[faces[:, 0]])
    normals = np.zeros((int(welded.max()) + 1, 3), dtype=positions.dtype)
    np.add.at(normals, welded[faces].reshape(-1), np.repeat(cross, 3, axis=0))
    normals = normals[welded]
    lengths = np.maximum(np.linalg.norm(normals, axis=1), 1e-8)
    attrs['NORMAL'][used] = normals[used] / lengths[used, None]
    material = asset.material('Practice_TaiChi_Linen_Trousers', [.22, .36, .33, 1])
    asset.mesh(body_node, 'PracticeTaiChiTrousers', [asset.primitive(attrs, faces, material)])


def training_clothes(asset, body_node, skin_parts):
    """Fit an opaque crop tank and ankle-length leggings to the original rig."""
    primary, *uncovered = skin_parts
    keys = ('POSITION', 'NORMAL', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0')
    attrs = {key: asset.read(primary['attributes'][key]) for key in keys}
    triangles = asset.read(primary['indices']).reshape(-1, 3)
    attrs, regions = training_surface(attrs, triangles)
    materials = {
        'skin': primary['material'],
        'leggings': asset.material('Practice_Training_Leggings', [.12, .245, .25, 1]),
        'waist': asset.material('Practice_Training_Waistband', [.10, .205, .21, 1]),
        'cuffs': asset.material('Practice_Training_Cuffs', [.10, .205, .21, 1]),
        'top': asset.material('Practice_Training_Top', [.25, .52, .46, 1]),
        'hem': asset.material('Practice_Training_Top_Hem', [.21, .46, .40, 1]),
    }
    parts = [asset.primitive(attrs, faces, materials[region]) for region, faces in regions.items()]
    asset.mesh(body_node, 'PracticeTrainingBody', [*parts, *uncovered])


TSHIRT_HEM = .994
TSHIRT_AXIS = np.array([.00051, -.016])


def hang_over(positions, vertices, cover, margin=.008, falling=.35, rising=.6):
    """Let garment VERTICES hang radially over the COVER triangles beneath them.

    Fabric clears the covered surface by MARGIN. Below a bulge it narrows
    at most FALLING per unit of height and above it RISING, so the hem
    drapes over the waistband instead of folding back under it.
    Returns the vertices that moved.
    """
    steps = 12
    a, b = np.meshgrid(np.arange(steps + 1), np.arange(steps + 1))
    inside = a + b <= steps
    a, b = a[inside] / steps, b[inside] / steps
    corners = cover[cover[:, :, 1].max(axis=1) > TSHIRT_HEM - .045]
    samples = (a[None, :, None] * corners[:, 0, None] + b[None, :, None] * corners[:, 1, None] +
               (1 - a - b)[None, :, None] * corners[:, 2, None]).reshape(-1, 3)
    columns, height, bottom = 180, .003, TSHIRT_HEM - .045
    rows = int(np.ceil((1.35 - bottom) / height))

    def polar(points):
        dx, dz = points[:, 0] - TSHIRT_AXIS[0], points[:, 2] - TSHIRT_AXIS[1]
        column = np.floor((np.arctan2(dz, dx) + np.pi) / (2 * np.pi) * columns).astype(int) % columns
        return column, np.hypot(dx, dz), dx, dz

    column, radius, _, _ = polar(samples)
    row = np.floor((samples[:, 1] - bottom) / height).astype(int)
    kept = (row >= 0) & (row < rows)
    need = np.full((columns, rows), -np.inf)
    np.maximum.at(need, (column[kept], row[kept]), radius[kept] + margin)
    # Close the gaps between samples, including around the angle seam.
    need = np.maximum.reduce([np.roll(need, shift, axis=0) for shift in (-1, 0, 1)])
    padded = np.pad(need, ((0, 0), (1, 1)), constant_values=-np.inf)
    need = np.maximum.reduce([padded[:, :-2], padded[:, 1:-1], padded[:, 2:]])
    heights = bottom + (np.arange(rows) + .5) * height

    points = positions[vertices]
    column, radius, dx, dz = polar(points)
    rise = heights[None, :] - points[:, 1, None]
    slope = np.where(rise > 0, falling, rising)
    wanted = np.max(need[column] - slope * np.abs(rise), axis=1)
    scale = np.maximum(radius, wanted) / np.maximum(radius, 1e-8)
    moved = scale > 1 + 1e-7
    positions[vertices[moved], 0] = TSHIRT_AXIS[0] + dx[moved] * scale[moved]
    positions[vertices[moved], 2] = TSHIRT_AXIS[1] + dz[moved] * scale[moved]
    return vertices[moved]


def smooth_normals(attrs, faces, vertices):
    """Recompute the smooth normals of moved VERTICES, welded across UV seams."""
    positions = attrs['POSITION']
    _, welded = np.unique(np.round(positions, 5), axis=0, return_inverse=True)
    welded = welded.reshape(-1)
    cross = np.cross(positions[faces[:, 1]] - positions[faces[:, 0]],
                     positions[faces[:, 2]] - positions[faces[:, 0]])
    normals = np.zeros((int(welded.max()) + 1, 3), dtype=np.float64)
    np.add.at(normals, welded[faces].reshape(-1), np.repeat(cross, 3, axis=0))
    normals = normals[welded[vertices]]
    lengths = np.linalg.norm(normals, axis=1)
    regular = lengths > 1e-10
    attrs['NORMAL'][vertices[regular]] = normals[regular] / lengths[regular, None]


def training_tshirt(asset, body_node, skin_parts, skin, trousers, trouser_faces):
    """Cut a short-sleeved crew-neck shirt on the skinned torso, worn over the trousers."""
    primary, *uncovered = skin_parts
    keys = ('POSITION', 'NORMAL', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0')
    attrs = {key: asset.read(primary['attributes'][key]) for key in keys}
    triangles = asset.read(primary['indices']).reshape(-1, 3)
    x, y, z = attrs['POSITION'].T
    across = np.abs(x - .00051)
    neck = 1.505 - (.054 + .021 * np.clip((.015 - z) / .070, 0, 1)) * np.exp(-(across / .061) ** 2)
    edge = np.column_stack((y - TSHIRT_HEM, .286 - across, neck - y))
    fields = np.column_stack((edge, edge - [.018, .014, .011], y - .185))
    attrs, polygons = cut_surface(attrs, triangles, fields)
    regions = {name: [] for name in ('skin', 'shirt', 'binding')}
    for poly, bits in polygons:
        name = 'skin'
        if (bits & 7) == 7:
            name = 'shirt' if (bits & 63) == 63 else 'binding'
        elif bits & 64 and not bits & 1:
            # Keep skin at the cuffs. The opaque trousers cover the legs up
            # to the waistband, and the shirt hangs over the waistband.
            continue
        regions[name].extend((poly[0], a, b) for a, b in zip(poly[1:-1], poly[2:]))

    garment = np.unique([*regions['shirt'], *regions['binding']])
    seams = np.intersect1d(garment, np.unique(regions['skin']))
    interior = np.setdiff1d(garment, seams)
    # Give the shirt a little ease. The sleeve and neck edges share the skin
    # positions, normals and joint weights, so they stay closed in reaching
    # poses. The hem is a free edge over the trousers.
    attrs['POSITION'][interior] += .005 * attrs['NORMAL'][interior]
    moved = hang_over(attrs['POSITION'], interior, trousers['POSITION'][trouser_faces])
    garment_faces = np.asarray([*regions['shirt'], *regions['binding']])
    smooth_normals(attrs, garment_faces, moved)
    # Carry the waistband's skinning into the overlapping shirt so the hem
    # moves with the trousers under it, blending back to the torso above.
    lower = interior[attrs['POSITION'][interior, 1] < 1.17]
    blend = np.clip((1.17 - attrs['POSITION'][lower, 1]) / .08, 0, 1)
    used = np.unique(trouser_faces)
    waistband = {key: trousers[key][used] for key in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')}
    fit_garment_weights(attrs, len(skin['joints']), waistband, lower, blend, waistband['POSITION'][:, 1] > .90)
    materials = {
        'skin': primary['material'],
        'shirt': asset.material('Practice_Training_Tshirt', [.32, .47, .40, 1]),
        'binding': asset.material('Practice_Training_Tshirt_Binding', [.28, .415, .36, 1]),
    }
    parts = [asset.primitive(attrs, faces, materials[region]) for region, faces in regions.items()]
    asset.mesh(body_node, 'PracticeTrainingBody', [*parts, *uncovered])


def training_trousers(asset, body_node, trousers):
    """Tailor the relaxed pattern for Workout, retaining its cuffs and skinning."""
    attrs = {key: asset.read(index) for key, index in trousers['attributes'].items()}
    faces = asset.read(trousers['indices']).reshape(-1, 3)
    positions = attrs['POSITION']
    x, y, z = positions.T.copy()

    def grade(start, end):
        t = np.clip((y - start) / (end - start), 0, 1)
        return t * t * (3 - 2 * t)

    above_cuff = grade(.15, .29)
    seat = grade(.75, .91)
    waist = grade(.96, 1.10)
    # Work around each leg's center below the crotch and around the whole
    # pelvis above it. Keep the vertical pattern and ankle opening intact.
    center_x = .00051 + np.sign(x - .00051) * (1 - seat) * (.058 + .027 * grade(.20, .79))
    center_z = .018 - .038 * grade(.22, .93)
    positions[:, 0] = x - (x - center_x) * above_cuff * (.27 - .18 * seat + .035 * waist)
    positions[:, 2] = z - (z - center_z) * above_cuff * (.25 - .12 * seat + .035 * waist)

    # The UV seam has separate indices. Accumulate the same smooth normal
    # for both sides so the narrower pattern does not expose a lighting seam.
    _, welded = np.unique(np.round(positions, 5), axis=0, return_inverse=True)
    cross = np.cross(positions[faces[:, 1]] - positions[faces[:, 0]],
                     positions[faces[:, 2]] - positions[faces[:, 0]])
    normals = np.zeros((int(welded.max()) + 1, 3), dtype=positions.dtype)
    np.add.at(normals, welded[faces].reshape(-1), np.repeat(cross, 3, axis=0))
    normals = normals[welded]
    lengths = np.linalg.norm(normals, axis=1)
    regular = (lengths > 1e-8) & (above_cuff > 0)
    attrs['NORMAL'][regular] = normals[regular] / lengths[regular, None]
    color = asset.doc['materials'][trousers['material']]['pbrMetallicRoughness']['baseColorFactor']
    material = asset.material('Practice_Workout_Trousers', color)
    asset.mesh(body_node, 'PracticeTrainingTrousers', [asset.primitive(attrs, faces, material)])
    return attrs, faces


def hair_lock(asset, profile, joints, material, uv_start):
    """Sweep a tapered lock along its centerline on the original hair rig."""
    profile = np.array(profile)
    padded = np.concatenate((profile[:1], profile, profile[-1:]))
    samples = []
    for previous, start, end, following in zip(padded, padded[1:], padded[2:], padded[3:]):
        for t in np.linspace(0, 1, 5, endpoint=False):
            samples.append(start + .5 * t * ((end - previous) + t * (
                2 * previous - 5 * start + 4 * end - following + t * (
                    -previous + 3 * start - 3 * end + following))))
    samples = np.array([*samples, profile[-1]])
    centers, radii = samples[:, :3], np.maximum(samples[:, 3:], .001)
    t = np.linspace(0, 1, len(samples))
    tangent = np.gradient(centers, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
    across = np.array([1., 0., 0.]) - tangent[:, :1] * tangent
    across /= np.linalg.norm(across, axis=1, keepdims=True)
    depth = np.cross(tangent, across)
    sides = 20
    angles = np.arange(sides + 1) * 2 * np.pi / sides
    ridges = 1 + .055 * np.cos(5 * angles - .8 * t[:, None])
    points = centers[:, None, :] + ridges[..., None] * (
        across[:, None, :] * radii[:, None, :1] * np.cos(angles)[None, :, None]
        + depth[:, None, :] * radii[:, None, 1:] * np.sin(angles)[None, :, None])
    rings = points[:, :-1]
    around = np.roll(rings, -1, axis=1) - np.roll(rings, 1, axis=1)
    along = np.gradient(rings, axis=0)
    normal = np.cross(around, along)
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    normal = np.concatenate((normal, normal[:, :1]), axis=1)
    points[:, -1] = points[:, 0]
    u, v = np.meshgrid(np.linspace(uv_start, uv_start + .21, sides + 1), .035 + .92 * t)
    # The tie rides with the head. A small blend from the two existing rear
    # spring chains moves the hanging length without pulling either side off it.
    swing = np.clip((1.565 - centers[:, 1]) / .23, 0, 1)
    swing = .32 * swing * swing * (3 - 2 * swing)
    weights = np.repeat(np.column_stack((1 - swing, swing / 2, swing / 2, 0 * swing)), sides + 1, axis=0)
    attrs = {
        'POSITION': np.vstack((points.reshape(-1, 3), centers[-1])),
        'NORMAL': np.vstack((normal.reshape(-1, 3), tangent[-1])),
        'TEXCOORD_0': np.vstack((np.stack((u, v), axis=2).reshape(-1, 2), [uv_start + .105, .955])),
        'JOINTS_0': np.tile([*joints, 0], (points.shape[0] * points.shape[1] + 1, 1)),
        'WEIGHTS_0': np.vstack((weights, weights[-1])),
    }
    row = sides + 1
    triangles = []
    for level in range(len(centers) - 1):
        for side in range(sides):
            a = level * row + side
            triangles.extend(((a, a + 1, a + row), (a + 1, a + row + 1, a + row)))
    last = (len(centers) - 1) * row
    triangles.extend((last + side, last + side + 1, len(weights)) for side in range(sides))
    return asset.primitive(attrs, triangles, material)


def woman_hair(asset):
    """Keep the original crown and bangs, replacing the two tails with one."""
    d = asset.doc
    hair_node = next(n for n in d['nodes'] if n.get('name') == 'Hair001')
    mesh = d['meshes'][hair_node['mesh']]
    source = mesh['primitives']
    skin = d['skins'][hair_node['skin']]
    joint_by_name = {d['nodes'][node]['name']: i for i, node in enumerate(skin['joints'])}
    joints = [joint_by_name['J_Bip_C_Head'], joint_by_name['HairJoint-e7d28e69-662e-4477-aab0-b5306c3d289e'],
              joint_by_name['HairJoint-bdda9c05-5e10-4c8a-abe5-be7e2c14be93']]
    # The checksummed VRoid mesh orders the ear tufts first and the two
    # tails after the crown. Leave the crown UVs and short forehead layers.
    kept = []
    for index, primitive in enumerate(source):
        if index < 6 or 50 <= index < 66:
            continue
        cheek = 14 <= index < 22
        nape = 77 <= index < 86 or 98 <= index < 107
        if not (cheek or nape):
            kept.append(primitive)
            continue
        attrs = {key: asset.read(accessor) for key, accessor in primitive['attributes'].items()}
        points, normals = attrs['POSITION'], attrs['NORMAL']
        depth = np.maximum((1.482 if cheek else 1.481) - points[:, 1], 0)
        # Compress just the hanging ends. Coordinate and inverse normal
        # scales approach identity as the edit meets the original crown.
        amount = np.minimum(depth, .090)
        points[:, 1] += 5.5 * amount ** 2
        normals[:, 1] /= 1 - 11 * amount
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
        triangles = asset.read(primitive['indices']).reshape(-1, 3)
        kept.append(asset.primitive(attrs, triangles, primitive['material']))

    dark = source[6]['material']
    pony = [
        # x, y, z, width radius, depth radius. The root enters the crown.
        [(0, 1.604, .087, .019, .016), (0, 1.636, .109, .023, .020),
         (-.003, 1.650, .143, .038, .024), (-.008, 1.619, .173, .052, .032),
         (-.010, 1.551, .192, .049, .035), (-.014, 1.478, .196, .034, .028),
         (-.008, 1.409, .202, .026, .021), (.004, 1.347, .219, .014, .013),
         (-.010, 1.286, .224, .001, .001)],
        [(-.013, 1.625, .112, .012, .011), (-.023, 1.645, .146, .020, .017),
         (-.042, 1.601, .181, .026, .022), (-.046, 1.516, .194, .022, .023),
         (-.043, 1.442, .201, .016, .018), (-.028, 1.372, .227, .010, .012),
         (-.035, 1.307, .240, .001, .001)],
        [(.013, 1.625, .113, .012, .011), (.023, 1.646, .145, .019, .017),
         (.038, 1.606, .180, .025, .020), (.031, 1.529, .213, .023, .021),
         (.020, 1.455, .220, .016, .015), (.028, 1.386, .235, .011, .011),
         (.017, 1.321, .245, .001, .001)],
    ]
    for profile, u in zip(pony, (.60, .51, .72)):
        kept.append(hair_lock(asset, profile, joints, dark, u))
    mesh['primitives'] = kept


def dress(source, target, person):
    if sha(source) != ORIGINAL[person]:
        raise ValueError(f'{source}: expected the original CC0 sample')
    asset = Asset(source)
    d = asset.doc
    body_node = next(i for i, n in enumerate(d['nodes']) if n.get('name') == 'Body')
    body = d['meshes'][d['nodes'][body_node]['mesh']]
    skin = d['skins'][d['nodes'][body_node]['skin']]
    foot_skin = next(p for p in body['primitives'] if is_foot_skin(asset, p))
    if person == 'man':
        remove_sock_dye(asset, body, foot_skin['material'])
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
    if person == 'woman':
        tai_chi_trousers(asset, body_node, skin_parts)
        training_clothes(asset, body_node, skin_parts)
        woman_hair(asset)
    else:
        trousers = next(part for part in cloth if part['material'] == bottom)
        # Opaque meshes draw in node order with a less-or-equal depth test,
        # so the shirt that hangs over the waistband comes after the trousers.
        trouser_attrs, trouser_faces = training_trousers(asset, body_node, trousers)
        training_tshirt(asset, body_node, skin_parts, skin, trouser_attrs, trouser_faces)
    # Removed hood springs have no visible geometry; keep skeleton compatibility.
    compacted = asset.compact()
    asset.save(target)
    return {'source_sha256': ORIGINAL[person], 'output_sha256': sha(target),
                       'bare_feet': measurements,
                       'changed_body_primitives': changed, 'skirt_preserved': person == 'woman',
                       'identity': 'Original face, body, skeleton and bare feet retained' if person == 'woman'
                       else 'Original face, hair, body, skeleton and bare feet retained',
                       'style': 'Matte linen cross-collar wrap, plain sash and flared skirt' if person == 'woman'
                       else 'Matte linen cross-collar tunic and relaxed trousers; hood/cord meshes removed',
                       **compacted,
                       **({'training_top': 'Short-sleeved crew-neck T-shirt',
                           'training_bottom': 'Tapered, ankle-length athletic trousers'} if person == 'man'
                          else {'hair': 'High layered ponytail on the original hair rig and texture',
                                'tai_chi_bottom': 'Relaxed ankle-length linen trousers under the wrap top'})}


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
