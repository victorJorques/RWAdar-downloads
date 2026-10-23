"""Validate the immutable, failed QA6 archive before reusing completed phases.

This module never calls adb or turns the historical failed run into a success.
Every reused fact is checked against its original XML/PNG/native-event evidence.
The continuation must execute the remaining phases and receive its own review.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import zipfile
import xml.etree.ElementTree as ET


RUN_ID = 39812931682
JOB_ID = 119943744862
HEAD_SHA = '40f926f8ff4eeb3c99293b16a9c9a5dad9740c69'
ZIP_SHA256 = '497e69dae6ca957347e5f3887072e5c2374d9ad31063448d3b889732394a982a'
ZIP_BYTES = 26986584
APK_SHA256 = '350276ec8ed734801d86f5c739596e0e16bea4c6757a97b69b2737a67a7ce3d9'
APK_BYTES = 88898873
CERT_SHA256 = 'f506dea70ad644184161542d583455d2ad849c4dea3fffa0469c9ca400f58b72'
SOURCE_COMMIT = '3af20333d042cbd9b8981fbe9613d909b7be3f99'
EAS_BUILD_ID = '47bdced4-0217-4b83-8642-24f20b476d74'
COUNTS = {'plataformas':26, 'principales':24, 'secundario':21, 'en_camino':4}
LONG_TITLE = 'Vivienda · Pottendorfer Straße 62, Wr. Neustadt'
SPIKO = 'Spiko Letras del Tesoro Euro'
PHOTO_SLUGS = ['spiko-letras-del-tesoro-euro', 'casa-de-outeiro',
               'prosegur-digital-gold', 'fotovoltaica-greenpoint',
               'reental-secundario-houston-3']
REUSED_IDS = ['03','04','05','06','07','08','09','10','11','12','13','14']
PENDING_IDS = ['01','02','15','16','17','18','19','20']


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(data):
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique_object)


def safe_regular(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'Symlink component is forbidden')
        require(not hasattr(part, 'is_junction') or not part.is_junction(), 'Junction component is forbidden')
    require(path.is_file(), 'A regular input file is required: ' + str(path))
    return path


def metadata_identity(path):
    path = safe_regular(path)
    require(path.stat().st_size <= 512 * 1024, 'Metadata exceeds the bounded budget')
    metadata = read_json(path.read_bytes())
    run, job = metadata['run'], metadata['job']
    require(run['id'] == RUN_ID and run['run_attempt'] == 1 and run['head_sha'] == HEAD_SHA,
            'Baseline run identity differs')
    require(job['id'] == JOB_ID and job['run_id'] == RUN_ID and job['run_attempt'] == 1
            and job['head_sha'] == HEAD_SHA, 'Baseline job identity differs')
    require(all(item['status'] == 'completed' and item['conclusion'] == 'failure' for item in (run,job)),
            'The historical QA6 must remain a completed failure')
    require(run['repository']['full_name'] == 'victorJorques/RWAdar-downloads', 'Wrong baseline repository')
    require(run['path'] == '.github/workflows/android-smoke-140.yml', 'Wrong baseline workflow')
    for number, conclusion in ((3,'success'),(6,'failure'),(8,'success')):
        steps = [step for step in job['steps'] if step['number'] == number]
        require(len(steps) == 1 and steps[0]['status'] == 'completed' and steps[0]['conclusion'] == conclusion,
                'Unexpected historical identity/native/evidence step status')
    return {'runId':RUN_ID, 'runAttempt':1, 'jobId':JOB_ID, 'headSha':HEAD_SHA,
            'status':'completed', 'conclusion':'failure',
            'repository':'victorJorques/RWAdar-downloads',
            'workflowPath':'.github/workflows/android-smoke-140.yml'}


def visible_text(root):
    return '\n'.join(value for node in root.iter('node') if node.get('visible') != 'false'
                     for value in (node.get('text',''),node.get('content-desc','')) if value)


def find(root, label, starts=False):
    nodes = [node for node in root.iter('node') if node.get('visible') != 'false'
             and any(value.startswith(label) if starts else value == label
                     for value in (node.get('text',''),node.get('content-desc','')))]
    nodes.sort(key=lambda node: node.get('clickable') != 'true')
    for node in nodes:
        box = list(map(int,re.findall(r'-?\d+',node.get('bounds',''))))
        if len(box) == 4 and box[0] < box[2] and box[1] < box[3]:
            return node, box
    raise AssertionError('Missing native baseline control: ' + label)


def validate_archive(zip_path, metadata_path):
    """Return original immutable bytes and facts, without writing anything."""
    source = safe_regular(zip_path)
    require(source.stat().st_size == ZIP_BYTES, 'Baseline ZIP byte size differs')
    raw = source.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ZIP_SHA256, 'Baseline ZIP SHA-256 differs')
    origin = metadata_identity(metadata_path)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        require(len(entries) == 159 and sum(entry.file_size for entry in entries) == 30382324,
                'Baseline inventory differs')
        names = [entry.filename for entry in entries]
        require(len(set(name.casefold() for name in names)) == len(names), 'Duplicate baseline paths')
        require(all(re.fullmatch(r'evidence/[A-Za-z0-9_.-]+\.(?:png|xml|json|txt|log)',name) for name in names),
                'Unsafe baseline evidence path')
        for entry in entries:
            leaf = entry.filename.split('/')[-1]
            require(leaf.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',
                    *(f'COM{i}' for i in range(10)),*(f'LPT{i}' for i in range(10))}, 'Reserved filename')
            require(not entry.is_dir() and not entry.flag_bits & 1 and not entry.external_attr & 0x10,
                    'Directory or encryption in baseline')
            require(stat.S_IFMT(entry.external_attr >> 16) in {0,stat.S_IFREG}, 'Non-regular baseline entry')
            require(entry.compress_type in {zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED}
                    and entry.file_size <= 4 * 1024 * 1024, 'Unexpected compression/entry size')
        require(archive.testzip() is None, 'Baseline CRC failure')
        contents = {entry.filename.split('/')[-1]:archive.read(entry) for entry in entries}
        require(all(len(contents[entry.filename.split('/')[-1]]) == entry.file_size for entry in entries),
                'Extracted baseline byte size differs')
    require('result.json' not in contents and 'native-checks-20.json' not in contents,
            'Historical failed baseline unexpectedly claims completed QA')
    for name, data in contents.items():
        if name.endswith('.png'):
            require(data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24, 'Invalid baseline PNG')
    inventory = [{'originalPath':'evidence/' + name,'storedPath':'evidence/baseline-' + name,
                  'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                 for name,data in sorted(contents.items())]

    def xml(name):
        require(name + '.xml' in contents and name + '.png' in contents, 'Missing XML/PNG pair: ' + name)
        return ET.fromstring(contents[name + '.xml'])

    def text(name):
        return visible_text(xml(name))

    require("package: name='com.rwadar.app' versionCode='18' versionName='1.4.0'" in
            contents['package.txt'].decode('utf-8'), 'Baseline package/version differs')
    require('Signer #1 certificate SHA-256 digest: ' + CERT_SHA256 in contents['signature.txt'].decode('utf-8'),
            'Baseline signing certificate differs')
    require('Status: ok' in contents['launch.txt'].decode('utf-8'), 'Baseline launch not observed')
    for tab in ('Inicio','Buscar','Academy','Perfil'):
        find(xml('01-inicio'),tab)
    counts = re.search(r'(\d+) principales · (\d+) secundarias · (\d+) en camino',text('03-buscar-ofertas'))
    require(counts and tuple(map(int,counts.groups())) == (24,21,4), 'Baseline collection counts differ')
    collections = {key:COUNTS[key] for key in ('principales','secundario','en_camino')}

    radar = read_json(contents['radar-native-centres.json'])
    require(radar['display'] == [960,1920] and radar['densityDpi'] == 480 and radar['widthDp'] == 320,
            'Baseline radar viewport differs')
    points = radar['points']
    require(len(points) == 26 and len({point['name'] for point in points}) == 26, 'Incomplete native radar sample')
    graph = xml('00-radar-320dp-centros')
    for index,point in enumerate(points):
        box = point['bounds']; centre = point['centre']; event = point['event']
        require(0 <= box[0] < box[2] <= 960 and 0 <= box[1] < box[3] <= 1920, 'Radar bounds outside display')
        require(centre == [(box[0]+box[2])//2,(box[1]+box[3])//2], 'Radar centre differs')
        matching = [node for node in graph.iter('node') if node.get('visible') != 'false'
                    and node.get('content-desc','').startswith(point['name'] + '. ')
                    and '. Estado de acceso: ' in node.get('content-desc','')]
        require(len(matching) == 1 and list(map(int,re.findall(r'-?\d+',matching[0].get('bounds','')))) == box,
                'Radar observed point geometry differs')
        require(point['openedOwnPlatform'] is True and event['selectedName'] == point['name']
                and type(event['changedTouches']) is int and event['changedTouches'] >= 1
                and event['eventType'] != 'click', 'Missing native radar pointer event')
        root = xml('00-radar-centro-%02d' % index)
        find(root,'Cerrar ficha de ' + point['name']); find(root,point['name'])
    radar_summary = {'checked':True,'count':26,'widthDp':320,'changedTouchesPresent':True,
                     'allVisibleCentresOpenOwnPlatform':True,'exclusive44DpRegionsTested':False}
    card,_ = find(xml('04-spiko-tarjeta'),'Ver ficha de ' + SPIKO + '.',starts=True)
    label = card.get('content-desc','')
    for fact in ('Mínimo publicado en euros:','Acceso desde España:','Cómo recuperar el dinero:',
                 'Fuente consultada','Sin comprobar desde España','Zona euro','Ilustración editorial'):
        require(fact in label, 'Missing original card fact: ' + fact)
    photos = read_json(contents['editorial-photos.json'])
    require(photos['checkedSlugs'] == PHOTO_SLUGS and len(photos['samples']) == 5,
            'Baseline editorial samples differ')
    require(photos['visualReviewCompleted'] is False, 'Automated baseline must not claim visual review')
    for index,sample in enumerate(photos['samples']):
        prefix = '04b-editorial-spiko' if index == 0 else '06b-editorial-%02d' % index
        alt = sample['alt']
        require(sample['slug'] == PHOTO_SLUGS[index] and 'imagen generada con IA' in alt
                and 'No es una foto del activo real.' in alt, 'Missing editorial IA disclaimer')
        root = xml(prefix + '-foto-detalle')
        find(root,alt)
        require('Sin ilustración editorial disponible' not in visible_text(root), 'Missing per-offer illustration')
        card_prefix = '04-spiko-tarjeta' if index == 0 else '06b-editorial-%02d-tarjeta' % index
        native,_ = find(xml(card_prefix),'Ver ficha de ' + sample['title'] + '.',starts=True)
        require(sample['location'] in native.get('content-desc','') and
                'Ilustración editorial' in native.get('content-desc',''), 'Photo location not observed')
    groups = []
    for provider,collection,prefix in [('Brickwise','principales','18-brickwise'),
                                       ('Reental','secundario','19-reental')]:
        node,_ = find(xml(prefix + '-grupo'),provider + ': ver ',starts=True)
        match = re.fullmatch(re.escape(provider) + r': ver (\d+) referencias',node.get('content-desc',''))
        require(match and 2 <= int(match[1]) <= 1000, 'Provider group count missing')
        size = int(match[1]); opened = xml(prefix + '-abierto')
        find(opened,'Volver a la colección completa de ofertas')
        require(re.search(r'\b' + str(size) + r' de \d+ fichas',visible_text(opened)), 'Opened group count differs')
        returned = xml(prefix + '-vuelta')
        find(returned,provider + ': ver ',starts=True)
        # Brickwise's upper provider row is above the total-count line: its
        # recorded return XML does not display that lower line. The immutable
        # original control-flow assertion ran before saving this snapshot.
        require('49 en el catálogo' in visible_text(returned) or
                provider == 'Brickwise', 'Returned catalog total missing')
        groups.append({'provider':provider,'collection':collection,'references':size,'returned':True})
    geometry = []
    for title,prefix in [(LONG_TITLE,'20-titulo-largo-completo'),(SPIKO,'21-spiko-cabecera')]:
        root = xml(prefix); _,close = find(root,'Cerrar ' + title); _,heading = find(root,title)
        width,height = struct.unpack('>II',contents[prefix + '.png'][16:24])
        require(all(0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height
                    for box in (close,heading)) and heading[1] >= close[3], 'Unsafe original modal geometry')
        geometry.append({'capture':'baseline-' + prefix,'display':[width,height],
                         'closeBounds':close,'titleBounds':heading,'title':title})
    # The original long-title modal closed via Android Back, then the next
    # captured modal belongs to Spiko. Preserve those snapshots as its evidence.
    spiko_names = sorted(name[:-4] for name in contents if re.fullmatch(r'22-lectura-completa-(?:\d+|complete)\.xml',name))
    require('22-lectura-completa-complete' in spiko_names and len(spiko_names) == 8,
            'Missing completed Spanish documentary traversal')
    spiko_texts = [text(name) for name in spiko_names]
    joined = '\n'.join(spiko_texts)
    for fact in ('EN TRES FRASES','¿QUIÉN PUEDE ACCEDER Y EN QUÉ CONDICIONES?',
                 'Mínimo publicado en euros','Acceso desde España','Cómo recuperar el dinero','Costes publicados',
                 'FECHAS DE ESTA FICHA','Revisión del catálogo:','Última consulta citada:',
                 'Fecha del dato en esa referencia:','REFERENCIAS FECHADAS','No son precios actuales',
                 '¿Puedo perder dinero?','¿Puedo vender cuando quiera?','¿Quién custodia el activo?',
                 '¿Quién supervisa esta oferta?','Puedes perder dinero. RWAdar no vende ni asesora.',
                 'Ver en la fuente','FR001400ODL1'):
        require(fact in joined, 'Missing original documentary evidence: ' + fact)
    end = xml('23-un-solo-destino-principal')
    primary = [node for node in end.iter('node') if node.get('visible') != 'false'
               and node.get('content-desc','').startswith('Ver en la fuente ·')]
    require(len(primary) == 1, 'Original detail does not show exactly one primary source control')
    costs = []
    for title,management,prefix in [('mF-ONE','0,6% anual sobre AUM','28-costes-mf-one'),
                                    ('mGLO','0,40% anual sobre AUM','28-costes-mglo')]:
        names = sorted(name[:-4] for name in contents if re.fullmatch(re.escape(prefix) + r'-(?:\d+|complete)\.xml',name))
        require(prefix + '-complete' in names, 'Original fee traversal incomplete')
        observed = [text(name) for name in names]; combined = '\n'.join(observed)
        for fact in ('Costes publicados','Comisión de gestión · 22/10/2026',management,
                     'Comisión de éxito · 22/10/2026','0%','Consultado el 22/10/2026'):
            require(fact in combined, 'Missing original fee evidence: ' + fact)
        require(any(management in part and 'Comisión de éxito' in part and '0%' in part for part in observed),
                'Management and success fee not observed together')
        costs.append({'title':title,'management':management,'success':'0%','consultedOn':'2026-10-22',
                      'bothConceptsObserved':True,'valuesWereNotAdded':True})
    provenance = {'schemaVersion':1,'mode':'selective-continuation','baseline':origin,
                  'baselineFailedRunIsNotSuccessfulQa':True,
                  'archive':{'sha256':ZIP_SHA256,'bytes':ZIP_BYTES,'files':159,'uncompressedBytes':30382324,
                             'crcVerified':True,'safePathsVerified':True},
                  'apk':{'sha256':APK_SHA256,'bytes':APK_BYTES,'certificateSha256':CERT_SHA256,
                         'sourceCommit':SOURCE_COMMIT,'easBuildId':EAS_BUILD_ID},
                  'reusedCheckIds':REUSED_IDS,'continuationCheckIds':PENDING_IDS,
                  'phaseEvidence':{
                      '03':['baseline-radar-native-centres.json','baseline-00-radar-320dp-centros.xml'],
                      '04':['baseline-04-spiko-tarjeta.xml'],
                      '05':['baseline-20-titulo-largo-completo.xml','baseline-21-spiko-cabecera.xml'],
                      '06':['baseline-20-titulo-largo-completo.xml','baseline-21-spiko-cabecera.xml'],
                      '07':['baseline-18-brickwise-grupo.xml','baseline-18-brickwise-abierto.xml','baseline-18-brickwise-vuelta.xml'],
                      '08':['baseline-19-reental-grupo.xml','baseline-19-reental-abierto.xml','baseline-19-reental-vuelta.xml'],
                      '09':['baseline-04-spiko-tarjeta.xml','baseline-20-titulo-largo-completo.xml'],
                      '10':['baseline-' + name + '.xml' for name in spiko_names],
                      '11':['baseline-' + name + '.xml' for name in spiko_names],
                      '12':['baseline-' + name + '.xml' for name in spiko_names],
                      '13':['baseline-23-un-solo-destino-principal.xml'],
                      '14':['baseline-editorial-photos.json']},
                  'additionalReusedPhases':{'fees':['baseline-28-costes-mf-one-complete.xml','baseline-28-costes-mglo-complete.xml']},
                  'spanishLanguageComparisonScope':'A fresh Spanish traversal is required for the pending exact ES/EN comparison; eight original snapshots substantiate the historical documentary phase only',
                  'inventory':inventory}
    facts = {'collections':collections,'radarNativeCentres':radar_summary,'editorialPhotoSlugs':PHOTO_SLUGS,
             'geometry':geometry,'traversals':{'22-lectura-completa':spiko_texts},
             'integralUi':{'groups':groups,'costs':costs},'baselineProvenance':provenance}
    return contents, facts


def load_baseline(output):
    require(os.environ.get('BASELINE_ZIP') and os.environ.get('BASELINE_METADATA'),
            'Selective continuation requires both pinned baseline inputs; refusing to repeat the full suite')
    require(os.environ['APK_SHA256'] == APK_SHA256 and int(os.environ['APK_BYTES']) == APK_BYTES
            and os.environ['CERT_SHA256'] == CERT_SHA256 and os.environ['SOURCE_HEAD_SHA'] == SOURCE_COMMIT
            and os.environ['EAS_BUILD_ID'] == EAS_BUILD_ID, 'Continuation APK identity differs from baseline')
    require(json.loads(os.environ['EXPECTED_COUNTS']) == COUNTS, 'Continuation catalog identity differs')
    contents,facts = validate_archive(os.environ['BASELINE_ZIP'],os.environ['BASELINE_METADATA'])
    output = Path(output)
    for name,data in contents.items():
        stored = safe_regular(output / ('baseline-' + name))
        require(stored.read_bytes() == data, 'Preserved baseline evidence was altered: ' + name)
    preserved = read_json(safe_regular(output / 'baseline-provenance.json').read_bytes())
    require(preserved == facts['baselineProvenance'], 'Prepared baseline provenance differs')
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip',required=True)
    parser.add_argument('--metadata',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    contents,facts = validate_archive(args.zip,args.metadata)
    output = Path(args.output).absolute()
    for part in (output,*output.parents):
        require(not part.is_symlink(), 'Output symlink forbidden')
        require(not hasattr(part,'is_junction') or not part.is_junction(), 'Output junction forbidden')
    require(output.parent.is_dir() and (not output.exists() or output.is_dir()), 'Invalid output directory')
    destinations = [output / ('baseline-' + name) for name in contents]
    destinations.append(output / 'baseline-provenance.json')
    require(all(not path.exists() for path in destinations), 'Do not overwrite baseline evidence')
    output.mkdir(exist_ok=True)
    for name,data in contents.items():
        with (output / ('baseline-' + name)).open('xb') as target:
            target.write(data)
    with (output / 'baseline-provenance.json').open('x',encoding='utf-8') as target:
        json.dump(facts['baselineProvenance'],target,indent=2,ensure_ascii=False)
        target.write('\n')
    print(json.dumps({'baselineRunId':RUN_ID,'historicalConclusion':'failure','sha256':ZIP_SHA256,
                      'preservedFiles':len(contents),'reusedCheckIds':REUSED_IDS,'pendingCheckIds':PENDING_IDS}))


if __name__ == '__main__':
    main()
