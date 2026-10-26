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
