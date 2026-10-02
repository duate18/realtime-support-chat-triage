from app.limits import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_refuses():
    clock = FakeClock()
    limiter = RateLimiter(max_events=3, window=10, clock=clock)

    assert [limiter.allow() for _ in range(5)] == [True, True, True, False, False]


def test_allows_again_once_the_window_has_passed():
    clock = FakeClock()
    limiter = RateLimiter(max_events=2, window=10, clock=clock)
    assert limiter.allow() and limiter.allow()
    assert not limiter.allow()

    clock.now += 10  # la finestra è scaduta
    assert limiter.allow()


def test_the_window_slides_instead_of_resetting_all_at_once():
    clock = FakeClock()
    limiter = RateLimiter(max_events=2, window=10, clock=clock)
    assert limiter.allow()  # t = 100
    clock.now += 6
    assert limiter.allow()  # t = 106
    clock.now += 5  # t = 111: il primo evento è uscito dalla finestra, il secondo no
    assert limiter.allow()
    assert not limiter.allow()


def test_refused_events_do_not_extend_the_block():
    clock = FakeClock()
    limiter = RateLimiter(max_events=1, window=10, clock=clock)
    assert limiter.allow()
    clock.now += 5
    assert not limiter.allow()  # rifiutato: non deve contare
    clock.now += 5  # sono passati 10 secondi dal solo evento accettato
    assert limiter.allow()
