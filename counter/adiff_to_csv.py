#!/usr/bin/env python3
import argparse
import sys
import csv
from lxml import etree
from pyproj import Geod
from shapely import wkb
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree


COLUMNS = ['ts', 'action', 'obj_action', 'kind', 'changeset', 'uid', 'username',
           'osm_id', 'region', 'lat', 'lon', 'length']


class Regions:
    def __init__(self, fileobj=None):
        self.tree = None
        self.region_map = {}
        if fileobj:
            self.load(fileobj)

    def load(self, fileobj):
        regions = []
        csv.field_size_limit(1000000)
        for row in csv.reader(fileobj):
            regions.append((row[0], wkb.loads(bytes.fromhex(row[1]))))
        self.tree = STRtree([r[1] for r in regions])
        self.region_map = {id(r[1]): r[0] for r in regions}

    def find(self, lon, lat):
        if not self.tree:
            return None
        pt = Point(lon, lat)
        results = self.tree.query(pt)
        results = [r for r in results if r.contains(pt)]
        return None if not results else self.region_map[id(results[0])]


def get_float_attr(attr, obj, backup=None):
    if attr in obj.attrib:
        return float(obj.get(attr))
    return float(backup.get(attr))


def init_data_from_object(obj, backup=None):
    result = {
        'ts': obj.get('timestamp'),
        'changeset': obj.get('changeset'),
        'uid': obj.get('uid'),
        'username': obj.get('user'),
        'osm_id': f'{obj.tag[0]}{obj.get("id")}',
    }
    if obj.tag == 'node':
        result.update({
            'lon': get_float_attr('lon', obj, backup),
            'lat': get_float_attr('lat', obj, backup),
        })
    else:
        bounds = obj.find('bounds')
        if bounds is None:
            bounds = backup.find('bounds')
        if bounds is None:
            sys.stderr.write(f'Missing bounds for {result}\n')
        result.update({
            'lon': (float(bounds.get('minlon')) + float(bounds.get('maxlon'))) / 2,
            'lat': (float(bounds.get('minlat')) + float(bounds.get('maxlat'))) / 2,
        })
    if obj.tag == 'way':
        # Calculate length
        nodes = obj.findall('nd')
        if len(nodes) == 0:
            nodes = backup.findall('nd')
        if len(nodes) < 2 or not all([nd.get('lat') for nd in nodes]):
            return None
        line = LineString([(float(nd.get('lon')), float(nd.get('lat'))) for nd in nodes])
        geod = Geod(ellps='WGS84')
        result['length'] = round(geod.geometry_length(line))
    elif obj.tag == 'relation' and len(obj.find('member')) == 0:
        return None
    return result


def get_tag_value(tag, obj=None):
    if obj is None:
        return None
    tags = [t for t in obj.findall('tag') if t.get('k') == tag]
    return None if not tags else tags[0].get('v')


def get_tag_action(tag, obj, old=None) -> str:
    new_value = get_tag_value(tag, obj)
    old_value = get_tag_value(tag, old)
    if new_value == old_value:
        return None
    if new_value:
        return 'create' if not old_value else 'modify'
    else:
        return 'delete'


def is_new_tag_action(k, v, obj, old=None) -> str:
    has_new = get_tag_value(k, obj) == v
    has_old = get_tag_value(k, old) == v
    if has_new == has_old:
        return None
    return 'create' if not has_old else 'delete'


def reduce_tag_actions(*args) -> str:
    actions = set([a for a in args if a])
    if not actions:
        return None
    if len(actions) == 1:
        return list(actions)[0]
    return 'modify'


def get_kinds(obj, old=None):
    result = []  # list of (kind, action)
    if obj.tag == 'node':
        result.append(('traffic_calming', get_tag_action('traffic_calming', obj, old)))
        ta = is_new_tag_action('highway', 'crossing', obj, old)
        if ta:
            result.append(('crossing', ta))
        else:
            result.append(('crossing_island', get_tag_action('crossing:island', obj, old)))
        result.append(('stop', is_new_tag_action('highway', 'bus_stop', obj, old)))
    elif obj.tag == 'way':
        result.append(('maxspeed', reduce_tag_actions(
            get_tag_action('maxspeed', obj, old),
            get_tag_action('maxspeed:backward', obj, old),
            get_tag_action('maxspeed:forward', obj, old),
        )))
        result.append(('lanes', reduce_tag_actions(
            get_tag_action('lanes', obj, old),
            get_tag_action('lanes:backward', obj, old),
            get_tag_action('lanes:forward', obj, old),
        )))
        result.append(('lit', get_tag_action('lit', obj, old)))
    return [r for r in result if r[1]]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Extracts road changes from an augmented diff file.')
    parser.add_argument('adiff', type=argparse.FileType('rb'),
                        help='Augmented diff file')
    parser.add_argument('-o', '--output', type=argparse.FileType('w'), default=sys.stdout,
                        help='Output CSV file')
    parser.add_argument('-r', '--regions', type=argparse.FileType('r'),
                        help='CSV file with names and wkb geometry for regions to filter')
    parser.add_argument('-t', '--table',
                        help='Instead of CSV, print SQL for importing into this psql table')
    options = parser.parse_args()

    regions = Regions(options.regions)
    adiff = etree.parse(options.adiff).getroot()
    writer = csv.DictWriter(options.output, COLUMNS)
    if not options.table:
        writer.writeheader()
    else:
        options.output.write(f"""\
create table if not exists {options.table} (
    ts timestamp with time zone not null,
    action text not null,
    obj_action text not null,
    kind text not null,
    changeset integer not null,
    uid integer not null,
    username text not null,
    osm_id text not null,
    region text,
    lat double precision,
    lon double precision,
    length integer
);
copy {options.table} ({','.join(COLUMNS)}) from stdin (format csv);
""")
    for action in adiff.findall('action'):
        atype = action.get('type')
        obj = action[0] if atype == 'create' else action.find('new')[0]
        if obj.tag == 'relation':
            continue
        old = None if atype == 'create' else action.find('old')[0]
        data = init_data_from_object(obj, old)
        data['obj_action'] = atype
        data['region'] = regions.find(data['lon'], data['lat'])
        if options.regions and not data['region']:
            continue
        kinds = get_kinds(obj, old)
        for k in kinds:
            data['action'] = k[1]
            data['kind'] = k[0]
            writer.writerow(data)
