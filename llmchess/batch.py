"""批量驱动（plan-batch2 0.5）：一批盘逐盘跑完、自动分析、出汇总。

    python3 -m llmchess.batch run --game chess --batch b1 --opp maia-1500 --seeds 1-2 --jobs 4
    python3 -m llmchess.batch run --game chess --batch b1 --opp random --seeds 101          # 同一批次追加对手 / 种子
    python3 -m llmchess.batch run --game xiangqi --batch b2cal-30v10 --player engine:fsf:nodes=30 \\
        --opp fsf:nodes=10 --seeds 1-10 --no-analyze --jobs 8                              # 两边都是引擎
    python3 -m llmchess.batch summary runs/b1                                               # 只重出汇总，不跑盘

一批 = runs/<批>/（--out 改上级目录），一盘一个子目录，名字是 <对手>-s<种子>-<w|b>：种子同时是开局种子和随机走子种子，
w / b 是「我方」（--player，默认 claude:opus）执先走的一方（红 / 白）还是黑方。--colors both 时同一开局两色各一盘。
协议 --protocol 同 play（默认 real：连续会话、走 llm-chat，memory 默认 session）；改协议之前开的批次要续跑、追加，
  得带 --protocol legacy（和它当初的 --memory），batch.json 里没有 protocol 就是 legacy。
我方的变量：--effort（默认 xhigh）、--memory（默认 real 下 session、legacy 下 stateless）、--set 变量=值（可重复，只加在我方，变量同 play 的 --w / --b）；
其余照 play 的默认值。随机开局默认国际象棋 random:8、中国象棋 random:6，--opening none 关掉。
对手写法同 play 的棋手，engine: 前缀可省：random、maia-1100 … maia-1900、stockfish:elo=1600、fsf:nodes=100。

批次的我方设置记在 runs/<批>/batch.json，再跑同一批次时必须一致（对手、种子可以追加）。
局面呈现照 play 的默认给法（中国象棋 pieces、国际象棋 all），--set show=all 回到旧提示；改默认之前开的中国象棋批次要续跑、
  追加，得带 --set show=all（batch.json 记的是实际给法，见 batch_meta）。
再跑同一条命令 = 续跑：下完的跳过、可续的 resume、没开的开；拒答、工具事件、结果不确定的盘会锁住。
撞额度：--on-limit（默认 wait，同 play）透传给每盘。wait 时撞了额度的盘在自己的进程里等到解除接着下，驱动照常开新盘
（新盘也跟着等）；pause 时撞额度的盘写 pause 退出码 3，驱动就按下面的「停下」处理。--timeout 也透传给每盘的 play / resume。
停下：任何一盘暂停或终止（含拒答、工具尝试、调用结果不确定），或驱动收到 Ctrl-C / SIGTERM，都走同一条路——
驱动置 claude_cli.STOP（不再开新盘）、在批次目录放 .stop（在跑的盘在下一步之前看到就写 pause 停下），并给每个在跑的盘
发一次 SIGTERM（它的 play 装了 claude_cli 的停止处理：正在等额度 / 等重试的调用马上醒来写 pause；已在跑的 claude -p
答完为止，然后在下一步之前停）。xhigh 一步可能要几分钟。全部停下后退出码 3，先查看暂停原因；被锁住的盘不得自动续跑。
再来一次信号就直接打断在跑的盘（向它的进程组发 SIGINT），同样退出码 3；agy 后端已发出的调用结果待核验，不重新问。
有盘出错（非暂停）退出码 1，其余照跑。
每盘在自己的进程组里跑，终端的 Ctrl-C 只到驱动，由驱动转告。同一批次同时只能有一个驱动（.lock）。
驱动被 kill -9 时在跑的盘不会跟着停（它们在自己的进程组里），要等它们下完或手动停掉，再跑同一条命令。
每盘的输出在 <盘>/play.log。跑完（或停下）都会重写 runs/<批>/summary.md 和 summary.json。

汇总口径：按（批次，对手）分组，只算下完的盘。
  - 战绩与得分率（胜 1、和 0.5），95% 区间用 Wilson（把得分当成功次数、盘数当试验次数）。
  - 大失误率：只算我方、未分胜负步、去掉随机开局的半回合；国际象棋用 lichess 口径（Blunder），中国象棋亏损 ≥250 厘兵
    （analyze 的口径）。分子分母都是全组合计。ACPL 是我方全部非开局步截断亏损的平均（全组合计）。没分析的盘不进这两项。
  - 独立性：同组各盘第 20 个半回合走完后的局面（不到 20 个半回合的盘用整盘着法）两两比较，重合的列出来，另报独立盘数。
"""
import argparse, concurrent.futures, json, math, os, re, signal, subprocess, sys, threading

from . import analyze, claude_cli, cli, opening, records, runner

ROOT = cli.ROOT
DEFAULT_OPENING = {'chess': 'random:8', 'xiangqi': 'random:6'}
CHECK_PLY = 20
STOP = '.stop'
LOCK = '.lock'
NAME = re.compile(r'^(?P<opp>.+)-s(?P<seed>\d+)-(?P<side>[wb])$')


# ---------------------------------------------------------------- 小工具
def parse_seeds(text):
    out = []
    for part in text.split(','):
        part = part.strip()
        m = re.match(r'^(\d+)(?:-(\d+))?$', part)
        if not m:
            raise SystemExit('种子写成 1-5 或 1,3,7 或混用，收到 %r' % text)
        lo, hi = int(m[1]), int(m[2] or m[1])
        out += [s for s in range(lo, hi + 1) if s not in out]
    return out


def full_spec(spec):
    return spec if spec.split(':', 1)[0] in runner.TURNS else 'engine:' + spec


def slug(spec):
    s = spec[len('engine:'):] if spec.startswith('engine:') else spec
    return re.sub(r'[^A-Za-z0-9.]+', '-', s.replace('=', '')).strip('-')


def wilson(k, n, z=1.96):
    """k 次成功（可以带 0.5）/ n 次试验的 Wilson 95% 区间。n=0 返回 (None, None)。"""
    if not n:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def write_atomic(path, text):
    tmp = '%s.tmp' % path
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def other(side):
    return 'b' if side == 'w' else 'w'


# ---------------------------------------------------------------- 批次设置与锁
def batch_meta(a):
    """呈现方式（show）单独记：--set 里的 show=… 不进 set，改记实际生效的给法（不给就是棋种默认给法），而且只在它不是
    all 时才记——all 是改默认之前的给法，改之前开的批次 batch.json 里没有 show 这一项，照旧设置续跑、追加种子都还对得上；
    中国象棋的旧批次不写 --set show=all 就会因为多出 show: pieces 报不一致，不会悄悄把两种给法混进一批。
    给了自定义 view 或我方不是模型时不记。"""
    sets = [kv for kv in a.set or [] if not kv.startswith('show=')]
    kv = dict(x.split('=', 1) for x in a.set or [] if '=' in x)
    show = kv.get('show') or (None if 'view' in kv else cli.game_module(a.game).DEFAULT_SHOW)
    meta = {'game': a.game, 'player': a.player, 'effort': a.effort, 'memory': a.memory, 'set': sorted(sets),
            'opening': a.opening, 'max_plies': a.max_plies, 'retries': a.retries}
    if a.protocol != 'legacy':                   # 旧批次的 batch.json 没有这一项，legacy 照旧对得上
        meta['protocol'] = a.protocol
    if show not in (None, 'all') and a.player.startswith('claude:'):
        meta['show'] = show
    return meta


def check_meta(bdir, meta):
    """第一次写 batch.json；之后必须一致（对手和种子不在里面，可以追加）。只由驱动主线程读写。"""
    path = os.path.join(bdir, 'batch.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            old = json.load(f)
        diff = {k: (old.get(k), v) for k, v in meta.items() if old.get(k) != v}
        if diff:
            raise SystemExit('%s 的设置和这次不一致（旧值, 这次）：%s\n换个 --batch，或者照旧设置跑' % (
                path, json.dumps(diff, ensure_ascii=False)))
        return
    write_atomic(path, json.dumps(meta, ensure_ascii=False, indent=1) + '\n')


def take_lock(bdir):
    """同一批次同时只让一个驱动跑：.lock 里写 pid；占着的进程已经不在就接手。"""
    path = os.path.join(bdir, LOCK)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pid = 0
            try:
                with open(path) as f:
                    pid = int(f.read().strip() or 0)
                alive = pid > 0 and os.kill(pid, 0) is None
            except PermissionError:              # 进程在、只是不归我们管：当作还在跑
                alive = True
            except (ValueError, OSError):
                alive = False
            if not alive:
                os.remove(path)                  # 锁是本驱动自己建的；持有者已经不在，接手
                continue
            raise SystemExit('批次 %s 正由进程 %d 在跑，别同时跑两个驱动' % (bdir, pid))
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        return path
    raise SystemExit('拿不到批次锁 %s' % path)


# ---------------------------------------------------------------- 跑一盘
def game_state(gdir):
    """'new' / 'unfinished' / 'done'。"""
    log = os.path.join(gdir, 'game.jsonl')
    if not os.path.exists(log):
        return 'new'
    recs = records.read(log)
    return 'done' if analyze.end_of(recs)[1] else 'unfinished'


def play_cmd(a, gdir, opp, seed, side):
    players = {side: a.player, other(side): opp}
    cmd = [sys.executable, '-m', 'llmchess', 'play', '--game', a.game, '--tag', os.path.basename(gdir),
           '--out', os.path.dirname(gdir), '--white', players['w'], '--black', players['b'],
           '--protocol', a.protocol, '--effort', a.effort, '--memory', a.memory, '--max-plies', str(a.max_plies), '--retries', str(a.retries),
           '--seed', str(seed), '--stop-file', os.path.join(os.path.dirname(gdir), STOP)]
    for kv in a.set or []:
        cmd += ['--' + side, kv]
    n = opening.parse_mode(a.opening)
    if n:
        cmd += ['--opening', 'random:%d' % n, '--opening-seed', str(seed)]
    return cmd + pass_through(a)


def resume_cmd(a, gdir):
    cmd = [sys.executable, '-m', 'llmchess', 'resume', gdir, '--stop-file', os.path.join(os.path.dirname(gdir), STOP)]
    return cmd + pass_through(a)


def pass_through(a):
    """每盘的 play / resume 都带上：撞额度怎么办（默认 wait）、claude -p 单次超时（给了才传；resume 不给就沿用 config）。"""
    out = ['--on-limit', a.on_limit]
    if a.timeout is not None:
        out += ['--timeout', str(a.timeout)]
    return out


class Driver:
    def __init__(self, a, bdir, jobs):
        self.a, self.bdir, self.jobs = a, bdir, jobs
        self.lock = threading.RLock()            # 信号处理也在主线程里调 say / request_stop，要可重入
        self.result = {}
        self.procs = set()
        self.stopping = False                    # 停止只转告一次；「停没停」本身看 claude_cli.STOP

    def say(self, msg):
        with self.lock:
            print(msg, flush=True)

    def request_stop(self, why):
        """停下的唯一入口（某盘暂停、或第一次信号经 install_stop_handlers 转到这里）：置 STOP 不再开新盘；
        放 .stop，在跑的盘在下一步之前停；再给每个在跑的盘发 SIGTERM，叫醒它里面正在等额度 / 等重试的调用。
        .stop 和 SIGTERM 是同一个停止的两个送达方式：SIGTERM 叫醒等待，.stop 让不调模型的步（引擎、随机、开局）也停在两步之间。
        刚起、还没装好停止处理的盘（建盘、生成开局那几秒）会被这个 SIGTERM 直接杀掉：驱动按暂停算，记录停在两步之间或还没有，
        再跑同一条命令照样续跑或新开（有意接受，不值得为这几秒另搭一套握手）。"""
        with self.lock:                          # 和 run_one 里「查 STOP → 起进程 → 登记」互斥，不会漏掉刚起的盘
            claude_cli.STOP.set()
            if self.stopping:
                return
            self.stopping = True
            open(os.path.join(self.bdir, STOP), 'w').close()
            procs = list(self.procs)
        self.say('！%s：不再开新盘，在跑的盘走完当前这步就停（在等额度的马上停）' % why)
        for p in procs:
            try:
                p.send_signal(signal.SIGTERM)   # 只发给这盘的 play 进程本身，不连带它正在跑的 claude -p
            except OSError:
                pass

    def interrupt(self):
        """第二次信号：直接打断在跑的盘（向整个进程组发 SIGINT，连带 claude -p 和引擎）。"""
        self.say('！再次收到信号：打断在跑的盘')
        with self.lock:
            procs = list(self.procs)
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGINT)
            except OSError:
                pass

    def run_one(self, name, opp, seed, side):
        a, gdir = self.a, os.path.join(self.bdir, name)
        state = game_state(gdir)
        if state == 'done':
            self.result[name] = 'done'
            return self.after(name, gdir, fresh=False)
        if claude_cli.STOP.is_set():
            self.result[name] = 'not started'
            return
        cmd = resume_cmd(a, gdir) if state == 'unfinished' else play_cmd(a, gdir, opp, seed, side)
        if a.stop_after is not None:
            cmd += ['--stop-after', str(a.stop_after)]
        os.makedirs(gdir, exist_ok=True)
        with open(os.path.join(gdir, 'play.log'), 'a', encoding='utf-8') as out:
            with self.lock:
                if claude_cli.STOP.is_set():         # 上面查过之后才停的：目录已建，但没有 game.jsonl，汇总不算它
                    self.result[name] = 'not started'
                    return
                self.say('开始 %s（%s）' % (name, '续跑' if state == 'unfinished' else '新开'))
                # 自己的进程组：终端 Ctrl-C 不直接打到这盘，由驱动决定是等它停在两步之间还是打断
                p = self.spawn(cmd, out)
                self.procs.add(p)
            try:
                rc = p.wait()
            finally:
                with self.lock:
                    self.procs.discard(p)
        if rc not in (0, 3) and claude_cli.STOP.is_set():
            # 停下时被信号打断（第二次信号，或 SIGTERM 赶在这盘装好停止处理之前到）：下完了就算下完，否则按暂停
            rc = 0 if game_state(gdir) == 'done' else 3
        if rc == 3:
            self.result[name] = 'paused'
            self.request_stop('%s 暂停了' % name)
            self.say('停下 %s（见 %s）' % (name, os.path.join(gdir, 'play.log')))
            return
        if rc != 0:
            self.result[name] = 'error'
            self.say('！%s 出错退出（退出码 %d，见 %s）' % (name, rc, os.path.join(gdir, 'play.log')))
            return
        self.result[name] = 'done'
        self.after(name, gdir, fresh=True)

    def spawn(self, cmd, out):
        return subprocess.Popen(cmd, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)

    def after(self, name, gdir, fresh):
        if fresh:
            end = analyze.end_of(records.read(os.path.join(gdir, 'game.jsonl')))[0]
            self.say('下完 %s：%s' % (name, end_text(end, NAME.match(name)['side'])))
        if self.a.no_analyze:
            return
        try:
            analyze.analyse_run(gdir, log=lambda *x: None)
        except Exception as e:                   # 分析失败不耽误别的盘，汇总里这盘就没有失误数
            self.result[name] = 'analyze-error'
            self.say('！%s 分析失败：%s' % (name, e))

    def run(self, games):
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.jobs) as ex:
            futs = {ex.submit(self.run_one, *g): g[0] for g in games}
            for f in concurrent.futures.as_completed(futs):
                try:
                    f.result()
                except Exception as e:           # 驱动自己的错，也别让它悄悄吞掉
                    self.result[futs[f]] = 'error'
                    self.say('！%s 驱动出错：%r' % (futs[f], e))
        return self.result


def end_text(end, side):
    if not end:
        return '未完'
    return '我方%s（%s）' % ('和' if end['winner'] is None else '胜' if end['winner'] == side else '负', end['reason'])


def cmd_run(a):
    G = cli.game_module(a.game)
    a.player = full_spec(a.player)
    cli.check_player(G, a.player, a.protocol)
    if a.memory is None:
        a.memory = 'session' if a.protocol == 'real' else 'stateless'
    if a.retries is None:
        a.retries = cli.default_retries(a.protocol)
    opps = [full_spec(o) for o in a.opp]
    for o in opps:
        cli.check_player(G, o, a.protocol)
    if a.opening is None:
        a.opening = DEFAULT_OPENING[a.game]
    if a.opening == 'none':
        a.opening = ''
    try:
        opening.parse_mode(a.opening)
    except ValueError as e:
        raise SystemExit(str(e))
    for kv in a.set or []:
        k, sep, _ = kv.partition('=')
        if not sep or k not in cli.SIDE_KEYS:
            raise SystemExit('--set 写成 变量=值，变量是 %s 之一：%r' % ('/'.join(cli.SIDE_KEYS), kv))
    seeds = parse_seeds(a.seeds)
    colors = {'both': 'wb', 'w': 'w', 'b': 'b'}[a.colors]
    bdir = os.path.join(a.out or str(cli.RUNS), a.batch)
    os.makedirs(bdir, exist_ok=True)
    lock = take_lock(bdir)
    try:
        check_meta(bdir, batch_meta(a))
        stop = os.path.join(bdir, STOP)
        if os.path.exists(stop):
            os.remove(stop)                      # 上次暂停留下的停止标记（本驱动自己建的）
        games = [('%s-s%d-%s' % (slug(o), s, c), o, s, c) for o in opps for s in seeds for c in colors]
        names = [g[0] for g in games]
        if len(set(names)) != len(names):
            raise SystemExit('有两个对手的目录名撞了：%s' % names)
        print('批次 %s：%d 盘，%d 路并发' % (bdir, len(games), a.jobs), flush=True)
        drv = Driver(a, bdir, a.jobs)
        # 和 play 同一套停止处理：第一次信号置 STOP 并由 request_stop 转告各盘；第二次打断在跑的盘（不强退驱动自己）
        restore = claude_cli.install_stop_handlers(
            on_stop=lambda: drv.request_stop('收到停止信号（再来一次就直接打断在跑的盘）'), on_force=drv.interrupt)
        try:
            res = drv.run(games)
        finally:
            restore()
        if os.path.exists(stop):
            os.remove(stop)
    finally:
        os.remove(lock)
    rows = summarize([bdir])
    md = markdown(rows)
    write_atomic(os.path.join(bdir, 'summary.md'), md)
    write_atomic(os.path.join(bdir, 'summary.json'), json.dumps(rows, ensure_ascii=False, indent=1) + '\n')
    print(md)
    counts = {k: sum(v == k for v in res.values()) for k in sorted(set(res.values()))}
    print('本次：%s；汇总已写 %s' % (json.dumps(counts, ensure_ascii=False), os.path.join(bdir, 'summary.md')))
    if any(v in ('paused', 'not started') for v in res.values()):
        print('有盘暂停，请先查看各盘原因；拒答、工具尝试或调用结果不确定的盘禁止自动续跑')
        return 3
    return 1 if any(v in ('error', 'analyze-error') for v in res.values()) else 0


# ---------------------------------------------------------------- 汇总
def position_key(G, moves):
    """第 CHECK_PLY 个半回合走完后的局面（FEN 去掉步数计数）；不够长的盘用整盘着法。"""
    if len(moves) < CHECK_PLY:
        return 'short:' + ' '.join(moves)
    st = G.start()
    for mv in moves[:CHECK_PLY]:
        G.push(st, mv)
    return ' '.join(st['fens'][CHECK_PLY].split()[:4])


def read_analysis(gdir):
    path = os.path.join(gdir, 'analysis.jsonl')
    sp = os.path.join(gdir, 'analysis-summary.json')
    if not (os.path.exists(path) and os.path.exists(sp)):
        return None
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def game_row(bdir, name):
    gdir = os.path.join(bdir, name)
    m = NAME.match(name)
    if not m or not os.path.exists(os.path.join(gdir, 'game.jsonl')):
        return None
    recs = records.read(os.path.join(gdir, 'game.jsonl'))
    cfg = recs[0]['cfg']
    side = m['side']
    moves = [r['move'] for r in sorted((r for r in recs if r['type'] == 'move'), key=lambda r: r['ply'])]
    end, done = analyze.end_of(recs)
    row = {'batch': os.path.basename(os.path.normpath(bdir)), 'game': cfg['game'], 'run': name,
           'player': cfg['players'][side], 'opponent': cfg['players'][other(side)], 'seed': int(m['seed']),
           'side': side, 'opening': len(opening.moves_of(cfg)), 'plies': len(moves), 'finished': done,
           'effort': cfg['sides'][side].get('effort'), 'memory': cfg['sides'][side].get('memory'),
           'score': None, 'result': '未完', 'reason': next((r['why'] for r in reversed(recs) if r['type'] == 'pause'),
                                                           '没有 end'),
           'key': position_key(cli.game_module(cfg['game']), moves)}
    if done:
        row['score'] = 0.5 if end['winner'] is None else 1.0 if end['winner'] == side else 0.0
        row['result'] = {1.0: '胜', 0.5: '和', 0.0: '负'}[row['score']]
        row['reason'] = end['reason']
    rows = read_analysis(gdir)
    if rows is not None and len(rows) == len(moves):
        mine = [r for r in rows if r['side'] == side and not r.get('opening')]
        und = [r for r in mine if not r['decided']]
        if cfg['game'] == 'chess':
            big = sum(r.get('lichess') == 'Blunder' for r in und)
        else:
            big = sum(r['cls'] == 'blunder' for r in und)
        row.update({'analysed': True, 'moves_mine': len(mine), 'undecided': len(und), 'blunders': big,
                    'loss_sum': sum(max(0, r['loss']) for r in mine)})
    else:
        row['analysed'] = False
    return row


def summarize(bdirs):
    """每盘一行（games）加每组一行（groups），组 = （批次，对手）。"""
    games = []
    for b in bdirs:
        for name in sorted(os.listdir(b)):
            r = game_row(b, name)
            if r:
                games.append(r)
    groups = {}
    for r in games:
        groups.setdefault((r['batch'], r['opponent']), []).append(r)
    out = []
    for (batch, opp), rs in groups.items():
        fin = [r for r in rs if r['finished']]
        n = len(fin)
        pts = sum(r['score'] for r in fin)
        lo, hi = wilson(pts, n)
        an = [r for r in fin if r['analysed']]
        und = sum(r['undecided'] for r in an)
        mine = sum(r['moves_mine'] for r in an)
        keys = {}
        for r in fin:
            keys.setdefault(r['key'], []).append(r['run'])
        g = {'batch': batch, 'game': rs[0]['game'], 'player': rs[0]['player'], 'effort': rs[0]['effort'],
             'memory': rs[0]['memory'], 'opponent': opp, 'games': len(rs), 'finished': n,
             'win': sum(r['score'] == 1 for r in fin), 'draw': sum(r['score'] == 0.5 for r in fin),
             'loss': sum(r['score'] == 0 for r in fin), 'points': pts,
             'score_rate': round(pts / n, 4) if n else None,
             'ci95': [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
             'analysed': len(an), 'blunders': sum(r['blunders'] for r in an), 'undecided': und,
             'blunder_rate': round(sum(r['blunders'] for r in an) / und, 4) if und else None,
             'acpl': round(sum(r['loss_sum'] for r in an) / mine, 1) if mine else None,
             'independent': len(keys), 'overlaps': [v for v in keys.values() if len(v) > 1]}
        out.append(g)
    return {'groups': out, 'games': games}


def _pct(x):
    return '–' if x is None else '%.0f%%' % (100 * x)


def markdown(res):
    lines = ['## 按对手汇总', '',
             '| 批次 | 我方 | 对手 | 下完/共 | 胜-和-负 | 得分率 | 95%% 区间 | 大失误（率，分母） | ACPL | 独立盘数 | 第 %d 个半回合局面重合 |'
             % CHECK_PLY, '|' + '---|' * 11]
    for g in res['groups']:
        me = g['player'] + (' %s %s' % (g['effort'], g['memory'])
                            if g['player'].split(':', 1)[0] in runner.MODEL_KINDS else '')
        lines.append('| %s | %s | %s | %d/%d | %d-%d-%d | %s | %s | %s | %s | %d | %s |' % (
            g['batch'], me, g['opponent'], g['finished'], g['games'], g['win'], g['draw'], g['loss'],
            _pct(g['score_rate']), '–' if g['ci95'][0] is None else '%s–%s' % (_pct(g['ci95'][0]), _pct(g['ci95'][1])),
            '–' if not g['analysed'] else '%d（%s，%d）' % (g['blunders'], _pct(g['blunder_rate']), g['undecided']),
            '–' if g['acpl'] is None else g['acpl'], g['independent'],
            '；'.join('、'.join(v) for v in g['overlaps']) or '无'))
    lines += ['', '## 每盘', '',
              '| 批次 | 盘 | 我方执 | 结果 | 终局原因 | 半回合（开局） | 大失误 / 未分胜负步 | ACPL |', '|' + '---|' * 8]
    for r in res['games']:
        lines.append('| %s | %s | %s | %s | %s | %d（%d） | %s | %s |' % (
            r['batch'], r['run'], r['side'], r['result'], str(r['reason']).replace('|', '/'), r['plies'], r['opening'],
            '%d / %d' % (r['blunders'], r['undecided']) if r['analysed'] else '–',
            '%.1f' % (r['loss_sum'] / r['moves_mine']) if r['analysed'] and r['moves_mine'] else '–'))
    lines += ['', '口径：只算下完的盘；得分胜 1 和 0.5，区间是 Wilson 95%%；大失误只算我方未分胜负、非随机开局的步'
              '（国际象棋 lichess Blunder，中国象棋亏损 ≥250 厘兵）；ACPL 是我方全部非开局步的截断亏损平均；'
              '独立性比的是第 %d 个半回合走完后的局面（不到 %d 个半回合的盘比整盘着法），重合的只能按一盘算。' % (CHECK_PLY, CHECK_PLY)]
    return '\n'.join(lines) + '\n'


def cmd_summary(a):
    for d in a.dirs:
        if not os.path.isdir(d):
            raise SystemExit('没有这个批次目录：%s' % d)
    if a.analyze:
        for d in a.dirs:
            for name in sorted(os.listdir(d)):
                if NAME.match(name) and game_state(os.path.join(d, name)) == 'done':
                    analyze.analyse_run(os.path.join(d, name), log=lambda *x: None)
    res = summarize(a.dirs)
    md = markdown(res)
    out = a.out or (os.path.join(a.dirs[0], 'summary') if len(a.dirs) == 1 else None)
    if out is None:
        raise SystemExit('多个批次一起汇总时要给 --out（写成 <路径前缀>，会写 .md 和 .json）')
    write_atomic(out + '.md', md)
    write_atomic(out + '.json', json.dumps(res, ensure_ascii=False, indent=1) + '\n')
    print(md)
    print('已写 %s.md、%s.json' % (out, out))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m llmchess.batch', description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('run', help='跑一批（再跑同一条命令就是续跑）')
    p.add_argument('--game', required=True, choices=sorted(cli.GAMES))
    p.add_argument('--batch', required=True, help='批次名，记录放在 runs/<批次>/')
    p.add_argument('--out', help='批次的上级目录，默认仓库里的 runs/')
    p.add_argument('--player', default='claude:opus', help='我方棋手，默认 claude:opus；写引擎就是引擎对引擎')
    p.add_argument('--opp', action='append', required=True, help='对手，可重复；engine: 前缀可省')
    p.add_argument('--seeds', required=True, help='开局种子，如 1-5、1,3,7')
    p.add_argument('--colors', default='both', choices=('both', 'w', 'b'), help='我方执哪方，both = 同一开局两色各一盘')
    p.add_argument('--opening', help='random:N 或 none；默认国际象棋 random:8、中国象棋 random:6')
    p.add_argument('--effort', default='xhigh')
    p.add_argument('--protocol', choices=('real', 'legacy'), default='real', help='同 play 的 --protocol')
    p.add_argument('--memory', default=None, help='默认 real 下 session、legacy 下 stateless')
    p.add_argument('--set', action='append', metavar='变量=值', help='只加在我方的变量（同 play 的 --w / --b），可重复')
    p.add_argument('--max-plies', dest='max_plies', type=int, default=200)
    p.add_argument('--retries', type=int, default=None, help='同 play 的 --retries，默认 real 2、legacy 3')
    p.add_argument('--jobs', type=int, default=4, help='并发盘数')
    p.add_argument('--timeout', type=int, help='透传给每盘 play / resume 的 --timeout（claude -p 单次调用的秒数）；'
                   '不给时新盘用 play 的默认 3600，续跑沿用该盘 config')
    p.add_argument('--on-limit', dest='on_limit', choices=('wait', 'pause'), default='wait',
                   help='透传给每盘：撞额度时 wait（默认）在该盘进程里等到解除接着下；pause 写 pause 退出码 3，驱动随即停下')
    p.add_argument('--no-analyze', dest='no_analyze', action='store_true', help='下完不做引擎分析（引擎标定用）')
    p.add_argument('--stop-after', dest='stop_after', type=int, help='每盘本次最多走几个半回合就暂停（测续跑用）')
    s = sub.add_parser('summary', help='只重出汇总，不跑盘')
    s.add_argument('dirs', nargs='+', help='批次目录 runs/<批次>')
    s.add_argument('--out', help='另存成 <out>.md / <out>.json；只给一个批次时默认写在批次目录里')
    s.add_argument('--analyze', action='store_true', help='先给下完、还没分析的盘补分析')
    a = ap.parse_args(argv)
    return cmd_run(a) if a.cmd == 'run' else cmd_summary(a)


if __name__ == '__main__':
    sys.exit(main())
