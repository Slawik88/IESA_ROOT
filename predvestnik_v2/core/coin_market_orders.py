"""Conditional spot orders. All amounts remain integer micro-Mora / milli-coins."""
from core.coin_market_v2 import MarketError, integer, MORA
MAX_ACTIVE=10
LIFETIME_TICKS=30*576  # 30 days of 150-second ticks

def triggered(direction, price, threshold):
    return price<=threshold if direction=='below' else price>=threshold

def validate(coin, state, side, direction, threshold, amount, units):
    if side not in ('buy','sell') or direction not in ('below','above'):
        raise MarketError('Выберите покупку/продажу и направление цены.')
    integer(threshold,minimum=1);coin.price(threshold)
    if triggered(direction,state.price,threshold):
        raise MarketError('Цена уже достигла условия. Выберите другой порог или обычную сделку.')
    integer(amount);integer(units)
    if side=='buy' and (amount<=0 or units!=0):
        raise MarketError('Укажите бюджет покупки в Море.')
    if side=='buy' and amount<10*MORA:
        raise MarketError('Минимальный бюджет автопокупки — 10 Моры.')
    if side=='sell' and (units<=0 or amount!=0):
        raise MarketError('Укажите количество монет для продажи.')
