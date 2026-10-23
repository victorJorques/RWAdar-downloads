"""QA scoped to anonymous access and packaging. Never authorizes release."""
import hashlib, json, os, pathlib, re, struct, subprocess, sys, time, traceback, zipfile, xml.etree.ElementTree as ET
out = pathlib.Path('evidence')
out.mkdir(exist_ok=True)
scroll_gestures = []
EXPECTED_SOURCE = '1ecf7e7aa8941400d6ad954680cd6deb89107c42'
EXPECTED_EAS = '215e184c-2856-408f-9323-ed285f41b3ed'
EXPECTED_APK_SHA256 = 'f384a20017e09a4bc0650a0be82231b29acf6abd9629e1075442d458bd277624'
EXPECTED_APK_BYTES = 88961445
PHOTOS=[{'slug': 'aktionariat', 'bytes': 66118, 'hashSha256': 'fba8276ae85f496ec2ac963ceb6d5efe3a3cb219d07f094621d2ad087c98cd8a'}, {'slug': 'apartamento-vacacional-hinterstoder-50', 'bytes': 71648, 'hashSha256': '096581c56c2ab598bfb9f6ac074820ab75d0ac3a67f62f6b2bd58a96319ca38f'}, {'slug': 'boss-info', 'bytes': 43046, 'hashSha256': 'eefb6294c388d35509076d588ce5a0ec80ad0451862b9e2b89aa7169da0a0389'}, {'slug': 'casa-de-outeiro', 'bytes': 76464, 'hashSha256': 'ba40a863620ae5e7846068e3a3d3f909caaca976aaf784c560235db228026952'}, {'slug': 'drautalresidenz-paternion', 'bytes': 58670, 'hashSha256': '56b68f826356e8c99b93ee8902b3b434220431fcc1aa70237369c5b22e34841b'}, {'slug': 'fotovoltaica-cohotel', 'bytes': 35060, 'hashSha256': '2676899be75ecb64f3872450a5c15bb0902144ce3c558ebbc706f8ef64aa985b'}, {'slug': 'fotovoltaica-greenpoint', 'bytes': 42470, 'hashSha256': '46b1085be2730803e83c478bbc6261ed9dfee391a94e4983470b1e7dffcd3a72'}, {'slug': 'hausera-proximas-ofertas', 'bytes': 62086, 'hashSha256': '455f0ce616cf7f7c883096624dc164f9f761d3d57de56226d7a3639d1796111b'}, {'slug': 'iod-occasio', 'bytes': 69368, 'hashSha256': 'b0959bf7b237aec15dc1fbda23319989b82f53fe3fa23d213ea55b3095889669'}, {'slug': 'local-de-estanco-klagenfurt', 'bytes': 58604, 'hashSha256': '3072a97b0d8898bbae6e9a699210ebf7c90ecca6ab642a884670db9e7c230198'}, {'slug': 'mf-one', 'bytes': 72732, 'hashSha256': 'dc97cb8bca4ec476f7a58f1a68556eff44299a09fd9c4e2e2b35f1b80f678175'}, {'slug': 'mglo', 'bytes': 49326, 'hashSha256': '7c308994bb30d7cc7cf9f0dfade0eabbc39cac8e0e7cfce4f8d1b150aae1659e'}, {'slug': 'mglobal', 'bytes': 51478, 'hashSha256': '40927e53e1238dcd3bb8b32b6b05caa2a3a7c4f35f2059b914621e955a6e94c5'}, {'slug': 'mgloeuro', 'bytes': 34966, 'hashSha256': 'caf2e4591b07e0f082d9896bbf88d6fe81e5acf1fec87b163bf0a5c1406f040e'}, {'slug': 'mtbill', 'bytes': 41512, 'hashSha256': '7337326d1d234482f88fc42f12241ce3e74d635bea4efd80dc3a66639e5afd09'}, {'slug': 'prosegur-digital-gold', 'bytes': 64062, 'hashSha256': '1eef9d20a89baa866aa01657019f03ef1ecb65171c3ea072caaf12babf12d0b0'}, {'slug': 'randhartingergasse-9-viena', 'bytes': 52508, 'hashSha256': '9deb3f7da6c66ab337ef97ad3a8706da6e6fdbe21abc60bce2d3a81908447ff8'}, {'slug': 'reental-emision-primaria', 'bytes': 63602, 'hashSha256': '58c9a20136371c0e118acc691fdb49738569e1eae793fff95b7bd8a79ec5a5ad'}, {'slug': 'reental-secundario-abu-dhabi-1', 'bytes': 59404, 'hashSha256': 'a829faa3481d90c39da73e922074cf5ab98b544cc9f9255574eea872b5d9c83d'}, {'slug': 'reental-secundario-atlanta-1', 'bytes': 46366, 'hashSha256': 'f90e1b7e877b42cfd2630c653f29c333ed112c2efb5639ff27fc39d3a9bc615b'}, {'slug': 'reental-secundario-carolina-del-norte-1', 'bytes': 90006, 'hashSha256': '9509ae2b070eda395ecdb40b02fe7ed110181ed3ac4d9720528695de3b9de05c'}, {'slug': 'reental-secundario-dania-beach-1', 'bytes': 59916, 'hashSha256': '0ed52073dc2069bc8edf49bd1a33865850e7e1e5627f2cffc6c704fc4abf636d'}, {'slug': 'reental-secundario-granada-3', 'bytes': 74198, 'hashSha256': '7c4362c77faacea6d8cf50f5a19a6e8d85eb21aea498aebfb04d8aeab4266bd3'}, {'slug': 'reental-secundario-houston-1', 'bytes': 53704, 'hashSha256': '0671c6d9f717fa39f31714f59b79ee93e48fa314b6385f5a5f3052f9d7ae9ff6'}, {'slug': 'reental-secundario-houston-2', 'bytes': 85534, 'hashSha256': '418a646995c2b589772bd48a1ce18ccf157963fc85ca5e3eff90b5db8b339b54'}, {'slug': 'reental-secundario-houston-3', 'bytes': 79930, 'hashSha256': '80064cb8dcd295822529894d45a19a12b6843daee53ea57cf947626ce9ac71e2'}, {'slug': 'reental-secundario-levante-1', 'bytes': 62000, 'hashSha256': 'd4d064c424aef6cfb2881c905b226ff71f0db5c7fefaedfd1d372d0b0a8d42a9'}, {'slug': 'reental-secundario-malaga-6', 'bytes': 69548, 'hashSha256': '1d49671033060b4d215900f18f5ac94103cb71f21f225bc46b5f4c569c233649'}, {'slug': 'reental-secundario-miami-1', 'bytes': 60724, 'hashSha256': '6f4e0633e9d4c6af9c025ba6cba33f3582d80bc5f3ed127ed19f942bbad1f61c'}, {'slug': 'reental-secundario-miami-2', 'bytes': 94928, 'hashSha256': 'a2a7ce2c8834e9406a7ed4e09dabd710166753bc9f7176a4c85a3eb2bd1eb1b2'}, {'slug': 'reental-secundario-miami-3', 'bytes': 48754, 'hashSha256': '4e42766fc38f78029c868f5d6bed7c3db3db27bd3f4f8f8ba414ecb966ece163'}, {'slug': 'reental-secundario-miami-5', 'bytes': 68964, 'hashSha256': '820c91a4ddcbaa7f65c113e41bef65bf4eff67050cd6da93ca8f2f9231566976'}, {'slug': 'reental-secundario-opportunity-2', 'bytes': 61404, 'hashSha256': 'acf387e755cfe077c0cd6930bfe705f9d675b37fbf00b22d16d0ad84301f99b9'}, {'slug': 'reental-secundario-pirineos-1', 'bytes': 66368, 'hashSha256': 'e5c0c74da090faf49484c2eb2b8765b9ed15c46f962c267faecc246194780ddd'}, {'slug': 'reental-secundario-proyecto-100', 'bytes': 73586, 'hashSha256': 'c103a7eab315d6bb64f107ea2ecff6217fb02d354c6edb6b9797499cca79f384'}, {'slug': 'reental-secundario-rentas-1', 'bytes': 71270, 'hashSha256': '8d1daff4fa37dd5768e9304fb0caf40d2c48f3df4d0babea4da0c357190c7568'}, {'slug': 'reental-secundario-rentas-2', 'bytes': 75868, 'hashSha256': '7ec7206862167eb6a8e630cfc93dbaa370eb2f187f4a5592bd3610899614582a'}, {'slug': 'reental-secundario-rentas-3', 'bytes': 59868, 'hashSha256': '6ea97ced81e72784555c2f634ad5bcd09f64e840be1ce79b511b7180e9c1fed4'}, {'slug': 'reental-secundario-san-antonio-1', 'bytes': 54070, 'hashSha256': 'b38f4eed604372e14f3bd19862153da415461ee4374bf9ad45e7b4a43f4cb164'}, {'slug': 'servicehunter-quitt', 'bytes': 55938, 'hashSha256': '728425617b4226dabdf0670c20ba1d15dd614a5626a4a90e9f966792c126c71d'}, {'slug': 'spiko-letras-del-tesoro-euro', 'bytes': 44674, 'hashSha256': '36765508129b9a90475ffcca024f56c767ac21ed06d048f2cd0d8a3c8aac8eca'}, {'slug': 'switzerlend', 'bytes': 60752, 'hashSha256': 'fd3b7d9e489eb7f7b81d8438bb9f093dce6fd4d27b128499ea8119fe97c94594'}, {'slug': 'terreno-con-arrendamiento-billa', 'bytes': 86094, 'hashSha256': 'a27447e69016501a25d25b37b411d25b3d815daf2bab2248b19a64f02499b32b'}, {'slug': 'vivienda-pluddemanngasse-101-graz', 'bytes': 57236, 'hashSha256': '68ffb11a12c2924e4712e05aa0becb93e42506dfeb891ce54bf7c5057dd13507'}, {'slug': 'vivienda-pottendorfer-stra-e-62-wr-neustadt', 'bytes': 45228, 'hashSha256': 'dd90f1d52a7742c4a131d9fffe528450ea3a34052d82487b65e35135af39d7ae'}, {'slug': 'vivienda-schwarzer-weg-18-graz', 'bytes': 67808, 'hashSha256': '4b938a75099b59e849f76443ecbbd2dcffbd0e6969c029ff9d3b212c2e452f70'}, {'slug': 'vivienda-sonnleithnergasse-2-viena', 'bytes': 88962, 'hashSha256': 'd588ca9b84844f6cc729a9ebdac4ca23fe77a518ca283e9fe8d59d3417f90ace'}, {'slug': 'vivienda-stallhofstra-e-28-gratwein', 'bytes': 77928, 'hashSha256': '3f6355db0b63f7c97b25fe1e28ec31760af2ef49f52ab7b3a9c7f81cf717f3f6'}, {'slug': 'wemakeit', 'bytes': 69858, 'hashSha256': 'ef7e8e3cde4029d179350f2c75eab9b7f72e2ffd64c84562a50198d2dd41fdf7'}]
class TransientSnapshotError(Exception):
    pass


def adb(*args, timeout=20):
    return subprocess.run(['adb', *args], check=True, capture_output=True, timeout=timeout).stdout.decode('utf-8', errors='replace')


def dump_once(timeout=30):
    raw = adb('shell', 'am', 'instrument', '-w', '-r', 'com.rwadar.smoketest/.DumpRunner', timeout=timeout)
    out.joinpath('latest-ui-instrumentation.txt').write_text(raw, encoding='utf-8')
    marker = 'INSTRUMENTATION_RESULT: rwadar_ui='
    if marker not in raw and 'No active UI root' in raw:
        raise TransientSnapshotError('UiAutomation has no active root during a window transition')
    assert marker in raw, 'Fresh UI snapshot failed: ' + raw[-1200:]
    xml = raw.split(marker, 1)[1].split('\nINSTRUMENTATION_', 1)[0].strip()
    root = ET.fromstring(xml)
    out.joinpath('latest-ui.xml').write_text(xml, encoding='utf-8')
    return root


def dump(timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return dump_once(timeout=max(.1, deadline - time.monotonic()))
        except TransientSnapshotError as error:
            with out.joinpath('snapshot-errors.log').open('a', encoding='utf-8') as log:
                log.write(str(error) + '\n')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(2, remaining))


def visible_text(root):
    return '\n'.join(value for node in root.iter('node') if node.get('visible') != 'false' for value in [node.get('text', ''), node.get('content-desc', '')] if value)


def wait_ui(*texts, timeout=75):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            root = dump(timeout=min(30, max(.1, deadline - time.monotonic())))
            if all(text in visible_text(root) for text in texts):
                return root
        except (subprocess.SubprocessError, ET.ParseError, TransientSnapshotError) as error:
            with out.joinpath('snapshot-errors.log').open('a', encoding='utf-8') as log:
                log.write(str(error) + '\n')
        time.sleep(2)
    raise AssertionError('Native UI did not visibly show: ' + ', '.join(texts))


def screen(name, root=None):
    image = subprocess.run(['adb', 'exec-out', 'screencap', '-p'], check=True, capture_output=True, timeout=20).stdout
    assert image.startswith(b'\x89PNG'), 'Screenshot must be a real PNG'
    out.joinpath(name + '.png').write_bytes(image)
    if root is not None:
        out.joinpath(name + '.xml').write_text(ET.tostring(root, encoding='unicode'), encoding='utf-8')


def capture_failure(name):
    # Capture the failing viewport before finally restores display/font settings.
    # Keep the original assertion if either diagnostic operation also fails.
    for kind, operation in [('png', lambda: screen(name)),
                            ('xml', lambda: out.joinpath(name + '.xml').write_text(
                                ET.tostring(dump(timeout=10), encoding='unicode'), encoding='utf-8'))]:
        try:
            operation()
        except Exception as error:
            with out.joinpath('failure-capture-errors.log').open('a', encoding='utf-8') as log:
                log.write(name + '.' + kind + ': ' + type(error).__name__ + '\n')


def display_size():
    data = subprocess.run(['adb', 'exec-out', 'screencap', '-p'], check=True, capture_output=True, timeout=20).stdout
    assert data.startswith(b'\x89PNG'), 'Need actual rotated display dimensions'
    return struct.unpack('>II', data[16:24])


def find_node(root, label, starts=False):
    candidates = []
    for node in root.iter('node'):
        values = [node.get('content-desc', ''), node.get('text', '')]
        if node.get('visible') != 'false' and any(v.startswith(label) if starts else v == label for v in values):
            candidates.append(node)
    candidates.sort(key=lambda n: n.get('clickable') != 'true')
    for node in candidates:
        bounds = list(map(int, re.findall(r'-?\d+', node.get('bounds', ''))))
        if len(bounds) == 4 and bounds[2] > bounds[0] and bounds[3] > bounds[1]:
            return node, bounds
    raise AssertionError('Accessible control not found: ' + label)


def tap_observed(root, label, starts=False):
    node, bounds = find_node(root, label, starts)
    adb('shell', 'input', 'tap', str((bounds[0]+bounds[2])//2), str((bounds[1]+bounds[3])//2))
    return node


def scroll_down():
    swipe_scroll(forward=True)
    time.sleep(.5)


def swipe_scroll(forward, root=None):
    # Fixed headers differ between Home, Search and translated/font-scaled UI.
    # Use the actual vertical native viewport, never screen-percentage guesses.
    root = dump() if root is None else root
    width, height = display_size()
    regions = []
    for node in root.iter('node'):
        if node.get('visible') == 'false' or node.get('class') not in (
                'android.widget.ScrollView', 'androidx.recyclerview.widget.RecyclerView'):
            continue
        bounds = list(map(int, re.findall(r'-?\d+', node.get('bounds', ''))))
        if len(bounds) != 4:
            continue
        left, top, right, bottom = bounds
        if 0 <= left < right <= width and 0 <= top < bottom <= height and bottom-top >= 80:
            regions.append(bounds)
    assert len(regions) == 1, 'Need one unambiguous visible vertical native scroll viewport: ' + str(regions)
    left, top, right, bottom = regions[0]
    x = (left+right)//2
    low = top + int((bottom-top)*.16)
    high = top + int((bottom-top)*.84)
    start, end = (high, low) if forward else (low, high)
    assert top < min(start,end) < max(start,end) < bottom, 'Gesture must stay inside the observed viewport'
    scroll_gestures.append({'display':[width,height], 'bounds':regions[0],
        'direction':'forward' if forward else 'backward', 'start':[x,start], 'end':[x,end]})
    out.joinpath('native-scroll-gestures.json').write_text(json.dumps(scroll_gestures,indent=2),encoding='utf-8')
    adb('shell','input','swipe',str(x),str(start),str(x),str(end),'450')


def scroll_top():
    previous = None
    for _ in range(12):
        root = dump()
        # A tall visible paragraph can retain identical text while its native
        # bounds move through a short viewport. Include observed bounds before
        # deciding that a swipe has reached a stable edge.
        current = scroll_position(root)
        if current == previous:
            return
        previous = current
        swipe_scroll(forward=False,root=root)
        time.sleep(.3)


def reach_control(label, starts=False):
    previous = None
    for _ in range(14):
        root = dump()
        try:
            find_node(root, label, starts=starts)
            return root
        except AssertionError:
            current = scroll_position(root)
            if current == previous:
                break
            previous = current
            scroll_down()
    capture_failure('control-not-reached-' + re.sub(r'[^a-z0-9]+','-',label.lower()).strip('-')[:70])
    raise AssertionError('Control not reachable by native scrolling: ' + label)


def scroll_position(root):
    return tuple((node.get('class',''),node.get('bounds',''),node.get('text',''),node.get('content-desc',''))
                 for node in root.iter('node') if node.get('visible') != 'false')



def verify_photos(apk):
    expected = {p['hashSha256']: p for p in PHOTOS}
    assert len(expected) == 49, 'Need 49 distinct reviewed editorial photos'
    found = {}
    with zipfile.ZipFile(apk) as archive:
        assert archive.testzip() is None, 'APK ZIP CRC failure'
        for info in archive.infolist():
            if not info.is_dir() and info.filename.lower().endswith('.webp'):
                assert info.file_size <= 4*1024*1024
                data = archive.read(info)
                digest = hashlib.sha256(data).hexdigest()
                if digest in expected:
                    assert len(data) == expected[digest]['bytes'] and digest not in found
                    found[digest] = info.filename
    assert set(found) == set(expected), 'Missing or changed reviewed photos'
    return [{'slug': p['slug'], 'sha256': h, 'bytes': p['bytes'], 'apkEntry': found[h]} for h, p in expected.items()]


def denied(root):
    values = {v for n in root.iter('node') for v in [n.get('text', ''), n.get('content-desc', '')] if v}
    assert not values.intersection({'Inicio', 'Buscar', 'Perfil', 'Ofertas específicas', 'Mostrar plataformas', 'Tu cartera'}), 'Anonymous user reached catalog/tab bar'


def reachable(label):
    # Each next target can be above the previous one on font1.5/short screens.
    scroll_top()
    root = reach_control(label)
    denied(root)
    _, b = find_node(root, label)
    w, h = display_size()
    assert 0 <= b[0] < b[2] <= w and 0 <= b[1] < b[3] <= h, 'Clipped control: ' + label
    return root


def click(label):
    tap_observed(reachable(label), label)
    time.sleep(.2)


def restart():
    adb('shell', 'am', 'force-stop', 'com.rwadar.app')
    launched = adb('shell', 'am', 'start', '-W', '-n', 'com.rwadar.app/.MainActivity')
    assert 'Status: ok' in launched, launched
    root = wait_ui('Tu radar, con tu cuenta', 'Entra en tu cuenta', timeout=30)
    denied(root)
    return root


def forms(prefix, invalid=False):
    scroll_top()
    for label in ('Correo', 'Contraseña', 'Entrar', 'Crear una cuenta gratis', 'He olvidado la contraseña'):
        reachable(label)
    screen(prefix + '-entrar', dump())
    click('Crear una cuenta gratis')
    wait_ui('Crea tu cuenta', timeout=20)
    for label in ('Correo', 'Contraseña · mínimo 12 caracteres', 'Acepto las condiciones y he leído la privacidad', 'Crear cuenta', 'Volver a entrar'):
        reachable(label)
    screen(prefix + '-alta', dump())
    if invalid:
        scroll_top()
        tap_observed(reachable('Correo'), 'Correo')
        adb('shell', 'input', 'text', 'correo-invalido')
        adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
        click('Crear cuenta')
        scroll_top()
        root = wait_ui('Escribe un correo válido.', timeout=15)
        denied(root)
        screen(prefix + '-error-local', root)
    click('Volver a entrar')
    scroll_top()
    root = wait_ui('Entra en tu cuenta', timeout=20)
    assert 'Escribe un correo válido.' not in visible_text(root), 'View change must clear local error'
    click('He olvidado la contraseña')
    scroll_top()
    wait_ui('Recupera tu acceso', timeout=20)
    for label in ('Correo', 'Enviar enlace de recuperación', 'Volver a entrar'):
        reachable(label)
    screen(prefix + '-recuperar-sin-envio', dump())
    # Never press recovery or confirmation, never use a valid address/credential.
    click('Volver a entrar')
    scroll_top()
    denied(wait_ui('Entra en tu cuenta', timeout=20))
    return {'controlsReachable': True, 'catalogAbsent': True, 'signup12CharacterLabel': True,
            'invalidEmailLocallyChecked': invalid, 'recoveryNotSubmitted': True}


def block_form_network():
    # AOSP ConnectivityService shell: airplane-mode [enable|disable].
    # https://android.googlesource.com/platform/packages/modules/Connectivity/+/refs/heads/main/service/src/com/android/server/ConnectivityService.java
    # The system service sends its protected broadcast; the adb shell must not.
    adb('shell', 'cmd', 'connectivity', 'airplane-mode', 'enable')
    adb('shell', 'svc', 'wifi', 'disable')
    adb('shell', 'svc', 'data', 'disable')
    deadline = time.monotonic() + 15
    state = {}
    while True:
        state = {'airplane': adb('shell', 'cmd', 'connectivity', 'airplane-mode').strip(),
                 'wifi': adb('shell', 'settings', 'get', 'global', 'wifi_on').strip(),
                 'mobileData': adb('shell', 'settings', 'get', 'global', 'mobile_data').strip()}
        connectivity = adb('shell', 'dumpsys', 'connectivity')
        state['noActiveDefaultNetwork'] = bool(re.search(r'(?m)^\s*Active default network:\s*none\s*$', connectivity))
        if state == {'airplane': 'enabled', 'wifi': '0', 'mobileData': '0', 'noActiveDefaultNetwork': True}:
            out.joinpath('network-blocked.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
            return state
        assert time.monotonic() < deadline, 'Network not disabled before forms: ' + repr(state)
        time.sleep(.5)


def main():
    assert os.environ['SOURCE_HEAD_SHA'] == EXPECTED_SOURCE
    assert os.environ['EAS_BUILD_ID'] == EXPECTED_EAS
    assert os.environ['APK_SHA256'] == EXPECTED_APK_SHA256
    assert int(os.environ['APK_BYTES']) == EXPECTED_APK_BYTES
    apk = pathlib.Path('rwadar.apk')
    assert apk.stat().st_size == int(os.environ['APK_BYTES'])
    with apk.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == os.environ['APK_SHA256']
    report = {'scope': 'anonymous-access-and-package-only', 'sourceHeadSha': EXPECTED_SOURCE,
              'easBuildId': EXPECTED_EAS, 'apkSha256': os.environ['APK_SHA256'], 'apkBytes': apk.stat().st_size,
              'version': '1.4.0', 'versionCode': 19, 'status': 'failed', 'checks': {},
              'authenticatedCatalogQA': 'pending-real-confirmed-account', 'full20PointQA': False,
              'releaseApproved': False, 'formNetwork': 'blocked-airplane-mode'}
    original = {k: adb('shell', 'settings', 'get', 'system', k).strip()
                for k in ('font_scale', 'accelerometer_rotation', 'user_rotation')}
    original['airplane'] = adb('shell', 'settings', 'get', 'global', 'airplane_mode_on').strip()
    original['wifi'] = adb('shell', 'settings', 'get', 'global', 'wifi_on').strip()
    original['data'] = adb('shell', 'settings', 'get', 'global', 'mobile_data').strip()
    try:
        report['checks']['photos49'] = verify_photos(apk)
        assert "versionCode='19' versionName='1.4.0'" in out.joinpath('package.txt').read_text()
        report['checks']['packageIdentity'] = True
        # Disposable emulator only. Block delivery before entering invalid text.
        report['checks']['networkBlockedBeforeForms'] = block_form_network()
        adb('logcat', '-c')
        restart()
        report['checks']['standard'] = forms('01-standard', True)
        adb('shell', 'settings', 'put', 'system', 'font_scale', '1.5')
        adb('shell', 'wm', 'size', '900x1600')
        restart()
        report['checks']['font15'] = forms('02-font15')
        adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', '0')
        adb('shell', 'settings', 'put', 'system', 'user_rotation', '1')
        time.sleep(1)
        restart()
        dimensions = display_size()
        report['checks']['rotationAttempt'] = forms('03-rotation-attempt')
        report['checks']['rotationAttempt'].update({'actualDisplay': list(dimensions),
            'actualLandscape': dimensions[0] > dimensions[1], 'declaredOrientationPolicy': 'portrait',
            'note': 'Portrait-locked output does not certify a landscape layout.'})
        errors = adb('logcat', '-d', '-v', 'threadtime', 'AndroidRuntime:E', 'ReactNativeJS:E', '*:S')
        out.joinpath('native-errors.log').write_text(errors, encoding='utf-8')
        assert not re.search(r'FATAL EXCEPTION|ReactNativeJS.*(?:TypeError|ReferenceError|Invariant Violation|Error:)', errors), 'Runtime exception'
        report['checks']['noRuntimeException'] = True
        report['status'] = 'passed-scoped-only'
    except Exception as error:
        capture_failure('failure-anonymous-access')
        report['failure'] = str(error)
        out.joinpath('failure-traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        # Try every restoration; never replace the original test traceback.
        original_error_active = sys.exc_info()[0] is not None
        cleanup_errors = []
        commands = [('shell', 'wm', 'size', 'reset')]
        for key, default in [('font_scale', '1.0'), ('accelerometer_rotation', '1'), ('user_rotation', '0')]:
            commands.append(('shell', 'settings', 'put', 'system', key, original[key] if original[key] not in ('', 'null') else default))
        commands.extend([
            ('shell', 'cmd', 'connectivity', 'airplane-mode', 'enable' if original['airplane'] == '1' else 'disable'),
            ('shell', 'svc', 'wifi', 'enable' if original['wifi'] == '1' else 'disable'),
            ('shell', 'svc', 'data', 'enable' if original['data'] == '1' else 'disable'),
        ])
        for command in commands:
            try:
                adb(*command)
            except Exception as error:
                cleanup_errors.append(' '.join(command) + ': ' + str(error))
        if cleanup_errors:
            report['cleanupErrors'] = cleanup_errors
            if not original_error_active:
                report['status'] = 'failed-cleanup'
        try:
            out.joinpath('anonymous-access-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as error:
            cleanup_errors.append('Writing result: ' + str(error))
        if cleanup_errors and not original_error_active:
            raise AssertionError('QA cleanup failed: ' + '; '.join(cleanup_errors))


if __name__ == '__main__':
    main()
