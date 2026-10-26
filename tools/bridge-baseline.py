"""Keep a manually bootstrapped 0.3.1 installation labelled as the baseline until signed upgrade."""
import ast
import re
import sys
from pathlib import Path


def baseline_source(source):
    assignments=[node for node in ast.parse(source).body if isinstance(node,ast.Assign)
                 and any(isinstance(target,ast.Name) and target.id=='VERSION' for target in node.targets)]
    if len(assignments)!=1 or not isinstance(assignments[0].value,ast.Constant):
        raise ValueError('Expected one explicit application VERSION assignment')
    target=assignments[0]
    if not isinstance(target.value.value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',target.value.value):
        raise ValueError('Expected a numeric application version')
    lines=source.splitlines(keepends=True)
    if target.end_lineno!=target.lineno or lines[target.lineno-1].strip()!='VERSION = '+repr(target.value.value):
        raise ValueError('Unexpected application version declaration')
    ending='\n' if lines[target.lineno-1].endswith('\n') else ''
    lines[target.lineno-1]="VERSION = '0.3.1'"+ending
    return ''.join(lines)


if __name__=='__main__':
    path=Path('/opt/harbor/server.py')
    if sys.platform!='linux':raise SystemExit('Run the updater bridge on the intended Linux appliance.')
    path.write_text(baseline_source(path.read_text(encoding='utf-8')),encoding='utf-8',newline='\n')
