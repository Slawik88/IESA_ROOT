"""Independent coordinate/BFS oracle for actual Python + shipped JS gameplay."""
import json
from pathlib import Path
import random
import subprocess
from core import minesweeper_v2 as rules


def neighbours(size, cell):
    y,x=divmod(cell,size)
    return [c for c in range(size*size) if c!=cell and max(abs(c//size-y),abs(c%size-x))==1]


fixtures,expected=[],[]
for spec in rules.DIFFICULTIES.values():
    for seed in range(48):
        first=seed%(spec.size**2);layout=rules.board(seed.to_bytes(32,'big'),spec,first);mines=set(layout['mines'])
        adjacent={c:len(set(neighbours(spec.size,c))&mines) for c in range(spec.size**2)}
        assert adjacent==layout['adjacent']
        revealed,flags=set(),set();actions=[];states=[];opens=0
        def act(kind,cell):
            global opens,revealed,flags
            actions.append(dict(kind=kind,cell=cell,elapsed_ms=len(actions)*127))
            before=set(revealed);status='active'
            if kind=='toggle_flag':
                if cell not in revealed:
                    if cell in flags:flags.remove(cell)
                    elif len(flags)<spec.mines:flags.add(cell)
            elif cell not in revealed and cell not in flags:
                opens+=1
                if cell in mines:revealed.add(cell);status='lost'
                else:
                    queue=[cell]
                    while queue:
                        c=queue.pop(0)
                        if c in revealed or c in flags or c in mines:continue
                        revealed.add(c)
                        if adjacent[c]==0:queue.extend(neighbours(spec.size,c))
                    if len(revealed)==spec.size**2-spec.mines:status='won'
            got_r,got_f,got_s,_=rules.apply_action(spec=spec,layout=layout,revealed=before,flags=set(states[-1]['flags']) if states else set(),kind=kind,cell=cell)
            assert (got_r,got_f,got_s)==(revealed,flags,status)
            states.append(dict(revealed=sorted(revealed),flags=sorted(flags),status=status,opened_actions=opens))
            return status
        act('open',first);assert states[-1]['status']=='active'
        closed=[c for c in range(spec.size**2) if c not in revealed and c not in mines]
        wrong=closed[-1];act('toggle_flag',wrong);act('open',wrong)
        # Wrong safe flag blocks flood and victory; mines fill the remaining cap.
        for c in sorted(mines):act('toggle_flag',c)
        assert len(flags)==spec.mines
        for c in range(spec.size**2):
            if c not in mines and c!=wrong and c not in revealed:act('open',c)
        assert states[-1]['status']=='active'
        act('toggle_flag',wrong);assert act('open',wrong)=='won'
        packet=dict(state=dict(run_id='probe',difficulty=spec.id,size=spec.size,mine_count=spec.mines,status='awaiting_first_open',revision=0,opened_actions=0,revealed=[],flags=[],elapsed_ms=0),first_cell=None,layouts={str(first):sorted(mines)})
        fixtures.append(dict(packet=packet,actions=actions));expected.append(states)
result=subprocess.run(['node',str(Path(__file__).with_name('mines_gameplay_probe.cjs'))],input=json.dumps(fixtures),capture_output=True,text=True,check=True)
for boards,wants in zip(json.loads(result.stdout),expected):
    for got,want in zip(boards,wants):
        assert sorted(got['revealed'])==want['revealed'] and sorted(got['flags'])==want['flags']
        assert got['status']==want['status'] and got['opened_actions']==want['opened_actions']
print(f"PASS: {len(fixtures)} boards, {sum(len(x) for x in expected)} real actions; numbered borders, wrong flags, cap, unflag and win; Python/JS/BFS agree")
