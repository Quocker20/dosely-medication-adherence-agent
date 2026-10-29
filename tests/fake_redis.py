"""Tiny in-memory Redis stand-in with TTL support for unit tests."""


class FakeRedisPipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list = []

    def set(self, key, value, ex=None, nx=False):
        self._ops.append(("set", key, value, ex, nx))
        return self

    def incr(self, key):
        self._ops.append(("incr", key))
        return self

    def delete(self, *keys):
        self._ops.append(("delete", keys))
        return self

    async def execute(self):
        self._redis.round_trips += 1
        out = []
        for op in self._ops:
            if op[0] == "set":
                out.append(await self._redis.set(op[1], op[2], ex=op[3], nx=op[4]))
            elif op[0] == "incr":
                out.append(await self._redis.incr(op[1]))
            else:
                out.append(await self._redis.delete(*op[1]))
        return out

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRedis:
    def __init__(self) -> None:
        self.now = 0.0
        self.data: dict[str, int | str] = {}
        self.expiry: dict[str, float] = {}
        self.round_trips = 0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def _purge(self, key: str) -> None:
        exp = self.expiry.get(key)
        if exp is not None and exp <= self.now:
            self.data.pop(key, None)
            self.expiry.pop(key, None)

    def pipeline(self, transaction: bool = True) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)

    async def set(self, key, value, ex=None, nx=False):
        self._purge(key)
        if nx and key in self.data:
            return None
        self.data[key] = value
        if ex is not None:
            self.expiry[key] = self.now + ex
        else:
            self.expiry.pop(key, None)
        return True

    async def get(self, key):
        self._purge(key)
        return self.data.get(key)

    async def incr(self, key):
        self._purge(key)
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    async def delete(self, *keys):
        n = 0
        for key in keys:
            self._purge(key)
            if self.data.pop(key, None) is not None:
                n += 1
            self.expiry.pop(key, None)
        return n

    async def ttl(self, key):
        self._purge(key)
        if key not in self.data:
            return -2
        exp = self.expiry.get(key)
        if exp is None:
            return -1
        return int(round(exp - self.now))

    async def expire(self, key, seconds):
        self.expiry[key] = self.now + seconds
        return True
