import json, os, pathlib, re, struct, subprocess, time, xml.etree.ElementTree as ET

out = pathlib.Path('evidence')
expected_counts = json.loads(os.environ['EXPECTED_COUNTS'])
assert set(expected_counts) == {'plataformas', 'principales', 'secundario', 'en_camino'}
assert all(type(n) is int and n > 0 for n in expected_counts.values())
assert 26 <= expected_counts['plataformas'] <= 256
assert 49 <= sum(expected_counts[k] for k in ('principales', 'secundario', 'en_camino')) <= 1000
assert re.fullmatch(r'[a-f0-9]{40}', os.environ['SOURCE_HEAD_SHA'])
assert re.fullmatch(r'[a-f0-9-]{36}', os.environ['EAS_BUILD_ID'])
geometry = []
traversals = {}


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


def radar_center_checks():
    # Exercise actual input events at each observed visible point centre. The
    # native receiver may be a different overlapping box; the opened platform
    # and the release's local event trace must both identify the visible point.
    prior_density = adb('shell','wm','density')
    prior_size = adb('shell','wm','size')
    prior_font = adb('shell','settings','get','system','font_scale').strip()
    reports = []
    try:
        adb('shell','wm','density','480')
        adb('shell','wm','size','960x1920')
        adb('shell','settings','put','system','font_scale','1.0')
        adb('shell','am','force-stop','com.rwadar.app')
        adb('shell','am','start','-W','-n','com.rwadar.app/.MainActivity')
        wait_ui('Noticias de RWAdar')
        for _ in range(12):
            root = dump()
            points = []
            width,height = display_size()
            for node in root.iter('node'):
                label = node.get('content-desc','')
                if node.get('visible') == 'false' or '. Estado de acceso: ' not in label or not label.endswith('. Abrir ficha.'):
                    continue
                bounds = list(map(int,re.findall(r'-?\d+',node.get('bounds',''))))
                if len(bounds) == 4 and 0 <= bounds[0] < bounds[2] <= width and 0 <= bounds[1] < bounds[3] <= height:
                    name = label.split('. Estado de acceso: ',1)[0].rsplit('. ',1)[0]
                    points.append({'name':name,'label':label,'bounds':bounds})
            if len(points) == expected_counts['plataformas']:
                break
            scroll_down()
        assert len(points) == expected_counts['plataformas'], 'Need every actual radar point visible before centre taps'
        assert len({p['name'] for p in points}) == len(points), 'Radar point names must be unique'
        screen('00-radar-320dp-centros',root)
        for index,point in enumerate(points):
            current = dump()
            _,bounds = find_node(current,point['label'])
            centre = [(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2]
            adb('shell','input','tap',*map(str,centre))
            current = wait_ui('Cerrar ficha de ' + point['name'],timeout=30)
            find_node(current,point['name'])
            screen('00-radar-centro-%02d' % index,current)
            log = adb('logcat','-d','-v','raw','ReactNativeJS:I','*:S')
            events = []
            for line in log.splitlines():
                if 'RWADAR_RADAR_TOUCH' not in line:
                    continue
                match = re.search(r'(\{.*\})',line)
                if match:
                    try:
                        events.append(json.loads(match[1]))
                    except json.JSONDecodeError:
                        pass
            assert events, 'Actual release must expose the local native event-shape evidence'
            event = events[-1]
            assert event['selectedName'] == point['name'], 'The observed visible centre must open its own platform'
            assert type(event['changedTouches']) is int and event['changedTouches'] >= 1, 'Android onPress must carry a real end-event touch sequence'
            assert event['eventType'] != 'click', 'This test must use physical pointer input rather than an accessibility click'
            reports.append({'name':point['name'],'centre':centre,'bounds':bounds,'event':event,'openedOwnPlatform':True})
            tap_observed(current,'Cerrar ficha de ' + point['name'])
            wait_ui(point['label'])
        out.joinpath('radar-native-centres.json').write_text(json.dumps({'display':[width,height],
            'densityDpi':480,'widthDp':320,'points':reports,
            'scope':'Exact visible centres, not 44dp exclusive touch regions or TalkBack traversal'},indent=2),encoding='utf-8')
    finally:
        density = re.search(r'Override density:\s*(\d+)',prior_density)
        size = re.search(r'Override size:\s*(\d+x\d+)',prior_size)
        adb('shell','wm','density',density[1] if density else 'reset')
        adb('shell','wm','size',size[1] if size else 'reset')
        adb('shell','settings','put','system','font_scale',prior_font if prior_font not in ('','null') else '1.0')
        adb('shell','am','force-stop','com.rwadar.app')
        adb('shell','am','start','-W','-n','com.rwadar.app/.MainActivity')
        wait_ui('Noticias de RWAdar')
    return {'checked':True,'count':len(reports),'widthDp':320,'changedTouchesPresent':True,
            'allVisibleCentresOpenOwnPlatform':True,'exclusive44DpRegionsTested':False}


def scroll_down():
    width, height = display_size()
    adb('shell', 'input', 'swipe', str(width//2), str(int(height*.80)), str(width//2), str(int(height*.32)), '450')
    time.sleep(.5)


def document_detail(prefix, title, required, forbidden=(), inspect=None, scan_to_end=False):
    root = wait_ui('Cerrar ' + title)
    remaining = set(required)
    previous_text = None
    observed = []
    for index in range(40):
        root = dump()
        text = visible_text(root)
        observed.append(text)
        if inspect:
            inspect(root)
        assert not any(item in text for item in forbidden), 'Commercial claim in documentary detail: ' + text
        newly = {item for item in remaining if item in text}
        if newly or index == 0:
            screen(prefix + '-%02d' % index, root)
        remaining -= newly
        if not remaining and (not scan_to_end or text == previous_text):
            if scan_to_end:
                screen(prefix + '-complete', root)
            traversals[prefix] = observed
            return root
        previous_text = text
        scroll_down()
    raise AssertionError('Missing visible documentary evidence: ' + ', '.join(sorted(remaining)))


def search(root, query):
    # Reset through the actual accessible native control; do not rely
    # on a stale tree, keyboard shortcuts, or an unobserved coordinate.
    scroll_top()
    root = dump()
    try:
        find_node(root, 'Limpiar búsqueda y filtros de ofertas')
    except AssertionError:
        pass
    else:
        tap_observed(root, 'Limpiar búsqueda y filtros de ofertas')
        time.sleep(.5)
        root = wait_ui('Ofertas específicas')
    tap_observed(root, 'Buscar ofertas por nombre, proveedor, país o métrica')
    adb('shell', 'input', 'text', query.replace(' ', '%s'))
    adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
    return wait_ui(query, '1 de ')


def assert_counts(root):
    text = visible_text(root)
    match = re.search(r'(\d+) principales · (\d+) secundarias · (\d+) en camino', text)
    assert match, 'Missing explicit V2 collection counts: ' + text
    counts = tuple(map(int, match.groups()))
    assert counts == tuple(expected_counts[k] for k in ('principales','secundario','en_camino')), 'Partial or unexpected V2 catalog: ' + str(counts)
    assert '28 fichas' not in text and 'fixture local' not in text and 'copia sin conexión' not in text, 'Old/local/offline catalog must not pass'
    return {'principales': counts[0], 'secundario': counts[1], 'en_camino': counts[2]}


def scroll_top():
    width, height = display_size()
    previous = None
    for _ in range(12):
        current = visible_text(dump())
        if current == previous:
            return
        previous = current
        adb('shell', 'input', 'swipe', str(width//2), str(int(height*.32)), str(width//2), str(int(height*.80)), '350')
        time.sleep(.3)


def reach_control(label, starts=False):
    previous = None
    for _ in range(14):
        root = dump()
        try:
            find_node(root, label, starts=starts)
            return root
        except AssertionError:
            current = visible_text(root)
            if current == previous:
                break
            previous = current
            scroll_down()
    raise AssertionError('Control not reachable by native scrolling: ' + label)


def assert_empty_field(root, label, password=False):
    candidates = [n for n in root.iter('node')
                  if n.get('visible') != 'false'
                  and n.get('class', '').endswith('EditText')
                  and n.get('content-desc') == label]
    assert candidates, 'Accessible native input missing: ' + label
    for field in candidates:
        assert not field.get('text', ''), 'Smoke must never enter credentials or personal data'
        assert field.get('enabled') == 'true', 'Input must be usable: ' + label
        assert field.get('password') == str(password).lower(), 'Password masking mismatch: ' + label


def open_collection(collection):
    scroll_top()
    root = dump()
    try:
        find_node(root, 'Limpiar búsqueda y filtros de ofertas')
    except AssertionError:
        pass
    else:
        tap_observed(root, 'Limpiar búsqueda y filtros de ofertas')
        time.sleep(.5)
    label = ('Mostrar principales ' if collection == 'principales' else 'Mostrar reventa ') + str(expected_counts[collection])
    root = reach_control(label)
    tap_observed(root, label)
    return wait_ui('Ofertas específicas')


def assert_modal_top(root, title, prefix):
    _, close = find_node(root, 'Cerrar ' + title)
    title_node, heading = find_node(root, title)
    width, height = display_size()
    for box in (close, heading):
        assert 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height, 'Modal control outside visible display'
    assert heading[1] >= close[3], 'Full title must start below the persistent modal controls'
    assert title in (title_node.get('text', ''), title_node.get('content-desc', '')), 'Full title missing from the fresh native hierarchy'
    geometry.append({'capture':prefix,'display':[width,height],'closeBounds':close,'titleBounds':heading,'title':title})
    screen(prefix, root)


def group_roundtrip(provider, collection, prefix):
    open_collection(collection)
    label = provider + ': ver '
    root = reach_control(label, starts=True)
    node, _ = find_node(root, label, starts=True)
    match = re.fullmatch(re.escape(provider) + r': ver (\d+) referencias', node.get('content-desc', ''))
    assert match and 2 <= int(match[1]) <= 1000
    size = int(match[1])
    screen(prefix + '-grupo', root)
    tap_observed(root, label, starts=True)
    root = wait_ui('Volver a la colección', 'Referencias de ' + provider)
    assert re.search(r'\b' + str(size) + r' de \d+ fichas', visible_text(root)), 'Group count must count its individual offers'
    screen(prefix + '-abierto', root)
    tap_observed(root, 'Volver a la colección completa de ofertas')
    root = wait_ui('Ofertas específicas')
    assert str(sum(collections.values())) + ' en el catálogo' in visible_text(root), 'Total catalog count must remain visible'
    root = reach_control(label, starts=True)
    screen(prefix + '-vuelta', root)
    return {'provider':provider,'collection':collection,'references':size,'returned':True}


def open_observed_offer(query, title):
    root = search(dump(), query)
    label = 'Ver ficha de ' + title + '.'
    root = reach_control(label, starts=True)
    tap_observed(root, label, starts=True)
    return wait_ui('Cerrar ' + title)


def integral_native_checks():
    groups = [group_roundtrip('Brickwise','principales','18-brickwise'),
              group_roundtrip('Reental','secundario','19-reental')]
    open_collection('principales')
    title = os.environ['LONG_TITLE']
    root = open_observed_offer(os.environ['LONG_TITLE_QUERY'],title)
    assert_modal_top(root,title,'20-titulo-largo-completo')
    adb('shell','input','keyevent','KEYCODE_BACK')
    wait_ui('Ofertas específicas')
    root = open_observed_offer('Spiko','Spiko Letras del Tesoro Euro')
    assert_modal_top(root,'Spiko Letras del Tesoro Euro','21-spiko-cabecera')
    root = document_detail('22-lectura-completa','Spiko Letras del Tesoro Euro',[
        'EN TRES FRASES','¿QUIÉN PUEDE ACCEDER Y EN QUÉ CONDICIONES?',
        'Mínimo publicado en euros','Acceso desde España','Cómo recuperar el dinero','Costes publicados',
        'FECHAS DE ESTA FICHA','Revisión del catálogo:','Última consulta citada:',
        'Fecha del dato en esa referencia:','REFERENCIAS FECHADAS','No son precios actuales',
        '¿Puedo perder dinero?','¿Puedo vender cuando quiera?',
        '¿Quién custodia el activo?','¿Quién supervisa esta oferta?',
        'Puedes perder dinero. RWAdar no vende ni asesora.','Ver en la fuente'],scan_to_end=True)
    principal = [n for n in root.iter('node') if n.get('visible') != 'false' and n.get('content-desc','').startswith('Ver en la fuente ·')]
    assert len(principal) == 1, 'Only one primary source CTA must remain at the end'
    screen('23-un-solo-destino-principal', root)
    tap_observed(root,'Cerrar Spiko Letras del Tesoro Euro')
    wait_ui('Ofertas específicas')
    costs = []
    for sample in [('mF-ONE','0,6% anual sobre AUM'),('mGLO','0,40% anual sobre AUM')]:
        title_cost,management = sample
        open_collection('principales')
        open_observed_offer(title_cost,title_cost)
        prefix = '28-costes-' + ('mf-one' if title_cost == 'mF-ONE' else 'mglo')
        document_detail(prefix,title_cost,['Costes publicados','Comisión de gestión · 22/10/2026',
            management,'Comisión de éxito · 22/10/2026','0%','Consultado el 22/10/2026'],scan_to_end=True)
        combined = any(management in text and 'Comisión de éxito' in text and '0%' in text for text in traversals[prefix])
        assert combined, 'Management and success fees must remain visible together with dated references'
        costs.append({'title':title_cost,'management':management,'success':'0%','consultedOn':'2026-10-22',
                      'bothConceptsObserved':True,'valuesWereNotAdded':True})
        tap_observed(dump(),'Cerrar ' + title_cost)
        wait_ui('Ofertas específicas')
    prior_font = adb('shell','settings','get','system','font_scale').strip()
    prior_rotate = adb('shell','settings','get','system','accelerometer_rotation').strip()
    prior_user_rotate = adb('shell','settings','get','system','user_rotation').strip()
    try:
        adb('shell','settings','put','system','font_scale','1.5')
        adb('shell','wm','size','900x1600')
        adb('shell','am','force-stop','com.rwadar.app')
        adb('shell','am','start','-W','-n','com.rwadar.app/.MainActivity')
        root = wait_ui('Noticias de RWAdar')
        tap_observed(root,'Buscar'); root = wait_ui('Explora lo verificado')
        tap_observed(root,'Mostrar ofertas',starts=True); wait_ui('Ofertas específicas')
        open_collection('principales')
        root = open_observed_offer(os.environ['LONG_TITLE_QUERY'],title)
        assert float(adb('shell','settings','get','system','font_scale').strip()) == 1.5
        assert_modal_top(root,title,'24-fuente-grande-pantalla-corta')
        reach_control('Ver en la fuente ·',starts=True)
        screen('25-fuente-grande-salida-alcanzable',dump())
        adb('shell','settings','put','system','accelerometer_rotation','0')
        adb('shell','settings','put','system','user_rotation','1')
        time.sleep(2)
        scroll_top(); root = wait_ui('Cerrar ' + title)
        assert_modal_top(root,title,'26-rotacion-solicitada')
        size = list(display_size())
        landscape = os.environ['ORIENTATION_POLICY'] == 'default'
        if landscape:
            assert size[0] > size[1], 'A rotatable release must provide real landscape evidence'
            reach_control('Ver en la fuente ·',starts=True)
            screen('27-horizontal-salida-alcanzable',dump())
        else:
            assert os.environ['ORIENTATION_POLICY'] == 'portrait'
        orientation = {'policy':os.environ['ORIENTATION_POLICY'],'requested':'landscape','display':size,
                       'landscapeTested':landscape,'portraitLockIsNotLandscapeCoverage':not landscape}
    finally:
        adb('shell','settings','put','system','font_scale',prior_font if prior_font not in ('','null') else '1.0')
        adb('shell','settings','put','system','accelerometer_rotation',prior_rotate if prior_rotate not in ('','null') else '0')
        adb('shell','settings','put','system','user_rotation',prior_user_rotate if prior_user_rotate not in ('','null') else '0')
        adb('shell','wm','size','reset')
        adb('shell','am','force-stop','com.rwadar.app')
        adb('shell','am','start','-W','-n','com.rwadar.app/.MainActivity')
        wait_ui('Noticias de RWAdar')
    packages = adb('shell','pm','list','packages','com.google.android.marvin.talkback')
    talkback = {'installed':'package:com.google.android.marvin.talkback' in packages,'tested':False,
                'scope':'Accessibility hierarchy is not a TalkBack traversal. Manual speech/focus/gesture review remains pending.'}
    out.joinpath('native-geometry.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')
    out.joinpath('talkback-scope.json').write_text(json.dumps(talkback,indent=2),encoding='utf-8')
    out.joinpath('orientation-scope.json').write_text(json.dumps(orientation,indent=2),encoding='utf-8')
    return {'groups':groups,'fullTitleAndPersistentControls':True,'sourceDatesSeparated':True,
            'fourDecisionFacts':True,'fourRiskQuestions':True,'singlePrimarySourceCta':True,
            'fontScale':1.5,'shortDisplay':[900,1600],'orientation':orientation,'talkback':talkback,'costs':costs}


def language_checks():
    root = dump()
    tap_observed(root,'English')
    root = wait_ui('Home','Search','Profile')
    assert find_node(root,'English')[0].get('checked') == 'true'
    assert_empty_field(root,'Email')
    assert_empty_field(root,'Password',password=True)
    screen('40-idioma-english-perfil-sin-credenciales',root)
    adb('shell','am','force-stop','com.rwadar.app')
    adb('shell','am','start','-W','-n','com.rwadar.app/.MainActivity')
    root = wait_ui('RWAdar news','Home','Search','Profile')
    assert find_node(root,'English')[0].get('checked') == 'true', 'English selection must survive process restart'
    screen('41-english-persistente-tras-reinicio',root)
    radar_label = 'ADDX. Equities and private capital. Access status:'
    root = reach_control(radar_label,starts=True)
    tap_observed(root,radar_label,starts=True)
    root = wait_ui('Close platform details for ADDX')
    screen('41b-radar-english-destino-correcto',root)
    trace = adb('logcat','-d','-v','raw','ReactNativeJS:I','*:S')
    events = []
    for line in trace.splitlines():
        match = re.search(r'RWADAR_RADAR_TOUCH.*?(\{.*\})',line)
        if match:
            events.append(json.loads(match[1]))
    assert events and events[-1]['selectedName'] == 'ADDX' and events[-1]['changedTouches'] >= 1, 'English must preserve native pointer event and destination'
    english_radar_event = events[-1]
    tap_observed(root,'Close platform details for ADDX')
    root = dump()
    tap_observed(root,'Search')
    root = wait_ui('Explore documented information')
    tap_observed(root,'Show offers',starts=True)
    root = wait_ui('Specific offers')
    tap_observed(root,'Search offers by name, provider, country or metric')
    adb('shell','input','text','Spiko')
    adb('shell','input','keyevent','KEYCODE_BACK')
    root = wait_ui('Spiko','1 of ')
    label = 'View details for Spiko Letras del Tesoro Euro.'
    card,_ = find_node(root,label,starts=True)
    for text in ('Published minimum in euros:','Access from Spain:','How to get your money back:'):
        assert text in card.get('content-desc',''), 'Card decision labels must switch to English'
    tap_observed(root,label,starts=True)
    title = 'Spiko Letras del Tesoro Euro'
    root = wait_ui('Close ' + title)
    find_node(root,title) # Offer title stays in its documented original form.
    _,close = find_node(root,'Close ' + title)
    _,heading = find_node(root,title)
    assert heading[1] >= close[3], 'English mode must preserve the modal safe area'
    required = {'Original source text (Spanish)','IN THREE SENTENCES','Published costs','DATES FOR THIS ENTRY',
        'DATED REFERENCES','Could I lose money?','Can I sell whenever I want?','Who holds the asset?',
        'Who supervises this offer?','FR001400ODL1','View at source'}
    english = []
    previous = None
    for index in range(45):
        root = dump(); text = visible_text(root); english.append(text)
        newly = {part for part in required if part in text}
        if newly or index == 0:
            screen('42-ficha-english-%02d' % index,root)
        required -= newly
        if not required and text == previous:
            break
        previous = text
        scroll_down()
    assert not required, 'Missing English/native original-source evidence: ' + ', '.join(sorted(required))
    spanish_text = '\n'.join(traversals['22-lectura-completa'])
    english_text = '\n'.join(english)
    tokens = lambda text:set(re.findall(r'[0-9][0-9.,]*\s*(?:EUR|USD|CHF|GBP|€|%)|(?:EUR|USD|CHF|GBP|€)\s*[0-9][0-9.,]*',text))
    dates = lambda text:set(re.findall(r'\b\d{2}/\d{2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b',text))
    urls = lambda text:set(re.findall(r'https://[^\s<>]+',text))
    assert tokens(spanish_text) and tokens(spanish_text) == tokens(english_text), 'Language switch must not change financial values or units'
    assert dates(spanish_text) == dates(english_text), 'Language switch must preserve source dates'
    assert urls(spanish_text), 'Need actual source destinations observed in the Spanish native traversal'
    assert urls(spanish_text) == urls(english_text), 'Language switch must preserve the source destinations'
    tap_observed(root,'Close ' + title)
    root = wait_ui('Specific offers')
    tap_observed(root,'Español')
    wait_ui('Inicio','Buscar','Perfil')
    adb('shell','am','force-stop','com.rwadar.app')
    adb('shell','am','start','-W','-n','com.rwadar.app/.MainActivity')
    root = wait_ui('Noticias de RWAdar','Inicio','Buscar','Perfil')
    assert find_node(root,'Español')[0].get('checked') == 'true', 'Spanish selection must survive process restart'
    screen('43-espanol-persistente-tras-reinicio',root)
    result = {'englishUi':True,'englishPersistedAfterRestart':True,'spanishUi':True,'spanishPersistedAfterRestart':True,
        'originalOfferTitle':title,'originalSourceNoticeObserved':True,'financialValuesAndUnitsUnchanged':True,
        'sourceDatesUnchanged':True,'sourceUrlsUnchanged':True,'credentialsEntered':False,
        'englishRadarEvent':english_radar_event,
        'observedFinancialTokens':sorted(tokens(spanish_text)),'observedSourceDates':sorted(dates(spanish_text))}
    out.joinpath('language-native.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


# Public, non-secret expectations from the approved editorial-v2 assets.
# Card locations and detail alt text must identify the new per-offer
# photo; a generic category fallback deliberately fails this QA.
editorial_samples = [
  {
    "query": "Spiko",
    "title": "Spiko Letras del Tesoro Euro",
    "slug": "spiko-letras-del-tesoro-euro",
    "group": "principales",
    "location": "Zona euro",
    "alt": "Ilustración editorial de un edificio ministerial neoclásico genérico, como imagen de un fondo que compra letras del Tesoro de la zona euro, imagen generada con IA. Pasos: compras participaciones; el fondo compra letras; pides el reembolso. No es una foto del activo real."
  },
  {
    "query": "Outeiro",
    "title": "Casa de Outeiro",
    "slug": "casa-de-outeiro",
    "group": "principales",
    "location": "Ribeira Sacra · Lugo",
    "alt": "Ilustración editorial de una casa solariega de piedra restaurada entre viñedos en terrazas sobre un cañón fluvial de la Ribeira Sacra, parecida a la real, imagen generada con IA. Pasos: suscribes la ampliación; recibes tus acciones; socio de bodega y hotel. No es una foto del activo real."
  },
  {
    "query": "Prosegur",
    "title": "Prosegur Digital Gold",
    "slug": "prosegur-digital-gold",
    "group": "principales",
    "location": "Custodia en España",
    "alt": "Ilustración editorial de unos lingotes de oro sin marcas en una cámara acorazada, imagen generada con IA. Pasos: compras gramos de oro; se guarda en una cámara; vendes y cobras en euros. No es una foto del activo real."
  },
  {
    "query": "GreenPoint",
    "title": "Fotovoltaica GreenPoint",
    "slug": "fotovoltaica-greenpoint",
    "group": "principales",
    "location": "Wiener Neustadt · Austria",
    "alt": "Ilustración editorial de unos paneles solares en la cubierta de un edificio de oficinas de una ciudad austriaca, imagen generada con IA. Pasos: compras participaciones; los paneles dan energía; reparto del excedente. No es una foto del activo real."
  },
  {
    "query": "Houston 3",
    "title": "Houston 3",
    "slug": "reental-secundario-houston-3",
    "group": "secundario",
    "location": "Houston · EE. UU.",
    "alt": "Ilustración editorial de una hilera de casas estrechas de tres plantas con garaje en Houston, parecida a la real, imagen generada con IA. Pasos: compras si hay oferta; la casa se alquila; reparto o reventa. No es una foto del activo real."
  }
]
editorial_checked = []


def editorial_detail(sample, prefix):
    root = wait_ui('Cerrar ' + sample['title'])
    root = reach_control(sample['alt'])
    assert 'Sin ilustración editorial disponible' not in visible_text(root)
    assert 'imagen generada con IA' in sample['alt']
    assert 'No es una foto del activo real.' in sample['alt']
    time.sleep(.75)
    root = dump()
    find_node(root, sample['alt'])
    screen(prefix + '-foto-detalle', root)
    editorial_checked.append(sample['slug'])
    return root


launch = adb('shell', 'am', 'start', '-W', '-n', 'com.rwadar.app/.MainActivity')
out.joinpath('launch.txt').write_text(launch, encoding='utf-8')
assert 'Status: ok' in launch, launch
# Install the signed production candidate unchanged. No account credentials,
# no acceptance of terms, no Auth submission and no remote SQL mutation.
root = wait_ui('Plataformas de tokenización, con la fuente al lado', 'Noticias de RWAdar')
for tab in ('Inicio', 'Buscar', 'Academy', 'Perfil'):
    find_node(root, tab)
screen('01-inicio', root)
radar_native = radar_center_checks()
root = dump()
tap_observed(root, 'Buscar')
root = wait_ui('Explora lo verificado', str(expected_counts['plataformas']) + ' plataformas')
screen('02-buscar-empresas', root)
tap_observed(root, 'Mostrar ofertas', starts=True)
root = wait_ui('Ofertas específicas', f"{expected_counts['principales']} principales · {expected_counts['secundario']} secundarias · {expected_counts['en_camino']} en camino")
collections = assert_counts(root)
assert sum(collections.values()) == sum(expected_counts[k] for k in ('principales','secundario','en_camino'))
screen('03-buscar-ofertas', root)
root = search(root, 'Spiko')
node, _ = find_node(root, 'Ver ficha de Spiko Letras del Tesoro Euro.', starts=True)
label = node.get('content-desc', '')
out.joinpath('spiko-card.txt').write_text(label, encoding='utf-8')
# Date-sensitive yields are not hardcoded: the complete public catalog
# must stay available even when a revision expires.
assert 'Spiko Letras del Tesoro Euro' in label, label
for field in ('Mínimo publicado en euros:', 'Acceso desde España:', 'Cómo recuperar el dinero:', 'Fuente consultada'):
    assert field in label, 'Missing documented card fact: ' + field
assert 'Sin comprobar desde España' in label, 'QA must not infer Spain admission from geography'
assert editorial_samples[0]['location'] in label and 'Ilustración editorial' in label, label
screen('04-spiko-tarjeta', root)
tap_observed(root, 'Ver ficha de Spiko Letras del Tesoro Euro.', starts=True)
root = editorial_detail(editorial_samples[0], '04b-editorial-spiko')
tap_observed(root, 'Guardar Spiko Letras del Tesoro Euro en Perfil')
root = wait_ui('Quitar Spiko Letras del Tesoro Euro de guardadas')
screen('05-favorito-local', root)
root = document_detail('06-spiko-ficha', 'Spiko Letras del Tesoro Euro',
                       ['CARACTERÍSTICAS DOCUMENTADAS', 'FR001400ODL1', 'REFERENCIAS FECHADAS', 'FECHAS DE ESTA FICHA'])
tap_observed(root, 'Cerrar Spiko Letras del Tesoro Euro')
root = wait_ui('Ofertas específicas')
for index, sample in enumerate(editorial_samples[1:], start=1):
    scroll_top()
    root = dump()
    group_label = 'Mostrar principales ' + str(expected_counts['principales']) if sample['group'] == 'principales' else 'Mostrar reventa ' + str(expected_counts['secundario'])
    root = reach_control(group_label)
    tap_observed(root, group_label)
    root = search(wait_ui('Ofertas específicas'), sample['query'])
    card_label = 'Ver ficha de ' + sample['title'] + '.'
    card, _ = find_node(root, card_label, starts=True)
    accessible = card.get('content-desc', '')
    assert sample['location'] in accessible and 'Ilustración editorial' in accessible, accessible
    prefix = '06b-editorial-%02d' % index
    screen(prefix + '-tarjeta', root)
    tap_observed(root, card_label, starts=True)
    root = editorial_detail(sample, prefix)
    tap_observed(root, 'Cerrar ' + sample['title'])
    root = wait_ui('Ofertas específicas')
assert editorial_checked == [sample['slug'] for sample in editorial_samples]
out.joinpath('editorial-photos.json').write_text(json.dumps({
    'samples':editorial_samples, 'checkedSlugs':editorial_checked,
    'automaticScope':'Exact per-offer alt text and location; screenshots require separate visual review',
    'visualReviewCompleted':False}, indent=2), encoding='utf-8')
integral = integral_native_checks()
root = dump()
tap_observed(root, 'Academy')
root = wait_ui('de 7 lecciones leídas')
screen('07-academy', root)
root = reach_control('Lección 1:', starts=True)
tap_observed(root, 'Lección 1:', starts=True)
root = wait_ui('Lección 1 de', 'Volver a las lecciones')
screen('07b-academy-leccion-real', root)
tap_observed(root, 'Volver a las lecciones')
root = wait_ui('de 7 lecciones leídas')
tap_observed(root, 'Perfil')
root = wait_ui('Entra en tu cuenta')
assert_empty_field(root, 'Correo')
assert_empty_field(root, 'Contraseña', password=True)
screen('08-perfil-entrar', root)
# The EMPTY login is rejected by local validation before the controller:
# no actual email/password is entered or sent.
root = reach_control('Entrar')
tap_observed(root, 'Entrar')
scroll_top()
root = wait_ui('Escribe un correo válido.')
screen('09-validacion-local-sin-credenciales', root)
root = reach_control('Crear una cuenta gratis')
tap_observed(root, 'Crear una cuenta gratis')
scroll_top()
root = wait_ui('Crea tu cuenta')
assert_empty_field(root, 'Correo')
root = reach_control('Contraseña · mínimo 12 caracteres')
assert_empty_field(root, 'Contraseña · mínimo 12 caracteres', password=True)
root = reach_control('Nombre (opcional)')
assert_empty_field(root, 'Nombre (opcional)')
root = reach_control('Acepto las condiciones y he leído la privacidad')
consent, _ = find_node(root, 'Acepto las condiciones y he leído la privacidad')
assert consent.get('checkable') == 'true' and consent.get('checked') == 'false', 'Terms must not be accepted by QA'
screen('10-perfil-alta-sin-aceptacion', root)
for control in ('Leer condiciones', 'Leer privacidad', 'Crear cuenta'):
    reach_control(control)
# Do not press Crear cuenta, send recovery/confirmation, or open external
# provider investment links. These forms are inspected only.
root = reach_control('Volver a entrar')
tap_observed(root, 'Volver a entrar')
scroll_top()
root = wait_ui('Entra en tu cuenta')
root = reach_control('He olvidado la contraseña')
tap_observed(root, 'He olvidado la contraseña')
scroll_top()
root = wait_ui('Recupera tu acceso')
assert_empty_field(root, 'Correo')
root = reach_control('Enviar enlace de recuperación')
# Regression found during the APK13 visual review: the local-favorite
# note must not invade the account card. Compare real native bounds
# on the fixed Pixel6 emulator, not only a static style assertion.
root = reach_control('Los siguientes favoritos se guardan solo', starts=True)
_, return_bounds = find_node(root, 'Volver a entrar')
_, note_bounds = find_node(root, 'Los siguientes favoritos se guardan solo', starts=True)
note_gap_pixels = note_bounds[1] - return_bounds[3]
assert note_gap_pixels >= 40, 'Local-favorite note overlaps account card: gap=' + str(note_gap_pixels)
screen('11-recuperacion-sin-envio', root)
root = reach_control('Volver a entrar')
tap_observed(root, 'Volver a entrar')
scroll_top()
root = wait_ui('Entra en tu cuenta')
root = reach_control('No he recibido la confirmación')
tap_observed(root, 'No he recibido la confirmación')
scroll_top()
root = wait_ui('Confirma tu correo')
root = reach_control('Correo para reenviar la confirmación')
assert_empty_field(root, 'Correo para reenviar la confirmación')
reach_control('Reenviar confirmación')
screen('12-confirmacion-sin-reenvio', dump())
root = reach_control('Ya confirmé: entrar')
tap_observed(root, 'Ya confirmé: entrar')
scroll_top()
root = wait_ui('Entra en tu cuenta')
root = reach_control('Ofertas guardadas · 1')
screen('13-favorito-en-perfil', root)
root = reach_control('Spiko Letras del Tesoro Euro.', starts=True)
screen('14-oferta-guardada', root)
tap_observed(root, 'Inicio')
root = wait_ui('Noticias de RWAdar')
screen('15-vuelta-a-inicio', root)
tap_observed(root, 'Perfil')
scroll_top()
root = wait_ui('Entra en tu cuenta')
assert '1 guardado en este dispositivo' in visible_text(root), 'Singular favorite heading must be correct'
assert_empty_field(root, 'Correo')
assert_empty_field(root, 'Contraseña', password=True)
screen('16-perfil-reabierto', root)
# Local favorites must survive a full process restart; accounts must
# still be unauthenticated because the smoke never signed in.
adb('shell', 'am', 'force-stop', 'com.rwadar.app')
restart = adb('shell', 'am', 'start', '-W', '-n', 'com.rwadar.app/.MainActivity')
assert 'Status: ok' in restart, restart
root = wait_ui('Noticias de RWAdar')
tap_observed(root, 'Perfil')
root = wait_ui('Entra en tu cuenta')
assert_empty_field(root, 'Correo')
assert_empty_field(root, 'Contraseña', password=True)
root = reach_control('Ofertas guardadas · 1')
reach_control('Spiko Letras del Tesoro Euro.', starts=True)
screen('17-favorito-tras-reinicio', dump())
assert adb('shell', 'pidof', 'com.rwadar.app').strip(), 'App process must remain alive'
language = language_checks()
logs = adb('logcat', '-d', '-v', 'threadtime', 'AndroidRuntime:E', 'ReactNativeJS:E', '*:S')
out.joinpath('app-errors.log').write_text(logs, encoding='utf-8')
assert 'FATAL EXCEPTION' not in logs, 'Android crash recorded'
assert not re.search(r'ReactNativeJS.*(?:Error:|TypeError|ReferenceError|Invariant Violation)', logs), 'JavaScript error recorded'
checks20 = [
    ('01','Identidad, firma, instalación y arranque del APK exacto'),
    ('02','Cuatro pestañas ES/EN y selección de idioma persistente tras reinicio'),
    ('03','Conteos íntegros y 26 centros reales del radar abren su plataforma a 320dp'),
    ('04','Tarjeta con mínimo EUR, España, salida y cifra contextualizada'),
    ('05','Título largo completo bajo controles persistentes'),
    ('06','Atrás de Android cierra la ficha'),
    ('07','Grupo Brickwise abre y vuelve conservando conteos'),
    ('08','Grupo Reental abre y vuelve conservando conteos'),
    ('09','Búsqueda exacta accede a fichas individuales'),
    ('10','Revisión, consulta y fecha del dato separadas'),
    ('11','Referencias históricas contextualizadas'),
    ('12','Cuatro preguntas de riesgo accesibles antes del enlace'),
    ('13','Un CTA principal de fuente al final de la ficha'),
    ('14','Cinco ilustraciones específicas con alt y capturas'),
    ('15','Escala de texto 1.5 y pantalla corta alcanzan cierre y fuente'),
    ('16','Política de giro y dimensiones reales documentadas'),
    ('17','Academy y una lección real navegables'),
    ('18','Favorito local persiste tras reiniciar el proceso'),
    ('19','Formularios accesibles sin credenciales ni consentimientos'),
    ('20','Proceso vivo y sin excepciones Android/JavaScript registradas'),
]
checks20 = [{'id':identifier,'point':point,'status':'checked'} for identifier,point in checks20]
assert len(checks20) == 20 and len({c['id'] for c in checks20}) == 20
out.joinpath('native-checks-20.json').write_text(json.dumps({'points':checks20,
    'scope':'Automatic observations on this emulator; screenshots need separate visual review. TalkBack, physical device and real Auth are excluded.'},indent=2),encoding='utf-8')
result = {'package':'com.rwadar.app', 'version':'1.4.0', 'versionCode':18,
          'accountPanelNoteSeparated':True, 'accountPanelNoteGapPixels':note_gap_pixels,
          'apkSha256':os.environ['APK_SHA256'], 'apkBytes':int(os.environ['APK_BYTES']),
          'certificateSha256':os.environ['CERT_SHA256'], 'workflowSha':os.environ['WORKFLOW_SHA'],
          'headSha':os.environ['HEAD_SHA'], 'runId':os.environ['RUN_ID'],
          'androidApi':35, 'installation':True, 'launch':True,
          'tabs':['Inicio', 'Buscar', 'Academy', 'Perfil'],
          'visibleCatalogPlatforms':expected_counts['plataformas'], 'catalogSchemaVersion':2, 'collections':collections,
          'sourceCommit':os.environ['SOURCE_HEAD_SHA'],'easBuildId':os.environ['EAS_BUILD_ID'],
          'nativeChecks20':checks20,'integralUi':integral,
          'radarNativeCentres':radar_native,
          'languageUi':language,
          'talkBackTested':False,'landscapeTested':integral['orientation']['landscapeTested'],
          'dailyCatalogExpansionOnDeviceTested':False,
          'spikoDocumentaryDetail':True, 'academyLessons':7,
          'editorialPhotoSlugs':editorial_checked, 'editorialPhotoAccessibility':True,
          'editorialVisualReviewCompleted':False,
          'localFavoritePersistsAfterRestart':True,
          'accountForms':['login', 'signup', 'recovery', 'confirmation'],
          'emptyLoginValidation':True, 'passwordInputsMasked':True,
          'credentialsEntered':False, 'termsAccepted':False,
          'authEndToEndTested':False, 'smtpTested':False,
          'physicalDevice':False, 'scope':'Signed APK on Android API35 emulator; no actual account creation/login/deletion'}
out.joinpath('result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
