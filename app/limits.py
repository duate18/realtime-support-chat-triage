"""Limite di frequenza: quanti messaggi accetta una singola connessione in una finestra di tempo."""
import time
from collections import deque


class RateLimiter:
    """Finestra scorrevole: al massimo `max_events` eventi negli ultimi `window` secondi."""

    def __init__(self, max_events: int, window: float, clock=time.monotonic) -> None:
        self.max_events = max_events
        self.window = window
        self.clock = clock  # iniettabile, così nei test controlliamo il tempo
        self.events: deque[float] = deque()  # istanti degli eventi accettati, dal più vecchio

    def allow(self) -> bool:
        """Registra un evento e restituisce True se è consentito, False se si supera il limite."""
        now = self.clock()
        while self.events and now - self.events[0] >= self.window:
            self.events.popleft()  # eventi ormai fuori dalla finestra
        if len(self.events) >= self.max_events:
            return False
        self.events.append(now)
        return True
