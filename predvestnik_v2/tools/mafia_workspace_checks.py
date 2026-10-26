"""Interaction checks shared by the real-server Mafia browser regression."""


def check_workspace(page, out):
    original = page.viewport_size
    for width, height in ((320, 640), (390, 740), (430, 740), (900, 700), (1440, 900), (1920, 1080), (390, 360)):
        page.set_viewport_size({'width': width, 'height': height})
        for panel in ('players', 'table', 'chat'):
            page.evaluate('(panel) => moTab(panel)', panel)
            page.locator('#mo-text').fill('Черновик остаётся рядом с игрой')
            assert page.evaluate("document.activeElement.id === 'mo-text'")
            bounds = page.evaluate("""() => {
              const chat=el('mo-chat').getBoundingClientRect(), input=el('mo-text').getBoundingClientRect();
              return {chat:chat.height,bottom:input.bottom,top:input.top,overflow:document.documentElement.scrollWidth>innerWidth};
            }""")
            assert bounds['chat'] >= 60, (width, height, panel, bounds)
            assert bounds['bottom'] <= height and bounds['top'] >= 0, bounds
            assert not bounds['overflow'], bounds
        page.evaluate("moShowEvent({kind:'role',role:'mafia',title:'Твоя роль — Мафия',detail:'Договорись с командой и выбери цель.'})")
        event = page.locator('#mo-event').bounding_box()
        chat = page.locator('#mo-chat').bounding_box()
        assert event['y'] >= 0 and event['y'] + event['height'] <= height, event
        assert event['y'] + event['height'] <= chat['y'] or width >= 900, (event, chat)
        page.evaluate('moHelp()')
        page.locator('#mo-text').fill('Можно писать, пока открыты правила')
        assert page.locator('#mo-sheet').is_visible()
        assert page.evaluate("!el('mo-sheet').matches(':modal')")
        page.keyboard.press('Escape')
        assert page.locator('#mo-sheet').is_hidden()
        assert page.evaluate("el('modal').open")
        page.locator('#mo-text').fill('')
        page.evaluate('moLatest()')
        page.screenshot(path=str(out / f'workspace-{width}-{height}.png'))

    page.set_viewport_size({'width': 390, 'height': 740})
    page.evaluate('moLatest()')
    page.emulate_media(reduced_motion='reduce')
    page.evaluate("document.body.classList.add('no-fx')")
    # The composer carries the channels now; the duplicated note row is gone and
    # privacy lives in the chip tooltip and the placeholder.
    assert page.locator('#mo-channel-note').count() == 0
    assert page.evaluate("document.querySelector('.mo-compose-meta').contains(el('mo-channels'))")
    chip = page.evaluate("""() => {
      const b=[...document.querySelectorAll('#mo-channels>button')].find(x=>x.classList.contains('on'));
      return {title:b?.title||'',count:document.querySelectorAll('#mo-channels>button').length};
    }""")
    assert chip['count'] and chip['title'], chip
    page.evaluate("moChannel('mafia')")
    page.wait_for_timeout(50)
    assert page.evaluate("el('mo-text').placeholder.length > 5")
    page.evaluate("moChannel('table')")
    # The phase band is compact by default and grows back for the flash.
    compact = page.evaluate("el('mo-status').querySelector('.mo-phase').getBoundingClientRect().height")
    page.evaluate('moPhaseFlash()')
    flashed = page.evaluate("el('mo-status').querySelector('.mo-phase').getBoundingClientRect().height")
    assert compact <= 56 and flashed >= compact + 8, (compact, flashed)
    page.evaluate("el('mo-root').classList.remove('mo-phase-flash')")
    # Reading mode: scrolling up hides the tool rows, returning to the bottom restores them.
    before = page.evaluate("el('mo-chat').getBoundingClientRect().height")
    scrollable = page.evaluate("el('mo-chat').scrollHeight > el('mo-chat').clientHeight + 120")
    page.evaluate("el('mo-chat').scrollTop = 0")
    page.wait_for_timeout(80)
    if scrollable:
        assert page.evaluate("el('mo-root').classList.contains('mo-reading')")
        assert not page.evaluate("el('mo-actionbar').getBoundingClientRect().height > 0")
        during = page.evaluate("el('mo-chat').getBoundingClientRect().height")
        assert during > before + 20, (before, during)
        page.evaluate('moLatest()')
        page.wait_for_timeout(80)
        assert not page.evaluate("el('mo-root').classList.contains('mo-reading')")
        assert page.evaluate("el('mo-actionbar').getBoundingClientRect().height > 0")
    message = page.locator('.mo-msg:not(.system):not(.hidden-message)').last
    message.locator('.mo-direct-reply').click()
    assert page.locator('#mo-reply').inner_text().startswith('Ответ')
    page.keyboard.press('Escape')
    assert page.locator('#mo-reply').inner_text() == ''

    message.locator('.mo-msg-menu').click()
    page.locator('#mo-sheet').get_by_role('button', name='Ответить', exact=True).click()
    page.wait_for_timeout(60)  # The native close event is queued after the click.
    assert page.evaluate("document.activeElement.id === 'mo-text'")
    page.keyboard.press('Escape')

    # Native touch events test intent detection, capture, and vertical scroll cancellation.
    cdp = page.context.new_cdp_session(page)
    bubble = message.locator('.mo-bubble p')
    bubble.scroll_into_view_if_needed()
    rect = bubble.bounding_box()
    x, y = rect['x'] + min(rect['width'] - 4, 130), rect['y'] + rect['height'] / 2
    def touch(kind, px=0, py=0):
        cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [] if kind == 'touchEnd' else [{'x': px, 'y': py}]})
    touch('touchStart', x, y)
    touch('touchMove', x - 4, y - 22)
    touch('touchEnd')
    assert page.evaluate('MO.reply === null'), 'vertical reading must not select a reply'
    page.wait_for_timeout(400)  # Let the native vertical-scroll gesture finish.
    bubble.scroll_into_view_if_needed()
    rect = bubble.bounding_box()
    y = rect['y'] + rect['height'] / 2
    touch('touchStart', x, y)
    touch('touchMove', x - 20, y)
    touch('touchMove', x - 70, y)
    touch('touchEnd')
    assert page.evaluate('MO.reply !== null'), 'left swipe must reply'
    assert page.evaluate("document.activeElement.id === 'mo-text'")
    page.keyboard.press('Escape')
    page.locator('#mo-text').fill('')
    cdp.detach()
    page.emulate_media(reduced_motion='no-preference')
    page.evaluate("document.body.classList.remove('no-fx')")
    page.set_viewport_size(original)
