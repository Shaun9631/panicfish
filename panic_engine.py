"""
Panic Engine - Controller for Stockfish with Dynamic Check-Based Degradation
Starting at 3600 Elo, losing 300 Elo per check, degrading into potato mode at 0 Elo.
"""

import random
import logging
from typing import Optional, Tuple
import chess
import chess.engine

logger = logging.getLogger(__name__)


class PanicEngine:
    """
    Manages the chess engine instance and recalculates dynamic Elo
    based on check count against the bot's king.
    """

    def __init__(
        self,
        stockfish_path: str,
        starting_elo: int = 3600,
        elo_drop_per_check: int = 300,
        min_elo: int = 0
    ):
        self.stockfish_path = stockfish_path
        self.starting_elo = starting_elo
        self.elo_drop_per_check = elo_drop_per_check
        self.min_elo = min_elo
        self.engine: Optional[chess.engine.SimpleEngine] = None
        self.checks_against_bot = 0
        self.is_bot_white = True
        self._last_move_count = 0

    def start(self):
        """Initializes the Stockfish engine process with safety timeout."""
        if self.engine is None:
            logger.info(f"Spawning Stockfish instance from: {self.stockfish_path}")
            self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path, timeout=30.0)
            self.configure_for_elo(self.starting_elo)

    def close(self):
        """Terminates the Stockfish process cleanly and frees memory."""
        if self.engine is not None:
            try:
                self.engine.close()
            except Exception as e:
                logger.warning(f"Error while closing engine: {e}")
            finally:
                self.engine = None

    def reset_game(self, is_bot_white: bool):
        """Resets the state for a new game."""
        self.is_bot_white = is_bot_white
        self.checks_against_bot = 0
        self._last_move_count = 0
        if self.engine:
            self.configure_for_elo(self.starting_elo)

    def get_current_elo(self) -> int:
        """Calculates current Elo rating based on check count."""
        calculated = self.starting_elo - (self.checks_against_bot * self.elo_drop_per_check)
        return max(self.min_elo, calculated)

    def analyze_moves_and_count_checks(self, uci_moves: list[str]) -> Tuple[bool, int, int]:
        """
        Replays the game moves and counts how many checks were delivered
        specifically against the bot's king.

        Returns:
            (new_check_occurred: bool, total_checks: int, current_elo: int)
        """
        board = chess.Board()
        bot_color = chess.WHITE if self.is_bot_white else chess.BLACK
        checks_count = 0

        # Replay move by move to accurately count checks against bot
        for i, move_uci in enumerate(uci_moves):
            try:
                move = chess.Move.from_uci(move_uci)
                if move in board.legal_moves:
                    board.push(move)
                    # After pushing, if it is now bot's turn and board is in check,
                    # the opponent just delivered check to the bot's king!
                    if board.turn == bot_color and board.is_check():
                        checks_count += 1
            except ValueError:
                logger.error(f"Invalid UCI move encountered: {move_uci}")

        new_check = (checks_count > self.checks_against_bot)
        self.checks_against_bot = checks_count
        self._last_move_count = len(uci_moves)
        current_elo = self.get_current_elo()

        return new_check, self.checks_against_bot, current_elo

    def get_depth_for_elo(self, elo: int) -> Tuple[int, float]:
        """
        Returns (depth, max_time_seconds) for a given Elo.
        Uses pure Calculation Horizon (depth) scaling at Skill Level 20.
        This guarantees 100% tactical clarity for all tactical opportunities
        within its depth horizon (never missing free pieces, hanging rooks, or mates),
        while shrinking its forward-thinking horizon as its rating collapses.
        """
        if elo >= 3400:
            return 20, 1.5
        elif elo >= 3100:
            return 16, 1.2
        elif elo >= 2800:
            return 14, 1.0
        elif elo >= 2500:
            return 12, 0.8
        elif elo >= 2200:
            return 10, 0.6
        elif elo >= 1900:
            return 9, 0.5
        elif elo >= 1600:
            return 7, 0.4
        elif elo >= 1300:
            return 5, 0.3
        elif elo >= 1000:
            return 4, 0.25
        elif elo >= 700:
            return 3, 0.2
        elif elo >= 400:
            return 2, 0.15
        else:  # 100 - 300 Elo
            return 1, 0.05

    def configure_for_elo(self, elo: int):
        """Ensures Stockfish calculates with full tactical precision at its depth limit with low memory footprint."""
        if not self.engine:
            return

        try:
            self.engine.configure({
                "Threads": 1,
                "Hash": 8,
                "UCI_LimitStrength": False,
                "Skill Level": 20
            })
        except Exception as e:
            logger.warning(f"Could not configure engine options: {e}")

    def choose_move(self, board: chess.Board, time_limit: float = 1.5) -> Optional[chess.Move]:
        """
        Determines the next move for the bot depending on current Elo rating.
        Uses pure Depth Horizon scaling with blunder simulation for low Elo.
        """
        if not self.engine:
            self.start()

        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None

        current_elo = self.get_current_elo()

        # Tier 4: 0 Elo - Potato Mode (pure random legal moves / catastrophic collapse)
        if current_elo <= self.min_elo:
            logger.info("POTATO MODE (0 Elo): Selecting random legal move.")
            return random.choice(legal_moves)

        # Tier 3: 300 - 1200 Elo Human Panic Mode (Plausible tactical mistakes)
        if current_elo <= 1200:
            panic_chance = (1300 - current_elo) / 1300.0 * 0.70
            if random.random() < panic_chance and len(legal_moves) > 1:
                try:
                    analysis = self.engine.analyse(
                        board,
                        chess.engine.Limit(depth=4, time=0.1),
                        multipv=min(5, len(legal_moves))
                    )
                    if analysis and len(analysis) > 1:
                        top_entry = analysis[0]
                        top_score = top_entry["score"].relative.score(mate_score=10000)
                        if top_score is not None:
                            # Find plausible human blunders (-100 to -400 centipawns worse than best move)
                            blunder_candidates = [
                                entry["pv"][0]
                                for entry in analysis[1:]
                                if entry.get("pv")
                                and entry["score"].relative.score(mate_score=10000) is not None
                                and -400 <= (entry["score"].relative.score(mate_score=10000) - top_score) <= -100
                            ]
                            if blunder_candidates:
                                chosen = random.choice(blunder_candidates)
                                logger.info(f"Human Panic Mode ({current_elo} Elo): Playing human-like mistake {chosen.uci()}")
                                return chosen
                            # Fallback: Pick 2nd or 3rd candidate move
                            fallback_candidates = [
                                entry["pv"][0]
                                for entry in analysis[1:3]
                                if entry.get("pv")
                            ]
                            if fallback_candidates:
                                chosen = random.choice(fallback_candidates)
                                logger.info(f"Human Panic Mode ({current_elo} Elo): Playing sub-optimal candidate {chosen.uci()}")
                                return chosen
                except Exception as e:
                    logger.warning(f"Human panic analysis fallback: {e}")

        depth, target_time = self.get_depth_for_elo(current_elo)
        self.configure_for_elo(current_elo)

        # Opening Variety (Moves 1 - 3): randomly choose among top GM moves within <= 25 centipawns
        if board.fullmove_number <= 3 and current_elo >= 2400:
            try:
                analysis = self.engine.analyse(board, chess.engine.Limit(depth=12, time=0.35), multipv=4)
                if analysis and len(analysis) > 1:
                    top_score = analysis[0]["score"].relative.score(mate_score=10000)
                    if top_score is not None:
                        candidates = [
                            entry["pv"][0]
                            for entry in analysis
                            if entry.get("pv")
                            and entry["score"].relative.score(mate_score=10000) is not None
                            and abs(entry["score"].relative.score(mate_score=10000) - top_score) <= 25
                        ]
                        if candidates:
                            chosen = random.choice(candidates)
                            logger.info(f"Opening Variety: playing {chosen.uci()} from {len(candidates)} top GM moves.")
                            return chosen
            except Exception as e:
                logger.warning(f"Opening variety analysis fallback: {e}")

        actual_time = max(0.05, min(time_limit, target_time))
        try:
            limit = chess.engine.Limit(depth=depth, time=actual_time)
            result = self.engine.play(board, limit)
            return result.move
        except Exception as e:
            logger.error(f"Engine play error: {e}")
            return random.choice(legal_moves)
