"""
Panic Engine - Master Controller for Stockfish with Dynamic Check-Based Degradation
Shared singleton engine supporting multiple concurrent game sessions with minimal memory footprint.
"""

import math
import random
import logging
import threading
from typing import Optional, Tuple
import chess
import chess.engine

logger = logging.getLogger(__name__)


class GameSession:
    """Tracks state and check-based rating degradation for an individual match."""

    def __init__(
        self,
        is_bot_white: bool = True,
        starting_elo: int = 3600,
        elo_drop_per_check: int = 300,
        min_elo: int = 0
    ):
        self.is_bot_white = is_bot_white
        self.starting_elo = starting_elo
        self.elo_drop_per_check = elo_drop_per_check
        self.min_elo = min_elo
        self.checks_against_bot = 0
        self.used_quotes: set[str] = set()
        self.triggered_easter_eggs: set[str] = set()

    def reset(self, is_bot_white: bool):
        self.is_bot_white = is_bot_white
        self.checks_against_bot = 0
        self.used_quotes.clear()
        self.triggered_easter_eggs.clear()

    def get_current_elo(self) -> int:
        calculated = self.starting_elo - (self.checks_against_bot * self.elo_drop_per_check)
        return max(self.min_elo, calculated)

    def analyze_moves_and_count_checks(self, uci_moves: list[str]) -> Tuple[bool, int, int]:
        """
        Replays the game moves and counts how many checks were delivered
        specifically against the bot's king.
        """
        board = chess.Board()
        bot_color = chess.WHITE if self.is_bot_white else chess.BLACK
        checks_count = 0

        for move_uci in uci_moves:
            try:
                move = chess.Move.from_uci(move_uci)
                if move in board.legal_moves:
                    board.push(move)
                    if board.turn == bot_color and board.is_check():
                        checks_count += 1
            except ValueError:
                logger.error(f"Invalid UCI move encountered: {move_uci}")

        new_check = (checks_count > self.checks_against_bot)
        self.checks_against_bot = checks_count
        current_elo = self.get_current_elo()

        return new_check, self.checks_against_bot, current_elo


class PanicEngine:
    """
    Shared Master Chess Engine instance.
    Handles move evaluation for multiple concurrent games through thread-safe locking.
    Implements 13-tier nerfing architecture across:
    - God-Mode (3600 Elo)
    - Unified Softmax Temperature & Depth Scaling over MultiPV (3300 down to 600 Elo)
    - Passive Error Choice (300 Elo)
    - Engine Bypass / Potato Mode (0 Elo)
    """

    def __init__(self, stockfish_path: str):
        self.stockfish_path = stockfish_path
        self.engine: Optional[chess.engine.SimpleEngine] = None
        self.engine_lock = threading.Lock()

    def start(self):
        """Initializes the persistent master Stockfish process."""
        with self.engine_lock:
            if self.engine is None:
                logger.info(f"Spawning Master Stockfish instance from: {self.stockfish_path}")
                self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path, timeout=30.0)
                try:
                    self.engine.configure({
                        "Threads": 1,
                        "Hash": 8,
                        "UCI_LimitStrength": False,
                        "Skill Level": 20
                    })
                except Exception as e:
                    logger.warning(f"Could not configure engine options: {e}")

    def close(self):
        """Terminates the master engine process cleanly."""
        with self.engine_lock:
            if self.engine is not None:
                try:
                    self.engine.close()
                except Exception as e:
                    logger.warning(f"Error while closing engine: {e}")
                finally:
                    self.engine = None

    def _softmax_sample(self, analysis: list[dict], temp: float) -> Optional[chess.Move]:
        """
        Samples a move from MultiPV analysis using a Boltzmann Softmax probability distribution.
        P(move_i) = exp(score_i / (100 * temp)) / sum(exp(score_j / (100 * temp)))
        """
        candidates = []
        cps = []
        for entry in analysis:
            pv = entry.get("pv")
            score = entry.get("score")
            if not pv or score is None:
                continue
            rel_score = score.relative.score(mate_score=10000)
            if rel_score is not None:
                candidates.append(pv[0])
                cps.append(rel_score)

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        max_cp = max(cps)
        # Scaled by 100 centipawns (1.0 pawn) * temperature
        weights = [math.exp(max(-20.0, min(20.0, (cp - max_cp) / (100.0 * temp)))) for cp in cps]
        total_w = sum(weights)
        if total_w <= 0:
            return candidates[0]
        probs = [w / total_w for w in weights]
        return random.choices(candidates, weights=probs, k=1)[0]

    def choose_move(self, board: chess.Board, current_elo: int, time_limit: float = 1.5) -> Optional[chess.Move]:
        """
        Calculates the next move based on the 13-tier nerfing architecture.
        Thread-safe across multiple concurrent game sessions.
        """
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None

        # Tier 6: 0 Elo - Potato Mode (pure random legal moves / 0 engine calculation)
        if current_elo <= 0:
            logger.info("POTATO MODE (0 Elo): Selecting random legal move.")
            return random.choice(legal_moves)

        with self.engine_lock:
            if not self.engine:
                self.start()

            # Tier 5: 300 Elo - Passive Error Choice (Worst 3 candidates at Depth 1)
            if current_elo <= 300:
                try:
                    analysis = self.engine.analyse(
                        board,
                        chess.engine.Limit(depth=1),
                        multipv=min(5, len(legal_moves))
                    )
                    worst_3 = [entry["pv"][0] for entry in analysis[-3:] if entry.get("pv")]
                    if worst_3:
                        chosen = random.choice(worst_3)
                        logger.info(f"Passive Error Choice (300 Elo): Selected from worst candidates -> {chosen.uci()}")
                        return chosen
                except Exception as e:
                    logger.warning(f"300 Elo passive error fallback: {e}")
                return random.choice(legal_moves)

            # Tier 2: 3300 - 600 Elo - Unified Softmax Temperature & Depth Scaling over MultiPV
            if current_elo <= 3300:
                softmax_cfg = {
                    # Top Lichess GM Tiers (Ultra-low temperature: world-class GM intuition)
                    3300: (2, 14, 0.14),
                    3000: (3, 12, 0.20),
                    2700: (3, 10, 0.25),

                    # Lichess Master / Expert Tiers (2400-2100 Lichess Blitz)
                    2400: (4,  8, 0.45),
                    2100: (4,  6, 0.85),

                    # Lichess Club / Casual Tiers (1800-1500 Lichess Blitz)
                    1800: (4,  5, 1.40),
                    1500: (5,  4, 2.10),

                    # Lichess Beginner / Novice Tiers (1200-600 Lichess Blitz)
                    1200: (5,  3, 2.90),
                    900:  (6,  2, 3.90),
                    600:  (6,  1, 4.80),
                }
                mpv, d, temp = softmax_cfg.get(current_elo, (5, 4, 2.10))
                try:
                    analysis = self.engine.analyse(
                        board,
                        chess.engine.Limit(depth=d, time=0.25),
                        multipv=min(mpv, len(legal_moves))
                    )
                    chosen = self._softmax_sample(analysis, temp)
                    if chosen:
                        logger.info(f"Softmax Sampling ({current_elo} Elo, T={temp}, D={d}, MPV={mpv}): Played {chosen.uci()}")
                        return chosen
                except Exception as e:
                    logger.warning(f"Softmax analysis error: {e}")
                return random.choice(legal_moves)

            # Tier 1: 3600 Elo - God-Mode (Uncapped Depth)
            actual_time = max(0.1, min(time_limit, 1.0))
            try:
                res = self.engine.play(board, chess.engine.Limit(time=actual_time))
                logger.info(f"God-Mode (3600 Elo): Played {res.move.uci()} (Time: {actual_time}s)")
                return res.move
            except Exception as e:
                logger.error(f"God-mode error: {e}")
                return random.choice(legal_moves)

