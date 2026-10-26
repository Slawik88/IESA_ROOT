"""Exercise the actual chat entrypoint: game nouns must not invoke bare actions."""
import asyncio
from unittest.mock import AsyncMock, patch

from test_word_chain_ux import BOT, message
from bot import chat


async def main():
    with (patch.object(chat.word_chain.feature_switches,
                       'disabled', AsyncMock(return_value=None)),
          patch.object(chat, '_silent', AsyncMock(return_value=False)),
          patch.object(chat.mafia, 'gate_message', AsyncMock(return_value=False)),
          patch.object(chat.mafia, 'after_message', AsyncMock()),
          patch.object(chat.purge, 'purge_gate', AsyncMock(return_value=False)),
          patch.object(chat.moderation, 'closed_gate', AsyncMock(return_value=False)),
          patch.object(chat, 'record_message', AsyncMock()) as track,
          patch.object(chat.achievements, 'after_message', AsyncMock()),
          patch.object(chat, 'dispatch', AsyncMock(return_value=True)) as dispatch,
          patch.object(chat.word_chain, 'play_message', AsyncMock()) as play):
        nouns = [name for name in chat.registry.names if name in chat.word_chain.rules.WORDS and chat.registry.get(name).bare]
        assert len(nouns) >= 40, nouns
        for noun in nouns:
            assert chat.registry.get(noun).bare, noun
            await chat.on_message(message(text=noun), BOT, object())
            assert play.call_args.args[-1] == noun
        assert not dispatch.called, 'addressed nouns must reach the game before generic commands'
        assert track.await_count == len(nouns), 'one original message is tracked once'
        play.reset_mock()
        for text in ('бот слова, стоп', '@qa_bot слова, подсказка', 'бот помощь'):
            await chat.on_message(message(text=text), BOT, object())
        assert not play.called and dispatch.await_count == 3
        await chat.on_message(message(text='чай', reply=False), BOT, object())
        assert not play.called and dispatch.await_count == 4, 'normal chat retains bare actions'
        dispatch.reset_mock()
        with patch.object(chat.word_chain.feature_switches, 'disabled', AsyncMock(side_effect=lambda db, features, cid: ('section:games', '') if 'section:games' in features else None)):
            await chat.on_message(message(text='чай'), BOT, object())
        assert not dispatch.called and not play.called, 'disabled game cannot accidentally invoke a warp'
    print('PASS actual chat routing: colliding nouns, explicit commands, normal chat, disabled game, one activity record')


if __name__ == '__main__':
    asyncio.run(main())
