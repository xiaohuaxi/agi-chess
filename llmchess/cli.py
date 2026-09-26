"""命令行：模型对模型、模型对引擎 / 随机走子，下中国象棋或国际象棋。

    python3 -m llmchess play --game xiangqi --tag x1 --black random --max-plies 6
    python3 -m llmchess play --game chess --tag c1 --black engine:maia-1100 --memory notes
    python3 -m llmchess play --game chess --tag c2 --b effort=high --b memory=session   # 两方分设
    python3 -m llmchess play --game xiangqi --tag x2 --dry-run                          # 只打印提示，不调模型
    python3 -m llmchess play --game chess --tag c3 --black engine:maia-1500 --opening random:8 --opening-seed 1
    python3 -m llmchess resume runs/x1                                                  # 暂停后接着下

棋手：claude:<模型>（默认 claude:opus）/ engine:<引擎>[:参数] / random。
  国际象棋引擎 maia-1100 … maia-1900（lc0，go nodes 1）、stockfish[:elo=N|nodes=N|depth=N|movetime=毫秒]；
  中国象棋引擎 fsf[:nodes=N|depth=N|movetime=毫秒]（Fairy-Stockfish，默认 nodes=1000）。
模型相关变量（公共值用 --变量，一方单设用 --w / --b 变量=值，w 是先走的红方 / 白方）：
  effort medium|high|xhigh|max、memory stateless|notes|session、view（逗号分隔）、history（-1 全部 / 0 / N）、
  legal none|list、selfcheck on|off、recite on|off（只有中国象棋）、notes_keep N、session_view full|move。
随机开局 --opening random:N：前 N 个半回合由程序替双方走（引擎浅搜 MultiPV 3、分差 ≤50 厘兵的着法按 --opening-seed 抽），
  开局写进 config、续跑照记录重放；模型只在着法历史里看到这几步。--dry-run 打印的是开局走完后模型方第一步的提示。
记录在 runs/<tag>/（不入库）：game.jsonl、record.txt，国际象棋另有 game.pgn。
暂停（--on-limit pause 时撞额度、连续调不通、--stop-after、停止信号）退出码 3。
--timeout：单次 claude -p 调用的超时秒数（默认 3600），记进 config，resume 沿用；超时 / 调不通各记一条 call_fail。
--on-limit wait|pause：撞额度时在程序里等到解除接着下（默认，起止各记一条 limit_wait），或按旧行为暂停退出（退出码 3）。
  等待中 Ctrl-C / SIGTERM 马上写 pause 退出（退出码 3），resume 接着下；再按一次强退。
"""
import argparse, importlib, json, os, pathlib, random, subprocess, sys, tempfile, uuid

from . import claude_cli, memory, opening, records, runner

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / 'runs'
GAMES = {'xiangqi': 'llmchess.xiangqi', 'chess': 'llmchess.chess_'}
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
SIDE_KEYS = {'effort': str, 'memory': str, 'view': str, 'history': int, 'legal': str, 'selfcheck': str,
             'recite': str, 'notes_keep': int, 'session_view': str}


def game_module(name):
    return importlib.import_module(GAMES[name])


def side_cfg(a, G, overrides, max_plies):
    sc = {k: getattr(a, k) for k in SIDE_KEYS}
    sc['view'] = sc['view'] or G.DEFAULT_VIEW
    for item in overrides or []:
        k, sep, v = item.partition('=')
        if not sep or k not in SIDE_KEYS:
            raise SystemExit('一方单设写成 变量=值，变量是 %s 之一：%r' % ('/'.join(SIDE_KEYS), item))
        sc[k] = SIDE_KEYS[k](v)
    sc['view'] = sc['view'].split(',') if isinstance(sc['view'], str) else sc['view']
    for v in sc['view']:
        if v not in G.VIEWS:
            raise SystemExit('不认识的 view：%s（可选 %s）' % (v, ','.join(G.VIEWS)))
    checks = {'effort': EFFORTS, 'memory': memory.MODES, 'legal': ('none', 'list'), 'selfcheck': ('on', 'off'),
              'recite': ('on', 'off'), 'session_view': ('full', 'move')}
    for k, allowed in checks.items():
        if sc[k] not in allowed:
            raise SystemExit('%s 只能是 %s，收到 %r' % (k, '/'.join(allowed), sc[k]))
    if sc['recite'] == 'on' and not G.RECITE:
        raise SystemExit('这种棋还没有复述打分，recite 只能 off')
    sc['max_plies'] = max_plies
    return sc


def check_player(G, spec):
    kind = runner.player_kind(spec)
    if kind == 'claude' and ':' in spec and spec.split(':', 1)[1]:
        return
    if kind == 'random' and spec == 'random':
        return
    if kind == 'engine' and ':' in spec:
        try:
            G.engine_spec(spec.split(':', 1)[1])    # 参数不对在这里报错
        except ValueError as e:
            raise SystemExit(str(e))
        return
    raise SystemExit('棋手写成 claude:<模型> / engine:<引擎>[:参数] / random，收到 %r' % spec)


def commit():
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True)
        dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'llmchess'],
                               capture_output=True, text=True).stdout.strip()
        return out.stdout.strip() + ('-dirty' if dirty else '')
    except Exception as e:                       # 只是记进 config
        return '? (%s)' % e


def build_cfg(a):
    G = game_module(a.game)
    players = {'w': a.red or a.white or 'claude:opus', 'b': a.black or 'claude:opus'}
    for s in 'wb':
        check_player(G, players[s])
    sides = {'w': side_cfg(a, G, a.w, a.max_plies), 'b': side_cfg(a, G, a.b, a.max_plies)}
    cfg = {'game': a.game, 'tag': a.tag, 'players': players, 'sides': sides, 'retries': a.retries,
           'max_plies': a.max_plies, 'seed': a.seed if a.seed is not None else random.randrange(10 ** 9),
           'forfeit': runner.FORFEIT_NOTE, 'timeout': a.timeout}
    cfg['system'] = {s: G.system_prompt(s, sides[s], memory.system_text(sides[s])) for s in 'wb'}
    cfg['commands'] = {s: claude_cli.shown(claude_cli.command(players[s].split(':', 1)[1], sides[s]['effort'], '-'))
                       for s in 'wb' if runner.player_kind(players[s]) == 'claude'}
    cfg['engines'] = {s: G.engine_spec(players[s].split(':', 1)[1])
                      for s in 'wb' if runner.player_kind(players[s]) == 'engine'}
    return G, cfg


def play_stoppable(ctx, a):
    """下一盘：按 --on-limit 设撞额度的行为，装停止信号处理（等额度时 Ctrl-C / SIGTERM 能马上停下写 pause）。"""
    claude_cli.LIMIT_MODE = a.on_limit
    restore = claude_cli.install_stop_handlers()
    try:
        return 0 if runner.play(ctx, a.stop_after) else 3
    finally:
        restore()


def add_opening(a, G, cfg):
    """--opening random:N：生成开局写进 config（生成一次，续跑不重抽）。"""
    try:
        n = opening.parse_mode(a.opening)
    except ValueError as e:
        raise SystemExit(str(e))
    if not n:
        return
    if n >= a.max_plies:
        raise SystemExit('开局半回合数 %d 要小于 --max-plies %d' % (n, a.max_plies))
    seed = a.opening_seed if a.opening_seed is not None else random.randrange(10 ** 9)
    cfg['opening'] = opening.generate(G, a.game, n, seed)


def dry_run_position(G, cfg, tmp):
    """--dry-run：走完随机开局；轮到的若不是模型、另一方是模型，就让这一方（引擎 / 随机）真走一步，
    好打印模型方真正的第一步提示。记录写在临时目录里，用完就删。返回 (要打印提示的那一方, ctx)。"""
    ctx = runner.new_ctx(G, cfg, tmp)
    st = ctx['st']
    for mv in opening.moves_of(cfg):
        G.push(st, mv)
    side = G.turn(st)
    kind = runner.player_kind(cfg['players'][side])
    if kind != 'claude' and runner.player_kind(cfg['players'][runner.other(side)]) == 'claude' and G.ending(st) is None:
        if kind == 'engine':
            ctx['engines'][side] = runner.Engine(G.engine_spec(cfg['players'][side].split(':', 1)[1])).start()
        try:
            moves = G.legal(st)
            mv = runner.TURNS[kind](ctx, side, moves, G.banned(st, moves))[0]
        finally:
            for eng in ctx['engines'].values():
                eng.close()
        G.push(st, mv)
        side = runner.other(side)
    return side, ctx


def cmd_play(a):
    G, cfg = build_cfg(a)
    add_opening(a, G, cfg)
    if a.dry_run:
        for s in 'wb':
            print('== 系统提示（%s，%s）==\n%s\n' % (G.SIDES[s], cfg['players'][s], cfg['system'][s]))
        with tempfile.TemporaryDirectory() as tmp:
            side, ctx = dry_run_position(G, cfg, tmp)
        sc = cfg['sides'][side]
        what = '随机开局 %d 个半回合之后' % len(cfg['opening']['moves']) if cfg.get('opening') else '开局'
        print('== %s，%s第一步的用户提示（%s）==\n%s' % (what, G.SIDES[side], cfg['players'][side],
                                               G.render(ctx['st'], sc) + '\n\n' + memory.ask(sc)))
        return 0
    if not a.tag:
        raise SystemExit('要 --tag')
    run_dir = (pathlib.Path(a.out) if a.out else RUNS) / a.tag
    if (run_dir / 'game.jsonl').exists():
        raise SystemExit('%s 已有记录，换个 --tag 或用 resume' % run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg['claude_version'] = claude_cli.version()
    cfg['commit'] = commit()
    cfg['argv'] = sys.argv
    cfg['claude_cwd'] = os.path.join(os.path.realpath(tempfile.gettempdir()), 'llmchess-cwd',
                                     '%s-%s' % (a.tag, uuid.uuid4().hex[:8]))
    ctx = runner.new_ctx(G, cfg, str(run_dir))
    runner.log(ctx, {'type': 'config', 'cfg': cfg})
    return play_stoppable(ctx, a)


def cmd_resume(a):
    run_dir = pathlib.Path(a.dir)
    cfg = records.read(run_dir / 'game.jsonl')[0]['cfg']
    G = game_module(cfg['game'])
    ctx = runner.load(G, str(run_dir))
    if ctx['end']:
        raise SystemExit('这盘已经结束：%s' % json.dumps(ctx['end'], ensure_ascii=False))
    runner.log(ctx, {'type': 'resume', 'ply': len(ctx['st']['moves']), 'commit': commit()})
    print('接着下 %s：已走 %d 个半回合' % (cfg['tag'], len(ctx['st']['moves'])))
    return play_stoppable(ctx, a)


LIMIT_HELP = ('撞额度时：wait（默认）在程序里等到解除再接着下，每次等待的起止记 limit_wait；'
              'pause 是旧行为，写 pause 后退出码 3')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m llmchess', description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('play', help='开一盘')
    p.add_argument('--game', required=True, choices=sorted(GAMES))
    p.add_argument('--tag', help='这盘的名字，记录放在 runs/<tag>/')
    p.add_argument('--out', help='记录的上级目录，默认仓库里的 runs/')
    p.add_argument('--red', help='中国象棋红方（同 --white）')
    p.add_argument('--white', help='国际象棋白方（同 --red）')
    p.add_argument('--black')
    p.add_argument('--effort', default='medium')
    p.add_argument('--memory', default='stateless')
    p.add_argument('--view', default=None, help='默认：中国象棋 grid,pieces,fen；国际象棋 fen,ascii')
    p.add_argument('--history', type=int, default=-1)
    p.add_argument('--legal', default='none')
    p.add_argument('--selfcheck', default='off')
    p.add_argument('--recite', default='off')
    p.add_argument('--notes-keep', dest='notes_keep', type=int, default=1)
    p.add_argument('--session-view', dest='session_view', default='full')
    p.add_argument('--w', action='append', metavar='变量=值', help='只改先走一方（红 / 白），可重复')
    p.add_argument('--b', action='append', metavar='变量=值', help='只改黑方，可重复')
    p.add_argument('--retries', type=int, default=3)
    p.add_argument('--max-plies', dest='max_plies', type=int, default=200)
    p.add_argument('--seed', type=int, help='随机走子的种子，默认随机取一个并记进 config')
    p.add_argument('--opening', help='random:N：前 N 个半回合由程序替双方走（随机开局），默认不用')
    p.add_argument('--opening-seed', dest='opening_seed', type=int, help='随机开局的种子，默认随机取一个并记进 config')
    p.add_argument('--stop-after', dest='stop_after', type=int, help='本次最多走几个半回合就暂停（测续跑用）')
    p.add_argument('--timeout', type=int, default=claude_cli.TIMEOUT, help='单次 claude -p 调用的超时秒数，默认 3600')
    p.add_argument('--on-limit', dest='on_limit', choices=('wait', 'pause'), default='wait', help=LIMIT_HELP)
    p.add_argument('--dry-run', action='store_true', help='只打印系统提示和第一步提示，不调模型')
    r = sub.add_parser('resume', help='按记录接着下')
    r.add_argument('dir')
    r.add_argument('--stop-after', dest='stop_after', type=int)
    r.add_argument('--on-limit', dest='on_limit', choices=('wait', 'pause'), default='wait', help=LIMIT_HELP)
    a = ap.parse_args(argv)
    return cmd_play(a) if a.cmd == 'play' else cmd_resume(a)
