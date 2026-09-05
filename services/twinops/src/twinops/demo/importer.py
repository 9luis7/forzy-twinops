"""Signature-aware, standard-library ingestion of normalized historical pairs."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import math
from pathlib import Path
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
EXPECTED = ('1.1. Velocidade', '1.2. Aceleração', '1.3. Temperatura',
            '2.1. Velocidade', '2.2. Aceleração', '2.3. Temperatura')


def _xlsx_rows(content):
    with ZipFile(io.BytesIO(content)) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(node.itertext()) for node in
                       ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        book = ET.fromstring(archive.read('xl/workbook.xml'))
        sheet = book.find('s:sheets/s:sheet', NS)
        if sheet is None:
            raise ValueError('history workbook has no sheet')
        relation = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(node.attrib['Target'] for node in rels if node.attrib['Id'] == relation)
        path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        with archive.open(path) as stream:
            for _, element in ET.iterparse(stream, events=('end',)):
                if element.tag != '{' + NS['s'] + '}row':
                    continue
                row = [''] * 9
                for cell in element.findall('s:c', NS):
                    letters = re.match(r'[A-Z]+', cell.attrib.get('r', 'A1')).group()
                    column = 0
                    for letter in letters:
                        column = column * 26 + ord(letter) - 64
                    if column > 9:
                        continue
                    value = cell.findtext('s:v', default='', namespaces=NS)
                    if cell.attrib.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.attrib.get('t') == 'inlineStr':
                        value = ''.join(cell.find('s:is', NS).itertext())
                    row[column - 1] = value
                yield row
                element.clear()


def read_history(path, *, timezone_name='America/Sao_Paulo', expected_hash=None):
    """Return public metadata and normalized pairs; never retain PDI or paths."""
    content = Path(path).read_bytes()
    digest = sha256(content).hexdigest()
    if expected_hash and digest != expected_hash.removeprefix('sha256:'):
        raise ValueError('history source hash mismatch')
    zipped = content.startswith(b'PK\x03\x04')
    rows = iter(_xlsx_rows(content) if zipped else
                csv.reader(io.StringIO(content.decode('utf-8-sig')), delimiter=';'))
    try:
        first, semantic, units = next(rows), next(rows), next(rows)
    except StopIteration:
        raise ValueError('history requires three header rows') from None
    # Some native workbooks contain UTF-8 bytes decoded as Latin-1 in labels.
    def label(value):
        try:
            return value.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
    if any(len(row) != 9 for row in (first, semantic, units)) or tuple(map(label, semantic[3:])) != EXPECTED:
        raise ValueError('unrecognized history header')
    zone = ZoneInfo(timezone_name)
    pairs = []
    previous = None
    for source_row, row in enumerate(rows, 1):
        if len(row) != 9 or not row[0]:
            raise ValueError(f'invalid history row {source_row}')
        try:
            observed = datetime.fromisoformat(row[0])
        except ValueError:
            try:
                observed = datetime(1899, 12, 30) + timedelta(days=float(row[0]))
            except (ValueError, OverflowError):
                raise ValueError(f'invalid timestamp at row {source_row}') from None
        assumed = observed.tzinfo is None
        if assumed:
            observed = observed.replace(tzinfo=zone)
        observed = observed.astimezone(timezone.utc)
        if previous is not None and observed < previous:
            raise ValueError(f'non-monotonic timestamp at row {source_row}')
        previous = observed
        timestamp = observed.isoformat().replace('+00:00', 'Z')
        try:
            values = [float(value.replace(',', '.')) for value in row[3:]]
        except (ValueError, OverflowError):
            raise ValueError(f'invalid measurement at row {source_row}') from None
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f'non-finite measurement at row {source_row}')
        sensors = {}
        for offset, sensor_id in ((0, 's1'), (3, 's2')):
            sensors[sensor_id] = {
                'vibrationVelocityRms': {'value': values[offset], 'unit': 'mm/s', 'semanticConfidence': 'inferred_from_datasheet'},
                'vibrationAcceleration': {'value': values[offset + 1], 'unit': 'g', 'statistic': 'unknown', 'semanticConfidence': 'unconfirmed'},
                'temperature': {'value': values[offset + 2], 'unit': 'degC', 'semanticConfidence': 'inferred_from_datasheet'},
            }
        pairs.append({'sourceRow': source_row, 'observedAt': timestamp, 'sensors': sensors,
                      'qualityFlags': [f'observed_timezone_assumed:{timezone_name}'] if assumed else []})
    if not pairs:
        raise ValueError('history contains no pairs')
    metadata = {'datasetId': 'forzy-history-' + digest[:16], 'label': 'Histórico real Forzy',
                'pairCount': len(pairs), 'readingCount': len(pairs) * 2,
                'startAt': pairs[0]['observedAt'], 'endAt': pairs[-1]['observedAt'],
                'sourceHash': 'sha256:' + digest, 'sourceFormat': 'zip-ooxml' if zipped else 'csv',
                'guided': {'startRow': 141, 'endRow': 440}}
    return metadata, pairs


def import_history(path, repository, **kwargs):
    metadata, pairs = read_history(path, **kwargs)
    repository.import_dataset(metadata, pairs)
    return metadata
