"""Replay only two original DQN cash expressions; no model, training or orders.

Reference: sachink2010/AutomatedStockTrading-DeepQ-Learning (MIT),
commit a95bb6231b71723dc13b0501fc072b4bcfcda773, Trading.ipynb.
Input is code cells joined by a newline in original notebook order.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

SOURCE_SHA256 = 'f74d020c4e4baff4bc7ba25fa98a8f8f55e20d61815d9eb373b5602f5f96ebd1'


def replay(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Pinned source hash mismatch')
    source = raw.decode()
    expressions = []
    for line in source.splitlines():
        statement = line.strip().split('#')[0].strip()
        if statement in (
            'open_cash_t1=state_class_obj.open_cash-state_class_obj.Stock1Price',
            'open_cash_t1=state_class_obj.open_cash+state_class_obj.Stock1Price'):
            expressions.append(ast.parse(statement).body[0].value)
    if len(expressions) != 2:
        raise ValueError('Original buy/sell expressions not found exactly once')
    permitted = (ast.BinOp, ast.Attribute, ast.Name, ast.Load, ast.Sub, ast.Add)
    for expression in expressions:
        if any(not isinstance(node, permitted) for node in ast.walk(expression)):
            raise ValueError('Unexpected executable source')
    compiled = [compile(ast.Expression(x), '<pinned-cash-expression>', 'eval') for x in expressions]
    rows = []
    for exit_price in (95, 100, 105):
        account = SimpleNamespace(open_cash=10000, Stock1Price=100)
        account.open_cash = eval(compiled[0], {'__builtins__': {}}, {'state_class_obj': account})
        account.Stock1Price = exit_price
        gross = (eval(compiled[1], {'__builtins__': {}}, {'state_class_obj': account})-10000)*1000
        net = 1000*exit_price*(1-.001425-.003)-1000*100*(1+.001425)
        assert abs(gross-1000*(exit_price-100)) < .000001
        assert net < gross
        rows.append({'entry':100,'exit':exit_price,'quantity':1000,
                     'original_cash_pnl':gross,'jei_fee_tax_net_pnl':round(net,3),
                     'omitted_cost':round(gross-net,3)})
    assert rows[1]['original_cash_pnl'] == 0
    assert rows[1]['jei_fee_tax_net_pnl'] == -585
    return {'scope':'cash-expression-only; no model training or performance claim',
            'source_sha256':SOURCE_SHA256,'cases':rows,
            'slippage_included':False,'minimum_fee_included':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--training-source',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(replay(args.training_source),indent=2))
