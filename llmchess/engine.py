"""很薄的 UCI 文本收发，当对手用：每步把起始局面和全部着法发过去（position fen … moves …），等待有上限。

两种棋都走它；棋种模块给出启动命令、setoption 参数、go 命令和坐标换算（engine_spec / to_engine / from_engine）。
构造时不起进程，start() 才起，close() 收掉；也可以 with Engine(spec) as e。
"""
import queue, subprocess, threading, time


class EngineError(RuntimeError):
    pass


class Engine:
    def __init__(self, spec, timeout=60):
        self.spec, self.timeout = spec, timeout
        self.p, self.q, self.reader, self.id = None, None, None, None

    def start(self):
        try:
            return self._start()
        except Exception:
            self.close()                         # 握手失败也要收掉进程和读线程
            raise

    def _start(self):
        self.p = subprocess.Popen(self.spec['cmd'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.q = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self._send('uci')
        head = self._until('uciok')
        self.id = next((l[8:] for l in head if l.startswith('id name ')), '?')
        for k, v in self.spec.get('options', []):
            self._send('setoption name %s value %s' % (k, v))
        self._send('isready')
        self._until('readyok')
        return self

    def _read(self):
        for line in self.p.stdout:
            self.q.put(line.strip())
        self.q.put(None)                     # 进程退出

    def _send(self, s):
        self.p.stdin.write(s + '\n')
        self.p.stdin.flush()

    def _until(self, prefix, timeout=None):
        deadline = time.time() + (timeout or self.timeout)
        lines = []
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise EngineError('引擎 %s 超过 %d 秒没回 %s' % (self.spec['name'], timeout or self.timeout, prefix))
            try:
                line = self.q.get(timeout=left)
            except queue.Empty:
                continue
            if line is None:
                raise EngineError('引擎 %s 进程意外退出' % self.spec['name'])
            lines.append(line)
            if line.startswith(prefix):
                return lines

    def best(self, start_fen, moves, searchmoves=None):
        """走完 moves（引擎写法）之后轮到的一方的着法（引擎写法）。searchmoves 给了就只在其中挑。"""
        self._send('ucinewgame')
        self._send('isready')
        self._until('readyok')
        self._send('position fen %s%s' % (start_fen, (' moves ' + ' '.join(moves)) if moves else ''))
        cmd = self.spec['go']
        if searchmoves:
            cmd += ' searchmoves ' + ' '.join(searchmoves)
        self._send(cmd)
        t = self._until('bestmove')[-1].split()
        if len(t) < 2 or t[1] in ('(none)', '0000'):
            raise EngineError('引擎 %s 没给出着法：%s' % (self.spec['name'], ' '.join(t)))
        return t[1]

    def close(self):
        if self.p is None:
            return
        if self.p.poll() is None:
            try:
                self._send('quit')
                self.p.wait(timeout=5)
            except Exception:
                self.p.kill()
                self.p.wait()
        if self.reader is not None:
            self.reader.join(timeout=5)
        for pipe in (self.p.stdin, self.p.stdout):
            try:
                pipe.close()
            except Exception:                    # 进程已死时关管道可能报 BrokenPipe，收尾不必在意
                pass
        self.p = self.reader = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.close()
