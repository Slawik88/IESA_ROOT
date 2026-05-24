"""Поиск split-trans конструкций которые ломают грамматику переводов.

Ищет в шаблонах паттерны:
- `{% trans "X" %} <span>{% trans "Y" %}</span>` — два trans подряд, склейка
  работает в EN, но в uk/fr/de часто требует другого падежа.
- `{% trans "X" %} {{ var }}` — переменная подставляется в середину фразы,
  переводчик не контролирует контекст.
- `{% trans "X" %} <a>{% trans "Y" %}</a>` — два trans подряд через ссылку.
- Несколько подряд идущих trans-тегов без разделителей.

Решение для каждого: использовать {% blocktrans %} с HTML/переменными внутри.
"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE = Path(__file__).resolve().parent.parent
TEMPLATES_DIRS = [
    BASE / 'core' / 'templates',
    BASE / 'blog' / 'templates',
    BASE / 'users' / 'templates',
    BASE / 'gallery' / 'templates',
    BASE / 'notifications' / 'templates',
    BASE / 'products' / 'templates',
    BASE / 'templates',
]

# Паттерн: два {% trans "..." %} в одной строке с минимальной разметкой между
SPLIT_TRANS_RE = re.compile(
    r'\{%\s*trans\s+"([^"]+)"\s*%\}'   # первый trans
    r'\s*(<[^>]+>)?\s*'                 # опциональный HTML-тег
    r'\{%\s*trans\s+"([^"]+)"\s*%\}'   # второй trans
)

# Паттерн: trans + переменная + (возможно) trans
TRANS_VAR_RE = re.compile(
    r'\{%\s*trans\s+"([^"]+)"\s*%\}'
    r'\s*[<>\w\s\-/="]*'
    r'\{\{\s*\w+[^}]*\}\}'
)


def scan_file(path: Path):
    """Возвращает список (line_no, type, msgid1, msgid2_or_var, snippet)."""
    issues = []
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        return issues

    for lineno, line in enumerate(text.split('\n'), 1):
        # Пропускаем комментарии
        if line.strip().startswith('{#') or line.strip().startswith('<!--'):
            continue

        # Тип 1: два trans подряд (split phrase)
        for m in SPLIT_TRANS_RE.finditer(line):
            mid1, _wrap, mid2 = m.group(1), m.group(2), m.group(3)
            # Пропускаем если оба msgid это аббревиатуры/одиночные слова
            if len(mid1) <= 3 and len(mid2) <= 3:
                continue
            issues.append({
                'line': lineno,
                'type': 'SPLIT',
                'msgid1': mid1,
                'msgid2': mid2,
                'snippet': line.strip()[:120],
            })

        # Тип 2: trans + переменная
        for m in TRANS_VAR_RE.finditer(line):
            mid1 = m.group(1)
            issues.append({
                'line': lineno,
                'type': 'TRANS+VAR',
                'msgid1': mid1,
                'msgid2': '',
                'snippet': line.strip()[:120],
            })
    return issues


def main():
    all_issues = {}
    for tdir in TEMPLATES_DIRS:
        if not tdir.exists():
            continue
        for path in tdir.rglob('*.html'):
            issues = scan_file(path)
            if issues:
                rel = path.relative_to(BASE)
                all_issues[str(rel)] = issues

    print(f'Просканировано шаблонов: {sum(1 for _ in [p for d in TEMPLATES_DIRS if d.exists() for p in d.rglob("*.html")])}')
    print(f'Файлов с проблемами: {len(all_issues)}\n')

    total_split = 0
    total_var = 0
    for file, issues in sorted(all_issues.items()):
        # Дедуплицируем по (type, msgid1, msgid2, line)
        seen = set()
        unique = []
        for iss in issues:
            key = (iss['type'], iss['msgid1'], iss['msgid2'], iss['line'])
            if key not in seen:
                seen.add(key)
                unique.append(iss)

        split_count = sum(1 for i in unique if i['type'] == 'SPLIT')
        var_count = sum(1 for i in unique if i['type'] == 'TRANS+VAR')
        total_split += split_count
        total_var += var_count

        if split_count == 0 and var_count == 0:
            continue

        print(f'\n📄 {file}  (SPLIT={split_count}, VAR={var_count})')
        for iss in unique[:8]:
            if iss['type'] == 'SPLIT':
                print(f'  L{iss["line"]:>4}  SPLIT:  {iss["msgid1"]!r} + {iss["msgid2"]!r}')
            else:
                print(f'  L{iss["line"]:>4}  VAR:    {iss["msgid1"]!r} + {{var}}')

    print(f'\n{"=" * 70}')
    print(f'ИТОГО: SPLIT={total_split}, TRANS+VAR={total_var}')
    print(f'{"=" * 70}')


if __name__ == '__main__':
    main()
