"""Bot/browser balance formatting agrees and never invents a spendable cent."""
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.formatting import format_balance

cases=[('80','80'),('79.99','79,99'),('79.9','79,90'),('79.999999','79,99'),
       ('1094.000013','1\u00a0094,00'),('0','0'),('0.009999','0,00'),
       ('999999999999.999999','999\u00a0999\u00a0999\u00a0999,99')]
for value,want in cases:
    assert format_balance(Decimal(value))==want,(value,format_balance(Decimal(value)))
    assert format_balance(value)==want
assert format_balance(79.99)=='79,99'
assert format_balance(0.1+0.2)=='0,30'
assert format_balance(float('nan'))=='—'
script="""const fs=require('fs'),vm=require('vm');const src=fs.readFileSync(process.argv[1],'utf8');const ctx=vm.createContext({});vm.runInContext(src.slice(src.indexOf('function fmtBalance('),src.indexOf('\\nfunction vipName(')),ctx);console.log(JSON.stringify(JSON.parse(process.argv[2]).map(x=>ctx.fmtBalance(x))));"""
node=shutil.which('node') or 'C:/Program Files/nodejs/node.exe'
actual=json.loads(subprocess.check_output([node,'-e',script,str(ROOT/'FastAPI/static/app.01.js'),json.dumps([v for v,_ in cases])],text=True,encoding='utf8'))
assert actual==[want for _,want in cases],actual
print('PASS: bot/browser cents, whole balances, decimal dust, large exact amounts and 79.99 < 80 display boundary')
