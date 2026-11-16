"""Native independent-engine comparison on the same frozen development rasters.

Use the official Audiveris 5.11 macOS arm64 read-only bundle, not an installation.
The local jar copy changes only WellKnowns' environment key HOME to the dedicated
AUDIVERIS_TASK_HOME, keeping state inside this workspace without changing HOME.
This path-only bytecode change is recorded by hashes and does not alter OMR.
Audiveris is AGPL-3.0; this benchmark does not integrate it into the web product.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from practice_metrics import METRIC_VERSION, compare, read

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'web/src/py'))
import pipeline


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_paths_jar(source, target):
    with ZipFile(source) as original, ZipFile(target, 'w', compression=ZIP_DEFLATED) as patched:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == 'org/audiveris/omr/WellKnowns.class':
                old, new = b'\x00\x04HOME', b'AUDIVERIS_TASK_HOME'
                if data.count(old) != 1:
                    raise ValueError('Unexpected WellKnowns class: refuse to patch')
                data = data.replace(old, len(new).to_bytes(2, 'big')+new)
            patched.writestr(info, data)


def parse_mxl(path):
    with ZipFile(path) as archive:
        container = ET.fromstring(archive.read('META-INF/container.xml'))
        rootfile = next(node for node in container.iter() if node.tag.endswith('rootfile'))
        return ET.fromstring(archive.read(rootfile.get('full-path')))


def run(args):
    bundle, output = args.bundle.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = output/'engine-state'
    state.mkdir(exist_ok=True)
    original = bundle/'Contents/app/audiveris.jar'
    patched = state/'audiveris-local-paths.jar'
    local_paths_jar(original, patched)
    java = bundle/'Contents/runtime/Contents/Home/bin/java'
    command = [str(java), f'-Duser.home={state}', '-Djava.awt.headless=true',
               '-XX:ActiveProcessorCount=4', '-Xmx2G', '--add-exports=java.desktop/sun.awt.image=ALL-UNNAMED',
               '--enable-native-access=ALL-UNNAMED', '-cp', f'{patched}:{bundle}/Contents/app/*', 'Audiveris']
    env = dict(os.environ, AUDIVERIS_TASK_HOME=str(state))
    version = subprocess.run(command+['-version'], env=env, capture_output=True, text=True, timeout=60, check=True)
    report = {'engine': 'Audiveris', 'license': 'AGPL-3.0', 'versionOutput': version.stdout+version.stderr,
              'metricVersion': METRIC_VERSION, 'originalJarSha256': digest(original), 'localPathsJarSha256': digest(patched),
              'binaryAdaptation': 'Only WellKnowns HOME environment key changed to AUDIVERIS_TASK_HOME; recognition code and model resources unchanged',
              'inputPolicy': 'same frozen development PNG pages; embedded engine OCR, no GT-derived output edits',
              'normalization': 'MusicXML decompress + part-preserving page concatenation only; no bar alignment or transposition',
              'scope': 'native Java CPU diagnostic; not a browser backend', 'cases': []}
    def save():
        (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    for directory in sorted(args.cases_root.resolve().glob('dev-*')):
        case = json.loads((directory/'case.json').read_text())
        if args.only and case['id'] not in args.only:
            continue
        truth = directory/'truth.musicxml'
        if digest(truth) != case['truthSha256']:
            raise ValueError('Frozen truth hash changed')
        dest = output/case['id']
        dest.mkdir(exist_ok=True)
        pages = sorted(directory.glob('input-*.png'))
        item = {'id': case['id'], 'truthSha256': digest(truth),
                'inputs': [{'file': p.name, 'sha256': digest(p)} for p in pages], 'commands': []}
        started = time.monotonic()
        try:
            readings = []
            for page in pages:
                copied = dest/page.name
                shutil.copy2(page, copied)
                call = command+['-batch', '-export', '-output', str(dest), '--', str(copied)]
                item['commands'].append(call)
                with (dest/(page.stem+'.log')).open('w') as log:
                    subprocess.run(call, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
                readings.append(parse_mxl(dest/(page.stem+'.mxl')))
            merged = pipeline._merge_pages(readings)
            path = dest/'merged.musicxml'
            ET.ElementTree(merged).write(path, encoding='utf-8', xml_declaration=True)
            item.update(status='read', metrics=compare(ET.parse(truth).getroot(), merged), outputSha256=digest(path))
            (dest/'strict.json').write_text(json.dumps(item['metrics'], indent=2)+'\n')
        except Exception as error:
            total = sum(read(ET.parse(truth).getroot())['events'].values())
            item.update(status='failed', error=str(error), metrics={'events': {'truth': total, 'reading': 0, 'correct': 0}})
        item['seconds'] = round(time.monotonic()-started, 3)
        report['cases'].append(item)
        save()
        print(json.dumps({key: item[key] for key in ('id', 'status', 'seconds')} | {'events': item['metrics']['events']}), flush=True)
    report['status'] = 'complete'
    save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, default=ROOT.parent/'audiveris-mount/Audiveris.app')
    parser.add_argument('--only', nargs='*')
    run(parser.parse_args())
